"""Per-user personality engine.

Maintains a living trait profile for every user (0-100 per trait,
starting at 50). Conversations are periodically analysed by the LLM,
which emits small trait deltas; archetypes are derived from the profile.

Pure scoring/parsing helpers live at module level; DB access goes through
the shared connection pool in ``src.moderation.database``.
"""

import datetime
import re
from typing import Dict, List, Optional, Tuple

from src.moderation.logging import logger

TRAITS = [
    "curiosity", "humor", "logic", "creativity",
    "kindness", "competitiveness", "confidence",
]

DEFAULT_SCORE = 50.0
MIN_SCORE = 0.0
MAX_SCORE = 100.0
MAX_DELTA = 3.0  # per analysis pass, per trait

# How many messages between LLM trait analyses (offset from the notes
# updater, which runs on multiples of 10, to spread model load)
TRAIT_UPDATE_INTERVAL = 10
TRAIT_UPDATE_OFFSET = 5

# Weighted trait blends; the highest-scoring blend is the archetype
ARCHETYPES = {
    "Scholar":   {"logic": 0.5, "curiosity": 0.5},
    "Creator":   {"creativity": 0.6, "curiosity": 0.4},
    "Explorer":  {"curiosity": 0.6, "confidence": 0.4},
    "Leader":    {"confidence": 0.5, "competitiveness": 0.3, "kindness": 0.2},
    "Trickster": {"humor": 0.6, "creativity": 0.4},
    "Visionary": {"creativity": 0.4, "logic": 0.3, "confidence": 0.3},
    "Guardian":  {"kindness": 0.6, "logic": 0.4},
    "Champion":  {"competitiveness": 0.6, "confidence": 0.4},
}

_DELTA_LINE = re.compile(
    rf"({'|'.join(TRAITS)})\s*[:=]?\s*([+-]\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def clamp_score(value: float) -> float:
    return max(MIN_SCORE, min(MAX_SCORE, float(value)))


def parse_trait_deltas(raw_text: str) -> Dict[str, float]:
    """Parse LLM output like 'curiosity +2' / 'humor: -1' into a delta map."""
    deltas: Dict[str, float] = {}
    for m in _DELTA_LINE.finditer(raw_text):
        trait = m.group(1).lower()
        delta = float(m.group(2))
        delta = max(-MAX_DELTA, min(MAX_DELTA, delta))
        deltas[trait] = deltas.get(trait, 0.0) + delta
    return deltas


def apply_deltas(traits: Dict[str, float], deltas: Dict[str, float]) -> Dict[str, float]:
    updated = dict(traits)
    for trait, delta in deltas.items():
        if trait in TRAITS:
            updated[trait] = clamp_score(updated.get(trait, DEFAULT_SCORE) + delta)
    return updated


def derive_archetype(traits: Dict[str, float]) -> Tuple[str, float]:
    """Return (archetype_name, blend_score). 'Balanced' until a profile
    deviates meaningfully from the neutral starting point."""
    if not traits or all(abs(traits.get(t, DEFAULT_SCORE) - DEFAULT_SCORE) < 5 for t in TRAITS):
        return "Balanced", DEFAULT_SCORE

    best_name, best_score = "Balanced", float("-inf")
    for name, blend in ARCHETYPES.items():
        score = sum(traits.get(trait, DEFAULT_SCORE) * weight for trait, weight in blend.items())
        if score > best_score:
            best_name, best_score = name, score
    return best_name, best_score


def summarize_traits(traits: Dict[str, float], top_n: int = 3) -> str:
    """Short natural-language summary of a user's strongest traits."""
    notable = [
        (t, s) for t, s in traits.items()
        if t in TRAITS and abs(s - DEFAULT_SCORE) >= 5
    ]
    if not notable:
        return ""
    notable.sort(key=lambda kv: abs(kv[1] - DEFAULT_SCORE), reverse=True)
    parts = []
    for trait, score in notable[:top_n]:
        level = "high" if score > DEFAULT_SCORE else "low"
        parts.append(f"{level} {trait}")
    archetype, _ = derive_archetype(traits)
    return f"{', '.join(parts)} (archetype: {archetype})"


def _build_analysis_prompt(username: str, user_messages: List[str]) -> str:
    return (
        f"Analyze {username}'s recent chat messages and rate how they shift "
        "these personality traits: " + ", ".join(TRAITS) + ".\n"
        "Output one line per trait that changed, in the exact form "
        "'trait +N' or 'trait -N' where N is 1 to 3. "
        "Only include traits with clear evidence. If nothing stands out, reply 'none'.\n\n"
        f"Messages from {username}:\n" + "\n".join(user_messages[-15:])
    )


# ============================================================================
# DATABASE-BACKED OPERATIONS
# ============================================================================

async def get_user_traits(user_id: str) -> Optional[Dict[str, float]]:
    from src.moderation import database
    async with database.db_pool.get_connection() as db:
        cursor = await db.execute(
            f"SELECT {', '.join(TRAITS)} FROM user_personality WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    if not row:
        return None
    return {trait: float(row[i]) for i, trait in enumerate(TRAITS)}


async def save_user_traits(user_id: str, traits: Dict[str, float]) -> None:
    from src.moderation import database
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    columns = ", ".join(TRAITS)
    placeholders = ", ".join("?" for _ in TRAITS)
    updates = ", ".join(f"{t} = excluded.{t}" for t in TRAITS)
    values = [clamp_score(traits.get(t, DEFAULT_SCORE)) for t in TRAITS]
    async with database.db_pool.get_connection() as db:
        await db.execute(
            f"INSERT INTO user_personality (user_id, {columns}, updated_at) "
            f"VALUES (?, {placeholders}, ?) "
            f"ON CONFLICT(user_id) DO UPDATE SET {updates}, updated_at = excluded.updated_at",
            [user_id] + values + [now]
        )
        await db.commit()


async def delete_user_traits(user_id: str) -> None:
    from src.moderation import database
    async with database.db_pool.get_connection() as db:
        await db.execute("DELETE FROM user_personality WHERE user_id = ?", (user_id,))
        await db.commit()


async def analyze_and_update_traits(user_id: str, username: str, history: List[Dict]) -> Optional[Dict[str, float]]:
    """Run one LLM trait-extraction pass over recent messages and persist
    the resulting deltas. Returns the updated profile, or None if skipped."""
    from src.services.llm_service import chat_completion

    user_messages = [
        h["content"] for h in history
        if h.get("role") == "user" and h.get("name") == username
    ]
    if len(user_messages) < 3:
        return None

    prompt = _build_analysis_prompt(username, user_messages)
    try:
        response = await chat_completion(
            [{"role": "system", "content": prompt}],
            {"max_tokens": 120, "temperature": 0.3},
        )
    except Exception as e:
        logger.debug(f"[Personality Engine] Trait analysis unavailable for {username}: {e}")
        return None

    deltas = parse_trait_deltas(response or "")
    if not deltas:
        return None

    traits = await get_user_traits(user_id) or {t: DEFAULT_SCORE for t in TRAITS}
    updated = apply_deltas(traits, deltas)
    await save_user_traits(user_id, updated)
    logger.info(f"[Personality Engine] {username}: {deltas} -> {derive_archetype(updated)[0]}")
    return updated


async def maybe_update_traits(user_id: str, username: str, history: List[Dict], interactions: int) -> None:
    """Cadence gate used by the message pipeline."""
    if interactions % TRAIT_UPDATE_INTERVAL != TRAIT_UPDATE_OFFSET:
        return
    try:
        await analyze_and_update_traits(user_id, username, history)
    except Exception as e:
        logger.debug(f"[Personality Engine] Update failed for {username}: {e}")


async def get_persona_context(user_id: str, username: str) -> str:
    """One-line persona summary for prompt injection ('' when unknown)."""
    try:
        traits = await get_user_traits(user_id)
    except Exception:
        return ""
    if not traits:
        return ""
    summary = summarize_traits(traits)
    if not summary:
        return ""
    return f"{username}'s personality profile: {summary}."

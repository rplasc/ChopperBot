"""Memory pipeline helpers: fact parsing, categorisation, and re-ranking.

Pure functions only — database access stays in ``src.moderation.database``
so these are trivially unit-testable.
"""

import datetime
import re
from typing import Dict, List, Optional

# The plan's memory taxonomy plus the legacy categories still present in
# older rows ('trait', 'interest', 'behavior' predate the v2 schema).
MEMORY_CATEGORIES = [
    "preference", "fact", "project", "relationship", "goal",
    "experience", "opinion", "skill", "observation",
    "trait", "interest", "behavior",
]

DEFAULT_IMPORTANCE = 3
MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 5

_CATEGORY_ALT = "|".join(MEMORY_CATEGORIES)
# Matches "[skill|4] Knows Python" and legacy "[trait] Is sarcastic"
_FACT_LINE = re.compile(
    rf"\[\s*({_CATEGORY_ALT})\s*(?:\|\s*(\d)\s*)?\]\s*(.+)",
    re.IGNORECASE,
)

FACT_EXTRACTION_INSTRUCTIONS = (
    "For each fact, start the line with a tag of the form [category|importance] where "
    "category is one of: preference, fact, project, relationship, goal, experience, "
    "opinion, skill, observation — and importance is 1 (trivial) to 5 (defining). "
    "Example: [skill|4] Writes Python tooling for work.\n"
    "Output one fact per line. Be specific and neutral."
)


# Words that carry no retrieval signal; keeps FTS queries focused
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "he", "her",
    "him", "his", "how", "i", "if", "in", "is", "it", "its", "just", "like",
    "me", "my", "no", "not", "of", "on", "or", "our", "she", "so", "some",
    "that", "the", "their", "them", "then", "there", "they", "this", "to",
    "u", "up", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your",
}

_MAX_QUERY_TERMS = 12


def build_fts_query(text: str) -> str:
    """Turn a natural-language message into an FTS5 OR-query.

    FTS5 treats bare space-separated terms as implicit AND, which almost
    never matches a stored memory against a full chat message. OR semantics
    with BM25 ranking rewards rows matching the most meaningful terms.
    """
    cleaned = re.sub(r"[^\w\s]", " ", text or "").lower().split()
    seen = set()
    terms = []
    for word in cleaned:
        if len(word) < 2 or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        terms.append(word)
        if len(terms) >= _MAX_QUERY_TERMS:
            break
    return " OR ".join(terms)


def clamp_importance(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_IMPORTANCE
    return max(MIN_IMPORTANCE, min(MAX_IMPORTANCE, int(value)))


def parse_fact_lines(raw_text: str) -> List[Dict]:
    """Parse LLM output into structured facts.

    Returns dicts with ``category``, ``importance``, ``content``. Lines
    without a recognised tag are kept as low-importance 'observation'
    facts so nothing the model extracted is silently dropped.
    """
    facts = []
    for line in raw_text.splitlines():
        line = line.strip().lstrip("-•* ").strip()
        if not line:
            continue
        if line.lower() in ("no changes", "none"):
            continue
        m = _FACT_LINE.match(line)
        if m:
            category = m.group(1).lower()
            importance = clamp_importance(int(m.group(2)) if m.group(2) else None)
            content = m.group(3).strip()
        else:
            # Skip obvious non-fact chatter (questions, headers)
            if line.endswith(":") or line.endswith("?"):
                continue
            category, importance, content = "observation", MIN_IMPORTANCE + 1, line
        if content:
            facts.append({
                "category": category,
                "importance": importance,
                "content": content,
            })
    return facts


def rerank_memories(rows: List[Dict], limit: int = 3, now: Optional[datetime.datetime] = None) -> List[Dict]:
    """Blend FTS relevance, importance, and recency into a final ranking.

    ``rows`` entries need: content, bm25 (SQLite FTS5 — lower/more negative
    is more relevant), importance (1-5), created_at (ISO string).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)

    def score(row: Dict) -> float:
        relevance = -float(row.get("bm25", 0.0))  # higher = better
        importance = clamp_importance(row.get("importance"))
        recency = 0.0
        created = row.get("created_at")
        if created:
            try:
                dt = datetime.datetime.fromisoformat(created)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                age_days = max(0.0, (now - dt).total_seconds() / 86400)
                recency = 1.0 / (1.0 + age_days / 30)  # decays over ~months
            except (ValueError, TypeError):
                pass
        return relevance + 0.6 * importance + 0.8 * recency

    return sorted(rows, key=score, reverse=True)[:limit]

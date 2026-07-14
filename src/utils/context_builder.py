from typing import List, Dict, Optional
from src.personalities import get_personality
from src.moderation.database import (
    get_user_log_cached,
    get_relevant_user_memories,
    get_relevant_world_facts,
    get_relevant_channel_memories,
    _fts_escape,
)
from src.services.personality_engine import get_persona_context
from src.utils.history_util import trim_history
from src.aclient import client

# ============================================================================
# MODULAR PROMPT SECTIONS
# Each section builder returns a system-message string (or None to skip),
# so the final prompt is assembled from independent, testable pieces:
#   base personality + user memories -> persona profile -> world context
#   -> channel memories -> conversation history
# ============================================================================

def _extract_rag_query(history: List[Dict]) -> str:
    """Use the current user message as the retrieval query."""
    if history:
        last = history[-1]
        if last.get("role") == "user":
            return _fts_escape(last.get("content", ""))
    return ""

async def _memory_section(user_id: str, rag_query: str) -> Optional[str]:
    """Most relevant stored facts about the user (RAG over user_memories)."""
    if rag_query and rag_query != '*':
        memories = await get_relevant_user_memories(user_id, rag_query, limit=3)
        if memories:
            return "; ".join(memories)
    # Fallback: denormalized blob (covers no-query and empty FTS result)
    user_log = await get_user_log_cached(user_id)
    return user_log[4] if user_log and user_log[4] else None

async def _persona_section(user_id: str, user_name: str) -> Optional[str]:
    """One-line trait/archetype profile from the personality engine."""
    persona = await get_persona_context(user_id, user_name)
    return persona or None

async def _world_section(server_id: str, rag_query: str) -> str:
    """Server 'world' header plus any world facts relevant to this message."""
    guild = client.get_guild(int(server_id))
    server_name = guild.name if guild else "Unknown Server"
    owner_name = "Unknown"
    if guild and guild.owner:
        owner_name = guild.owner.name

    if rag_query and rag_query != '*':
        relevant_facts = await get_relevant_world_facts(server_id, rag_query, limit=5)
    else:
        relevant_facts = []

    world_lines = [
        f"🌍 **Current World Context**\n"
        f"• **Location**: {server_name}\n"
        f"• **Owner/Ruler**: {owner_name}"
    ]
    for fact in relevant_facts:
        key = fact["key"].replace("_", " ").title()
        world_lines.append(f"• **{key}**: {fact['value']}")
    return "\n".join(world_lines)

async def _channel_memory_section(
    server_id: str, channel_id: str, rag_query: str
) -> Optional[str]:
    """Long-term channel memories relevant to this message."""
    if not rag_query or rag_query == '*':
        return None
    channel_mems = await get_relevant_channel_memories(
        server_id, channel_id, rag_query, limit=3
    )
    if not channel_mems:
        return None
    return "📜 **Relevant past conversations:**\n" + "\n".join(
        f"• {m}" for m in channel_mems
    )

async def build_message_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: Optional[str],
    conversation_type: str,
    max_tokens: int = 2000,
    channel_id: Optional[str] = None,
) -> List[Dict]:
    rag_query = _extract_rag_query(history)

    user_notes = await _memory_section(user_id, rag_query)

    personality = get_personality()
    system_content = personality.adapt_for_context(conversation_type, user_notes)
    messages = [{"role": "system", "content": system_content}]

    persona = await _persona_section(user_id, user_name)
    if persona:
        messages.append({"role": "system", "content": persona})

    if server_id:
        messages.append({
            "role": "system",
            "content": await _world_section(server_id, rag_query)
        })

        if channel_id:
            channel_section = await _channel_memory_section(server_id, channel_id, rag_query)
            if channel_section:
                messages.append({"role": "system", "content": channel_section})

    messages.extend(history)
    return trim_history(messages, max_tokens=max_tokens)

async def build_dm_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    conversation_type: str
) -> List[Dict]:
    return await build_message_context(
        history=history,
        user_id=user_id,
        user_name=user_name,
        server_id=None,
        conversation_type=conversation_type,
        max_tokens=2000,
    )

async def build_server_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: str,
    conversation_type: str,
    channel_id: Optional[str] = None,
) -> List[Dict]:
    return await build_message_context(
        history=history,
        user_id=user_id,
        user_name=user_name,
        server_id=server_id,
        conversation_type=conversation_type,
        max_tokens=2000,
        channel_id=channel_id,
    )

def format_user_message(
    user_name: str,
    content: str,
    is_dm: bool = False
) -> Dict:
    if is_dm:
        # DMs don't need name prefix since context is clear
        return {"role": "user", "name": user_name, "content": content}
    else:
        # Group chats need attribution
        return {"role": "user", "name": user_name, "content": f"{user_name}: {content}"}

def should_compress_history(history: List[Dict], threshold: int = 15) -> bool:
    return len(history) > threshold

def get_recent_and_older_history(
    history: List[Dict],
    recent_count: int = 10
) -> tuple[List[Dict], List[Dict]]:
    if len(history) <= recent_count:
        return [], history
    
    return history[:-recent_count], history[-recent_count:]

def create_history_summary(older_messages: List[Dict]) -> str:
    if not older_messages:
        return ""
    
    # Extract key information
    user_names = set()
    topics = set()
    
    for msg in older_messages:
        if msg.get("role") == "user":
            name = msg.get("name")
            if name:
                user_names.add(name)
            
            # Simple topic extraction (words > 6 chars)
            content = msg.get("content", "")
            words = content.lower().split()
            meaningful_words = [w for w in words if len(w) > 6 and w.isalpha()]
            topics.update(meaningful_words[:3])
    
    summary_parts = []
    
    if user_names:
        summary_parts.append(f"Earlier conversation with: {', '.join(list(user_names)[:3])}")
    
    if topics:
        summary_parts.append(f"Topics: {', '.join(list(topics)[:5])}")
    
    return ". ".join(summary_parts) if summary_parts else "Earlier conversation"

async def build_hierarchical_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: Optional[str],
    conversation_type: str
) -> List[Dict]:

    return await build_message_context(
        history, user_id, user_name, server_id, conversation_type
    )

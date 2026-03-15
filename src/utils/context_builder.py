from typing import List, Dict, Optional
from src.utils.personality_manager import get_server_personality
from src.moderation.database import (
    get_user_log_cached,
    get_relevant_user_memories,
    get_relevant_world_facts,
    get_relevant_channel_memories,
    _fts_escape,
)
from src.utils.history_util import trim_history
from src.aclient import client

async def build_message_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: Optional[str],
    conversation_type: str,
    max_tokens: int = 2000,
    channel_id: Optional[str] = None,
) -> List[Dict]:
    # Use the current user message as the RAG query
    rag_query = ""
    if history:
        last = history[-1]
        if last.get("role") == "user":
            rag_query = _fts_escape(last.get("content", ""))

    # RAG: retrieve only the most relevant user memory facts
    user_notes = None
    if rag_query and rag_query != '*':
        memories = await get_relevant_user_memories(user_id, rag_query, limit=3)
        if memories:
            user_notes = "; ".join(memories)
    if not user_notes:
        # Fallback: use the denormalized blob (covers no-query and empty FTS result)
        user_log = await get_user_log_cached(user_id)
        user_notes = user_log[4] if user_log and user_log[4] else None

    personality = await get_server_personality(server_id)
    system_content = personality.adapt_for_context(conversation_type, user_notes)
    messages = [{"role": "system", "content": system_content}]

    if server_id:
        guild = client.get_guild(int(server_id))
        server_name = guild.name if guild else "Unknown Server"
        owner_name = "Unknown"
        if guild and guild.owner:
            owner_name = guild.owner.name

        # RAG: retrieve only the world facts relevant to this message
        if rag_query and rag_query != '*':
            relevant_facts = await get_relevant_world_facts(server_id, rag_query, limit=5)
        else:
            relevant_facts = []

        # Always show the header; only attach matched custom facts
        world_lines = [
            f"🌍 **Current World Context**\n"
            f"• **Location**: {server_name}\n"
            f"• **Owner/Ruler**: {owner_name}"
        ]
        for fact in relevant_facts:
            key = fact["key"].replace("_", " ").title()
            world_lines.append(f"• **{key}**: {fact['value']}")
        messages.append({"role": "system", "content": "\n".join(world_lines)})

        # RAG: inject relevant long-term channel memories
        if channel_id and rag_query and rag_query != '*':
            channel_mems = await get_relevant_channel_memories(
                server_id, channel_id, rag_query, limit=3
            )
            if channel_mems:
                mem_text = "📜 **Relevant past conversations:**\n" + "\n".join(
                    f"• {m}" for m in channel_mems
                )
                messages.append({"role": "system", "content": mem_text})

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

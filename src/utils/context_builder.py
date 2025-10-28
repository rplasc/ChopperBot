from typing import List, Dict, Optional
from src.utils.personality_manager import get_server_personality
from src.moderation.database import get_user_log_cached, build_context as db_build_context
from src.utils.history_util import trim_history

async def build_message_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: Optional[str],
    conversation_type: str,
    max_tokens: int = 2000
) -> List[Dict]:
    # Get user notes for personalization
    user_log = await get_user_log_cached(user_id)
    user_notes = user_log[4] if user_log and user_log[4] else None

    personality = await get_server_personality(server_id)
    
    # Build system prompt with context awareness
    system_content = personality.adapt_for_context(conversation_type, user_notes)
    
    messages = [{"role": "system", "content": system_content}]
    
    # Add personality notes and world context from database
    context_msgs = await db_build_context(user_id, user_name, server_id)
    if context_msgs:
        messages.extend(context_msgs)
    
    # Add conversation history
    messages.extend(history)
    
    # Trim to token limit
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
        server_id=None,  # No server context for DMs
        conversation_type=conversation_type,
        max_tokens=2000
    )

async def build_server_context(
    history: List[Dict],
    user_id: str,
    user_name: str,
    server_id: str,
    conversation_type: str
) -> List[Dict]:
    return await build_message_context(
        history=history,
        user_id=user_id,
        user_name=user_name,
        server_id=server_id,
        conversation_type=conversation_type,
        max_tokens=2000
    )

def format_user_message(
    user_name: str,
    content: str,
    is_dm: bool = False
) -> Dict:
    if is_dm:
        # DMs don't need name prefix since context is clear
        return {"role": "user","name": user_name, "content": content}
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
    # Get user notes
    user_log = await get_user_log_cached(user_id)
    user_notes = user_log[4] if user_log and user_log[4] else None

    personality = await get_server_personality(server_id)
    
    # Build system prompt with context awareness
    system_content = personality.adapt_for_context(conversation_type, user_notes)
    
    messages = [{"role": "system", "content": system_content}]
    
    # Add personality and world context
    context_msgs = await db_build_context(user_id, user_name, server_id)
    if context_msgs:
        messages.extend(context_msgs)
    
    # Check if we should compress history
    if should_compress_history(history):
        older, recent = get_recent_and_older_history(history)
        
        # Add summary of older conversation
        if older:
            summary = create_history_summary(older)
            messages.append({
                "role": "system",
                "content": f"Previous conversation context: {summary}"
            })
        
        # Add recent messages in full
        messages.extend(recent)
    else:
        # All messages are recent enough
        messages.extend(history)
    
    # Final trim to token limit
    return trim_history(messages, max_tokens=2000)
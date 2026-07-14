import os
import asyncio
from collections import OrderedDict
from discord import DMChannel, File, Interaction, app_commands
from src.aclient import client
from src.utils.history_util import trim_history
from src.moderation.database import (init_db, record_user_message, maybe_queue_notes_update,
                                    get_user_interactions, load_interaction_cache, close_connection_pool,
                                    flush_pending_notes_periodically,
                                    store_channel_memory, CHANNEL_MEMORY_INTERVAL)
from src.moderation.logging import init_logging_db, logger, log_chat_message
from src.commands import (admin, user, mystical, recommend, relationship, chatgpt, images,
                        personality, crime, memory)
from src.services.personality_engine import maybe_update_traits
from src.utils.message_util import to_discord_output
from src.utils.vision_util import analyze_discord_attachment, is_image_attachment
from src.utils.response_generator import (detect_conversation_type, generate_and_track_response, sanitize_response)
from src.utils.context_builder import (build_dm_context, build_server_context, format_user_message)


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_CACHED_CHANNELS = 50
MAX_CACHED_DM_USERS = 25

# Per-channel message counters for channel memory generation
channel_message_counts: dict = {}  # {(server_id, channel_id): int}

# ============================================================================
# CONVERSATION HISTORY CACHE (LRU)
# ============================================================================

conversation_histories_cache = OrderedDict()

def get_or_create_history(server_id: str, channel_id: str) -> list:
    key = (server_id, channel_id)
    
    # If exists, move to end (mark as recently used)
    if key in conversation_histories_cache:
        conversation_histories_cache.move_to_end(key)
        return conversation_histories_cache[key]
    
    # Determine cache limit based on type
    is_dm = server_id == "dm"
    max_cache = MAX_CACHED_DM_USERS if is_dm else MAX_CACHED_CHANNELS
    
    # Evict oldest entry if cache is full
    if len(conversation_histories_cache) >= max_cache:
        evicted_key, _ = conversation_histories_cache.popitem(last=False)
        logger.debug(f"LRU evicted: {evicted_key[0]}/{evicted_key[1]}/{evicted_key[2]}")
    
    # Create new history
    conversation_histories_cache[key] = []
    return conversation_histories_cache[key]

# ============================================================================
# BOT LIFECYCLE
# ============================================================================

@client.event
async def on_ready():
    await init_db()
    await init_logging_db()
    await client.tree.sync()
    await load_interaction_cache()

    # Background tasks
    client.loop.create_task(flush_pending_notes_periodically())

    print(f'Logged in as {client.user.name}')
    logger.info(f"Logged in as {client.user.name}")

async def shutdown():
    logger.info("Shutting down bot...")
    try:
        await close_connection_pool()
        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# ============================================================================
# MESSAGE HANDLING
# ============================================================================

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance(message.channel, DMChannel):
        await handle_dm_message(message)
    else:
        await handle_server_message(message)

async def handle_dm_message(message):
    user_id = str(message.author.id)
    user_name = message.author.name

    # Get conversation history
    history = get_or_create_history("dm", user_id)

    # Add user message
    user_msg = format_user_message(user_name, message.content, is_dm=True)
    history.append(user_msg)
    history[:] = trim_history(history, max_tokens=2000)

    # Detect conversation type for adaptive responses
    conv_type = detect_conversation_type(message.content)

    # Build context (includes system prompt, user notes, history)
    messages = await build_dm_context(history, user_id, user_name, conv_type)

    try:
        async with message.channel.typing():
            # Generate response with quality checks and tracking
            response = await generate_and_track_response(
                messages, 
                conv_type, 
                f"dm_{user_id}",
                server_id=None
            )
        
        # Add to history and send
        history.append({"role": "assistant", "content": response})
        await message.reply(response)
        
    except Exception as e:
        logger.exception(f"[DM Error] {e}")
        await message.channel.send("I'm currently offline. Try again later.")

async def handle_server_message(message):
    server_id = str(message.guild.id)
    channel_id = str(message.channel.id)
    user_id = str(message.author.id)
    user_name = message.author.name
    user_message = message.content
    
    # Get conversation history
    history = get_or_create_history(server_id, channel_id)

    # Check if message has image attachments
    has_images = any(att.content_type and att.content_type.startswith('image/') for att in message.attachments)

    # Add user message
    user_msg = format_user_message(user_name, user_message, is_dm=False)
    history.append(user_msg)

    # Trim history
    history[:] = trim_history(history, max_tokens=2000)

    # Respond when mentioned OR when replying with images
    should_respond = client.user.mentioned_in(message) or (
        has_images and message.reference and 
        message.reference.resolved and 
        message.reference.resolved.author == client.user
    )
    
    if should_respond:
        await generate_and_send_response(
            message, history, user_id, user_name, 
            server_id, channel_id, user_message,
            has_images=has_images
        )
    
    # Background tasks (non-blocking)
    await update_user_stats(server_id, user_id, user_name, history, channel_id=channel_id)
    await log_chat_message(server_id, channel_id, user_id, user_name, "user", user_message)

async def generate_and_send_response(
    message, history, user_id, user_name, 
    server_id, channel_id, user_message,
    has_images=False
):

    image_analysis = None
    if has_images:        
        try:
            # Get first image
            image_att = next(att for att in message.attachments if is_image_attachment(att))
            
            # Analyze image with user's question
            prompt = user_message if user_message else "Describe this image in detail."
            image_analysis = await analyze_discord_attachment(image_att, prompt, use_personality=False, server_id=server_id)
            
            logger.info(f"Image analyzed in {server_id}/{channel_id}")
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            await message.reply("I tried to look at your image but something went wrong 👀")
            return
    
    # Detect conversation type
    conv_type = detect_conversation_type(user_message)
    
    # Build context (with channel_id for long-term memory retrieval)
    messages = await build_server_context(
        history, user_id, user_name, server_id, conv_type,
        channel_id=channel_id
    )
    
    if image_analysis:
        messages.append({
            "role": "system",
            "content": f"Image analysis: {image_analysis}"
        })

    try:
        async with message.channel.typing():
            # Generate response
            response = await generate_and_track_response(
                messages,
                conv_type,
                f"server_{server_id}_{channel_id}",
                server_id=server_id
            )
            
            # Sanitize output
            response = sanitize_response(response)

        # Add to history
        history.append({"role": "assistant", "content": response})

        # Send response (handle long messages)
        output = to_discord_output(response)
        
        if isinstance(output, File):
            await message.reply("📄 Response was too long, see attached file:", file=output)
        else:
            for i, chunk in enumerate(output):
                if i == 0:
                    await message.reply(chunk)
                else:
                    await message.channel.send(chunk)

        # Log assistant message
        await log_chat_message(
            server_id, channel_id, str(client.user.id), 
            client.user.name, "assistant", response
        )

    except Exception as e:
        logger.error(f"[Message Error] {e}")
        await message.reply("Chopperbot is currently unavailable.")

async def update_user_stats(server_id, user_id, user_name, history, channel_id: str = None):
    await record_user_message(server_id, user_id, user_name)

    interactions = await get_user_interactions(user_id)
    user_history = [msg for msg in history if msg.get("role") == "user"]
    asyncio.create_task(maybe_queue_notes_update(user_id, user_name, user_history, interactions))
    asyncio.create_task(maybe_update_traits(user_id, user_name, user_history, interactions))

    # Channel memory: accumulate and periodically summarise
    if channel_id and server_id:
        key = (server_id, channel_id)
        channel_message_counts[key] = channel_message_counts.get(key, 0) + 1
        asyncio.create_task(
            maybe_store_channel_memory(server_id, channel_id, history, channel_message_counts[key])
        )

async def maybe_store_channel_memory(
    server_id: str, channel_id: str, history: list, message_count: int
) -> None:
    """Every CHANNEL_MEMORY_INTERVAL messages, summarise recent history and persist it."""
    if message_count % CHANNEL_MEMORY_INTERVAL != 0:
        return
    if len(history) < 5:
        return

    recent = history[-20:]
    participants = list({
        msg.get("name") for msg in recent
        if msg.get("role") == "user" and msg.get("name")
    })

    lines = [
        f"{msg.get('name', 'Bot')}: {msg.get('content', '')}"
        for msg in recent if msg.get("content")
    ]
    prompt = (
        "Summarize the following Discord conversation in 2-3 sentences. "
        "Focus on topics discussed, decisions made, and key moments.\n\n"
        + "\n".join(lines)
    )

    try:
        from src.services.llm_service import chat_completion
        summary = await chat_completion([{"role": "system", "content": prompt}])
        if summary and summary.strip():
            await store_channel_memory(server_id, channel_id, summary.strip(), participants)
            logger.info(f"[Channel Memory] Stored summary for {server_id}/{channel_id}")
    except Exception as e:
        logger.debug(f"[Channel Memory] Failed to generate summary: {e}")

# ============================================================================
# GLOBAL ERROR HANDLER
# ============================================================================

@client.tree.error
async def on_app_command_error(interaction: Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "You do not have permission to use this command.", 
                ephemeral=True
            )
    else:
        logger.error(f"Command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "An error occurred while executing the command.", 
                ephemeral=True
            )

# ============================================================================
# STARTUP
# ============================================================================

try:
    client.run(os.getenv('DISCORD_BOT_TOKEN'))
except KeyboardInterrupt:
    logger.info("Received shutdown signal")
finally:
    asyncio.run(shutdown())
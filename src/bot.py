import os
import asyncio
from collections import OrderedDict
from discord import DMChannel, File
from src.aclient import client
from src.utils.history_util import trim_history
from src.moderation.database import (init_db, increment_server_interaction, queue_increment, flush_user_logs_periodically,
                                    queue_user_log, maybe_queue_notes_update, get_user_interactions,
                                    interaction_cache, load_interaction_cache, maybe_update_world, add_to_world_history,
                                    close_connection_pool, flush_user_logs)
from src.moderation.logging import init_logging_db, logger, log_chat_message
from src.commands import admin, user, mystical, news, recommend, relationship, weather, chatgpt, images
from src.utils.message_util import to_discord_output
from src.utils.vision_util import analyze_discord_attachment, is_image_attachment
from src.utils.response_generator import (detect_conversation_type, generate_and_track_response, sanitize_response)
from src.utils.context_builder import (build_dm_context, build_server_context, format_user_message)

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_CACHED_CHANNELS = 50  # Adjust based on your bot's scale and memory constraints
MAX_CACHED_DM_USERS = 25   # Separate limit for DM conversations

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

def extract_user_history(history: list, user_id: str = None) -> list:
    user_msgs = []
    for msg in history:
        if msg.get("role") == "user":
            # For user-specific filtering (if needed)
            if user_id is None or msg.get("name") == user_id:
                user_msgs.append(msg)
    return user_msgs

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
    client.loop.create_task(increment_server_interaction())
    client.loop.create_task(flush_user_logs_periodically())

    print(f'Logged in as {client.user.name}')
    logger.info(f"Logged in as {client.user.name}")

async def shutdown():
    logger.info("Shutting down bot...")
    try:
        await flush_user_logs()
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
    add_to_world_history(server_id, message.author.display_name, user_message)

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
    await update_user_stats(server_id, user_id, user_name, history)
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
            image_analysis = await analyze_discord_attachment(image_att, prompt, use_personality=True)
            
            logger.info(f"Image analyzed in {server_id}/{channel_id}")
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            await message.reply("I tried to look at your image but something went wrong 👀")
            return
    
    # Detect conversation type
    conv_type = detect_conversation_type(user_message)
    
    # Build context
    messages = await build_server_context(
        history, user_id, user_name, server_id, conv_type
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

async def update_user_stats(server_id, user_id, user_name, history):
    # Queue stats updates
    await queue_increment(server_id, user_id)
    interaction_cache[user_id] = interaction_cache.get(user_id, 0) + 1
    await queue_user_log(user_id, user_name)
    
    # Get interaction count
    interactions = await get_user_interactions(user_id)
    
    # Extract user-only messages for notes
    user_history = [msg for msg in history if msg.get("role") == "user"]
    
    # Run these in background (non-blocking)
    asyncio.create_task(maybe_queue_notes_update(user_id, user_name, user_history, interactions))
    asyncio.create_task(maybe_update_world(server_id))

# ============================================================================
# STARTUP
# ============================================================================

try:
    client.run(os.getenv('DISCORD_BOT_TOKEN'))
except KeyboardInterrupt:
    logger.info("Received shutdown signal")
finally:
    asyncio.run(shutdown())
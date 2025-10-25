import os
import asyncio
from collections import OrderedDict
from discord import DMChannel, File
from src.aclient import client
from src.personalities import get_system_content
from src.utils.koboldcpp_util import get_kobold_response, sanitize_bot_output
from src.utils.history_util import trim_history
from src.moderation.database import (init_db, increment_server_interaction, queue_increment, flush_user_logs_periodically,
                                    queue_user_log, maybe_queue_notes_update, get_user_interactions,
                                    interaction_cache, load_interaction_cache, get_personality_context,
                                    build_context, maybe_update_world, add_to_world_history)
from src.moderation.logging import init_logging_db, logger, log_chat_message
from src.commands import admin, user, mystical, news, recommend, relationship, weather, chatgpt
from src.utils.message_util import to_discord_output

# LRU Cache Configuration
MAX_CACHED_CHANNELS = 50  # Adjust based on your bot's scale and memory constraints
MAX_CACHED_DM_USERS = 25   # Separate limit for DM conversations

# LRU-cached conversation histories
# Structure: {(personality, server_id_or_"dm", channel_id_or_user_id): [messages]}
conversation_histories_cache = OrderedDict()

def get_or_create_history(personality: str, server_id: str, channel_id: str) -> list:
    key = (personality, server_id, channel_id)
    
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

@client.event
async def on_ready():
    await init_db()
    await init_logging_db()
    await client.tree.sync()
    await load_interaction_cache()
    client.loop.create_task(increment_server_interaction())
    client.loop.create_task(flush_user_logs_periodically())
    print(f'Logged in as {client.user.name}')
    logger.info(f"Logged in as {client.user.name}")

async def shutdown():
    from src.moderation.database import close_connection_pool, flush_user_logs
    logger.info("Shutting down bot...")
    try:
        await flush_user_logs()
        await close_connection_pool()
        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance(message.channel, DMChannel):
        user_id = str(message.author.id)
        user_name = message.author.name
        personality = getattr(client, "current_personality", "Default")

        history = get_or_create_history(personality, "dm", user_id)

        history.append({"role": "user", "name": message.author.name, "content": message.content})
        history[:] = trim_history(history, max_tokens=2000)

        system_content = get_system_content()
        messages = [{"role": "system", "content": system_content}] + history
        notes_context = await get_personality_context(user_id, user_name)
        if notes_context:
            messages += [{"role": "system", "content": notes_context}]

        try:
            async with message.channel.typing():
                client_response = await get_kobold_response(messages)
            history.append({"role": "assistant", "content": client_response})
            await message.reply(client_response)
        except Exception as e:
            logger.exception(f"[DM Error] {e}")
            await message.channel.send("I’m currently offline. Try again later.")
        return

    server_id = str(message.guild.id)
    channel_id = str(message.channel.id)
    user_id = str(message.author.id)
    user_name = message.author.name
    user_message_content = message.content

    # Initialize nested history structure:
    # { personality -> server -> channel -> [messages] }
    personality = getattr(client, "current_personality", "Default")

    history = get_or_create_history(personality, server_id, channel_id)

    # Add user message to history
    history.append({"role": "user", "name": user_name, "content":f"{user_name}: {user_message_content}"})
    add_to_world_history(str(server_id), message.author.display_name, user_message_content)

    # Trim history (token based)
    history[:] = trim_history(history, max_tokens=2000)

    # Only respond when bot is mentioned
    if client.user.mentioned_in(message):
        system_content = get_system_content()
        messages = [{"role": "system", "content": system_content}]

        context_msgs = await build_context(user_id, user_name, str(message.guild.id) if message.guild else None)
        if context_msgs:
            messages += context_msgs
        messages += history

        try:
            async with message.channel.typing():
                client_response = await get_kobold_response(messages)
                client_response = sanitize_bot_output(client_response)

            # Save assistant response
            history.append({"role": "assistant", "content": client_response})

            output = to_discord_output(client_response)

            if isinstance(output, File):
                await message.reply("📄 Response was too long, see attached file:", file=output)
            else:
                for i, chunk in enumerate(output):
                    if i == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)

            await log_chat_message(server_id, channel_id, str(client.user.id), client.user.name, "assistant", client_response)

        except Exception as e:
            logger.error(f"[Message Error] {e}")
            await message.reply("Chopperbot is currently unavailable.")
    
    # Increment yap stats
    await queue_increment(server_id, user_id)

    # increment interaction count in memory
    interaction_cache[user_id] = interaction_cache.get(user_id, 0) + 1

    # Queue user log update
    await queue_user_log(user_id, user_name)

    # fetch interaction count fresh from DB
    interactions = await get_user_interactions(user_id)

    # Maybe update personality and world notes
    user_history = [msg for msg in history if msg.get("role") == "user"]
    asyncio.create_task(maybe_queue_notes_update(user_id, user_name, user_history, interactions))
    asyncio.create_task(maybe_update_world(str(server_id)))

    await log_chat_message(server_id, channel_id, user_id, user_name, "user", user_message_content)
    
try:
    client.run(os.getenv('DISCORD_BOT_TOKEN'))
except KeyboardInterrupt:
    logger.info("Received shutdown signal")
finally:
    asyncio.run(shutdown())
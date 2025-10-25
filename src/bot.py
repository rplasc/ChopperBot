import os
from discord import DMChannel, File
from src.aclient import client
from src.personalities import get_system_content
from src.utils.kobaldcpp_util import get_kobold_response, sanitize_bot_output
from src.utils.history_util import trim_history
from src.moderation.database import (init_db, increment_server_interaction, queue_increment, flush_user_logs_periodically,
                                    queue_user_log, maybe_queue_notes_update, get_user_interactions,
                                    interaction_cache, load_interaction_cache, get_personality_context,
                                    build_context, maybe_update_world, add_to_world_history)
from src.moderation.logging import init_logging_db, logger, log_chat_message
from src.commands import admin, user, mystical, news, recommend, relationship, weather, chatgpt
from src.utils.message_util import to_discord_output

# Maintain a dynamic conversation history
conversation_histories = {}
user_only_histories = {}

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

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance(message.channel, DMChannel):
        user_id = str(message.author.id)
        user_name = message.author.name
        personality = getattr(client, "current_personality", "Default")

        if personality not in conversation_histories:
            conversation_histories[personality] = {}
        if "dm" not in conversation_histories[personality]:
            conversation_histories[personality]["dm"] = {}
        if user_id not in conversation_histories[personality]["dm"]:
            conversation_histories[personality]["dm"][user_id] = []

        history = conversation_histories[personality]["dm"][user_id]
        history.append({"role": "user", "name": message.author.name, "content": message.content})
        history = trim_history(history, max_tokens=2000)
        conversation_histories[personality]["dm"][user_id] = history

        system_content = get_system_content()
        messages = [{"role": "system", "content": system_content}] + history
        notes_context = await get_personality_context(user_id, user_name)
        if notes_context:
            messages += [{"role": "system", "content": notes_context}]

        try:
            async with message.channel.typing():
                client_response = await get_kobold_response(messages)
            history.append({"role": "assistant", "content": client_response})
            conversation_histories[personality]["dm"][user_id] = history
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
    if personality not in conversation_histories:
        conversation_histories[personality] = {}
    if server_id not in conversation_histories[personality]:
        conversation_histories[personality][server_id] = {}
    if channel_id not in conversation_histories[personality][server_id]:
        conversation_histories[personality][server_id][channel_id] = []
    
    if personality not in user_only_histories:
        user_only_histories[personality] = {}
    if server_id not in user_only_histories[personality]:
        user_only_histories[personality][server_id] = {}
    if channel_id not in user_only_histories[personality][server_id]:
        user_only_histories[personality][server_id][channel_id] = {}
    if user_id not in user_only_histories[personality][server_id][channel_id]:
        user_only_histories[personality][server_id][channel_id][user_id] = []

    if message.author != client.user:
        user_only_histories[personality][server_id][channel_id][user_id].append({
            "role": "user",
            "content": user_message_content
        })

    history = conversation_histories[personality][server_id][channel_id]

    # Add user message to history
    history.append({"role": "user", "name": user_name, "content":f"{user_name}: {user_message_content}"})
    add_to_world_history(str(server_id), message.author.display_name, user_message_content)

    # Trim history (token based)
    history = trim_history(history, max_tokens=2000)
    conversation_histories[personality][server_id][channel_id] = history

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
            conversation_histories[personality][server_id][channel_id] = history

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

    # Maybe update personality notes
    user_history = user_only_histories[personality][server_id][channel_id][user_id]
    await maybe_queue_notes_update(user_id, user_name, user_history, interactions)

    await maybe_update_world(str(server_id))

    await log_chat_message(server_id, channel_id, user_id, user_name, "user", user_message_content)
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))
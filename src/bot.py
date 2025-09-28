import os
from typing import List
import openai
from discord import DMChannel, Interaction, Embed, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities, get_system_content
from utils.kobaldcpp_util import get_kobold_response, sanitize_bot_output
from utils.history_util import trim_history
from utils.openai_util import get_openai_response
from utils.content_filter import censor_curse_words, filter_controversial
from src.moderation.database import (init_db, increment_yap, queue_increment, flush_user_logs_periodically,
                                    queue_user_log, maybe_queue_notes_update, get_user_interactions,
                                    interaction_cache, load_interaction_cache, get_personality_context,
                                    build_context, maybe_update_world, add_to_world_history)
from src.commands import admin, user, mystical, news, recommend, relationship, weather, miscellaneous

# Setup OpenAI api for conversation feature
openai.api_key = client.openAI_API_key

# Maintain a dynamic conversation history
conversation_histories = {}
ask_conversation_histories = {}
user_only_histories = {}

@client.event
async def on_ready():
    await init_db()
    await client.tree.sync()
    await load_interaction_cache()
    client.loop.create_task(increment_yap())
    client.loop.create_task(flush_user_logs_periodically())
    print(f'Logged in as {client.user.name}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance(message.channel, DMChannel):
        user_id = str(message.author.id)
        user_name = message.author.name
        personality = getattr(client, "current_personality", "Chopperbot")

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
            print(f"[DM Error] {e}")
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

            await message.reply(client_response, mention_author=False)

        except Exception as e:
            print(f"[Error] {e}")
            await message.reply("Chopperbot is currently sleeping.")
    
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
    
@client.tree.command(name= "help",description="List of all commands")
async def help(interaction: Interaction):
    embed = Embed(title="Help Text", description="The following commands are available:")
    commandlist = client.tree.walk_commands()
    for Command in commandlist:
        embed.add_field(name=Command.name,value=Command.description if Command.description else Command.name, inline=False)
    await interaction.response.send_message(embed=embed)
    
# Allows ChatGPT conversations
@client.tree.command(name="ask",description="Ask and recieve response quietly from ChatGPT.")
async def ask(interaction: Interaction, prompt: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    user_message_content = censor_curse_words(prompt)
    
    user_id = str(interaction.user.id)
    
    # Initialize conversation history for the user if it doesn't exist
    if user_id not in ask_conversation_histories:
        ask_conversation_histories[user_id] = []
    
    # Limit the conversation history to 5 messages for each user
    ask_conversation_histories[user_id].append({"role": "user", "content": user_message_content})
    ask_conversation_histories[user_id] = trim_history(ask_conversation_histories[user_id], max_tokens=1500)
    
    try:
        client_response = await get_openai_response(ask_conversation_histories[user_id])
        ask_conversation_histories[user_id].append({"role": "assistant", "content": client_response})
        ask_conversation_histories[user_id] = trim_history(ask_conversation_histories[user_id], max_tokens=1500)

    except Exception as e:
        print(f"[Ask Error] {e}")
        client_response = "I am currently unavailable."
    await interaction.followup.send(client_response, ephemeral=True)

@client.tree.command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: Interaction, personality: str):
    await interaction.response.defer()
    if personality in personalities:
        client.current_personality = personality
        client.is_custom_personality = False
        conversation_histories.clear()
        embed = Embed(title="Set Personality", description=f"Personality has been set to {personality}")
        await interaction.followup.send(embed=embed)
    else:
        embed = Embed(title="Set Personality", description=f'Invalid personality. Available options are: {", ".join(personalities.keys())}')
        await interaction.followup.send(embed=embed)

@set_personality.autocomplete("personality")
async def personality_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=personality, value=personality)
        for personality in personalities.keys()
        if current.lower() in personality.lower()
    ]
    
@client.tree.command(name="pretend", description="Set the bot's personality to a character/celebrity")
async def pretend(interaction: Interaction, personality: str):
    await interaction.response.defer()
    censored_personality = censor_curse_words(personality)
    if filter_controversial(censored_personality):
        client.current_personality = custom_personalities(censored_personality)
        client.is_custom_personality = True
        conversation_histories.clear()
        embed = Embed(title="Personality Change", description=f"I will now act like {censored_personality}")
    else:
        embed = Embed(title="Personality Change", description="Sorry, I cannot pretend to be that person.")
    await interaction.followup.send(embed=embed)
    
# Resets "memory" and personality back to default
@client.tree.command(name="reset",description="Resets to default personality")
async def reset(interaction: Interaction):
    await interaction.response.defer()
    if client.current_personality != 'Chopperbot':
        client.current_personality = "Chopperbot"
        client.is_custom_personality = False
        
    conversation_histories.clear()
    await interaction.followup.send("My memory has been wiped!")
    print("Personality has been reset.")
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))
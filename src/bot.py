import os
from typing import List
import openai
from discord import DMChannel, Interaction, Embed, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities, get_system_content
from utils.kobaldcpp_util import get_kobold_response
from utils.history_util import trim_history
from utils.openai_util import get_openai_response
from utils.content_filter import censor_curse_words, filter_controversial
from src.moderation.yappers import init_db, increment_yap, queue_increment
from src.commands import yaps, mystical, news, recommend, relationship

# Setup OpenAI api for conversation feature
openai.api_key = client.openAI_API_key

# Maintain a dynamic conversation history
conversation_histories = {}
ask_conversation_histories = {}

@client.event
async def on_ready():
    await init_db()
    await client.tree.sync()
    client.loop.create_task(increment_yap())
    print(f'Logged in as {client.user.name}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance(message.channel, DMChannel):
        user_id = str(message.author.id)
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

    # Increment yap stats
    await queue_increment(server_id, user_id)

    # Initialize nested history structure:
    # { personality -> server -> channel -> user -> [messages] }
    personality = getattr(client, "current_personality", "Chopperbot")
    if personality not in conversation_histories:
        conversation_histories[personality] = {}
    if server_id not in conversation_histories[personality]:
        conversation_histories[personality][server_id] = {}
    if channel_id not in conversation_histories[personality][server_id]:
        conversation_histories[personality][server_id][channel_id] = {}
    if user_id not in conversation_histories[personality][server_id][channel_id]:
        conversation_histories[personality][server_id][channel_id][user_id] = []

    history = conversation_histories[personality][server_id][channel_id][user_id]

    # Add user message to history
    history.append({"role": "user", "name": user_name, "content": user_message_content})

    # Trim history (token based)
    history = trim_history(history, max_tokens=2000)
    conversation_histories[personality][server_id][channel_id][user_id] = history

    # Only respond when bot is mentioned
    if client.user.mentioned_in(message):
        system_content = get_system_content()
        messages = [{"role": "system", "content": system_content}] + history

        try:
            async with message.channel.typing():
                client_response = await get_kobold_response(messages)

            # Save assistant response
            history.append({"role": "assistant", "content": client_response})
            conversation_histories[personality][server_id][channel_id][user_id] = history

            await message.reply(client_response, mention_author=False)

        except Exception as e:
            print(f"[Error] {e}")
            await message.reply("Chopperbot is currently sleeping.")
    
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
        print(f"[ASk Error] {e}")
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
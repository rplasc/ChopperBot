import os
from typing import List
import openai
from discord import DMChannel, Interaction, Embed, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities
from utils.kobaldcpp_util import get_kobold_response
from utils.openai_util import get_openai_response
from utils.content_filter import censor_curse_words, filter_controversial
from src.Moderation.yappers import init_db, increment_yap, queue_increment
from src.commands import user, yaps, images, mystical, news

# Setup OpenAI api for conversation feature
openai.api_key = client.openAI_API_key

# Maintain a dynamic conversation history
conversation_histories = {}
MAX_HISTORY_LENGTH = 20
whispers_conversation_histories = {}

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
    
    #TODO: Add DM channel interaction
    if isinstance (message.channel, DMChannel):
        await message.channel.send("Chopperbot is not available here.")
        return

    server_id = str(message.guild.id)
    user_id = str(message.author.id)
    await queue_increment(server_id, user_id)

    channel_id = message.channel.id
    user_message_content = message.content
    
    if server_id not in conversation_histories:
        conversation_histories[server_id] = {}
    if channel_id not in conversation_histories[server_id]:
        conversation_histories[server_id][channel_id] = []
        
    user_info = f"{message.author.id} ({message.author.name})"
    conversation_histories[server_id][channel_id].append({"role": "user", "content": f"{user_info}: {user_message_content}"})
    conversation_histories[server_id][channel_id] = conversation_histories[server_id][channel_id][-MAX_HISTORY_LENGTH:]

    # Uses KoboldCPP API to generate messages
    if client.user.mentioned_in(message):
        if client.is_custom_personality == False:
            messages = [
                {"role": "system", "content": personalities[client.current_personality]},
             ] + conversation_histories[server_id][channel_id]
        else:
            messages = [
                {"role": "system", "content": client.current_personality},
            ] + conversation_histories[server_id][channel_id]
        try:
            client_response = await get_kobold_response(messages)
            conversation_histories[server_id][channel_id].append({"role": "assistant", "content": client_response})
            await message.channel.send(client_response)
        except:
            await message.channel.send('I am currently sleeping.')
    
@client.tree.command(name= "help",description="List of all commands")
async def help(interaction: Interaction):
    embed = Embed(title="Help Text", description="The following commands are available:")
    commandlist = client.tree.walk_commands()
    for Command in commandlist:
        embed.add_field(name=Command.name,value=Command.description if Command.description else Command.name, inline=False)
    await interaction.response.send_message(embed=embed)
    
# Allows ChatGPT conversations
@client.tree.command(name="ask",description="Ask and recieve response quietly from ChatGPT.")
async def whisper(interaction: Interaction, prompt: str):
    user_message_content = censor_curse_words(prompt)
    
    user_id = str(interaction.user.id)
    
    # Initialize conversation history for the user if it doesn't exist
    if user_id not in whispers_conversation_histories:
        whispers_conversation_histories[user_id] = []
    
    # Limit the conversation history to 5 messages for each user
    whispers_conversation_histories[user_id].append({"role": "user", "content": user_message_content})
    whispers_conversation_histories[user_id] = whispers_conversation_histories[user_id][-5:]

    messages = [
        {"role": "system", "content": client.current_personality},
    ] + whispers_conversation_histories[user_id]
    
    try:
        client_response = await get_openai_response(messages)
        whispers_conversation_histories[user_id].append({"role": "assistant", "content": client_response})
    except:
        client_response = "I am currently unavailable."
    await interaction.response.send_message(client_response, ephemeral=True)

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
        
async def personality_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name=personality, value=personality) for personality in personalities.keys() if current.lower() in personality.lower()]
    return choices
    
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
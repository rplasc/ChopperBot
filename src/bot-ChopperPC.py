import os
import random
import discord
import openai
from typing import List, Tuple
from discord import Interaction, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities
from utils.openai_util import get_openai_response, generate_img
from utils.content_filter import censor_curse_words, filter_controversial
from src.Moderation.yappers import load_yaps, save_yaps


# Setup OpenAI api for conversation feature
openai.api_key = client.openAI_API_key
current_personality = "Chopperbot"  # Default personality
is_custom_personality = False

# Maintain a dynamic conversation history
conversation_histories = {}
MAX_HISTORY_LENGTH = 20
whispers_conversation_histories = {}

# Load Yappers Protocol
yaps_counter = load_yaps()
processed_messages = set()

@client.event
async def on_ready():
    await client.tree.sync()
    print(f'Logged in as {client.user.name}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if message.id not in processed_messages:
        server_id = str(message.guild.id)
        user_id = str(message.author.id)
        yaps_counter[server_id] = yaps_counter.get(server_id, {})
        yaps_counter[server_id][user_id] = yaps_counter[server_id].get(user_id, 0) + 1
        
        if len(processed_messages) == 10:
            processed_messages.clear()
    
        save_yaps(yaps_counter)
        processed_messages.add(message.id)
    
    server_id = str(message.guild.id)
    channel_id = message.channel.id
    user_message_content = censor_curse_words(message.content)
    
    if server_id not in conversation_histories:
        conversation_histories[server_id] = {}
    if channel_id not in conversation_histories[server_id]:
        conversation_histories[server_id][channel_id] = []
    conversation_histories[server_id][channel_id].append({"role": "user", "content": user_message_content})
    conversation_histories[server_id][channel_id] = conversation_histories[server_id][channel_id][-MAX_HISTORY_LENGTH:]

    if client.user.mentioned_in(message):
        global is_custom_personality
        if is_custom_personality == False:
            messages = [
                {"role": "system", "content": personalities[current_personality]},
             ] + conversation_histories[server_id][channel_id]
        else:
            messages = [
                {"role": "system", "content": current_personality},
            ] + conversation_histories[server_id][channel_id]
        try:
            client_response = await get_openai_response(messages)
            conversation_histories[server_id][channel_id].append({"role": "assistant", "content": client_response})
            await message.channel.send(client_response)
        except Exception as e:
            await message.channel.send('Sorry, I am not able to respond.')

@client.event            
async def on_reaction_add(reaction, user):
    message = reaction.message
    if message.content.startswith("Raise your hand if") and str(reaction) == "✋":  # Assuming the reaction is a raised hand
        if len(message.reactions) >= 5:  # Change 5 to your desired threshold
            await message.channel.send("Enough hands raised!")

# __Slash Commands__

# Changes personality from a given list
@client.tree.command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    if personality in personalities:
        current_personality = personality
        is_custom_personality = False
        conversation_histories.clear()
        embed = discord.Embed(title="Set Personality", description=f"Personality has been set to {personality}")
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(title="Set Personality", description=f'Invalid personality. Available options are: {", ".join(personalities.keys())}')
        await interaction.response.send_message(embed=embed)
        
@set_personality.autocomplete('personality')
async def personality_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name=personality, value=personality) for personality in personalities.keys() if current.lower() in personality.lower()]
    return choices

# Imitates personality of user input
@client.tree.command(name="pretend", description="Set the bot's personality to a character/celebrity")
async def pretend(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    censored_personality = censor_curse_words(personality)
    if filter_controversial(censored_personality):
        current_personality = custom_personalities(censored_personality)
        is_custom_personality = True
        conversation_histories.clear()
        embed = discord.Embed(title="Personality Change", description=f"I will now act like {censored_personality}")
    else:
        embed = discord.Embed(title="Personality Change", description="Sorry, I cannot pretend to be that person.")
    await interaction.response.send_message(embed=embed)
    
@client.tree.command(name="image",description="Generates image of prompt")
async def generate_image(interaction: discord.Interaction, description: str):
    # Generate image using DALL·E
    await interaction.response.defer()
    try:
        path = await generate_img(description)
        file = discord.File(path, filename=f"image.png")
        embed = discord.Embed(title="Generated Image")
        embed.set_image(url=f"attachment://image.png")
        await interaction.followup.send(embed=embed,file=file)
        os.remove(path)
    except Exception as e:
        await interaction.followup.send(content="Could not generate image!")
    
# Generates image based on personality
@client.tree.command(name="selfie",description="Generates image based off personality")
async def selfie(interaction: discord.Interaction):
    try:
        description = current_personality
        await interaction.response.defer()
        description = f"Personafication of {current_personality}"
        path = await generate_img(description)
        file = discord.File(path, filename=f"selfie.png")
    
        embed = discord.Embed().set_image(url=f"attachment://selfie.png")
        await interaction.followup.send(file=file,embed=embed)
        os.remove(path)
    except Exception as e:
       await interaction.response.send_message('I am feeling a little shy right now.. *uwu*')
    
# Resets "memory" and personality back to default
@client.tree.command(name="reset",description="Resets to default personality")
async def reset(interaction: discord.Interaction):
    global current_personality
    if current_personality != 'Chopperbot':
        current_personality = "Chopperbot"
        
    conversation_histories.clear()
    await interaction.response.send_message("My memory has been wiped!")
    print("Personality has been reset.")
    
@client.tree.command(name= "help",description="List of all commands")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Help Text", description="The following commands are available:")
    commandlist = client.tree.walk_commands()
    for Command in commandlist:
        embed.add_field(name=Command.name,value=Command.description if Command.description else Command.name, inline=False)
    await interaction.response.send_message(embed=embed)
    
# Allows private conversations
@client.tree.command(name="whisper",description="Ask and recieve response quietly.")
async def whisper(interaction: discord.Interaction, prompt: str):
    global is_custom_personality
    user_message_content = censor_curse_words(prompt)
    
    user_id = str(interaction.user.id)
    
    # Initialize conversation history for the user if it doesn't exist
    if user_id not in whispers_conversation_histories:
        whispers_conversation_histories[user_id] = []
    
    # Limit the conversation history to 5 messages for each user
    whispers_conversation_histories[user_id].append({"role": "user", "content": user_message_content})
    whispers_conversation_histories[user_id] = whispers_conversation_histories[user_id][-5:]

    if is_custom_personality == False:
        messages = [
            {"role": "system", "content": personalities[current_personality]}, 
            {"role": "user", "content": user_message_content}
        ]
    else:
        messages = [
            {"role": "system", "content": current_personality}, 
            {"role": "user", "content": user_message_content}
        ]

    client_response = await get_openai_response(messages)
    await interaction.response.send_message(client_response, ephemeral=True)
    
@client.tree.command(name="yaps", description="Shows number of messages you have sent")
async def yaps(interaction: discord.Interaction):
    server_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    
    server_yaps = yaps_counter.get(server_id, {})
    yaps = server_yaps.get(user_id, 0)
    
    await interaction.response.send_message(f'You have sent {yaps} messages so far.')

    
@client.tree.command(name='leaderboard', description='Shows top 10 yappers in the server')
async def yappers(interaction: discord.Interaction):
    server_id = str(interaction.guild.id)
    server_yaps = yaps_counter.get(server_id, {})
    sorted_yappers = sorted(server_yaps.items(), key=lambda x: x[1], reverse=True)
    
    embed = discord.Embed(title="Top 10 Yappers", description='In Decreasing Order:')
    
    for i, (user_id, yaps) in enumerate(sorted_yappers, start=1):
        user = await client.fetch_user(int(user_id))
        if user is not None and not user.bot:
            embed.add_field(name=f'#{i}', value=f'{user.name} {yaps}', inline=False)
            if i == 10:
                break
                
    await interaction.response.send_message(embed=embed)
    
@client.tree.command(name='dox', description='Generate address of user.')
async def address(interaction: discord.Interaction, user: discord.Member):
    try:
        if user is interaction.user:
            user = interaction.user
            message = "Your"
        else:
            message = f"{user.display_name}'s"
    
        number = random.randint(100, 500)
        streets = ["Mercy Ave", "Winton Ln", "Lucio Dr", "Hanzo Rd, Torb Rd, D.VA Way, E Cacalips Rd"]
        street = random.choice(streets)
        await interaction.response.send_message(f"{message} address is: {number} {street}, Merced, CA 95340")
    except Exception as e:
        await interaction.response.send_message("User not found in this server.")
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))
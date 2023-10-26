import asyncio
from code import interact
import io
import discord
from discord import Interaction, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities # Importing the personalities
import openai
from utils.openai_util import get_openai_response, generate_img
import os
import aiohttp

openai.api_key = client.openAI_API_key
current_personality = "Chopper Boy"  # Default personality
is_custom_personality = False

# Maintain a dynamic conversation history
conversation_histories = {}

@client.event
async def on_ready():
    await client.tree.sync()
    print(f'Logged in as {client.user.name}')

@client.event
async def on_message(message):
    # Avoid recursive loops with the bot's own messages
    if message.author == client.user:
        return

    channel_id = message.channel.id
    user_message_content = message.content
    username = str(message.author)

    # Update the conversation history
    if channel_id not in conversation_histories:
        conversation_histories[channel_id] = []
    conversation_histories[channel_id].append({"role": "user", "content": user_message_content})

    # If the bot is mentioned or addressed, generate a response using OpenAI
    if client.user.mentioned_in(message):
        global is_custom_personality
        if is_custom_personality == False:
            messages = [
                {"role": "system", "content": personalities[current_personality]},
             ] + conversation_histories[channel_id]
        else:
            messages = [
            {"role": "system", "content": current_personality},
            ] + conversation_histories[channel_id]

        client_response = await get_openai_response(messages)

        conversation_histories[channel_id].append({"role": "assistant", "content": client_response})

        await message.channel.send(client_response)

# Slash Commands Section
@client.tree.command(name="ping", description="Get bot latency")
async def ping(interaction: discord.Interaction):
    # Converts latency to milliseconds and sends through embedded message
    embed = discord.Embed(title="Ping",description=f"Pong!Current latency is {round(client.latency * 1000)}.")
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    if personality in personalities:
        current_personality = personality
        is_custom_personality = False
        conversation_histories.clear()
        embed = discord.Embed(title="Set Personality",description=f"Personality has been set to {personality}")
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(title="Set Personality",description=f'Invalid personality. Available options are: {", ".join(personalities.keys())}')
        await interaction.response.send_message(embed=embed)

@client.tree.command(name="custom_personality", description="Set the bot's personality to a character/celebrity")
async def custom_personality(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality,conversation_histories
    current_personality = custom_personalities(personality)
    is_custom_personality = True
    conversation_histories.clear()
    embed = discord.Embed(title="Custom Personality",description=f"Set personality to {personality}")
    await interaction.response.send_message(embed=embed)
    
@client.tree.command(name="image",description="Generates image of prompt")
async def generate_image(interaction: discord.Interaction, description: str):
    # Generate image using DALL·E
    await interaction.response.defer()
    path = await generate_img(description)
    file = discord.File(path, filename=f"selfie.png")
    embed = discord.Embed(title="Generated Image")
    embed.set_image(url=f"attachment://{file}")
    await interaction.followup.send(file=file,embed=embed)
    
    
# 
@client.tree.command(name="selfie",description="Generates image based off personality")
async def selfie(interaction: discord.Interaction):
    description = current_personality
    await interaction.response.defer()
    description = f"Personafication of {current_personality}"
    path = await generate_img(description)
    file = discord.File(path, filename=f"selfie.png")
    
    embed = discord.Embed().set_image(url=f"attachment://{file}")
    await interaction.followup.send(file=file,embed=embed)
    
# Resets "memory" and personality back to default
@client.tree.command(name="reset",description="Resets to default personality")
async def reset(interaction: discord.Interaction):
    global current_personality
    if current_personality != 'Chopper Boy':
        current_personality = "Chopper Boy"
        
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
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))

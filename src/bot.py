import discord
from discord import app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities # Importing the personalities
import openai
import os

openai.api_key = client.openAI_API_key
current_personality = "sassy"  # Default personality
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
            {"role": "system", "content": personalities[current_personality]},  # Use the current personality
            ] + conversation_histories[channel_id]
        else:
            messages = [
            {"role": "system", "content": current_personality},  # Use the current personality in custom format
            ] + conversation_histories[channel_id]
                
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.8,
            max_tokens=256
            )

        client_response = response.choices[0].message['content']
        conversation_histories[channel_id].append({"role": "assistant", "content": client_response})

        await message.channel.send(client_response)

# Slash Commands Section
@client.tree.command(name="ping", description="Get bot latency")
async def ping(interaction: discord.Interaction):
    # Converts latency to milliseconds
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f'Pong! Latency is {latency}ms.')

@client.tree.command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    if personality in personalities:
        current_personality = personality
        is_custom_personality = False
        conversation_histories.clear()
        await interaction.response.send_message(f'Personality set to {personality}!')
    else:
        await interaction.response.send_message(f'Invalid personality. Available options are: {", ".join(personalities.keys())}')

@client.tree.command(name="custom_personality", description="Set the bot's personality to a character")
async def custom_personality(interaction: discord.Interaction, personality: str):
    global current_personality, is_custom_personality,conversation_histories
    current_personality = custom_personalities(personality)
    is_custom_personality = True
    conversation_histories.clear()
    await interaction.response.send_message(f'Personality set to {personality}!')
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))

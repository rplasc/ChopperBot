import os
import openai
import asyncio
import discord
from discord import app_commands
from src.aclient import client

# Core Bot code
def run_discord_bot():
    @client.event
    async def on_ready():
        await client.tree.sync()
        print(f'Logged in as {client.user.name}')
    
    openai.api_key = client.openAI_API_key
    # Maintain a dynamic conversation history (consider using a more persistent storage for scalability)
    conversation_histories = {}
    # Responds to mentions    
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
            messages = [
                {"role": "system", "content": "You are a chatbot that is sassy."},
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
    
    # ------Slash Commands Section-----    
    @client.tree.command(name="ping",description="Get bot latency")
    async def ping(interaction: discord.Interaction):
       # Converts latency to milliseconds
       latency = round(client.latency * 1000)
       await interaction.response.send_message(f'Pong! Latency is {latency}ms.')
              
    client.run(os.getenv('DISCORD_BOT_TOKEN'))

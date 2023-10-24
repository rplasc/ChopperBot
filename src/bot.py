import os
import openai
import asyncio
import discord
from discord import app_commands
from src.aclient import client

def run_discord_bot():
    @client.event
    async def on_ready():
        await client.tree.sync()
        print(f'Logged in as {client.user.name}')
        
    @client.tree.command(name="check",description="Checks if bot is running")
    async def check(interaction: discord.Interaction):
       await interaction.response.send_message("I'm alive bozo")
        
    client.run(os.getenv('DISCORD_BOT_TOKEN'))
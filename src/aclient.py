import discord
import os
import asyncio
from dotenv import load_dotenv
from discord import Intents, app_commands

load_dotenv()

class aclient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents = intents)
        self.tree = app_commands.CommandTree(self)
        self.current_channel = None
        self.activity = discord.Activity(type = discord.ActivityType.watching, name='Porn')
        self.isPrivate = False
        
        # ChatGPT integration
        self.openAI_API_key = os.getenv('OPENAI_API_KEY')
        self.openAI_gpt_engine = os.getenv('GPT_ENGINE')
    
client = aclient()
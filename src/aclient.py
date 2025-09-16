import discord
import os
from dotenv import load_dotenv
from discord import Intents, app_commands

load_dotenv()  # take environment variables from .env.

# Creates client with Discord and OpenAI api
class aclient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents = intents)
        self.tree = app_commands.CommandTree(self)
        self.current_channel = None
        self.activity = discord.Activity(type = discord.ActivityType.listening,name='chopperboi')
        self.isPrivate = False
        self.current_personality = "Chopperbot"
        self.is_custom_personality = False
        
        # ChatGPT integration
        self.openAI_API_key = os.getenv('OPENAI_API_KEY')
        self.openAI_gpt_engine = os.getenv('GPT_ENGINE')
        
    
client = aclient()
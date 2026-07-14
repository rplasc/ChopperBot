import discord
import os
from dotenv import load_dotenv
from discord import app_commands

load_dotenv()

class aclient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents = intents)
        self.tree = app_commands.CommandTree(self)
        self.activity = discord.Activity(type = discord.ActivityType.listening, name='chopperboi')

        # KoboldCPP endpoints (vision, image gen, web search; text generation
        # goes through src.services.llm_service)
        self.kobold_text_api = os.getenv('KOBOLD_TEXT_API')
        self.kobold_web_api = os.getenv('KOBOLD_WEB_API')
        self.kobold_img_api = os.getenv('KOBOLD_IMG_API')


client = aclient()

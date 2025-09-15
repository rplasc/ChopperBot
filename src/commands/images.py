import os
from discord import Interaction, Embed, File
from src.aclient import client
from utils.openai_util import generate_img

@client.tree.command(name="image",description="Generates image of prompt")
async def generate_image(interaction: Interaction, description: str):
    # Generate image using DALL·E
    await interaction.response.defer()
    try:
        path = await generate_img(description)
        file = File(path, filename=f"image.png")
        embed = Embed(title="Generated Image")
        embed.set_image(url=f"attachment://image.png")
        await interaction.followup.send(embed=embed,file=file)
        os.remove(path)
    except Exception as e:
        await interaction.followup.send(content="Could not generate image!")
    
# Generates image based on personality
@client.tree.command(name="selfie",description="Generates image based off personality")
async def selfie(interaction: Interaction):
    try:
        description = client.current_personality
        await interaction.response.defer()
        description = f"Personafication of {client.current_personality}"
        path = await generate_img(description)
        file = File(path, filename=f"selfie.png")
    
        embed = Embed().set_image(url=f"attachment://selfie.png")
        await interaction.followup.send(file=file,embed=embed)
        os.remove(path)
    except Exception as e:
       await interaction.response.send_message('I am feeling a little shy right now.. *uwu*')
       
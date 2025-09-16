import os
import random
from discord import Interaction, Attachment, FFmpegPCMAudio, PCMVolumeTransformer
from src.aclient import client

@client.tree.command(name="play", description="Plays an attached file in the user's current voice channel")
async def play(interaction: Interaction, file: Attachment):
    # Check if the user is in a voice channel
    if interaction.guild.voice_client is None:
        await interaction.response.send_message("I'm not in a voice channel.")
        return

    if not interaction.data['options'][0]['value']:
        await interaction.response.send_message("Please attach a file to play.")
        return

    attachment = interaction.data['options'][0]['value']
    file_path = f"temp/{file.filename}"
    await attachment.save(file_path)

    # Join the user's voice channel
    voice_channel = interaction.author.voice.channel
    voice_client = interaction.guild.voice_client
    if voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    # Check if the file exists
    if not os.path.exists(file_path):
        await interaction.response.send_message("File not found.")
        return

    # Play the file
    voice_client.play(FFmpegPCMAudio(file_path), after=lambda e: print(f"Finished playing: {e}"))

    def after_play(error):
        os.remove(file_path)
        if error:
            print(f"Error playing audio: {error}")

    voice_client.source = PCMVolumeTransformer(voice_client.source)
    voice_client.source.volume = 0.5  # Set the volume (0.0 to 2.0)
    voice_client.source.after = after_play
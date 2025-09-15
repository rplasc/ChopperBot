import os
import random
from discord import Interaction, Embed, Member, Color, Attachment, FFmpegPCMAudio, PCMVolumeTransformer
from src.aclient import client

@client.tree.command(name='dox', description='Generate address of user.')
async def address(interaction: Interaction, user: Member):
    if user not in interaction.guild.members:
        await interaction.response.send_message("User not found in this server.")
        return
    if user is interaction.user:
        message = "Your"
    else:
        message = f"{user.display_name}'s"

    number = random.randint(100, 500)
    streets = ["Mercy Ave", "Winton Ln", "Lucio Dr", "Hanzo Rd"]
    street = random.choice(streets)
    await interaction.response.send_message(f"{message} random address is: {number} {street}, Merced, CA 95340")
    
def num_to_emoji(num):
    # Converts a number to a regional indicator emoji (1-10)
    regional_indicator_a = 0x1F1E6
    return chr(regional_indicator_a + num - 1)
    
@client.tree.command(name="poll", description="Create a poll using reactions")
async def poll(interaction: Interaction, question: str, *, choices: str):
    options = choices.split(',')
    if len(options) < 2 or len(options) > 10:
        await interaction.response.send_message("Please provide between 2 and 10 options.")
        return
    
    # Format the poll message
    poll_message = f"**{question}**\n\n"
    for i, option in enumerate(options, start=1):
        poll_message += f":{num_to_emoji(i)}: {option}\n"
    
    embed = Embed(title="Poll", description=poll_message, color=Color.blurple())
    embed.set_footer(text=f"Started by {interaction.user}")
    
    await interaction.response.send_message("Creating Poll:")
    
    # Send the poll message and add reactions
    message = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        emoji = num_to_emoji(i+1)
        await message.add_reaction(emoji)

@client.tree.command(name="play", description="Plays an attached file in the user's current voice channel")
async def play(interaction: Interaction, file: Attachment):
    # Check if the user is in a voice channel
    if interaction.guild.voice_client is None:
        await interaction.response.send_message("I'm not in a voice channel.")
        return

    # Check if there are attachments
    if not interaction.data['options'][0]['value']:
        await interaction.response.send_message("Please attach a file to play.")
        return

    # Get the first attachment (assuming only one file is uploaded)
    attachment = interaction.data['options'][0]['value']
    file_path = f"temp/{file.filename}"  # Save the file temporarily
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
import os
import discord
import openai
from src.aclient import client
from src.personalities import personalities
from utils.openai_util import get_openai_response
from utils.content_filter import censor_curse_words
from src.Moderation.yappers import init_db, increment_yap
from src.commands import admin, user, yaps, images

# Setup OpenAI api for conversation feature
openai.api_key = client.openAI_API_key

# Maintain a dynamic conversation history
conversation_histories = {}
MAX_HISTORY_LENGTH = 20
whispers_conversation_histories = {}

@client.event
async def on_ready():
    await init_db()
    await client.tree.sync()
    print(f'Logged in as {client.user.name}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if isinstance (message.channel, discord.DMChannel):
        await message.channel.send("Chopperbot is not available here.")
        return

    server_id = str(message.guild.id)
    user_id = str(message.author.id)
    await increment_yap(message.guild.id, user_id)

    channel_id = message.channel.id
    user_message_content = censor_curse_words(message.content)
    
    if server_id not in conversation_histories:
        conversation_histories[server_id] = {}
    if channel_id not in conversation_histories[server_id]:
        conversation_histories[server_id][channel_id] = []
        
    user_info = f"{message.author.id} ({message.author.name})"
    conversation_histories[server_id][channel_id].append({"role": "user", "content": f"{user_info}: {user_message_content}"})
    conversation_histories[server_id][channel_id] = conversation_histories[server_id][channel_id][-MAX_HISTORY_LENGTH:]

    if client.user.mentioned_in(message):
        if client.is_custom_personality == False:
            messages = [
                {"role": "system", "content": personalities[client.current_personality]},
             ] + conversation_histories[server_id][channel_id]
        else:
            messages = [
                {"role": "system", "content": client.current_personality},
            ] + conversation_histories[server_id][channel_id]
        try:
            client_response = await get_openai_response(messages)
            conversation_histories[server_id][channel_id].append({"role": "assistant", "content": client_response})
            await message.channel.send(client_response)
        except Exception as e:
            await message.channel.send('Sorry, I am not able to respond.')
    
@client.tree.command(name= "help",description="List of all commands")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Help Text", description="The following commands are available:")
    commandlist = client.tree.walk_commands()
    for Command in commandlist:
        embed.add_field(name=Command.name,value=Command.description if Command.description else Command.name, inline=False)
    await interaction.response.send_message(embed=embed)
    
# Allows private conversations
@client.tree.command(name="whisper",description="Ask and recieve response quietly.")
async def whisper(interaction: discord.Interaction, prompt: str):
    user_message_content = censor_curse_words(prompt)
    
    user_id = str(interaction.user.id)
    
    # Initialize conversation history for the user if it doesn't exist
    if user_id not in whispers_conversation_histories:
        whispers_conversation_histories[user_id] = []
    
    # Limit the conversation history to 5 messages for each user
    whispers_conversation_histories[user_id].append({"role": "user", "content": user_message_content})
    whispers_conversation_histories[user_id] = whispers_conversation_histories[user_id][-5:]

    if client.is_custom_personality == False:
        messages = [
            {"role": "system", "content": personalities[client.current_personality]}, 
            {"role": "user", "content": user_message_content}
        ]
    else:
        messages = [
            {"role": "system", "content": client.current_personality}, 
            {"role": "user", "content": user_message_content}
        ]

    client_response = await get_openai_response(messages)
    await interaction.response.send_message(client_response, ephemeral=True)
    
client.run(os.getenv('DISCORD_BOT_TOKEN'))
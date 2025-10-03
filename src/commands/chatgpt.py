from discord import Interaction
from src.aclient import client
from src.moderation.logging import logger
from utils.openai_util import get_openai_response
from utils.content_filter import censor_curse_words
from utils.history_util import trim_history

ask_conversation_histories = {}

# Allows ChatGPT conversations
@client.tree.command(name="ask",description="Ask and recieve response quietly from ChatGPT.")
async def ask(interaction: Interaction, prompt: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    user_message_content = censor_curse_words(prompt)
    
    user_id = str(interaction.user.id)
    
    # Initialize conversation history for the user if it doesn't exist
    if user_id not in ask_conversation_histories:
        ask_conversation_histories[user_id] = []
    
    # Limit the conversation history to 5 messages for each user
    ask_conversation_histories[user_id].append({"role": "user", "content": user_message_content})
    ask_conversation_histories[user_id] = trim_history(ask_conversation_histories[user_id], max_tokens=1500)
    
    try:
        client_response = await get_openai_response(ask_conversation_histories[user_id])
        ask_conversation_histories[user_id].append({"role": "assistant", "content": client_response})
        ask_conversation_histories[user_id] = trim_history(ask_conversation_histories[user_id], max_tokens=1500)

    except Exception as e:
        logger.error(f"[Ask Error] {e}")
        client_response = "I am currently unavailable."
    await interaction.followup.send(client_response, ephemeral=True)
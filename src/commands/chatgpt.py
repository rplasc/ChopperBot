from discord import Interaction, File
from src.aclient import client
from src.moderation.logging import logger
from src.services.llm_service import chat_completion
from src.utils.history_util import trim_history
from src.utils.message_util import to_discord_output

ask_conversation_histories = {}

# Private Q&A with the configured LLM (no personality, ephemeral)
@client.tree.command(name="ask", description="Ask and receive a response quietly.")
async def ask(interaction: Interaction, prompt: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    user_id = str(interaction.user.id)
    history = ask_conversation_histories.setdefault(user_id, [])
    history.append({"role": "user", "content": prompt})
    history[:] = trim_history(history, max_tokens=1500)

    try:
        response = await chat_completion(history, {"temperature": 0.7, "max_tokens": 512})
    except Exception as e:
        logger.error(f"[Ask Error] {e}")
        await interaction.followup.send("I am currently unavailable.", ephemeral=True)
        return

    history.append({"role": "assistant", "content": response})
    history[:] = trim_history(history, max_tokens=1500)

    output = to_discord_output(response)
    if isinstance(output, File):
        await interaction.followup.send("📄 Response was too long, see attached file:", file=output, ephemeral=True)
    else:
        for chunk in output:
            await interaction.followup.send(chunk, ephemeral=True)

from discord import Interaction, Embed, Color
from src.utils.websearch_util import perform_web_search, format_results_for_prompt
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger
from src.aclient import client

@client.tree.command(name="search", description="Ask the bot to search the web and summarize results.")
async def search_command(interaction: Interaction, query: str):
    await interaction.response.defer(thinking=True)

    try:
        # Step 1: Get web results
        results = await perform_web_search(query)
        if not results:
            await interaction.followup.send("No web results found.", ephemeral=True)
            return

        # Step 2: Format them for the model
        snippets = format_results_for_prompt(results)

        # Step 3: Ask the text model
        prompt = f"User question: {query}\n\nHere are web search results:\n{snippets}\n\nSummarize and answer based on these."

        answer = await generate_command_response(
            prompt=prompt,
            server_id=interaction.guild.id,
            use_personality=True,
            max_tokens=250
        )

        # Step 4: Build Embed
        username = interaction.user.id
        
        embed = Embed(title="🌐 Web Search 🌐", color=Color.blue())
        embed.add_field(name=f"{username}'s Query: ", value=f"*{query}*", inline=False)
        embed.add_field(name="**Result**", value=answer[:1024], inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"Web Search Proxy is unavailable.", ephemeral=True)
        logger.error(f"[Web Search Error] {e}")

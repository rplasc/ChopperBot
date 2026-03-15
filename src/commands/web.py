import discord
from discord import Interaction, Embed, Color
from src.utils.websearch_util import perform_web_search, format_results_for_prompt
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger
from src.aclient import client

# ============================================================================
# VIEWS
# ============================================================================

class SearchView(discord.ui.View):
    def __init__(self, query: str, snippets: str, server_id: str, username: str):
        super().__init__(timeout=120)
        self.query = query
        self.snippets = snippets
        self.server_id = server_id
        self.username = username

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Tell Me More", style=discord.ButtonStyle.primary, emoji="🔍")
    async def tell_me_more(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        button.disabled = True

        deep_prompt = (
            f"User question: {self.query}\n\nSearch results:\n{self.snippets}\n\n"
            "Go deeper on the most interesting aspect of these results. "
            "Give detail, specifics, and context the summary skipped."
        )
        try:
            deep_answer = await generate_command_response(
                prompt=deep_prompt,
                server_id=self.server_id,
                use_personality=False,
                max_tokens=400
            )
        except Exception as e:
            logger.error(f"[Search Deep Dive Error] {e}")
            deep_answer = "Couldn't go deeper right now."

        embed = Embed(title="🌐 Web Search — Deep Dive 🌐", color=Color.blue())
        embed.add_field(name=f"{self.username}'s Query:", value=f"*{self.query}*", inline=False)
        embed.add_field(name="**Deep Dive**", value=deep_answer[:1024], inline=False)
        await interaction.edit_original_response(embed=embed, view=self)


# ============================================================================
# COMMANDS
# ============================================================================

@client.tree.command(name="search", description="Ask the bot to search the web and summarize results.")
async def search_command(interaction: Interaction, query: str):
    await interaction.response.defer(thinking=True)

    try:
        results = await perform_web_search(query)
        if not results:
            await interaction.followup.send("No web results found.", ephemeral=True)
            return

        snippets = format_results_for_prompt(results)
        prompt = f"User question: {query}\n\nHere are web search results:\n{snippets}\n\nAnswer based on these."

        answer = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=False,
            max_tokens=250
        )

        username = interaction.user.name
        embed = Embed(title="🌐 Web Search 🌐", color=Color.blue())
        embed.add_field(name=f"{username}'s Query: ", value=f"*{query}*", inline=False)
        embed.add_field(name="**Result**", value=answer[:1024], inline=False)

        view = SearchView(query, snippets, str(interaction.guild.id), username)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send("Web Search Proxy is unavailable.", ephemeral=True)
        logger.error(f"[Web Search Error] {e}")

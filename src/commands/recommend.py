import discord
from discord import Interaction, Embed, Color, File, app_commands
from src.aclient import client
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger
from src.utils.message_util import chunk_message, to_discord_output


async def type_autocomplete(
    interaction: Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    options = ["song", "movie"]
    return [
        app_commands.Choice(name=opt, value=opt)
        for opt in options
        if current.lower() in opt.lower()
    ]


async def _build_recommend_embed(
    media_type: str, mood: str, genre_text: str, rating_text: str,
    results: int, extra_instruction: str = "", server_id: str = None
) -> tuple[Embed, str]:
    prompt = (
        f"Recommend {results} {media_type}{'s' if results > 1 else ''} "
        f"that match this request:\n"
        f"- Mood: {mood}\n"
        f"- Genre: {genre_text}\n"
        f"- Rating: {rating_text}\n"
        + (f"- Extra: {extra_instruction}\n" if extra_instruction else "")
        + "\nFormat the output as a numbered list with a short explanation."
    )

    try:
        recommendation = await generate_command_response(
            prompt=prompt,
            server_id=server_id,
            use_personality=True,
            temperature=0.8,
            max_tokens=512
        )
    except Exception as e:
        logger.error(f"[RECOMMEND ERROR] {e}")
        recommendation = "I couldn't think of any right now."

    items = [item.strip() for item in recommendation.split("\n") if item.strip()]

    embed = Embed(
        title=f"🎶 {results} {media_type.title()}{'s' if results > 1 else ''} Recommendation",
        description=f"Mood: **{mood}**, Genre: **{genre_text}**, Rating: **{rating_text}**",
        color=Color.blurple()
    )
    for item in items:
        chunks = chunk_message(item, limit=1024)
        for i, chunk in enumerate(chunks):
            embed.add_field(name="Recommendation" if i == 0 else "Continued", value=chunk, inline=False)

    return embed, recommendation


class RecommendView(discord.ui.View):
    def __init__(self, media_type: str, mood: str, genre_text: str, rating_text: str,
                 results: int, server_id: str):
        super().__init__(timeout=120)
        self.media_type = media_type
        self.mood = mood
        self.genre_text = genre_text
        self.rating_text = rating_text
        self.results = results
        self.server_id = server_id
        self._niche_used = False

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Give Me More", style=discord.ButtonStyle.primary, emoji="🔄")
    async def give_more(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await _build_recommend_embed(
            self.media_type, self.mood, self.genre_text, self.rating_text,
            self.results, "different from previous suggestions", self.server_id
        )
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Go Niche", style=discord.ButtonStyle.secondary, emoji="🕳️")
    async def go_niche(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        button.disabled = True
        self._niche_used = True
        embed, _ = await _build_recommend_embed(
            self.media_type, self.mood, self.genre_text, self.rating_text,
            self.results, "obscure, underground, and lesser-known only", self.server_id
        )
        embed.set_footer(text="🕳️ Going deep into the underground...")
        await interaction.edit_original_response(embed=embed, view=self)


@client.tree.command(name="recommend", description="Get a song or movie recommendation based on mood, genre, and rating")
@app_commands.describe(
    type="Choose whether you want a song or movie",
    mood="The mood you want matched",
    genre="Preferred genre (or 'any')",
    rating="Preferred rating (or 'any')",
    results="Number of recommendations (1–5)"
)
@app_commands.autocomplete(type=type_autocomplete)
async def recommend(
    interaction: Interaction,
    type: str,
    mood: str,
    genre: str = "any",
    rating: str = "any",
    results: int = 1
):
    await interaction.response.defer()
    type = type.lower()
    if type not in ["song", "movie"]:
        await interaction.followup.send("Type must be 'song' or 'movie'.", ephemeral=True)
        return

    results = max(1, min(results, 5))
    guild_id = str(interaction.guild.id) if interaction.guild else None
    genre_text = "any genre (wildcard)" if genre.lower() == "any" else genre
    rating_text = "any rating" if rating.lower() == "any" else rating

    embed, recommendation = await _build_recommend_embed(
        type, mood, genre_text, rating_text, results, server_id=guild_id
    )

    if len(embed) > 6000 or len(embed.fields) == 0:
        output = to_discord_output(recommendation)
        if isinstance(output, File):
            await interaction.followup.send(
                "📄 The recommendations were too long — see attached file:", file=output
            )
            return

    view = RecommendView(type, mood, genre_text, rating_text, results, guild_id)
    await interaction.followup.send(embed=embed, view=view)

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
        await interaction.response.send_message("Type must be 'song' or 'movie'.", ephemeral=True)
        return

    results = max(1, min(results, 5))

    genre_text = "any genre (wildcard)" if genre.lower() == "any" else genre
    rating_text = "any rating" if rating.lower() == "any" else rating

    prompt = (
        f"Recommend {results} {type}{'s' if results > 1 else ''} "
        f"that match this request:\n"
        f"- Mood: {mood}\n"
        f"- Genre: {genre_text}\n"
        f"- Rating: {rating_text}\n\n"
        f"Format the output as a numbered list with a short explanation."
    )

    try:
        recommendation = await generate_command_response(
            prompt=prompt,
            use_personality=True,
            temperature=0.8,
            max_tokens=512
        )
    except Exception as e:
        logger.error(f"[RECOMMEND ERROR] {e}")
        recommendation = "I couldn't think of any right now."

    items = [item.strip() for item in recommendation.split("\n") if item.strip()]

    embed = Embed(
        title=f"🎶 {results} {type.title()}{'s' if results > 1 else ''} Recommendation",
        description=f"Mood: **{mood}**, Genre: **{genre_text}**, Rating: **{rating_text}**",
        color=Color.blurple()
    )

    for item in items:
        chunks = chunk_message(item, limit=1024)
        for i, chunk in enumerate(chunks):
            name = "Recommendation" if i == 0 else "Continued"
            embed.add_field(name=name, value=chunk, inline=False)

    if len(embed) > 6000 or len(embed.fields) == 0:
        output = to_discord_output(recommendation)
        if isinstance(output, File):
            await interaction.followup.send(
                "📄 The recommendations were too long — see attached file:",
                file=output
            )
            return

    await interaction.followup.send(embed=embed)

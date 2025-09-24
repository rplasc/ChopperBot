from discord import Interaction, Embed, app_commands
from src.aclient import client
from src.personalities import personalities
from utils.kobaldcpp_util import get_kobold_response

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
async def recommend(interaction: Interaction, type: str, mood: str, genre: str = "any", rating: str = "any", results: int = 1):
    await interaction.response.defer()
    type = type.lower()
    if type not in ["song", "movie"]:
        await interaction.response.send_message("Type must be 'song' or 'movie'.", ephemeral=True)
        return

    if results < 1:
        results = 1
    elif results > 5:
        results = 5

    genre_text = "any genre (wildcard)" if genre.lower() == "any" else genre
    rating_text = "any rating" if rating.lower() == "any" else rating

    prompt = (
        f"Recommend {results} {type}{'s' if results > 1 else ''} "
        f"that match this request:\n"
        f"- Mood: {mood}\n"
        f"- Genre: {genre_text}\n"
        f"- Rating: {rating_text}\n\n"
        f"Each recommendation should include a title and a short description of why it fits."
    )

    system_content = (
        personalities[client.current_personality]
        if not client.is_custom_personality
        else client.current_personality
    )
    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": prompt}
    ]
    
    try:
        recommendation = await get_kobold_response(messages)
    except Exception:
        recommendation = "I couldn't think of any right now."

    await interaction.followup.send(recommendation)

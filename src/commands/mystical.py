import random
from discord import Interaction, Embed, Member, Color
from src.aclient import client
from src.utils.tarot_data import TAROT_CARDS
from src.utils.kobaldcpp_util import get_kobold_response
from src.utils.spellbook import SPELLS
from src.personalities import get_system_content
from src.moderation.logging import logger
# from utils.horoscope import ZODIAC_SIGNS, get_horoscope

@client.tree.command(name="tarot", description="Draw a tarot card for a reading.")
async def tarot(interaction: Interaction):
    card = random.choice(TAROT_CARDS)
    is_reversed = random.choice([True, False])
    
    orientation = "Reversed" if is_reversed else "Upright"
    meaning = card["reversed"] if is_reversed else card["upright"]

    embed = Embed(
        title=f"🔮 You drew: {card['name']} ({orientation})",
        description=meaning,
        color=Color.blurple()
    )
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="tarot_spread", description="Draw a 3-card tarot spread (past, present, future).")
async def tarot_spread(interaction: Interaction):
    await interaction.response.defer(thinking=True)

    cards = random.sample(TAROT_CARDS, 3)
    positions = ["Past", "Present", "Future"]

    spread = []
    spread_text = ""
    for pos, card in zip(positions, cards):
        is_reversed = random.choice([True, False])
        orientation = "Reversed" if is_reversed else "Upright"
        meaning = card["reversed"] if is_reversed else card["upright"]
        spread.append({"position": pos, "name": card["name"], "orientation": orientation, "meaning": meaning})
        spread_text += f"{pos}: {card['name']} ({orientation})"

    system_content = get_system_content()

    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": f"Here is a tarot spread:\n{spread_text}\nPlease interpret how these cards connect as a reading for the querent in a sentence."}
        ]

    try:
        interpretation = await get_kobold_response(messages)
    except Exception as e:
        logger.error(f"[Tarot Spread Error] {e}")
        interpretation = "The cards suggest change, growth, and reflection."

    embed = Embed(title="✨ Three-Card Tarot Reading ✨", color=Color.blurple())
    for card in spread:
        embed.add_field(name=f"{card['position']}: {card['name']} ({card['orientation']})",
                        value=card["meaning"], inline=False)
    embed.add_field(name="🔮 Interpretation", value=interpretation, inline=False)

    await interaction.followup.send(embed=embed)

@client.tree.command(name="cast", description="Cast a random spell on someone.")
async def cast(interaction: Interaction, target: Member):
    user_id  = interaction.user.id
    target_id = target._user.id
    spell = random.choice(SPELLS)
    await interaction.response.send_message(f"<@{user_id}> has cast **{spell['name']}!** on <@{target_id}>! {spell['message']}")

@client.tree.command(name="crystal_ball", description="Ask the crystal a question and it will generate an answer for you.")
async def crystal_ball(interaction: Interaction, question: str):
    await interaction.response.defer(thinking=True)

    system_content = get_system_content()
    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": f"Here is a question:\n{question}\nPlease give a vague response."}
        ]

    try:
        response = await get_kobold_response(messages)
    except Exception as e:
        logger.error(f"[Crystal Ball Error] {e}")
        response = "The future is too foggy at the moment."

    embed = Embed(color=Color.purple())
    embed.add_field(name="Your Question", value=question, inline=False)
    embed.add_field(name="🔮 Crystal Ball", value=response, inline=False)

    await interaction.followup.send(embed=embed)
import random
from discord import Interaction, Embed, Member
from src.aclient import client
from utils.tarot_data import TAROT_CARDS
from utils.openai_util import get_openai_response
from utils.spellbook import SPELLS
from src.personalities import personalities

@client.tree.command(name="tarot", description="Draw a tarot card for a reading.")
async def tarot(interaction: Interaction):
    card = random.choice(TAROT_CARDS)
    is_reversed = random.choice([True, False])
    
    orientation = "Reversed" if is_reversed else "Upright"
    meaning = card["reversed"] if is_reversed else card["upright"]

    embed = Embed(
        title=f"🔮 You drew: {card['name']} ({orientation})",
        description=meaning
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

    if client.is_custom_personality == False:
        messages = [
            {"role": "system", "content": personalities[client.current_personality]}, 
            {"role": "user", "content": f"Here is a tarot spread:\n{spread_text}\nPlease interpret how these cards connect as a reading for the querent in a sentence."}
        ]
    else:
        messages = [
            {"role": "system", "content": client.current_personality}, 
            {"role": "user", "content": f"Here is a tarot spread:\n{spread_text}\nPlease interpret how these cards connect as a reading for the querent in a sentence."}
        ]

    try:
        interpretation = await get_openai_response(messages)
    except Exception:
        interpretation = "The cards suggest change, growth, and reflection."

    embed = Embed(title="✨ Three-Card Tarot Reading ✨")
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

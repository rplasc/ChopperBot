import random
from discord import Interaction, Embed, Member
from src.aclient import client
from utils.tarot_data import TAROT_CARDS
from utils.kobaldcpp_util import get_kobold_response
from utils.spellbook import SPELLS
from src.personalities import personalities
from utils.horoscope import ZODIAC_SIGNS, get_horoscope

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
        interpretation = await get_kobold_response(messages)
    except Exception:
        interpretation = "The cards suggest change, growth, and reflection."

    embed = Embed(title="✨ Three-Card Tarot Reading ✨")
    for card in spread:
        embed.add_field(name=f"{card['position']}: {card['name']} ({card['orientation']})",
                        value=card["meaning"], inline=False)
    embed.add_field(name="🔮 Interpretation", value=interpretation, inline=False)

    await interaction.followup.send(embed=embed)

# TODO: Current api is down (permanently?)
# @client.tree.command(name="horoscope", description="Get your daily horoscope")
# async def horoscope(interaction: Interaction, sign: str):
#     await interaction.response.defer(thinking=True)

#     sign = sign.lower()
#     if sign not in ZODIAC_SIGNS:
#         await interaction.response.send_message("Please enter a valid zodiac sign.", ephemeral=True)
#         return
    
#     data = await get_horoscope(sign)

#     embed = Embed(title=f"✨ Horoscope for {sign.title()} ✨", description=data["description"])
#     embed.add_field(name="Mood", value=data["mood"])
#     embed.add_field(name="Lucky Number", value=data["lucky_number"])
#     embed.add_field(name="Lucky Color", value=data["color"])
#     embed.set_footer(text=f"Compatibility: {data['compatibility']} | Lucky Time: {data['lucky_time']}")

#     await interaction.followup.send(embed=embed)

@client.tree.command(name="cast", description="Cast a random spell on someone.")
async def cast(interaction: Interaction, target: Member):
    user_id  = interaction.user.id
    target_id = target._user.id
    spell = random.choice(SPELLS)
    await interaction.response.send_message(f"<@{user_id}> has cast **{spell['name']}!** on <@{target_id}>! {spell['message']}")

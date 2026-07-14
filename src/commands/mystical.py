import discord
import random
from discord import Interaction, Embed, Color
from src.aclient import client
from src.utils.tarot_data import TAROT_CARDS
from src.moderation.logging import logger
from src.utils.response_generator import generate_roleplay_response

# ============================================================================
# SHARED HELPER
# ============================================================================

_FORTUNE_CHARACTER = (
    "You are a mystical fortune teller who speaks in cryptic, poetic language. "
    "You see glimpses of possible futures and deliver them with dramatic flair."
)

async def _crystal_ball_embed(question: str) -> Embed:
    scenario = f'Someone asks: "{question}"\nProvide a cryptic, mystical prediction.'
    try:
        response = await generate_roleplay_response(
            character_description=_FORTUNE_CHARACTER,
            scenario=scenario,
            temperature=0.95,
            max_tokens=250
        )
    except Exception as e:
        logger.error(f"[Crystal Ball Error] {e}")
        response = "The future is too foggy at the moment."

    embed = Embed(color=Color.purple())
    embed.add_field(name="Your Question", value=question, inline=False)
    embed.add_field(name="🔮 Crystal Ball", value=response, inline=False)
    return embed

# ============================================================================
# VIEWS
# ============================================================================

class TarotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Draw Again", style=discord.ButtonStyle.secondary, emoji="🔮")
    async def draw_again(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        card = random.choice(TAROT_CARDS)
        is_reversed = random.choice([True, False])
        orientation = "Reversed" if is_reversed else "Upright"
        meaning = card["reversed"] if is_reversed else card["upright"]
        embed = Embed(
            title=f"🔮 You drew: {card['name']} ({orientation})",
            description=meaning,
            color=Color.blurple()
        )
        await interaction.edit_original_response(embed=embed, view=self)


class TarotSpreadView(discord.ui.View):
    def __init__(self, spread: list, base_embed: Embed):
        super().__init__(timeout=120)
        self.spread = spread
        self.base_embed = base_embed
        select = discord.ui.Select(
            placeholder="🔮 Explore a card in depth...",
            options=[
                discord.SelectOption(
                    label=f"{c['position']}: {c['name']}",
                    value=str(i),
                    description=c["orientation"]
                )
                for i, c in enumerate(spread)
            ]
        )
        select.callback = self.card_selected
        self.add_item(select)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def card_selected(self, interaction: Interaction):
        await interaction.response.defer()
        idx = int(interaction.data["values"][0])
        card = self.spread[idx]
        scenario = (
            f'A tarot card has appeared: {card["name"]} ({card["orientation"]}) '
            f'in the {card["position"]} position. Give a deep, specific mystical interpretation.'
        )
        try:
            detail = await generate_roleplay_response(
                character_description=_FORTUNE_CHARACTER,
                scenario=scenario,
                temperature=0.95,
                max_tokens=200
            )
        except Exception as e:
            logger.error(f"[Tarot Detail Error] {e}")
            detail = "The card's secrets remain veiled for now."

        embed = Embed.from_dict(self.base_embed.to_dict())
        embed.add_field(
            name=f"✨ Deep Reading: {card['name']}",
            value=detail,
            inline=False
        )
        await interaction.edit_original_response(embed=embed, view=self)


class AskAnotherModal(discord.ui.Modal, title="🔮 Ask the Crystal Ball"):
    question = discord.ui.TextInput(
        label="Your Question",
        placeholder="What do you wish to know?",
        max_length=200
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        embed = await _crystal_ball_embed(self.question.value)
        view = CrystalBallView()
        await interaction.edit_original_response(embed=embed, view=view)


class CrystalBallView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Ask Another", style=discord.ButtonStyle.secondary, emoji="🔮")
    async def ask_another(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AskAnotherModal())

# ============================================================================
# COMMANDS
# ============================================================================

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
    await interaction.response.send_message(embed=embed, view=TarotView())


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
        spread_text += f"{pos}: {card['name']} ({orientation}). "

    scenario = f'Someone draws these cards: "{spread_text}"\nProvide a cryptic, mystical prediction.'
    try:
        interpretation = await generate_roleplay_response(
            character_description=_FORTUNE_CHARACTER,
            scenario=scenario,
            temperature=0.95,
            max_tokens=250
        )
    except Exception as e:
        logger.error(f"[Tarot Spread Error] {e}")
        interpretation = "The cards suggest change, growth, and reflection."

    embed = Embed(title="✨ Three-Card Tarot Reading ✨", color=Color.blurple())
    for card in spread:
        embed.add_field(
            name=f"{card['position']}: {card['name']} ({card['orientation']})",
            value=card["meaning"],
            inline=False
        )
    embed.add_field(name="🔮 Interpretation", value=interpretation, inline=False)
    embed.set_footer(text="Select a card below to explore it in depth.")

    await interaction.followup.send(embed=embed, view=TarotSpreadView(spread, embed))

@client.tree.command(name="crystal_ball", description="Ask the crystal a question and it will generate an answer for you.")
async def crystal_ball(interaction: Interaction, question: str):
    await interaction.response.defer(thinking=True)
    embed = await _crystal_ball_embed(question)
    await interaction.followup.send(embed=embed, view=CrystalBallView())

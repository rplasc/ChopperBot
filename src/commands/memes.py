import discord
import random
from datetime import datetime, timezone
from discord import Interaction, Embed, Color
from src.aclient import client
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

_TRUE_IMAGE  = "https://cdn.discordapp.com/attachments/906441689114214420/1441626747614531594/IMG_7224.jpg?ex=69227b08&is=69212988&hm=0949e4b94accd62a7327254bd2e9553572d966220727f237c7312aef12eaa0b6&"
_FALSE_IMAGE = "https://cdn.discordapp.com/attachments/906441689114214420/1441626747245166714/IMG_8496.jpg?ex=69227b08&is=69212988&hm=5fe8614b7f769422d267446d5daa51325bc152c908882174cd577081d712e187&"

async def _build_fact_check_embed(statement: str, verdict: bool) -> Embed:
    verdict_word = "TRUE" if verdict else "FALSE"
    prompt = (
        f'Statement: "{statement}"\n'
        f"Verdict: {verdict_word}\n"
        "Write one short, chaotic, and funny sentence justifying this verdict as if you're a totally unreliable fact-checker. "
        "Be absurd, specific, and confident. No disclaimers."
    )
    try:
        reasoning = await generate_command_response(prompt, temperature=1.0, max_tokens=80)
    except Exception as e:
        logger.error(f"[Fact Check LLM Error] {e}")
        reasoning = "Our investigative team has reached this conclusion through rigorous guessing."

    embed = Embed(
        title="🗞️ Fact Check",
        color=Color.green() if verdict else Color.red()
    )
    embed.add_field(name="Statement", value=statement, inline=False)
    embed.add_field(name="Verdict", value=f"**{verdict_word}**", inline=True)
    embed.add_field(name="Reasoning", value=reasoning, inline=False)
    embed.set_image(url=_TRUE_IMAGE if verdict else _FALSE_IMAGE)
    embed.set_footer(text="Fact Checked by a real Illegal Immigrant")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


class FactCheckView(discord.ui.View):
    def __init__(self, statement: str, verdict: bool):
        super().__init__(timeout=120)
        self.statement = statement
        self.verdict = verdict

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Challenge This", style=discord.ButtonStyle.danger, emoji="⚖️")
    async def challenge(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        button.disabled = True
        # Flip the verdict for the challenge
        new_verdict = not self.verdict
        embed = await _build_fact_check_embed(self.statement, new_verdict)
        embed.set_footer(text="⚖️ Successfully Challenged — Fact Checked by a real Illegal Immigrant")
        await interaction.edit_original_response(embed=embed, view=self)


@client.tree.command(name="fact_check", description="Get a statement fact checked (totally accurate)")
async def fact_check(interaction: Interaction, statement: str):
    await interaction.response.defer(thinking=True)
    verdict = random.choice([True, False])
    embed = await _build_fact_check_embed(statement, verdict)
    await interaction.followup.send(embed=embed, view=FactCheckView(statement, verdict))

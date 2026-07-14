from typing import Optional
from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.moderation.database import (
    list_user_memories,
    delete_user_memory,
    delete_all_user_memories,
)
from src.services.personality_engine import (
    TRAITS, DEFAULT_SCORE, get_user_traits, derive_archetype,
)
from src.moderation.logging import logger

_MAX_LISTED = 20


@client.tree.command(name="memories", description="See what ChopperBot remembers about you")
async def memories_cmd(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)

    memories = await list_user_memories(user_id)
    if not memories:
        await interaction.followup.send("🧠 I don't have any memories about you yet.", ephemeral=True)
        return

    embed = Embed(
        title="🧠 Your Memories",
        description=f"I've stored {len(memories)} memories about you. "
                    "Use `/forget` with a memory ID to remove one.",
        color=Color.teal()
    )
    for mem in memories[:_MAX_LISTED]:
        stars = "★" * (mem["importance"] or 3)
        embed.add_field(
            name=f"#{mem['id']} · [{mem['category']}] {stars}",
            value=mem["content"][:1000],
            inline=False
        )
    if len(memories) > _MAX_LISTED:
        embed.set_footer(text=f"...and {len(memories) - _MAX_LISTED} more")

    await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.command(name="forget", description="Make ChopperBot forget a memory about you (or everything)")
async def forget_cmd(interaction: Interaction, memory_id: Optional[int] = None, everything: bool = False):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)

    if everything:
        deleted = await delete_all_user_memories(user_id)
        logger.info(f"[Forget] {interaction.user.name} wiped {deleted} memories")
        await interaction.followup.send(
            f"🧹 Forgot everything I knew about you ({deleted} memories).", ephemeral=True
        )
        return

    if memory_id is None:
        await interaction.followup.send(
            "Provide a `memory_id` (see `/memories`) or set `everything: True`.",
            ephemeral=True
        )
        return

    if await delete_user_memory(user_id, memory_id):
        logger.info(f"[Forget] {interaction.user.name} deleted memory #{memory_id}")
        await interaction.followup.send(f"✅ Forgot memory #{memory_id}.", ephemeral=True)
    else:
        await interaction.followup.send(
            f"❌ Memory #{memory_id} not found (it may not be yours).", ephemeral=True
        )


def _trait_bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


@client.tree.command(name="persona", description="View a user's evolving personality profile")
async def persona_cmd(interaction: Interaction, user: Optional[Member] = None):
    await interaction.response.defer()
    target = user or interaction.user

    traits = await get_user_traits(str(target.id))
    if not traits:
        await interaction.followup.send(
            f"📊 No personality profile for **{target.display_name}** yet — "
            "it builds up as they chat."
        )
        return

    archetype, _ = derive_archetype(traits)

    embed = Embed(
        title=f"🎭 {target.display_name}'s Persona",
        description=f"**Archetype:** {archetype}",
        color=Color.purple()
    )
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)

    lines = []
    for trait in TRAITS:
        score = traits.get(trait, DEFAULT_SCORE)
        lines.append(f"`{trait.capitalize():<16}` {_trait_bar(score)} {score:.0f}")
    embed.add_field(name="Traits", value="\n".join(lines), inline=False)

    await interaction.followup.send(embed=embed)

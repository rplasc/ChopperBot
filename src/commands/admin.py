from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.moderation.database import add_world_fact, get_world_context, get_user_log

@client.tree.command(name="add_fact", description="Add or update a world fact for this server")
async def add_fact(interaction: Interaction, key: str, value: str):
    await add_world_fact(str(interaction.guild.id), key, value)
    await interaction.response.send_message(f"✅ World fact updated: **{key}** → {value}")

@client.tree.command(name="show_world", description="Show saved world context for this server")
async def show_world(interaction: Interaction):
    context = await get_world_context(str(interaction.guild.id))
    if not context:
        await interaction.response.send_message("🌍 No world facts saved yet.")
    else:
        embed = Embed(title=f"🌍 World State for {interaction.guild.name}", description=context, color=Color.green())
        await interaction.response.send_message(embed=embed)

@client.tree.command(name="view_notes", description="View the long-term memory notes saved for a user.")
async def view_notes(interaction: Interaction, user: Member):
    log = await get_user_log(str(user.id))
    
    if not log:
        await interaction.followup.send("No profile found yet.")
        return
    
    await interaction.response.send_message(f"{log[1]}'s Notes:\n {log[4]}", ephemeral=True)
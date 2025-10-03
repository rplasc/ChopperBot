from discord import Interaction, Embed, Color, Member, app_commands
from src.aclient import client
from src.personalities import personalities, custom_personalities
from src.moderation.database import add_world_fact, get_world_context, get_user_log, delete_user_data, delete_world_context, reset_database, delete_world_entry
from src.moderation.logging import logger
from utils.content_filter import filter_controversial, censor_curse_words

# Flag for personality locking
personality_locked = False

# Wrapper for categories
def admin_only_command(*args, **kwargs):
    def wrapper(func):
        func.is_admin_only = True
        return client.tree.command(*args, **kwargs)(func)
    return wrapper

@admin_only_command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: Interaction, personality: str):
    from src.bot import conversation_histories

    if personality_locked and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "🚫 Personality changes are currently locked by an admin.",
            ephemeral=True
        )
        return

    await interaction.response.defer()
    if personality in personalities:
        client.current_personality = personality
        client.is_custom_personality = False
        conversation_histories.clear()
        embed = Embed(title="Set Personality", description=f"Personality has been set to {personality}")
        await interaction.followup.send(embed=embed)
    else:
        embed = Embed(
            title="Set Personality",
            description=f'Invalid personality. Available options: {", ".join(personalities.keys())}'
        )
        await interaction.followup.send(embed=embed)

@set_personality.autocomplete("personality")
async def personality_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=personality, value=personality)
        for personality in personalities.keys()
        if current.lower() in personality.lower()
    ]
    
@admin_only_command(name="roleplay", description="Set the bot's personality to a character/celebrity")
async def pretend(interaction: Interaction, personality: str):
    from src.bot import conversation_histories

    if personality_locked and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "🚫 Personality changes are currently locked by an admin.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer()
    censored_personality = censor_curse_words(personality)
    if filter_controversial(censored_personality):
        client.current_personality = custom_personalities(censored_personality)
        client.is_custom_personality = True
        conversation_histories.clear()
        embed = Embed(title="Personality Change", description=f"I will now act like {censored_personality}")
    else:
        embed = Embed(title="Personality Change", description="Sorry, I cannot pretend to be that person.")
    await interaction.followup.send(embed=embed)

@admin_only_command(name="lock_personality", description="Lock personality changes to admins only")
@app_commands.checks.has_permissions(administrator=True)
async def lock_personality(interaction: Interaction):
    global personality_locked
    personality_locked = True
    await interaction.response.send_message("🔒 Personality changes are now locked to admins only.", ephemeral=True)


@admin_only_command(name="unlock_personality", description="Unlock personality changes for all users")
@app_commands.checks.has_permissions(administrator=True)
async def unlock_personality(interaction: Interaction):
    global personality_locked
    personality_locked = False
    await interaction.response.send_message("🔓 Personality changes are now unlocked for all users.", ephemeral=True)
    
# Resets "memory" and personality back to default
@admin_only_command(name="refresh",description="Resets to default personality and clears conversation history.")
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: Interaction):
    await interaction.response.defer()
    from src.bot import conversation_histories
    if client.current_personality != 'Default':
        client.current_personality = "Default"
        client.is_custom_personality = False
        
    conversation_histories.clear()
    await interaction.followup.send("My memory has been wiped!")
    logger.info("Personality has been reset.")

@admin_only_command(name="add_fact", description="Add or update a world fact for this server")
@app_commands.checks.has_permissions(administrator=True)
async def add_fact(interaction: Interaction, key: str, value: str):
    await add_world_fact(str(interaction.guild.id), key, value)
    await interaction.response.send_message(f"✅ World fact updated: **{key}** → {value}", ephemeral=True)

@admin_only_command(name="show_world", description="Show saved world context for this server")
@app_commands.checks.has_permissions(administrator=True)
async def show_world(interaction: Interaction):
    context = await get_world_context(str(interaction.guild.id))
    if not context:
        await interaction.response.send_message("🌍 No world facts saved yet.")
    else:
        embed = Embed(title=f"🌍 World State for {interaction.guild.name}", description=context, color=Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

@admin_only_command(name="view_notes", description="View the long-term memory notes saved for a user.")
@app_commands.checks.has_permissions(administrator=True)
async def view_notes(interaction: Interaction, user: Member):
    log = await get_user_log(str(user.id))
    
    if not log:
        await interaction.followup.send("No profile found yet.")
        return
    
    await interaction.response.send_message(f"{log[1]}'s Notes:\n {log[4]}", ephemeral=True)

@admin_only_command(name="delete_user", description="Delete all stored data for a user")
@app_commands.checks.has_permissions(administrator=True)
async def delete_user(interaction: Interaction, user_id: str):
    await delete_user_data(user_id)
    logger.info(f"Deleted data for user {user_id}")
    await interaction.response.send_message(f"✅ Deleted data for user {user_id}", ephemeral=True)

@admin_only_command(
    name="delete_world_entry",
    description="Delete a single world context entry by key"
)
@app_commands.checks.has_permissions(administrator=True)
async def delete_world_entry_cmd(interaction: Interaction, key: str):
    server_id = str(interaction.guild.id)
    await delete_world_entry(server_id, key)
    await interaction.response.send_message(
        f"✅ Deleted world entry with key `{key}` for this server.",
        ephemeral=True
    )

@admin_only_command(name="delete_world", description="Delete world context for this server")
@app_commands.checks.has_permissions(administrator=True)
async def delete_world(interaction: Interaction):
    server_id = str(interaction.guild.id)
    await delete_world_context(server_id)
    logger.info(f"Deleted world context for {interaction.guild.name}")
    await interaction.response.send_message("✅ Deleted world context for this server", ephemeral=True)

@admin_only_command(
    name="reset_database",
    description="⚠️ Reset the entire database (requires confirmation)"
)
@app_commands.checks.has_permissions(administrator=True)
async def reset_db(interaction: Interaction, confirm: str):
    """
    Reset the DB only if confirm == 'CONFIRM'
    """
    if confirm != "CONFIRM":
        await interaction.response.send_message(
            "⚠️ You must type `CONFIRM` exactly to reset the database.",
            ephemeral=True
        )
        return

    await reset_database()
    await interaction.response.send_message(
        "⚠️ Database has been fully reset!",
        ephemeral=True
    )

@admin_only_command(name="admin_help", description="List of all admin commands")
@app_commands.checks.has_permissions(administrator=True)
async def admin_help(interaction: Interaction):
    embed = Embed(title="🛠️ Admin Help", description="The following admin commands are available:", color=Color.red())

    for cmd in client.tree.walk_commands():
        if getattr(cmd.callback, "is_admin_only", False):
            embed.add_field(
                name=f"/{cmd.name}",
                value=cmd.description or cmd.name,
                inline=False
            )

    await interaction.response.send_message(embed=embed, ephemeral=True)
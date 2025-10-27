from discord import Interaction, Embed, Color, Member, app_commands
from src.aclient import client
from src.personalities import personalities
from src.utils.personality_manager import (
    set_server_personality,
    set_server_custom_personality,
    reset_server_personality,
    get_server_personality_name,
    get_server_personality,
    personality_manager
)
from src.moderation.database import (
    manual_world_update, get_world_context, get_user_log, delete_user_data,
    delete_world_context, reset_database, delete_world_entry, get_pool_stats,
    invalidate_user_log_cache, list_world_facts
)
from src.moderation.logging import logger
from src.utils.content_filter import filter_controversial, censor_curse_words

# Flag for personality locking
personality_locks = {}  # {server_id: bool}

def is_personality_locked(server_id: str) -> bool:
    """Check if personality is locked for a specific server"""
    return personality_locks.get(server_id, False)

# Wrapper for categories
def admin_only_command(*args, **kwargs):
    def wrapper(func):
        func.is_admin_only = True
        return client.tree.command(*args, **kwargs)(func)
    return wrapper


# ============================================================================
# PERSONALITY MANAGEMENT COMMANDS
# ============================================================================

@admin_only_command(name="set_personality", description="Set the bot's personality for THIS server")
async def set_personality_cmd(interaction: Interaction, personality: str):
    
    server_id = str(interaction.guild.id)
    
    # Check if locked
    if is_personality_locked(server_id) and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "🔒 Personality changes are currently locked by an admin.",
            ephemeral=True
        )
        return

    await interaction.response.defer()
    
    if personality in personalities:
        success = await set_server_personality(server_id, personality)
        
        if success:
            # Clear history for this server only
            from src.bot import conversation_histories_cache
            keys_to_clear = [k for k in conversation_histories_cache.keys() if k[0] == server_id]
            for key in keys_to_clear:
                del conversation_histories_cache[key]
            
            embed = Embed(
                title="🎭 Personality Updated",
                description=f"This server's personality is now: **{personality}**",
                color=Color.green()
            )
            logger.info(f"Server {server_id} personality set to {personality}")
            await interaction.followup.send(embed=embed)
        else:
            embed = Embed(
                title="❌ Invalid Personality",
                description=f'Available: {", ".join(personalities.keys())}',
                color=Color.red()
            )
            await interaction.followup.send(embed=embed)
    else:
        embed = Embed(
            title="❌ Invalid Personality",
            description=f'Available options:\n' + '\n'.join(f"• {p}" for p in personalities.keys()),
            color=Color.red()
        )
        await interaction.followup.send(embed=embed)

@set_personality_cmd.autocomplete("personality")
async def personality_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=personality, value=personality)
        for personality in personalities.keys()
        if current.lower() in personality.lower()
    ]
    
@admin_only_command(name="roleplay", description="Set the bot to roleplay as a character (for THIS server)")
async def roleplay_cmd(interaction: Interaction, character: str):
    
    server_id = str(interaction.guild.id)
    
    if is_personality_locked(server_id) and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "🔒 Personality changes are currently locked by an admin.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer()
    
    censored_character = censor_curse_words(character)
    
    if filter_controversial(censored_character):
        await set_server_custom_personality(server_id, censored_character)
        
        from src.bot import conversation_histories_cache
        keys_to_clear = [k for k in conversation_histories_cache.keys() if k[0] == server_id]
        for key in keys_to_clear:
            del conversation_histories_cache[key]
        
        embed = Embed(
            title="🎭 Roleplay Mode Activated",
            description=f"I will now act like **{censored_character}** in this server!",
            color=Color.purple()
        )
        logger.info(f"Server {server_id} set to roleplay as {censored_character}")
        await interaction.followup.send(embed=embed)
    else:
        embed = Embed(
            title="❌ Cannot Roleplay",
            description="Sorry, I cannot pretend to be that character.",
            color=Color.red()
        )
        await interaction.followup.send(embed=embed)

@admin_only_command(name="reset_personality", description="Reset this server to Default personality")
@app_commands.checks.has_permissions(administrator=True)
async def reset_personality_cmd(interaction: Interaction):
    
    server_id = str(interaction.guild.id)
    await reset_server_personality(server_id)
    
    from src.bot import conversation_histories_cache
    keys_to_clear = [k for k in conversation_histories_cache.keys() if k[0] == server_id]
    for key in keys_to_clear:
        del conversation_histories_cache[key]
    
    logger.info(f"Reset personality for server {server_id}")
    await interaction.response.send_message(
        "✅ Reset to Default personality for this server.",
        ephemeral=True
    )

@admin_only_command(name="lock_personality", description="Lock personality changes to admins only (this server)")
@app_commands.checks.has_permissions(administrator=True)
async def lock_personality_cmd(interaction: Interaction):
    server_id = str(interaction.guild.id)
    personality_locks[server_id] = True
    logger.info(f"Personality locked for server {server_id}")
    await interaction.response.send_message(
        "🔒 Personality changes are now locked to admins only for this server.",
        ephemeral=True
    )

@admin_only_command(name="unlock_personality", description="Unlock personality changes (this server)")
@app_commands.checks.has_permissions(administrator=True)
async def unlock_personality_cmd(interaction: Interaction):
    server_id = str(interaction.guild.id)
    personality_locks[server_id] = False
    logger.info(f"Personality unlocked for server {server_id}")
    await interaction.response.send_message(
        "🔓 Personality changes are now unlocked for this server.",
        ephemeral=True
    )

@admin_only_command(name="current_personality", description="Show this server's current personality")
async def current_personality_cmd(interaction: Interaction):    
    server_id = str(interaction.guild.id)
    personality_name = await get_server_personality_name(server_id)
    
    is_locked = is_personality_locked(server_id)
    lock_status = "🔒 Locked (admins only)" if is_locked else "🔓 Unlocked"
    
    embed = Embed(
        title=f"🎭 Current Personality for {interaction.guild.name}",
        description=f"**{personality_name}**\n\n{lock_status}",
        color=Color.blue()
    )
    
    # Get personality object for details
    personality = await get_server_personality(server_id)
    
    if personality:
        embed.add_field(
            name="Quick Stats",
            value=f"Temperature: {personality.temperature}\n"
                  f"Max Tokens: {personality.max_tokens_preferred}\n"
                  f"Creativity: {personality.creativity:.0%}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
# Resets "memory" and personality back to default
@admin_only_command(name="refresh", description="Clear conversation history for THIS server")
@app_commands.checks.has_permissions(administrator=True)
async def refresh_cmd(interaction: Interaction):    
    await interaction.response.defer()
    server_id = str(interaction.guild.id)
    
    from src.bot import conversation_histories_cache
    
    # Clear only this server's history
    keys_to_clear = [k for k in conversation_histories_cache.keys() if k[0] == server_id]
    cleared_count = len(keys_to_clear)
    
    for key in keys_to_clear:
        del conversation_histories_cache[key]
    
    personality_name = await get_server_personality_name(server_id)
    
    await interaction.followup.send(
        f"🧹 Cleared {cleared_count} conversation(s) for this server!\n"
        f"_Personality remains: **{personality_name}**_"
    )
    logger.info(f"History cleared for server {server_id}")


# ============================================================================
# ADVANCED ADMIN COMMANDS
# ============================================================================

@admin_only_command(name="personality_info", description="Show detailed info about this server's personality")
@app_commands.checks.has_permissions(administrator=True)
async def personality_info(interaction: Interaction):    
    server_id = str(interaction.guild.id)
    personality = await get_server_personality(server_id)
    
    if not personality:
        await interaction.response.send_message("❌ No personality loaded", ephemeral=True)
        return
    
    embed = Embed(
        title=f"🎭 Personality: {personality.name}",
        description=f"Details for **{interaction.guild.name}**",
        color=Color.purple()
    )
    
    # Parameters
    embed.add_field(
        name="Generation Parameters",
        value=f"**Temperature:** {personality.temperature}\n"
              f"**Formality:** {personality.formality:.1%}\n"
              f"**Verbosity:** {personality.verbosity:.1%}\n"
              f"**Emotional Range:** {personality.emotional_range:.1%}\n"
              f"**Creativity:** {personality.creativity:.1%}",
        inline=True
    )
    
    # Characteristics
    embed.add_field(
        name="Characteristics",
        value=f"**Max Tokens:** {personality.max_tokens_preferred}\n"
              f"**Can Use Slang:** {'Yes' if personality.can_use_slang else 'No'}\n"
              f"**Can Be Edgy:** {'Yes' if personality.can_be_edgy else 'No'}\n"
              f"**Repetition Penalty:** {personality.repetition_penalty}",
        inline=True
    )
    
    # Preview of prompt
    prompt_preview = personality.get_base_prompt()[:200] + "..."
    embed.add_field(
        name="Prompt Preview",
        value=f"```{prompt_preview}```",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@admin_only_command(name="list_server_personalities", description="Show personality settings across all servers")
@app_commands.checks.has_permissions(administrator=True)
async def list_server_personalities_cmd(interaction: Interaction):    
    all_personalities = personality_manager.get_all_server_personalities()
    
    if not all_personalities:
        await interaction.response.send_message(
            "📋 All servers are using Default personality.",
            ephemeral=True
        )
        return
    
    embed = Embed(
        title="🌐 Server Personality Assignments",
        description=f"Showing custom personalities for {len(all_personalities)} server(s)",
        color=Color.blue()
    )
    
    for server_id, personality_name in list(all_personalities.items())[:20]:
        try:
            guild = client.get_guild(int(server_id))
            server_name = guild.name if guild else f"Unknown Server"
        except:
            server_name = f"Server {server_id[:8]}..."
        
        lock_emoji = "🔒" if is_personality_locked(server_id) else "🔓"
        
        embed.add_field(
            name=f"{lock_emoji} {server_name}",
            value=personality_name,
            inline=True
        )
    
    if len(all_personalities) > 20:
        embed.set_footer(text=f"...and {len(all_personalities) - 20} more servers")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================================
# WORLD MEMORY COMMANDS
# ============================================================================

@admin_only_command(name="world_set", description="Manually add or update a world fact")
@app_commands.checks.has_permissions(administrator=True)
async def add_fact(interaction: Interaction, key: str, value: str):
    await manual_world_update(str(interaction.guild.id), key, value)
    key_display = key.replace("_", " ").title()
    await interaction.response.send_message(f"✅ World fact updated: **{key_display}**: {value}", ephemeral=True)

@admin_only_command(name="world_list", description="View all world memory facts")
@app_commands.checks.has_permissions(administrator=True)
async def show_world(interaction: Interaction):
    await interaction.response.defer()

    facts = await list_world_facts(interaction.guild.id)

    if not facts:
        await interaction.followup.send("🌍 No world facts saved yet.")
        return

    embed = Embed(title=f"🌍 World State for {interaction.guild.name}", description="List of world facts", color=Color.green())

    for fact in facts[:20]:
            key_display = fact['key'].replace("_", " ").title()
            embed.add_field(name=key_display, value=fact['value'], inline=False)
        
    if len(facts) > 20:
        embed.set_footer(f"\n_...and {len(facts) - 20} more facts_")

    await interaction.followup.send(embed=embed, ephemeral=True)

@admin_only_command(name="world_view", description="View the world context as the bot sees it.")
async def world_view(interaction):    
    server_id = str(interaction.guild_id)
    context = await get_world_context(server_id)
    
    if not context:
        await interaction.response.send_message(
            "📭 No world context available yet.",
            ephemeral=True
        )
        return
    
    await interaction.response.send_message(
        f"**🌍 Current World Context**\n\n{context}",
        ephemeral=True
    )

@admin_only_command(name="world_delete", description="Delete a specific world fact")
@app_commands.checks.has_permissions(administrator=True)
async def delete_world_entry_cmd(interaction: Interaction, key: str):
    server_id = str(interaction.guild.id)
    key_clean = key.lower().replace(" ", "_")
    await delete_world_entry(server_id, key_clean)
    await interaction.response.send_message(f"✅ Deleted world entry with key `{key}` for this server.", ephemeral=True)

@admin_only_command(name="world_clear", description="Delete world context for this server")
@app_commands.checks.has_permissions(administrator=True)
async def delete_world(interaction: Interaction):
    server_id = str(interaction.guild.id)
    await delete_world_context(server_id)

    from src.moderation.database import world_histories, world_update_cooldowns
    if server_id in world_histories:
        del world_histories[server_id]
    if server_id in world_update_cooldowns:
        del world_update_cooldowns[server_id]
    
    logger.info(f"Deleted world context for {interaction.guild.name}")
    await interaction.response.send_message("✅ Deleted world context for this server", ephemeral=True)


# ============================================================================
# USER MANAGEMENT COMMANDS (unchanged)
# ============================================================================

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
    from src.moderation.database import interaction_cache
    if user_id in interaction_cache:
        del interaction_cache[user_id]
    await interaction.response.send_message(f"✅ Deleted data for user {user_id}", ephemeral=True)


# ============================================================================
# SYSTEM MANAGEMENT COMMANDS
# ============================================================================

@admin_only_command(name="reset_database", description="⚠️ Reset the entire database (requires confirmation)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_db(interaction: Interaction, confirm: str):
    if confirm != "CONFIRM":
        await interaction.response.send_message("⚠️ You must type `CONFIRM` exactly to reset the database.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)

    await reset_database()

    from src.bot import conversation_histories_cache
    from src.moderation.database import interaction_cache, world_histories, world_update_cooldowns
    
    conversation_histories_cache.clear()
    interaction_cache.clear()
    world_histories.clear()
    world_update_cooldowns.clear()
    
    logger.warning("DATABASE FULLY RESET by admin")

    await interaction.followup.send("⚠️ Database has been fully reset!", ephemeral=True)

@admin_only_command(name="clear_cache", description="Clear all in-memory caches")
@app_commands.checks.has_permissions(administrator=True)
async def clear_cache(interaction: Interaction):
    from src.bot import conversation_histories_cache
    from src.moderation.database import clear_user_log_cache, interaction_cache
    
    # Clear all caches
    conversation_histories_cache.clear()
    clear_user_log_cache()
    interaction_cache.clear()
    
    logger.info("All caches cleared by admin")
    await interaction.response.send_message(
        "✅ Cleared all in-memory caches (conversation history, user logs, interactions)",
        ephemeral=True
    )

@admin_only_command(name="invalidate_user_cache", description="Invalidate cache for a specific user")
@app_commands.checks.has_permissions(administrator=True)
async def invalidate_cache(interaction: Interaction, user: Member):
    user_id = str(user.id)
    invalidate_user_log_cache(user_id)
    
    await interaction.response.send_message(
        f"✅ Invalidated cache for {user.display_name}. Next access will fetch fresh data.",
        ephemeral=True
    )

@admin_only_command(name="pool_stats", description="Show database connection pool statistics")
@app_commands.checks.has_permissions(administrator=True)
async def pool_stats(interaction: Interaction):
    stats = get_pool_stats()
    
    if not stats:
        await interaction.response.send_message("❌ Connection pool not initialized", ephemeral=True)
        return
    
    embed = Embed(
        title="📊 Database Pool Statistics",
        color=Color.blue()
    )
    
    embed.add_field(
        name="Connection Pool",
        value=f"**Active:** {stats['pool_size']}/{stats['max_size']}\n"
              f"**Available:** {stats['available_connections']}\n"
              f"**In Use:** {stats['pool_size'] - stats['available_connections']}",
        inline=True
    )
    
    embed.add_field(
        name="Write Queue",
        value=f"**Pending:** {stats['write_queue_size']} interactions",
        inline=True
    )
    
    # Cache statistics
    from src.bot import conversation_histories_cache
    from src.moderation.database import user_log_cache, interaction_cache
    
    embed.add_field(
        name="Cache Statistics",
        value=f"**Conversations:** {len(conversation_histories_cache)}\n"
              f"**User Logs:** {len(user_log_cache)}\n"
              f"**Interactions:** {len(interaction_cache)}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

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

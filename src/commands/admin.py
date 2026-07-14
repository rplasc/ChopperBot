import time
import asyncio
from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.personalities import get_personality
from src.moderation.database import (
    manual_world_update, get_world_context, get_user_log, delete_user_data,
    delete_world_context, reset_database, delete_world_entry, get_pool_stats,
    invalidate_user_log_cache, list_world_facts,
    update_personality_notes_with_username,
    pending_notes_queue, clear_criminal_record
)
from src.services.llm_service import chat_completion
from src.moderation.logging import logger
from src.utils.permissions import is_admin, is_owner

# Wrapper for categories
def admin_only_command(*args, **kwargs):
    def wrapper(func):
        func.is_admin_only = True
        return client.tree.command(*args, **kwargs)(func)
    return wrapper


# ============================================================================
# CONVERSATION / PERSONALITY COMMANDS
# ============================================================================

@admin_only_command(name="refresh", description="Clear conversation history for THIS server")
@is_admin()
async def refresh_cmd(interaction: Interaction):
    await interaction.response.defer()
    server_id = str(interaction.guild.id)

    from src.bot import conversation_histories_cache

    # Clear only this server's history
    keys_to_clear = [k for k in conversation_histories_cache.keys() if k[0] == server_id]
    cleared_count = len(keys_to_clear)

    for key in keys_to_clear:
        del conversation_histories_cache[key]

    await interaction.followup.send(
        f"🧹 Cleared {cleared_count} conversation(s) for this server!"
    )
    logger.info(f"History cleared for server {server_id}")

@admin_only_command(name="personality_info", description="Show details of the bot's personality")
@is_admin()
async def personality_info(interaction: Interaction):
    personality = get_personality()

    embed = Embed(
        title=f"🎭 Personality: {personality.name}",
        description="ChopperBot runs one central personality everywhere.",
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
              f"**Repetition Penalty:** {personality.repetition_penalty}\n"
              f"**Can Search Web:** {'Yes' if personality.can_search_web else 'No'}",
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

# ============================================================================
# WORLD MEMORY COMMANDS
# ============================================================================

@admin_only_command(name="world_set", description="Manually add or update a world fact")
@is_admin()
async def add_fact(interaction: Interaction, key: str, value: str):
    success = await manual_world_update(str(interaction.guild.id), key, value)
    
    key_display = key.replace("_", " ").title()
    
    if success:
        await interaction.response.send_message(f"✅ World fact updated: **{key_display}**: {value}", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"⚠️ **World Context Full!**\n"
            f"You have reached the limit of facts. Please delete an old fact using `/world_delete` before adding a new one.",
            ephemeral=True
        )

@admin_only_command(name="world_list", description="View all world memory facts")
@is_admin()
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
    
    server_name = interaction.guild.name
    owner_name = interaction.guild.owner.display_name if interaction.guild.owner else "Unknown"

    context = await get_world_context(server_id, server_name, owner_name)
    
    await interaction.response.send_message(
        context,
        ephemeral=True
    )

@admin_only_command(name="world_delete", description="Delete a specific world fact")
@is_admin()
async def delete_world_entry_cmd(interaction: Interaction, key: str):
    server_id = str(interaction.guild.id)
    key_clean = key.lower().replace(" ", "_")
    await delete_world_entry(server_id, key_clean)
    await interaction.response.send_message(f"✅ Deleted world entry with key `{key}` for this server.", ephemeral=True)

@admin_only_command(name="world_clear", description="Delete world context for this server")
@is_admin()
async def delete_world(interaction: Interaction):
    server_id = str(interaction.guild.id)
    await delete_world_context(server_id)

    logger.info(f"Deleted world context for {interaction.guild.name}")
    await interaction.response.send_message("✅ Deleted world context for this server", ephemeral=True)


# ============================================================================
# USER MANAGEMENT COMMANDS
# ============================================================================

@admin_only_command(name="view_notes", description="View the long-term memory notes saved for a user.")
@is_admin()
async def view_notes(interaction: Interaction, user: Member):
    log = await get_user_log(str(user.id))
    
    if not log:
        await interaction.response.send_message("No profile found yet.", ephemeral=True)
        return
    
    if not log[4]:
        await interaction.response.send_message(f"No notes have been generated for {user.display_name} yet.", ephemeral=True)
        return
    
    embed = Embed(
        title=f"📝 Notes for {log[1]}",
        description=log[4],
        color=Color.blue()
    )
    
    embed.add_field(
        name="Stats",
        value=f"**Interactions:** {log[2]}\n**Last Seen:** {log[3]}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@admin_only_command(name="create_notes", description="Generate personality notes for active users in this channel")
@is_admin()
async def create_notes_cmd(interaction: Interaction, message_limit: int = 500, min_user_messages: int = 50, skip_existing: bool = True):

    await interaction.response.defer(ephemeral=True)
    
    server_id = str(interaction.guild.id)
    channel = interaction.channel
    
    # Validate limits
    if message_limit > 1000:
        await interaction.followup.send(
            "⚠️ Discord API limits message fetching to 1000 messages maximum.",
            ephemeral=True
        )
        return
    
    if message_limit < min_user_messages:
        await interaction.followup.send(
            f"⚠️ message_limit ({message_limit}) must be at least min_user_messages ({min_user_messages})",
            ephemeral=True
        )
        return
    
    await interaction.followup.send(
        f"📥 Fetching up to {message_limit} messages from this channel...",
        ephemeral=True
    )
    
    try:
        # Fetch messages directly from Discord
        messages = []
        async for message in channel.history(limit=message_limit):
            # Skip bot messages
            if message.author.bot:
                continue
            
            # Skip empty messages
            if not message.content.strip():
                continue
            
            messages.append({
                "user_id": str(message.author.id),
                "username": message.author.name,
                "display_name": message.author.display_name,
                "content": message.content,
                "timestamp": message.created_at
            })
        
        if not messages:
            await interaction.followup.send(
                "❌ No valid messages found in this channel.",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            f"📊 Fetched {len(messages)} messages. Analyzing users...",
            ephemeral=True
        )
        
        # Group messages by user
        user_data = {}
        for msg in messages:
            user_id = msg["user_id"]
            if user_id not in user_data:
                user_data[user_id] = {
                    "username": msg["username"],
                    "display_name": msg["display_name"],
                    "messages": []
                }
            user_data[user_id]["messages"].append(msg["content"])
        
        # Filter users who meet the threshold
        qualifying_users = {
            uid: data for uid, data in user_data.items() 
            if len(data["messages"]) >= min_user_messages
        }
        
        if not qualifying_users:
            await interaction.followup.send(
                f"ℹ️ No users found with at least {min_user_messages} messages.\n"
                f"Users found: {len(user_data)}",
                ephemeral=True
            )
            return
        
        skipped_count = 0
        if skip_existing:
            users_to_process = {}
            for user_id, data in qualifying_users.items():
                log = await get_user_log(user_id)
                if log and log[4]:  # log[4] is personality_notes
                    skipped_count += 1
                    continue
                users_to_process[user_id] = data
            qualifying_users = users_to_process
        
        if not qualifying_users:
            await interaction.followup.send(
                f"ℹ️ All {skipped_count} qualifying users already have notes.\n"
                f"Use `skip_existing: False` to regenerate notes for all users.",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            f"🔄 Generating notes for {len(qualifying_users)} users"
            f"{f' ({skipped_count} skipped with existing notes)' if skipped_count > 0 else ''}...\n"
            f"This may take a minute.",
            ephemeral=True
        )
        
        # Generate notes for each qualifying user
        success_count = 0
        failed_count = 0
        queued_count = 0
        
        for user_id, data in qualifying_users.items():
            username = data["username"]
            messages_list = data["messages"]
            
            # Take last 50 messages for analysis
            recent_msgs = messages_list[-50:]
            
            prompt = (
                f"Analyze {username}'s chat messages and summarize their personality traits, "
                "interests, and communication style in 1-2 sentences. "
                "Be specific, neutral, and descriptive.\n\n"
                f"Messages from {username}:\n"
                + "\n".join(recent_msgs)
            )
            
            try:
                
                response = await chat_completion([{"role": "system", "content": prompt}])
                notes = response.strip()
                
                if notes:
                    await update_personality_notes_with_username(user_id, username, notes)
                    success_count += 1
                    logger.info(f"[Bulk Notes] Generated for {username} ({len(messages_list)} messages)")
                else:
                    failed_count += 1
                    
            except Exception as e:
                # Queue for retry if model is unreachable
                logger.warning(f"[Bulk Notes] Failed for {username}, queueing: {e}")
                
                # Create a mock history format for queueing
                mock_history = [
                    {"role": "user", "name": username, "content": msg}
                    for msg in recent_msgs
                ]
                
                await pending_notes_queue.put({
                    "user_id": user_id,
                    "username": username,
                    "history": mock_history,
                    "is_update": False
                })
                queued_count += 1
        
        # Summary embed
        embed = Embed(
            title="✅ Notes Generation Complete",
            description=f"Processed {len(qualifying_users)} users from {len(messages)} messages",
            color=Color.green()
        )
        
        newline = '\n'
        embed.add_field(
            name="Results",
            value=f"**Successful:** {success_count} users\n"
                  f"**Failed:** {failed_count} users\n"
                  f"**Queued for retry:** {queued_count} users"
                  f"{f'{newline}**Skipped (existing notes):** {skipped_count} users' if skipped_count > 0 else ''}",
            inline=False
        )
        
        embed.add_field(
            name="User Breakdown",
            value=f"**Total users found:** {len(user_data)}\n"
                  f"**Qualified (≥{min_user_messages} msgs):** {len(qualifying_users) + skipped_count}",
            inline=False
        )
        
        if success_count > 0:
            embed.add_field(
                name="Next Steps",
                value="Use `/view_notes @user` to see the generated notes.",
                inline=False
            )
        
        if queued_count > 0:
            embed.add_field(
                name="⚠️ Queued Items",
                value=f"{queued_count} notes were queued for retry. They'll be generated automatically when the model is available.",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"[Bulk Notes] Server {server_id} - {success_count} successful, {failed_count} failed, {queued_count} queued, {skipped_count} skipped")
        
    except Exception as e:
        logger.exception(f"[Create Notes Error] {e}")
        await interaction.followup.send(
            f"❌ Error generating notes: {str(e)}",
            ephemeral=True
        )

@admin_only_command(name="delete_user", description="Delete all stored data for a user")
@is_admin()
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

async def check_kobold_text_api() -> dict:
    import aiohttp
    
    start = time.time()
    
    try:
        payload = {
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1,
            "temperature": 0.1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                client.kobold_text_api,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                latency = round((time.time() - start) * 1000, 2)
                
                if resp.status == 200:
                    return {
                        "ok": True,
                        "status": "Online",
                        "latency": latency
                    }
                else:
                    return {
                        "ok": False,
                        "status": f"Error {resp.status}",
                        "latency": latency
                    }
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "status": "Timeout",
            "latency": ">10000"
        }
    except Exception as e:
        logger.error(f"KoboldCPP health check failed: {e}")
        return {
            "ok": False,
            "status": "Unreachable",
            "latency": "N/A"
        }


async def check_web_search_api() -> dict:
    import aiohttp
    
    start = time.time()
    
    try:
        # Simple search query
        payload = {"q": "test"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                client.kobold_web_api,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                latency = round((time.time() - start) * 1000, 2)
                
                if resp.status == 200:
                    return {
                        "ok": True,
                        "status": "Online",
                        "latency": latency
                    }
                else:
                    return {
                        "ok": False,
                        "status": f"Error {resp.status}",
                        "latency": latency
                    }
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "status": "Timeout",
            "latency": ">10000"
        }
    except Exception as e:
        logger.error(f"Web search health check failed: {e}")
        return {
            "ok": False,
            "status": "Unreachable",
            "latency": "N/A"
        }

@admin_only_command(name="health", description="Check bot health and system status")
@is_admin()
async def health_check(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    
    start_time = time.time()
    
    embed = Embed(
        title="🏥 Bot Health Check",
        description=f"Status report for {client.user.name}",
        color=Color.green()
    )
    
    # 1. Discord API Latency
    latency_ms = round(client.latency * 1000, 2)
    latency_status = "🟢" if latency_ms < 200 else "🟡" if latency_ms < 500 else "🔴"
    
    embed.add_field(
        name="📡 Discord Connection",
        value=f"{latency_status} **Latency:** {latency_ms}ms\n"
              f"✅ **Status:** Connected",
        inline=True
    )
    
    # 2. Database Connection Pool
    pool_stats = get_pool_stats()
    if pool_stats:
        pool_health = pool_stats['available_connections'] > 0
        pool_status = "🟢" if pool_health else "🔴"
        
        embed.add_field(
            name="💾 Database Pool",
            value=f"{pool_status} **Active:** {pool_stats['pool_size']}/{pool_stats['max_size']}\n"
                  f"📊 **Available:** {pool_stats['available_connections']}",
            inline=True
        )
    else:
        embed.add_field(
            name="💾 Database Pool",
            value="🔴 **Status:** Not initialized",
            inline=True
        )
    
    # 3. KoboldCPP Text API
    kobold_text_status = await check_kobold_text_api()
    kobold_icon = "🟢" if kobold_text_status["ok"] else "🔴"
    
    embed.add_field(
        name="🤖 Text Generation API",
        value=f"{kobold_icon} **Status:** {kobold_text_status['status']}\n"
              f"⏱️ **Response:** {kobold_text_status['latency']}ms",
        inline=True
    )
    
    # 4. KoboldCPP Web Search API (if configured)
    if client.kobold_web_api:
        web_search_status = await check_web_search_api()
        web_icon = "🟢" if web_search_status["ok"] else "🔴"
        
        embed.add_field(
            name="🌐 Web Search API",
            value=f"{web_icon} **Status:** {web_search_status['status']}\n"
                  f"⏱️ **Response:** {web_search_status['latency']}ms",
            inline=True
        )
    else:
        embed.add_field(
            name="🌐 Web Search API",
            value="⚪ **Status:** Not configured",
            inline=True
        )
    
    # 5. Cache Statistics
    from src.bot import conversation_histories_cache
    from src.moderation.database import user_log_cache, interaction_cache
    
    embed.add_field(
        name="🗂️ Cache Status",
        value=f"💬 **Conversations:** {len(conversation_histories_cache)}\n"
              f"👤 **User Logs:** {len(user_log_cache)}\n"
              f"📈 **Interactions:** {len(interaction_cache)}",
        inline=True
    )
    
    # 6. Background Tasks
    from src.moderation.database import pending_notes_queue
    
    tasks_healthy = True
    tasks_info = []

    # Check pending notes queue
    notes_queue_size = pending_notes_queue.qsize()
    if notes_queue_size > 50:
        tasks_healthy = False
        tasks_info.append(f"⚠️ {notes_queue_size} pending notes")
    
    task_icon = "🟢" if tasks_healthy else "🟡"
    task_status = "All systems operational" if tasks_healthy else "\n".join(tasks_info)
    
    embed.add_field(
        name="⚙️ Background Tasks",
        value=f"{task_icon} **Status:** {task_status}\n"
              f"📝 **Notes Queue:** {notes_queue_size}",
        inline=True
    )
    
    # 7. Personality System
    personality = get_personality()

    embed.add_field(
        name="🎭 Personality System",
        value=f"🟢 **Status:** Loaded\n"
              f"🎤 **Voice:** {personality.name} (central)",
        inline=True
    )
    
    # 8. LLM Provider
    from src.services.llm_service import llm_service

    embed.add_field(
        name="🧠 LLM Provider",
        value=f"🟢 **Provider:** {llm_service.provider}\n"
              f"🎛️ **Model:** {llm_service.model or 'server default'}",
        inline=True
    )
    
    # Calculate total check time
    total_time = round((time.time() - start_time) * 1000, 2)
    
    # Overall health determination
    all_critical_ok = (
        latency_ms < 1000 and
        kobold_text_status["ok"] and
        (pool_stats is not None)
    )
    
    overall_color = Color.green() if all_critical_ok else Color.yellow()
    embed.color = overall_color
    
    embed.set_footer(text=f"Health check completed in {total_time}ms")
    
    # Add timestamp
    embed.timestamp = interaction.created_at
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    logger.info(f"Health check performed by {interaction.user.name}")

@admin_only_command(name="reset_database", description="⚠️ Reset the entire database (requires confirmation)")
@is_owner()
async def reset_db(interaction: Interaction, confirm: str):
    if confirm != "CONFIRM":
        await interaction.response.send_message("⚠️ You must type `CONFIRM` exactly to reset the database.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)

    await reset_database()

    from src.bot import conversation_histories_cache
    from src.moderation.database import interaction_cache

    conversation_histories_cache.clear()
    interaction_cache.clear()

    logger.warning("DATABASE FULLY RESET by admin")

    await interaction.followup.send("⚠️ Database has been fully reset!", ephemeral=True)

@admin_only_command(name="clear_cache", description="Clear all in-memory caches")
@is_admin()
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
@is_admin()
async def invalidate_cache(interaction: Interaction, user: Member):
    user_id = str(user.id)
    invalidate_user_log_cache(user_id)
    
    await interaction.response.send_message(
        f"✅ Invalidated cache for {user.display_name}. Next access will fetch fresh data.",
        ephemeral=True
    )

@admin_only_command(name="pool_stats", description="Show database connection pool statistics")
@is_admin()
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
        name="Notes Queue",
        value=f"**Pending:** {stats.get('pending_notes_queue_size', 0)} updates",
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

# ============================================================================
# MISC COMMANDS
# ============================================================================

@admin_only_command(name="pardon", description="Clear someone's criminal record.")
@is_admin()
async def pardon(interaction: Interaction, user: Member):
    await interaction.response.defer(ephemeral=True)
    
    await clear_criminal_record(str(user.id), str(interaction.guild.id))
    
    embed = Embed(
        title="✅ Record Cleared",
        description=f"{user.display_name} has been pardoned! Their criminal record has been wiped clean.",
        color=Color.green()
    )
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@admin_only_command(name="admin_help", description="List of all admin commands")
@is_admin()
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

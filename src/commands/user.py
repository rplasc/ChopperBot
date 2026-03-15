import discord
from discord import Interaction, Embed, Color, Member, app_commands
from datetime import datetime, timezone
from src.aclient import client
from src.moderation.database import show_server_interactions_user, show_server_interactions_leaderboard, get_user_log
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

_PER_PAGE = 10


async def _build_leaderboard_embed(entries: list, page: int) -> Embed:
    total_pages = max(1, (len(entries) + _PER_PAGE - 1) // _PER_PAGE)
    start = page * _PER_PAGE
    page_entries = entries[start:start + _PER_PAGE]

    embed = Embed(
        title="🏆 Leaderboard",
        description="Top yappers in decreasing order:",
        color=Color.gold()
    )
    rank = start + 1
    for user_id, yaps in page_entries:
        try:
            user = await client.fetch_user(int(user_id))
        except Exception:
            user = None
        if user and user.bot:
            continue
        name = user.name if user else f"User {user_id}"
        label = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**#{rank}**")
        embed.add_field(name="\u200b", value=f"{label} {name}    {yaps}", inline=False)
        rank += 1

    embed.set_footer(text=f"Page {page + 1} / {total_pages}")
    return embed


class LeaderboardView(discord.ui.View):
    def __init__(self, entries: list, page: int = 0):
        super().__init__(timeout=120)
        self.entries = entries
        self.page = page
        self._update_buttons()

    def _update_buttons(self):
        total_pages = max(1, (len(self.entries) + _PER_PAGE - 1) // _PER_PAGE)
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= total_pages - 1

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self._update_buttons()
        embed = await _build_leaderboard_embed(self.entries, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self._update_buttons()
        embed = await _build_leaderboard_embed(self.entries, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

@client.tree.command(name="help", description="List of all public commands")
async def help(interaction: Interaction):
    embed = Embed(title="📖 Help", description="The following commands are available:")

    for cmd in client.tree.walk_commands():
        if getattr(cmd.callback, "is_admin_only", False):
            continue  

        embed.add_field(
            name=f"/{cmd.name}",
            value=cmd.description or cmd.name,
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

async def send_profile(interaction: Interaction, target_user: Member):
    user_id = str(target_user.id)
    log = await get_user_log(user_id)
    
    if not log:
        await interaction.followup.send("No profile found yet.")
        return
    
    username = log[1]
    interactions = log[2]
    last_seen = log[3]
    personality_notes = log[4]

    if last_seen:
        try:
            dt = datetime.fromisoformat(last_seen)
            unix_ts = int(dt.timestamp())
            last_seen_display = f"<t:{unix_ts}:R>"
        except (ValueError, TypeError):
            last_seen_display = "Unknown"
    else:
        last_seen_display = "Never"

    summary = "Not enough data."
    if personality_notes:
        prompt = f"Summarize {username}'s personality using these notes: {personality_notes}"

        try:
            summary = await generate_command_response(
                prompt=prompt,
                server_id=str(interaction.guild.id),
                use_personality=True,
                temperature=0.85,
                max_tokens=200
            )
        except Exception as e:
            print(f"[Profile Error] {e}")
            logger.error(f"[Profile Error] {e}")
            summary = "Summary unavailable"

    embed = Embed(title=f"{username}'s Profile", color=Color.blue())
    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
    embed.add_field(name="Interactions", value=interactions, inline=True)
    embed.add_field(name="Last Seen", value=last_seen_display, inline=True)
    embed.add_field(name="🤖 AI Analysis 🤖", value=summary, inline=False)
    embed.timestamp = datetime.now(timezone.utc)

    await interaction.followup.send(embed=embed)

@client.tree.command(name="yaps", description="Shows number of messages you have sent")
async def yaps(interaction: Interaction):
    server_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    
    yaps = await show_server_interactions_user(server_id, user_id)
    
    await interaction.response.send_message(f'You have sent {yaps} messages so far.')
    
@client.tree.command(name='leaderboard', description='Shows top yappers in the server')
async def yappers(interaction: Interaction):
    await interaction.response.defer()
    server_id = str(interaction.guild.id)
    all_users = await show_server_interactions_leaderboard(server_id, limit=200)

    if not all_users:
        await interaction.followup.send("No activity recorded yet!")
        return

    embed = await _build_leaderboard_embed(all_users, page=0)
    view = LeaderboardView(all_users, page=0)
    await interaction.followup.send(embed=embed, view=view)

@client.tree.command(name="my_profile", description="See your ChopperBot profile")
async def my_profile(interaction: Interaction):
    await interaction.response.defer()
    await send_profile(interaction, interaction.user)


@client.tree.command(name="profile", description="View a user's ChopperBot profile")
async def profile(interaction: Interaction, user: Member):
    await interaction.response.defer()
    await send_profile(interaction, user)

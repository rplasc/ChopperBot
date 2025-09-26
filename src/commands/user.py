from discord import Interaction, Embed, Color, Member
from datetime import datetime, timezone
from src.aclient import client
from src.moderation.database import show_server_interactions_user, show_server_interactions_leaderboard, get_user_log
from utils.kobaldcpp_util import get_kobold_response
from src.personalities import get_system_content

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

    dt = datetime.fromisoformat(last_seen)
    unix_ts = int(dt.timestamp())

    summary = "Not enough data."
    if personality_notes:
        prompt = f"Summarize {username}'s personality using these notes: {personality_notes}"
        messages = [
            {"role": "system", "content": get_system_content()},
            {"role": "user", "content": prompt}
        ]
        try:
            summary = await get_kobold_response(messages)
        except Exception as e:
            print(f"[Profile Error] {e}")
            summary = "Summary unavailable"

    embed = Embed(title=f"{username}'s Profile", color=Color.blue())
    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
    embed.add_field(name="Interactions", value=interactions, inline=True)
    embed.add_field(name="Last Seen", value=f"<t:{unix_ts}:R>", inline=True)
    embed.add_field(name="🤖 AI Analysis 🤖", value=summary, inline=False)
    embed.timestamp = datetime.now(timezone.utc)

    await interaction.followup.send(embed=embed)

@client.tree.command(name="yaps", description="Shows number of messages you have sent")
async def yaps(interaction: Interaction):
    server_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    
    yaps = await show_server_interactions_user(server_id, user_id)
    
    await interaction.response.send_message(f'You have sent {yaps} messages so far.')
    
@client.tree.command(name='leaderboard', description='Shows top 10 yappers in the server')
async def yappers(interaction: Interaction):
    server_id = str(interaction.guild.id)
    top_users = await show_server_interactions_leaderboard(server_id)
    
    embed = Embed(title=f"Top {len(top_users)}", description='In Decreasing Order:', color=Color.gold())
    
    for i,  (user_id, yaps) in enumerate(top_users, start=1):
        user = await client.fetch_user(int(user_id))
        if user is not None and not user.bot:
            if i == 1:
                label = "🥇"
            elif i == 2:
                label = "🥈"
            elif i == 3:
                label = "🥉"
            else:
                label = f"**#{i}**"
            embed.add_field(name="\u200b", value=f'{label} {user.name}    {yaps}', inline=False)

    await interaction.response.send_message(embed=embed)

@client.tree.command(name="my_profile", description="See your ChopperBot profile")
async def my_profile(interaction: Interaction):
    await interaction.response.defer()
    await send_profile(interaction, interaction.user)


@client.tree.command(name="profile", description="View a user's ChopperBot profile")
async def profile(interaction: Interaction, user: Member):
    await interaction.response.defer()
    await send_profile(interaction, user)

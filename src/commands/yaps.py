from discord import Interaction, Embed
from src.aclient import client
from src.moderation.yappers import show_yaps_user, show_yaps_leaderboard
@client.tree.command(name="yaps", description="Shows number of messages you have sent")
async def yaps(interaction: Interaction):
    server_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    
    yaps = await show_yaps_user(server_id, user_id)
    
    await interaction.response.send_message(f'You have sent {yaps} messages so far.')

    
@client.tree.command(name='leaderboard', description='Shows top 10 yappers in the server')
async def yappers(interaction: Interaction):
    server_id = str(interaction.guild.id)
    top_users = await show_yaps_leaderboard(server_id)
    
    embed = Embed(title=f"Top {len(top_users)}", description='In Decreasing Order:')
    
    for i, (user_id, yaps) in enumerate(top_users, start=1):
        user = await client.fetch_user(int(user_id))
        if user is not None and not user.bot:
            embed.add_field(name=f'#{i}', value=f'{user.name} {yaps}', inline=False)
                
    await interaction.response.send_message(embed=embed)
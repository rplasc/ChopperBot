import random
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.personalities import personalities
from utils.kobaldcpp_util import get_kobold_response

@client.tree.command(name="matchmaker", description="Matchmaking for two users")
async def matchmaker(interaction: Interaction, user1: Member, user2: Member):
    await interaction.response.defer()

    # Generate a random compatibility percentage between 0 and 100
    compatibility = random.randint(0, 100)

    # Prompt based on compatibility
    prompt = f"{user1.display_name} and {user2.display_name} have a compatibility percentage of {compatibility}%. Give reasons and explain why they might be compatible in 2-3 sentences."

    if client.is_custom_personality == False:
        messages = [
            {"role": "system", "content": personalities[client.current_personality]}, 
            {"role": "user", "content": prompt}
        ]
    else:
        messages = [
            {"role": "system", "content": client.current_personality}, 
            {"role": "user", "content": prompt}
        ]

    try:
        summary = await get_kobold_response(messages)
    except Exception:
        summary = f"Based on a compatibility percentage of {compatibility}%, {user1.display_name} and {user2.display_name} "
        if compatibility < 50:
            summary += "appear to have a low level of compatibility."
        elif compatibility < 75:
            summary += "may have a medium level of compatibility."
        else:
            summary += "have a high level of compatibility."
    
    embed = Embed(title="💘 Matchmaker 💘", color=Color.pink(), description="Evaluating the compatibility of two users...")
    embed.add_field(name="Users:", value=f"<@{user1.id}> & <@{user2.id}>", inline=True)
    embed.add_field(name="Compatibility Percentage:", value=f"{compatibility}%", inline=True)
    embed.add_field(name="Summary", value=summary, inline=False)

    await interaction.followup.send(embed=embed)
import random
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.personalities import personalities
from utils.kobaldcpp_util import get_kobold_response

@client.tree.command(name="matchmaker", description="Matchmaking for two users")
async def matchmaker(interaction: Interaction, user1: Member, user2: Member):
    await interaction.response.defer()

    if user1.id == user2.id:
        await interaction.followup.send("You can’t match someone with themselves.", ephemeral=True)
        return

    # Generate a random compatibility percentage between 0 and 100
    compatibility = random.randint(0, 100)

    # Prompt based on compatibility
    prompt = f"{user1.display_name} and {user2.display_name} have a compatibility percentage of {compatibility}%. Give reasons and explain why they might be compatible in 2-3 sentences."

    system_content = (
        personalities[client.current_personality]
        if not client.is_custom_personality
        else client.current_personality
    )
    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": prompt}
    ]

    try:
        summary = await get_kobold_response(messages)
    except Exception as e:
        print(f"[Matchmaker Error] {e}")
        if compatibility < 50:
            summary = f"{user1.display_name} and {user2.display_name} don’t seem to vibe well."
        elif compatibility < 75:
            summary = f"{user1.display_name} and {user2.display_name} might get along sometimes, but it could be a rocky match."
        else:
            summary = f"{user1.display_name} and {user2.display_name} are a strong pair — sparks might fly!"

    if compatibility < 50:
        emoji = "💔"
    elif compatibility < 75:
        emoji = "💛"
    else:
        emoji = "❤️"
        
    embed = Embed(title="💘 Matchmaker 💘", color=Color.pink(), description="Evaluating the compatibility of two users...")
    embed.add_field(name="Users:", value=f"<@{user1.id}> & <@{user2.id}>", inline=True)
    embed.add_field(name="Compatibility Percentage:", value=f"{compatibility}% {emoji}", inline=True)
    embed.add_field(name="Summary", value=summary, inline=False)

    await interaction.followup.send(embed=embed)
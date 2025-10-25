import random
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.personalities import get_system_content
from src.utils.kobaldcpp_util import get_kobold_response
from src.utils.relationship_util import DATE_IDEAS
from src.moderation.logging import logger

@client.tree.command(name="compatibility", description="Check the compatibility between two users")
async def compatibility(interaction: Interaction, user1: Member, user2: Member):
    await interaction.response.defer()

    if user1.id == user2.id:
        await interaction.followup.send("You can’t match someone with themselves.", ephemeral=True)
        return

    # Generate a random compatibility percentage between 0 and 100
    compatibility = random.randint(0, 100)

    # Prompt based on compatibility
    prompt = f"{user1.display_name} and {user2.display_name} have a compatibility percentage of {compatibility}%. Give reasons and explain why they might be compatible in 2-3 sentences."

    system_content = get_system_content()
    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": prompt}
    ]

    try:
        summary = await get_kobold_response(messages)
    except Exception as e:
        print(f"[Compatibility Error] {e}")
        logger.error(f"[Compatibility Error] {e}")
        if compatibility < 50:
            summary = f"{user1.display_name} and {user2.display_name} don’t seem to vibe well."
        elif compatibility < 75:
            summary = f"{user1.display_name} and {user2.display_name} might get along sometimes, but it could be a rocky match."
        else:
            summary = f"{user1.display_name} and {user2.display_name} are a strong pair — sparks might fly!"

    # Default embed color
    message_color = Color.pink()

    if compatibility < 50:
        emoji = "💔"
        message_color = Color.red()
    elif compatibility < 75:
        emoji = "💛"
        message_color = Color.green()
    else:
        emoji = "❤️"
        
    embed = Embed(title="💌 Compatibility Check 💌", description="Evaluating the compatibility of two users...", color=message_color)
    embed.add_field(name="Users:", value=f"<@{user1.id}> • <@{user2.id}>", inline=True)
    embed.add_field(name="Compatibility Percentage:", value=f"{compatibility}% {emoji}", inline=True)
    embed.add_field(name="Summary", value=summary, inline=False)

    await interaction.followup.send(embed=embed)


@client.tree.command(name="matchmaker", description="Find a good match for a user!")
async def matchmaker(interaction: Interaction, user: Member):
    await interaction.response.defer()

    # Get all guild members with access to channel except the user and bots
    members = [m for m in interaction.channel.members if not m.bot and m.id != user.id]

    if not members:
        await interaction.followup.send("No available members to match with.", ephemeral=True)
        return

    # Randomly pick a match
    match = random.choice(members)

    # Rating out of 5 (minimum 3 stars)
    rating = random.randint(3, 5)
    stars = "⭐" * rating + "☆" * (5 - rating)

    # Random first date ideas
    first_date = random.choice(DATE_IDEAS)

    # Prompt for explanation
    prompt = f"{user.display_name} has been matched with {match.display_name}! Their match rating is {rating}/5. Give reasons and explain why they might (or might not) be compatible in 2-3 sentences."

    system_content = get_system_content()
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]

    try:
        summary = await get_kobold_response(messages)
    except Exception as e:
        print(f"[Matchmaker Error] {e}")
        logger.error(f"[Matchmaker Error] {e}")
        if rating == 3:
            summary = f"{user.display_name} and {match.display_name} could get along, but it might take effort."
        elif rating == 4:
            summary = f"{user.display_name} and {match.display_name} look like a promising match!"
        else:
            summary = f"{user.display_name} and {match.display_name} are a perfect match — sparks will fly!"

    # Build embed
    embed = Embed(title="💕 Matchmaker 💕", description="A new match has been made!", color=Color.pink())
    embed.add_field(name="Users:", value=f"<@{user.id}> 💞 <@{match.id}>", inline=True)
    embed.add_field(name="Match Rating:", value=f"{stars} ({rating}/5)", inline=True)
    embed.add_field(name="Summary", value=summary, inline=False)
    embed.add_field(name="First Date Idea", value=first_date, inline=False)

    await interaction.followup.send(embed=embed)
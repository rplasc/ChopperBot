import discord
import random
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.utils.response_generator import generate_command_response
from src.utils.relationship_util import DATE_IDEAS
from src.moderation.database import get_user_log
from src.moderation.logging import logger

# ============================================================================
# VIEWS
# ============================================================================

class CompatibilityView(discord.ui.View):
    def __init__(self, user1_id: int, user2_id: int, user1_name: str, user2_name: str,
                 notes1: str, notes2: str, server_id: str):
        super().__init__(timeout=120)
        self.user1_id = user1_id
        self.user2_id = user2_id
        self.user1_name = user1_name
        self.user2_name = user2_name
        self.notes1 = notes1
        self.notes2 = notes2
        self.server_id = server_id

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Re-evaluate", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def re_evaluate(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_compat = random.randint(0, 100)

        if self.notes1 and self.notes2:
            prompt = (
                f"Analyze the compatibility between {self.user1_name} and {self.user2_name}.\n\n"
                f"{self.user1_name}'s personality: {self.notes1}\n"
                f"{self.user2_name}'s personality: {self.notes2}\n\n"
                f"Their compatibility percentage is {new_compat}%. Based on their personalities, "
                "explain in 2-3 sentences why this percentage makes sense. "
                "Consider their communication styles, interests, and personality traits."
            )
        else:
            prompt = (
                f"{self.user1_name} and {self.user2_name} have a compatibility percentage of "
                f"{new_compat}%. Give reasons and explain why they might be compatible in 2-3 sentences."
            )

        try:
            summary = await generate_command_response(
                prompt=prompt, server_id=self.server_id,
                use_personality=True, temperature=0.75, max_tokens=350
            )
        except Exception as e:
            logger.error(f"[Compatibility Re-evaluate Error] {e}")
            summary = f"{self.user1_name} and {self.user2_name} — the stars have re-aligned."

        emoji = "💔" if new_compat < 50 else ("💛" if new_compat < 75 else "❤️")
        color = Color.red() if new_compat < 50 else (Color.green() if new_compat < 75 else Color.pink())

        embed = Embed(title="💌 Compatibility Check 💌", description="Re-evaluating...", color=color)
        embed.add_field(name="Users:", value=f"<@{self.user1_id}> • <@{self.user2_id}>", inline=True)
        embed.add_field(name="Compatibility Percentage:", value=f"{new_compat}% {emoji}", inline=True)
        embed.add_field(name="Summary", value=summary, inline=False)
        if self.notes1 and self.notes2:
            embed.set_footer(text="✨ Analysis based on personality data")
        await interaction.edit_original_response(embed=embed, view=self)


class MatchmakerView(discord.ui.View):
    def __init__(self, user_id: int, user_name: str, user_notes: str,
                 previous_match_id: int, server_id: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.user_name = user_name
        self.user_notes = user_notes
        self.previous_match_id = previous_match_id
        self.server_id = server_id

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Rematch", style=discord.ButtonStyle.primary, emoji="💘")
    async def rematch(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        members = [
            m for m in interaction.channel.members
            if not m.bot and m.id != self.user_id and m.id != self.previous_match_id
        ]
        if not members:
            members = [
                m for m in interaction.channel.members
                if not m.bot and m.id != self.user_id
            ]

        if not members:
            await interaction.edit_original_response(
                content="No available members to rematch with!", embed=None, view=None
            )
            return

        new_match = random.choice(members)
        self.previous_match_id = new_match.id

        match_log = await get_user_log(str(new_match.id))
        match_notes = match_log[4] if match_log and match_log[4] else None

        rating = random.randint(3, 5)
        stars = "⭐" * rating + "☆" * (5 - rating)
        first_date = random.choice(DATE_IDEAS)

        if self.user_notes and match_notes:
            prompt = (
                f"{self.user_name} has been matched with {new_match.display_name}! "
                f"Their match rating is {rating}/5.\n\n"
                f"{self.user_name}'s personality: {self.user_notes}\n"
                f"{new_match.display_name}'s personality: {match_notes}\n\n"
                "Based on their personalities, explain in 2-3 sentences why they might "
                "(or might not) be compatible. Consider their communication styles and interests."
            )
        else:
            prompt = (
                f"{self.user_name} has been matched with {new_match.display_name}! "
                f"Their match rating is {rating}/5. Give reasons and explain why they might "
                "(or might not) be compatible in 2-3 sentences."
            )

        try:
            summary = await generate_command_response(
                prompt=prompt, server_id=self.server_id,
                use_personality=True, temperature=0.9, max_tokens=250
            )
        except Exception as e:
            logger.error(f"[Rematch Error] {e}")
            summary = f"{self.user_name} and {new_match.display_name} — a fresh start!"

        embed = Embed(title="💕 Matchmaker 💕", description="A new match has been made!", color=Color.pink())
        embed.add_field(name="Users:", value=f"<@{self.user_id}> 💞 <@{new_match.id}>", inline=True)
        embed.add_field(name="Match Rating:", value=f"{stars} ({rating}/5)", inline=True)
        embed.add_field(name="Summary", value=summary, inline=False)
        embed.add_field(name="First Date Idea", value=first_date, inline=False)
        if self.user_notes and match_notes:
            embed.set_footer(text="✨ Analysis based on personality data")
        await interaction.edit_original_response(embed=embed, view=self)


# ============================================================================
# COMMANDS
# ============================================================================

@client.tree.command(name="compatibility", description="Check the compatibility between two users")
async def compatibility(interaction: Interaction, user1: Member, user2: Member):
    await interaction.response.defer()

    if user1.id == user2.id:
        await interaction.followup.send("You can’t match someone with themselves.", ephemeral=True)
        return
    
    # Get personality notes for both users
    log1 = await get_user_log(str(user1.id))
    log2 = await get_user_log(str(user2.id))
    
    notes1 = log1[4] if log1 and log1[4] else None
    notes2 = log2[4] if log2 and log2[4] else None

    # Generate a random compatibility percentage between 0 and 100
    compatibility = random.randint(0, 100)

    # Enhanced prompt if both users have notes
    if notes1 and notes2:
        prompt = (
            f"Analyze the compatibility between {user1.display_name} and {user2.display_name}.\n\n"
            f"{user1.display_name}'s personality: {notes1}\n"
            f"{user2.display_name}'s personality: {notes2}\n\n"
            f"Their compatibility percentage is {compatibility}%. Based on their personalities, "
            "explain in 2-3 sentences why this percentage makes sense. "
            "Consider their communication styles, interests, and personality traits."
        )
    else:
        prompt = f"{user1.display_name} and {user2.display_name} have a compatibility percentage of {compatibility}%. Give reasons and explain why they might be compatible in 2-3 sentences."

    try:
        summary = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=True,
            temperature=0.75,
            max_tokens=350
        )
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

    if notes1 and notes2:
        embed.set_footer(text="✨ Analysis based on personality data")

    view = CompatibilityView(user1.id, user2.id, user1.display_name, user2.display_name,
                             notes1, notes2, str(interaction.guild.id))
    await interaction.followup.send(embed=embed, view=view)

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

    # Get personality notes for both users
    user_log = await get_user_log(str(user.id))
    match_log = await get_user_log(str(match.id))

    user_notes = user_log[4] if user_log and user_log[4] else None
    match_notes = match_log[4] if match_log and match_log[4] else None

    # Rating out of 5 (minimum 3 stars)
    rating = random.randint(3, 5)
    stars = "⭐" * rating + "☆" * (5 - rating)

    # Random first date ideas
    first_date = random.choice(DATE_IDEAS)

    # Enhanced prompt if personality data exists
    if user_notes and match_notes:
        prompt = (
            f"{user.display_name} has been matched with {match.display_name}! "
            f"Their match rating is {rating}/5.\n\n"
            f"{user.display_name}'s personality: {user_notes}\n"
            f"{match.display_name}'s personality: {match_notes}\n\n"
            "Based on their personalities, explain in 2-3 sentences why they might "
            "(or might not) be compatible. Consider their communication styles and interests."
        )
    else:
        # Prompt for explanation
        prompt = f"{user.display_name} has been matched with {match.display_name}! Their match rating is {rating}/5. Give reasons and explain why they might (or might not) be compatible in 2-3 sentences."

    try:
        summary = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=True,
            temperature=0.9,
            max_tokens=250
        )
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

    if user_notes and match_notes:
        embed.set_footer(text="✨ Analysis based on personality data")

    view = MatchmakerView(user.id, user.display_name, user_notes,
                          match.id, str(interaction.guild.id))
    await interaction.followup.send(embed=embed, view=view)

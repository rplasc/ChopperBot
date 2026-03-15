import discord
from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.moderation.database import get_user_log, show_server_interactions_leaderboard
from src.utils.response_generator import generate_command_response, generate_roleplay_response
from src.moderation.logging import logger

# ============================================================================
# VIEWS
# ============================================================================

class SpiritAnimalView(discord.ui.View):
    def __init__(self, username: str, personality_notes: str, initial_result: str,
                 server_id: str, avatar_url: str):
        super().__init__(timeout=120)
        self.username = username
        self.personality_notes = personality_notes
        self.initial_result = initial_result
        self.server_id = server_id
        self.avatar_url = avatar_url

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Why This Animal?", style=discord.ButtonStyle.primary, emoji="🐾")
    async def why_this_animal(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        button.disabled = True
        prompt = (
            f"You previously assigned {self.username} a spirit animal with this reading:\n"
            f"{self.initial_result}\n\n"
            f"Their personality notes: {self.personality_notes}\n\n"
            "Now give a deeper, more specific explanation. Draw precise parallels between "
            "their actual personality traits and the animal's known behaviors, instincts, and symbolism. "
            "Be insightful and specific — not generic."
        )
        try:
            detail = await generate_command_response(
                prompt=prompt, server_id=self.server_id, use_personality=True,
                temperature=0.9, max_tokens=250
            )
        except Exception as e:
            logger.error(f"[Spirit Animal Detail Error] {e}")
            detail = "The spirit realm isn't talking right now."

        embed = Embed(
            title=f"🐺 {self.username}'s Spirit Animal — Deep Dive 🐺",
            description=self.initial_result,
            color=Color.teal()
        )
        embed.add_field(name="🐾 Why This Animal?", value=detail, inline=False)
        if self.avatar_url:
            embed.set_thumbnail(url=self.avatar_url)
        await interaction.edit_original_response(embed=embed, view=self)


class TherapyView(discord.ui.View):
    def __init__(self, username: str, problem: str, context: str,
                 initial_advice: str, server_id: str):
        super().__init__(timeout=120)
        self.username = username
        self.problem = problem
        self.context = context
        self.initial_advice = initial_advice
        self.server_id = server_id

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Continue Session", style=discord.ButtonStyle.primary, emoji="🛋️")
    async def continue_session(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        button.disabled = True
        character = "You are Dr. Chopperbot, a wildly unqualified but confident therapist."
        scenario = (
            f"You gave {self.username} this initial therapy session:\n{self.initial_advice}\n\n"
            f"They are still struggling with: '{self.problem}'\n"
            f"{self.context}\n\n"
            "Continue the session. Ask them a probing follow-up question, then give deeper "
            "(increasingly absurd) analysis. Include an upgraded prescription."
        )
        try:
            followup = await generate_roleplay_response(
                character_description=character,
                scenario=scenario,
                temperature=1.0,
                max_tokens=300
            )
        except Exception as e:
            logger.error(f"[Therapy Continue Error] {e}")
            followup = "Dr. ChopperBot has stepped out for a coffee break."

        embed = Embed(
            title="🛋️ Dr. ChopperBot's Therapy — Session 2 🛋️",
            description=(
                f"**Patient:** {self.username}\n**Issue:** {self.problem}\n\n"
                f"**Continued Analysis:**\n{followup}"
            ),
            color=Color.purple()
        )
        embed.set_footer(text="⚠️ Still not actual medical advice.")
        await interaction.edit_original_response(embed=embed, view=self)

# ============================================================================
# COMMANDS
# ============================================================================

@client.tree.command(name="spirit_animal", description="Find out what your spirit animal is")
async def spirit_animal(interaction: Interaction, user: Member = None):
    await interaction.response.defer()

    target_user = user if user else interaction.user
    user_id = str(target_user.id)
    log = await get_user_log(user_id)

    if not log or not log[4]:
        await interaction.followup.send(
            f"Need more data to find {target_user.display_name}'s spirit animal! 🦊"
        )
        return

    personality_notes = log[4]
    username = log[1]
    server_id = str(interaction.guild.id) if interaction.guild else None
    avatar_url = target_user.avatar.url if target_user.avatar else target_user.default_avatar.url

    prompt = (
        f"Based on these personality notes: {personality_notes}\n\n"
        f"Assign {username} a spirit animal that matches their personality. "
        "Name the animal clearly, then explain why in 2-3 sentences, drawing parallels between "
        "their traits and the animal's characteristics. Be creative and insightful!"
    )

    try:
        result = await generate_command_response(
            prompt=prompt, server_id=server_id, use_personality=True,
            temperature=0.9, max_tokens=200
        )
        embed = Embed(
            title=f"🐺 {username}'s Spirit Animal 🐺",
            description=result,
            color=Color.teal()
        )
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text="Click below to learn why this animal was chosen.")
        view = SpiritAnimalView(username, personality_notes, result, server_id, avatar_url)
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        logger.exception(f"[Spirit Animal Error] {e}")
        await interaction.followup.send("The spirit realm is unreachable! 🌙")


@client.tree.command(name="server_vibe", description="Analyze the overall vibe of the server")
async def server_vibe(interaction: Interaction):
    await interaction.response.defer()

    server_id = str(interaction.guild.id)
    top_users = await show_server_interactions_leaderboard(server_id)

    if not top_users:
        await interaction.followup.send("Not enough server activity yet!")
        return

    user_summaries = []
    for user_id, count in top_users[:5]:
        log = await get_user_log(str(user_id))
        if log and log[4]:
            user_summaries.append(f"- {log[1]}: {log[4]}")

    if len(user_summaries) < 2:
        await interaction.followup.send("Need more personality data from active members!")
        return

    prompt = (
        f"Based on the personalities of the most active members in {interaction.guild.name}:\n\n"
        + "\n".join(user_summaries) + "\n\n"
        "Describe the overall 'vibe' or culture of this server in 3-4 sentences. "
        "What kind of community is this? What energy do people bring?"
    )

    try:
        vibe_text = await generate_command_response(
            prompt=prompt, server_id=server_id, use_personality=True,
            temperature=0.85, max_tokens=250
        )
        embed = Embed(
            title=f"🌟 {interaction.guild.name} Server Vibe 🌟",
            description=vibe_text,
            color=Color.blue()
        )
        embed.set_footer(text=f"Based on top {len(user_summaries)} contributors")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.exception(f"[Server Vibe Error] {e}")
        await interaction.followup.send("Can't analyze server vibe right now!")


@client.tree.command(name="personality_twin", description="Find your personality twin in the server")
async def personality_twin(interaction: Interaction):
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    user_log = await get_user_log(user_id)

    if not user_log or not user_log[4]:
        await interaction.followup.send(
            "I don't have enough data on you yet! Chat more and try again. 👯"
        )
        return

    server_id = str(interaction.guild.id)
    top_users = await show_server_interactions_leaderboard(server_id)

    candidates = []
    for other_user_id, count in top_users:
        if str(other_user_id) == user_id:
            continue
        log = await get_user_log(str(other_user_id))
        if log and log[4]:
            candidates.append(f"{log[1]}: {log[4]}")

    if len(candidates) < 2:
        await interaction.followup.send("Not enough active users with personality data!")
        return

    prompt = (
        f"The user {user_log[1]} has this personality: {user_log[4]}\n\n"
        "Find their personality twin from these server members:\n"
        + "\n".join(candidates[:10]) + "\n\n"
        "Who is most similar to them? Explain in 2-3 sentences what traits they share."
    )

    try:
        result = await generate_command_response(
            prompt=prompt, server_id=server_id, use_personality=False,
            temperature=0.8, max_tokens=200
        )
        embed = Embed(
            title=f"👯 {interaction.user.display_name}'s Personality Twin",
            description=result,
            color=Color.purple()
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.exception(f"[Personality Twin Error] {e}")
        await interaction.followup.send("Twin finder is offline! 👯‍♀️")


@client.tree.command(name="trait_finder", description="Find the most likely person to have a trait")
async def trait_finder(interaction: Interaction, trait: str):
    await interaction.response.defer()

    server_id = str(interaction.guild.id)
    top_users = await show_server_interactions_leaderboard(server_id)

    candidates = []
    for user_id, count in top_users:
        log = await get_user_log(str(user_id))
        if log and log[4]:
            candidates.append(f"{log[1]}: {log[4]}")

    if len(candidates) < 2:
        await interaction.followup.send("Not enough active users with personality data!")
        return

    prompt = (
        "From these server members:\n"
        + "\n".join(candidates[:10]) + "\n\n"
        f"Determine who is likely to have this trait: {trait}. Explain your reasoning in 2-3 sentences."
    )

    try:
        analysis = await generate_command_response(
            prompt=prompt, server_id=server_id, use_personality=True,
            temperature=0.8, max_tokens=150
        )
        embed = Embed(
            title="🔍 Personality Trait Search",
            description=f"**Trait:** {trait}",
            color=Color.dark_blue()
        )
        embed.add_field(name="Analysis", value=analysis)
        embed.set_footer(text="Based on server interactions.")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.exception(f"[Trait Finder Error] {e}")
        await interaction.followup.send("Crystal ball is foggy! 🔮")


@client.tree.command(name="therapy", description="Get a therapy session from Dr. Bot")
async def therapy(interaction: Interaction, problem: str):
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    log = await get_user_log(user_id)
    username = interaction.user.display_name
    server_id = str(interaction.guild.id) if interaction.guild else None

    context = ""
    if log and log[4]:
        context = f"\nPatient's background: {log[4]}"

    character = "You are Dr. Chopperbot, a wildly unqualified but confident therapist."
    scenario = (
        f"Your patient {username} says: '{problem}'\n"
        f"{context}\n\n"
        "Give them absurd but oddly insightful 'therapy advice' in 3-4 sentences. "
        "Be funny, dramatic, and completely over-the-top. Include a ridiculous prescription at the end."
    )

    try:
        advice = await generate_roleplay_response(
            character_description=character,
            scenario=scenario,
            temperature=1.0,
            max_tokens=300
        )
        embed = Embed(
            title="🛋️ Dr. ChopperBot's Therapy Session 🛋️",
            description=(
                f"**Patient:** {username}\n**Issue:** {problem}\n\n"
                f"**Dr. ChopperBot's Analysis:**\n{advice}"
            ),
            color=Color.purple()
        )
        embed.set_footer(text="⚠️ Not actual medical advice. Consult a real therapist.")
        view = TherapyView(username, problem, context, advice, server_id)
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        logger.exception(f"[Therapy Error] {e}")
        await interaction.followup.send("Dr. ChopperBot is on vacation! 🏖️")


@client.tree.command(name="expose", description="Generate a dramatic exposé about a user")
async def expose(interaction: Interaction, target: Member):
    await interaction.response.defer()

    log = await get_user_log(str(target.id))
    dirt = ""
    if log and log[4]:
        dirt = f"\nInside sources reveal: {log[4]}"

    prompt = (
        f"Write a tabloid-style exposé about {target.display_name}!\n"
        f"{dirt}\n\n"
        "Write a dramatic article headline and 3-4 sentences of 'shocking revelations' "
        "that are completely ridiculous. Use phrases like 'sources say' and 'you won't believe'. "
        "Make it funny and absurd, not actually harmful."
    )

    try:
        expose_text = await generate_command_response(
            prompt=prompt, server_id=str(interaction.guild.id),
            use_personality=False, temperature=1.0, max_tokens=350
        )
        embed = Embed(title="📰 BREAKING NEWS 📰", description=expose_text, color=Color.gold())
        embed.set_author(name="The ChopperNews - Investigative Journalism")
        embed.add_field(name="Subject", value=target.display_name, inline=True)
        embed.add_field(name="Reliability", value="⭐ (Questionable)", inline=True)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.exception(f"[Expose Error] {e}")
        await interaction.followup.send("The lawyers shut us down! ⚖️")


@client.tree.command(name="eulogy", description="Write a dramatic eulogy for someone")
async def eulogy(interaction: Interaction, departed: Member, cause_of_death: str):
    await interaction.response.defer()

    log = await get_user_log(str(departed.id))
    life_story = ""
    if log and log[4]:
        life_story = f"\nTheir legacy: {log[4]}"

    prompt = (
        f"Write a dramatic and absurd eulogy for {departed.display_name} who tragically died from: {cause_of_death}\n"
        f"{life_story}\n\n"
        "Make it overly dramatic and funny (3-4 sentences). Include 'they will be missed' and "
        "ridiculous accomplishments they 'achieved' in life."
    )

    try:
        eulogy_text = await generate_command_response(
            prompt=prompt, server_id=interaction.guild.id,
            use_personality=True, temperature=0.95, max_tokens=350
        )
        embed = Embed(title="⚰️ IN LOVING MEMORY ⚰️", description=eulogy_text, color=Color.dark_grey())
        embed.add_field(name="Departed", value=departed.display_name, inline=True)
        embed.add_field(name="Cause of Death", value=cause_of_death, inline=True)
        embed.set_thumbnail(url=departed.avatar.url if departed.avatar else departed.default_avatar.url)
        embed.set_footer(text=f"Funeral services conducted by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.exception(f"[Eulogy Error] {e}")
        await interaction.followup.send("Too sad to continue... 😭")

import random
from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.moderation.database import get_user_log, show_server_interactions_leaderboard
from src.utils.response_generator import generate_command_response, generate_roleplay_response
from src.moderation.logging import logger

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
    
    prompt = (
        f"Based on these personality notes: {personality_notes}\n\n"
        f"Assign {username} a spirit animal that matches their personality. "
        "Explain why in 2-3 sentences, drawing parallels between their traits and the animal's characteristics. "
        "Be creative and insightful!"
    )
    
    try:
        result = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=True,
            temperature=0.9,
            max_tokens=200
        )
        
        embed = Embed(
            title=f"🐺 {username}'s Spirit Animal 🐺",
            description=result,
            color=Color.teal()
        )
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
        
        await interaction.followup.send(embed=embed)
        
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
    
    # Get notes for top 5 users
    user_summaries = []
    for user_id, count in top_users[:5]:
        log = await get_user_log(str(user_id))
        if log and log[4]:
            user_summaries.append(f"- {log[1]}: {log[4]}")
    
    if len(user_summaries) < 2:
        await interaction.followup.send(
            "Need more personality data from active members!"
        )
        return
    
    prompt = (
        f"Based on the personalities of the most active members in {interaction.guild.name}:\n\n"
        + "\n".join(user_summaries) + "\n\n"
        "Describe the overall 'vibe' or culture of this server in 3-4 sentences. "
        "What kind of community is this? What energy do people bring?"
    )
    
    try:
        vibe_text = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=True,
            temperature=0.85,
            max_tokens=250
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
    
    # Get notes for other users
    candidates = []
    for other_user_id, count in top_users:
        if str(other_user_id) == user_id:
            continue
        
        log = await get_user_log(str(other_user_id))
        if log and log[4]:
            candidates.append(f"{log[1]}: {log[4]}")
    
    if len(candidates) < 2:
        await interaction.followup.send(
            "Not enough active users with personality data!"
        )
        return
    
    prompt = (
        f"The user {user_log[1]} has this personality: {user_log[4]}\n\n"
        "Find their personality twin from these server members:\n"
        + "\n".join(candidates[:10]) + "\n\n"
        "Who is most similar to them? Explain in 2-3 sentences what traits they share."
    )
    
    try:
        result = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=False,
            temperature=0.8,
            max_tokens=200
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
    print(top_users)
    
    # Get notes for users
    candidates = []
    for user_id, count in top_users:
        
        log = await get_user_log(str(user_id))
        if log and log[4]:
            candidates.append(f"{log[1]}: {log[4]}")
        print(candidates)
    
    if len(candidates) < 2:
        await interaction.followup.send(
            "Not enough active users with personality data!"
        )
        return
    
    prompt = (
        "From these server members:\n"
        + "\n".join(candidates[:10]) + "\n\n"
        f"Determine who is likely to have this trait: {trait}. Explain your reasoning in 2-3 sentences."
    )
    
    try:
        analysis = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=True,
            temperature=0.8,
            max_tokens=150
        )
        
        embed = Embed(
            title=f"🔍 Personality Trait Search",
            description=f"**Trait:** {trait}",
            color=Color.dark_blue()
        )
        embed.add_field(name="Analysis", value=analysis)
        embed.set_footer(text="This is based off server interactions.")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"[Predict Response Error] {e}")
        await interaction.followup.send("Crystal ball is foggy! 🔮")

@client.tree.command(name="therapy", description="Get a therapy session from Dr. Bot")
async def therapy(interaction: Interaction, problem: str):
    await interaction.response.defer()
    
    user_id = str(interaction.user.id)
    log = await get_user_log(user_id)
    
    context = ""
    if log and log[4]:
        context = f"\nPatient's background: {log[4]}"

    character = "You are Dr. Chopperbot, a wildly unqualified but confident therapist."
    
    scenario = (
        f"Your patient {interaction.user.display_name} says: '{problem}'\n"
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
            description=f"**Patient:** {interaction.user.display_name}\n**Issue:** {problem}\n\n**Dr. ChopperBot's Analysis:**\n{advice}",
            color=Color.purple()
        )
        embed.set_footer(text="⚠️ Not actual medical advice. Consult a real therapist.")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"[Therapy Error] {e}")
        await interaction.followup.send("Dr. ChopperBot is on vacation! 🏖️")

@client.tree.command(name="arrest", description="Arrest someone for their crimes")
async def arrest(interaction: Interaction, criminal: Member, crime: str):
    await interaction.response.defer()
    
    if criminal.bot:
        await interaction.followup.send("Bots are above the law! 🤖⚖️")
        return
    
    log = await get_user_log(str(criminal.id))
    personality = ""
    if log and log[4]:
        personality = f"\nKnown behavior: {log[4]}"
    
    # Random sentence
    years = random.randint(1, 100)
    
    prompt = (
        f"Officer {interaction.user.display_name} has arrested {criminal.display_name} "
        f"for the crime of: {crime}\n"
        f"{personality}\n\n"
        f"Write a dramatic police report (3-4 sentences) explaining why they're guilty. "
        f"Be funny and absurd. They've been sentenced to {years} years."
    )
    
    try:
        report = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=False,
            temperature=0.95,
            max_tokens=250
        )
        
        embed = Embed(
            title="🚨 ARREST WARRANT 🚨",
            description=report,
            color=Color.red()
        )
        embed.add_field(name="Criminal", value=criminal.display_name, inline=True)
        embed.add_field(name="Crime", value=crime, inline=True)
        embed.add_field(name="Sentence", value=f"{years} years in jail", inline=True)
        embed.set_thumbnail(url=criminal.avatar.url if criminal.avatar else criminal.default_avatar.url)
        embed.set_footer(text=f"Arrested by Officer {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"[Arrest Error] {e}")
        await interaction.followup.send("The police department is defunded! 👮")

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
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=False,
            temperature=1.0,
            max_tokens=350
        )
        
        embed = Embed(
            title="📰 BREAKING NEWS 📰",
            description=expose_text,
            color=Color.gold()
        )
        embed.set_author(name="The ChopperNews - Investigative Journalism")
        embed.add_field(name="Subject", value=target.display_name, inline=True)
        embed.add_field(name="Reliability", value="⭐ (Questionable)", inline=True)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"[Expose Error] {e}")
        await interaction.followup.send("The lawyers shut us down! ⚖️")

from discord import Interaction, Embed, Color, Member
from src.aclient import client
from src.moderation.database import get_user_log, show_server_interactions_leaderboard
from src.utils.response_generator import generate_command_response
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
            server_id=interaction.guild.id,
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
            server_id=interaction.guild.id,
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
        f"You are: {user_log[4]}\n\n"
        "Find your personality twin from these server members:\n"
        + "\n".join(candidates[:10]) + "\n\n"
        "Who is most similar to you? Explain in 2-3 sentences what traits you share."
    )
    
    try:
        result = await generate_command_response(
            prompt=prompt,
            server_id=interaction.guild.id,
            use_personality=True,
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

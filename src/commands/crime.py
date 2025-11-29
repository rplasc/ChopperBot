import random
import datetime
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.moderation.database import (
    get_user_log,
    add_crime_record, 
    get_criminal_record,
    get_crime_statistics
)
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

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

    await add_crime_record(
        user_id=str(criminal.id),
        server_id=str(interaction.guild.id),
        crime=crime,
        arrested_by=interaction.user.display_name,
        jail_time=years
    )
    
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
    except Exception as e:
        logger.exception(f"[Arrest Error] {e}")
        report = f"{criminal.display_name} has been arrested for the crime of {crime} and was found guilty."
        
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

@client.tree.command(name="lawsuit", description="Take someone to court")
async def lawsuit(interaction: Interaction, defendent: Member, complaint: str, amount: int = 0):
    await interaction.response.defer()
    
    if defendent.bot:
        await interaction.followup.send("Bots are above the law! 🤖⚖️", ephemeral=True)
        return
    
    if defendent == interaction.user:
        await interaction.followup.send("You can't sue yourself!", ephemeral=True)
        return
    
    log = await get_user_log(str(defendent.id))
    personality = ""
    if log and log[4]:
        personality = f"\nKnown behavior: {log[4]}"

    # Trial Outcome
    verdict = random.choice(["guilty", "not guilty"])

    if verdict == "guilty":
        if amount > 0:
            multiplier = random.uniform(0.1,5)
            amount = int(amount * multiplier)
            await add_crime_record(
                user_id=str(defendent.id),
                server_id=str(interaction.guild.id),
                crime=complaint,
                arrested_by="N/A",
                jail_time=0
            )
        else:
            amount = random.randint(1,1000)
    else:
        amount = 0
    
    prompt = (
        f"{interaction.user.display_name} has filed a lawsuit against {defendent.display_name} "
        f"with this compaint: {complaint}\n"
        f"{personality}\n\n"
        f"As Judge ChopperBot, write a dramatic judge's statement (3-4 sentences) explaining why they're {verdict}. "
        f"Be funny and absurd. The plantiff is to be awarded to ${amount}."
    )
    
    try:
        statement = await generate_command_response(
            prompt=prompt,
            server_id=str(interaction.guild.id),
            use_personality=False,
            temperature=0.95,
            max_tokens=250
        )

    except Exception as e:
        logger.exception(f"[Lawsuit Error] {e}")
        statement = f"The court finds the defendant, {defendent.display_name}, {verdict} of {complaint}. The plantiff is to be awarded ${amount}."

    embed = Embed(
        title="⚖️ Trial ⚖️",
        description=statement,
        color=Color.dark_orange()
    )

    embed.add_field(name="Defendent", value=defendent.display_name, inline=True)
    embed.add_field(name="Complaint", value=complaint, inline=True)
    embed.add_field(name="Verdict", value=verdict, inline=True)
    embed.add_field(name="Amount Rewarded", value=f"${amount}", inline=True)
    embed.set_thumbnail(url=defendent.avatar.url if defendent.avatar else defendent.default_avatar.url)
    embed.set_footer(text=f"Filed by {interaction.user.display_name}")
    
    await interaction.followup.send(embed=embed)

@client.tree.command(name="criminal_record", description="View someone's criminal record")
async def record(interaction: Interaction, user: Member = None):
    await interaction.response.defer()
    
    target = user if user else interaction.user
    
    record = await get_criminal_record(
        str(target.id), 
        str(interaction.guild.id),
        limit=5
    )
    
    if record["total_crimes"] == 0:
        embed = Embed(
            title="📋 Criminal Record 📋",
            description=f"{target.display_name} has a clean record! 😇",
            color=Color.green()
        )
        embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
        await interaction.followup.send(embed=embed)
        return
    
    # Build crimes list
    crimes_list = []
    for i, (crime, officer, jail_time, timestamp) in enumerate(record["crimes"], 1):
        try:
            dt = datetime.datetime.fromisoformat(timestamp)
            time_str = f"<t:{int(dt.timestamp())}:R>"
        except:
            time_str = "Unknown date"
        
        crimes_list.append(
            f"**{i}.** {crime}\n"
            f"   ├ Sentence: {jail_time} years\n"
            f"   ├ Officer: {officer}\n"
            f"   └ {time_str}"
        )
    
    embed = Embed(
        title="🚔 Criminal Record 🚔",
        description=f"**Subject:** {target.display_name}\n**Status:** ⚠️ Repeat Offender",
        color=Color.red()
    )
    
    embed.add_field(
        name="📊 Statistics",
        value=f"**Total Crimes:** {record['total_crimes']}\n"
              f"**Total Jail Time:** {record['total_jail_time']:,} years\n"
              f"**Longest Sentence:** {record['longest_sentence']} years",
        inline=False
    )
    
    embed.add_field(
        name="🔍 Recent Offenses",
        value="\n\n".join(crimes_list),
        inline=False
    )
    
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    embed.set_footer(text=f"Showing last {len(record['crimes'])} crime(s)")
    
    await interaction.followup.send(embed=embed)

@client.tree.command(name="crime_stats", description="View server crime statistics")
async def crime_stats(interaction: Interaction):
    await interaction.response.defer()
    
    stats = await get_crime_statistics(str(interaction.guild.id))
    
    if stats["total_arrests"] == 0:
        await interaction.followup.send("No crimes recorded yet! This is a law-abiding server. 👮")
        return
    
    embed = Embed(
        title="📊 Crime Statistics 📊",
        description=f"Crime data for {interaction.guild.name}",
        color=Color.blue()
    )
    
    embed.add_field(
        name="🚨 Overall Statistics",
        value=f"**Total Arrests:** {stats['total_arrests']}\n"
              f"**Unique Criminals:** {stats['unique_criminals']}\n"
              f"**Total Jail Time:** {stats['total_jail_time']:,} years",
        inline=False
    )
    
    if stats["common_crimes"]:
        crimes_text = "\n".join([
            f"**{i}.** {crime} ({count} time(s))"
            for i, (crime, count) in enumerate(stats["common_crimes"], 1)
        ])
        
        embed.add_field(
            name="🔥 Most Common Crimes",
            value=crimes_text,
            inline=False
        )
    
    embed.set_footer(text=f"Source: {interaction.guild.name} PD")
    
    await interaction.followup.send(embed=embed)
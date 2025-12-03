import random
import datetime
from discord import Interaction, Member, Embed, Color
from src.aclient import client
from src.moderation.database import (
    get_user_log,
    add_crime_record, 
    get_criminal_record,
    get_crime_statistics,
    add_civil_case,
    get_civil_record
)
from src.utils.response_generator import generate_command_response, generate_roleplay_response
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
    years = random.randint(1, 99)
    
    # DYNAMIC OUTCOMES with weighted probabilities
    outcomes = [
        ("arrested", 60),
        ("evaded", 20),
        ("resisted", 10),
        ("bribed", 5),
        ("killed", 3),
        ("undercover", 2),
    ]
    
    # Weighted random choice
    outcome = random.choices(
        [o[0] for o in outcomes],
        weights=[o[1] for o in outcomes],
        k=1
    )[0]
    
    # Generate outcome-specific narratives
    if outcome == "arrested":
        # NORMAL ARREST - Save to database
        await add_crime_record(
            user_id=str(criminal.id),
            server_id=str(interaction.guild.id),
            crime=crime,
            arrested_by=interaction.user.display_name,
            jail_time=years
        )
        
        prompt = (
            f"Officer {interaction.user.display_name} successfully arrested {criminal.display_name} "
            f"for: {crime}\n{personality}\n\n"
            f"Write a dramatic police report (3-4 sentences). They've been sentenced to {years} years."
        )
        
        embed_title = "🚨 ARREST WARRANT 🚨"
        embed_color = Color.red()
        footer = f"Arrested by Officer {interaction.user.display_name} | Record saved"
        
    elif outcome == "evaded":
        # ESCAPED - No record saved
        prompt = (
            f"{criminal.display_name} evaded arrest from Officer {interaction.user.display_name} "
            f"for the crime of: {crime}\n{personality}\n\n"
            f"Write a dramatic escape scene (3-4 sentences). They got away! "
            "Include action movie tropes and ridiculous escape methods."
        )
        
        embed_title = "💨 SUSPECT EVADED 💨"
        embed_color = Color.orange()
        footer = "⚠️ Suspect remains at large | No record saved"
        years = "AT LARGE"
        
    elif outcome == "resisted":
        # RESISTED - Half sentence
        years = years // 2
        await add_crime_record(
            user_id=str(criminal.id),
            server_id=str(interaction.guild.id),
            crime=f"{crime} + resisting arrest",
            arrested_by=interaction.user.display_name,
            jail_time=years
        )
        
        prompt = (
            f"{criminal.display_name} resisted arrest by Officer {interaction.user.display_name}! "
            f"Crime: {crime}\n{personality}\n\n"
            f"Write a dramatic fight scene (3-4 sentences). They were eventually subdued. "
            f"Reduced sentence: {years} years due to good lawyer."
        )
        
        embed_title = "⚔️ RESISTED ARREST ⚔️"
        embed_color = Color.dark_red()
        footer = f"Subdued by Officer {interaction.user.display_name} | Record saved"
        
    elif outcome == "bribed":
        # BRIBED - No record, they pay money
        bribe_amount = random.randint(100, 10000)
        
        prompt = (
            f"{criminal.display_name} bribed Officer {interaction.user.display_name} "
            f"to avoid arrest for: {crime}\n{personality}\n\n"
            f"Write a corrupt cop scene (3-4 sentences). "
            f"They paid ${bribe_amount} and walked free. Be funny and dramatic."
        )
        
        embed_title = "💰 BRIBE ACCEPTED 💰"
        embed_color = Color.gold()
        footer = f"💵 ${bribe_amount} changed hands | No record (wink wink)"
        years = f"$0 (paid ${bribe_amount} bribe)"
        
    elif outcome == "killed":
        # KILLED - Permanent record with 0 years (they're dead)
        await add_crime_record(
            user_id=str(criminal.id),
            server_id=str(interaction.guild.id),
            crime=f"{crime} (DECEASED)",
            arrested_by=interaction.user.display_name,
            jail_time=0
        )
        
        prompt = (
            f"{criminal.display_name} was killed during arrest by Officer {interaction.user.display_name} "
            f"for: {crime}\n{personality}\n\n"
            f"Write a dramatic death scene (3-4 sentences). Over-the-top and absurd. "
            "They won't be committing any more crimes."
        )
        
        embed_title = "💀 SUSPECT DECEASED 💀"
        embed_color = Color.dark_gray()
        footer = f"KIA by Officer {interaction.user.display_name} | RIP"
        years = "DECEASED ☠️"
        
    else:  # undercover
        # UNDERCOVER COP - Reverse arrest!
        await add_crime_record(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild.id),
            crime="Attempted arrest of undercover officer",
            arrested_by=criminal.display_name,
            jail_time=years
        )
        
        prompt = (
            f"Plot twist! {criminal.display_name} was an undercover cop all along! "
            f"Officer {interaction.user.display_name} attempted to arrest them for: {crime}\n"
            f"{personality}\n\n"
            f"Write a dramatic plot twist reveal (3-4 sentences). "
            f"{interaction.user.display_name} is now arrested for {years} years!"
        )
        
        embed_title = "🕵️ UNDERCOVER REVEALED 🕵️"
        embed_color = Color.blue()
        footer = f"UNO REVERSE! {interaction.user.display_name} arrested instead!"
        criminal = interaction.user  # Swap for embed display
    
    # Generate AI narrative
    try:
        report = await generate_command_response(
            prompt=prompt,
            server_id=interaction.guild.id,
            use_personality=False,
            temperature=1.0,  # Higher temp for more chaos
            max_tokens=300
        )
    except Exception as e:
        logger.exception(f"[Arrest Error] {e}")
        report = f"Standard procedure executed. Outcome: {outcome}"
    
    # Build embed
    embed = Embed(
        title=embed_title,
        description=report,
        color=embed_color
    )
    embed.add_field(name="Suspect", value=criminal.display_name, inline=True)
    embed.add_field(name="Crime", value=crime, inline=True)
    embed.add_field(name="Outcome", value=str(years), inline=True)
    embed.set_thumbnail(url=criminal.avatar.url if criminal.avatar else criminal.default_avatar.url)
    embed.set_footer(text=footer)
    
    await interaction.followup.send(embed=embed)

@client.tree.command(name="lawsuit", description="Take someone to court")
async def lawsuit(interaction: Interaction, defendant: Member, complaint: str, amount: int = 0):
    await interaction.response.defer()
    
    if defendant.bot:
        await interaction.followup.send("Bots are above the law! 🤖⚖️", ephemeral=True)
        return
    
    if defendant == interaction.user:
        await interaction.followup.send("You can't sue yourself!", ephemeral=True)
        return
    
    log = await get_user_log(str(defendant.id))
    personality = ""
    if log and log[4]:
        personality = f"\nKnown behavior: {log[4]}"
    
    # DYNAMIC OUTCOMES with weighted probabilities
    outcomes = [
        ("guilty", 40),
        ("not_guilty", 35),
        ("settled", 15),
        ("counter_sued", 5),
        ("dismissed", 3),
        ("mistrial", 2),
    ]
    
    outcome = random.choices(
        [o[0] for o in outcomes],
        weights=[o[1] for o in outcomes],
        k=1
    )[0]
    
    # Calculate amounts based on outcome
    if amount <= 0:
        amount = random.randint(1, 9999)
    
    if outcome == "guilty":
        # NORMAL WIN - Defendant pays
        multiplier = random.uniform(0.5, 3.0)
        final_amount = int(amount * multiplier)
        verdict = "guilty"
        
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(interaction.user.id),
            defendant_id=str(defendant.id),
            complaint=complaint,
            amount=final_amount,
            verdict=verdict
        )
        
        prompt = (
            f"Judge rules GUILTY! {defendant.display_name} must pay {interaction.user.display_name} "
            f"${final_amount} for: {complaint}\n{personality}\n\n"
            f"Write dramatic judge's ruling (3-4 sentences). Justice is served!"
        )
        
        embed_title = "⚖️ GUILTY VERDICT ⚖️"
        embed_color = Color.green()
        footer = f"Case won by {interaction.user.display_name}"
        
    elif outcome == "not_guilty":
        # NORMAL LOSS - Nobody pays
        final_amount = 0
        verdict = "not guilty"
        
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(interaction.user.id),
            defendant_id=str(defendant.id),
            complaint=complaint,
            amount=0,
            verdict=verdict
        )
        
        prompt = (
            f"Judge rules NOT GUILTY! {defendant.display_name} is innocent of: {complaint}\n"
            f"{personality}\n\n"
            f"{interaction.user.display_name} gets nothing. Write judge's dismissal (3-4 sentences)."
        )
        
        embed_title = "⚖️ NOT GUILTY ⚖️"
        embed_color = Color.red()
        footer = f"Case dismissed | {defendant.display_name} vindicated"
        
    elif outcome == "settled":
        # SETTLED - Split the difference
        final_amount = int(amount * random.uniform(0.2, 0.6))
        verdict = "guilty"
        
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(interaction.user.id),
            defendant_id=str(defendant.id),
            complaint=complaint,
            amount=final_amount,
            verdict=verdict
        )
        
        prompt = (
            f"SETTLED OUT OF COURT! {defendant.display_name} pays {interaction.user.display_name} "
            f"${final_amount} to avoid trial for: {complaint}\n{personality}\n\n"
            f"Write about the settlement negotiation (3-4 sentences). Both parties compromise."
        )
        
        embed_title = "🤝 SETTLED 🤝"
        embed_color = Color.blue()
        footer = f"Settled for ${final_amount} | Case closed"
        
    elif outcome == "counter_sued":
        # COUNTER-SUED - Plaintiff loses and pays!
        final_amount = int(amount * random.uniform(1.5, 3.0))
        verdict = "not guilty"
        
        # Original case
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(interaction.user.id),
            defendant_id=str(defendant.id),
            complaint=complaint,
            amount=0,
            verdict=verdict
        )
        
        # Counter-suit (reverse roles)
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(defendant.id),
            defendant_id=str(interaction.user.id),
            complaint=f"Frivolous lawsuit about '{complaint}'",
            amount=final_amount,
            verdict="guilty"
        )
        
        prompt = (
            f"UNO REVERSE! {defendant.display_name} counter-sued {interaction.user.display_name} "
            f"for filing a frivolous lawsuit! {interaction.user.display_name} now owes ${final_amount}!\n"
            f"{personality}\n\n"
            f"Write dramatic counter-suit victory (3-4 sentences). Tables have turned!"
        )
        
        embed_title = "🔄 COUNTER-SUED! 🔄"
        embed_color = Color.purple()
        footer = f"Plot twist! {interaction.user.display_name} must pay ${final_amount}"
        temp = defendant
        defendant = interaction.user
        interaction._user = temp
        
    elif outcome == "dismissed":
        # DISMISSED - Waste of court's time, plaintiff pays fine
        final_amount = random.randint(50, 500)
        verdict = "not guilty"
        
        await add_civil_case(
            server_id=str(interaction.guild.id),
            plaintiff_id=str(interaction.user.id),
            defendant_id=str(defendant.id),
            complaint=complaint,
            amount=0,
            verdict="not guilty"
        )
        
        prompt = (
            f"CASE DISMISSED! Judge throws out {interaction.user.display_name}'s lawsuit about: {complaint}\n"
            f"Waste of court time! {interaction.user.display_name} fined ${final_amount} for frivolous case.\n"
            f"{personality}\n\n"
            f"Write angry judge rant (3-4 sentences). This case was ridiculous!"
        )
        
        embed_title = "🚫 DISMISSED 🚫"
        embed_color = Color.dark_red()
        footer = f"Frivolous lawsuit! {interaction.user.display_name} fined ${final_amount}"
        final_amount = f"-${final_amount} (fine)"
        
    else:  # mistrial
        # MISTRIAL - Do it all over again, no record saved
        final_amount = "MISTRIAL"
                
        prompt = (
            f"MISTRIAL DECLARED! The case of {interaction.user.display_name} vs {defendant.display_name} "
            f"about '{complaint}' has ended in mistrial!\n{personality}\n\n"
            f"Write chaotic courtroom scene (3-4 sentences). Something went horribly wrong. "
            "Case must be retried!"
        )
        
        embed_title = "⚠️ MISTRIAL ⚠️"
        embed_color = Color.orange()
        footer = "Case must be retried | No record saved"
    
    # Generate AI narrative
    try:
        character_description = "You are Judge ChopperBot, a dramatic and witty AI programmed to pass judgement over civil cases."

        statement = await generate_roleplay_response(
            character_description=character_description,
            scenario=prompt,
            temperature=1.0,
            max_tokens=300
        )
    except Exception as e:
        logger.exception(f"[Lawsuit Error] {e}")
        statement = f"The court has reached a decision. Outcome: {outcome}"
    
    # Build embed
    embed = Embed(
        title=embed_title,
        description=statement,
        color=embed_color
    )
    
    embed.add_field(name="Plaintiff", value=interaction.user.display_name, inline=True)
    embed.add_field(name="Defendant", value=defendant.display_name, inline=True)
    embed.add_field(name="Complaint", value=complaint[:100], inline=False)
    embed.add_field(name="Outcome", value=outcome.replace("_", " ").title(), inline=True)
    embed.add_field(name="Amount", value=f"${final_amount:,}" if isinstance(final_amount, int) else final_amount, inline=True)
    
    embed.set_thumbnail(url=defendant.avatar.url if defendant.avatar else defendant.default_avatar.url)
    embed.set_footer(text=footer)
    
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

@client.tree.command(name="legal_record", description="View someone's legal case history")
async def legal_record(interaction: Interaction, user: Member = None):
    await interaction.response.defer()
    
    target = user if user else interaction.user
        
    record = await get_civil_record(str(target.id), str(interaction.guild.id))
    
    # Calculate win rate
    total_cases = record["cases_filed"]
    if total_cases > 0:
        win_rate = (record["cases_won"] / total_cases) * 100
    else:
        win_rate = 0
    
    # Calculate net money
    net_money = record["money_won"] - record["money_lost"]
    
    embed = Embed(
        title="⚖️ Legal Record ⚖️",
        description=f"**{target.display_name}'s Legal History**",
        color=Color.blue()
    )
    
    # As Plaintiff
    embed.add_field(
        name="📋 As Plaintiff",
        value=f"**Cases Filed:** {record['cases_filed']}\n"
              f"**Cases Won:** {record['cases_won']}\n"
              f"**Win Rate:** {win_rate:.1f}%\n"
              f"**Money Won:** ${record['money_won']:,}",
        inline=True
    )
    
    # As Defendant
    embed.add_field(
        name="🎯 As Defendant",
        value=f"**Times Sued:** {record['times_sued']}\n"
              f"**Cases Lost:** {record['cases_lost']}\n"
              f"**Money Lost:** ${record['money_lost']:,}",
        inline=True
    )
    
    # Net worth
    net_emoji = "📈" if net_money >= 0 else "📉"
    embed.add_field(
        name=f"{net_emoji} Net Worth",
        value=f"**${net_money:,}**",
        inline=False
    )
    
    # Recent cases
    if record["recent_cases"]:
        cases_text = []
        for plaintiff_id, defendant_id, complaint, amount, verdict, timestamp, role in record["recent_cases"]:
            try:
                dt = datetime.datetime.fromisoformat(timestamp)
                time_str = f"<t:{int(dt.timestamp())}:R>"
            except:
                time_str = "Unknown"
            
            if role == "plaintiff":
                opponent_id = defendant_id
                result = "WON" if verdict == "guilty" else "LOST"
                money = f"+${amount:,}" if verdict == "guilty" else "$0"
            else:
                opponent_id = plaintiff_id
                result = "LOST" if verdict == "guilty" else "WON"
                money = f"-${amount:,}" if verdict == "guilty" else "$0"
            
            try:
                opponent = await client.fetch_user(int(opponent_id))
                opponent_name = opponent.name if opponent else "Unknown"
            except:
                opponent_name = "Unknown"
            
            cases_text.append(
                f"**{result}** vs {opponent_name} | {money}\n"
                f"└ {complaint[:40]}{'...' if len(complaint) > 40 else ''} | {time_str}"
            )
        
        embed.add_field(
            name="📜 Recent Cases",
            value="\n\n".join(cases_text[:3]),
            inline=False
        )
    
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    
    await interaction.followup.send(embed=embed)
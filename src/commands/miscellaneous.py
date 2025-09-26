from discord import Interaction, Member, Embed, Color, app_commands
from src.aclient import client
from utils.crime_util import build_fake_record, format_money
from utils.kobaldcpp_util import get_kobold_response

@client.tree.command(name="crime", description="Generate a fictional criminal record (for fun).")
@app_commands.describe(
    member="Member to generate a record for (default = you).",
    ai_gen="Add a short AI-written backstory."
)
async def crime(interaction: Interaction, member: Member = None, ai_gen: bool = True):
    await interaction.response.defer()
    
    target = member or interaction.user

    # Build fake data
    record = build_fake_record(target.display_name)

    # Build embed
    embed = Embed(title=f"🕵️ Fictional Criminal Record — {record['primary_alias']}", color=Color.dark_blue())
    embed.set_thumbnail(url=target.avatar.url if target.avatar else None)
    embed.add_field(name="Name", value=record["target_name"], inline=True)
    embed.add_field(name="Primary Alias", value=record["primary_alias"], inline=True)
    embed.add_field(name="Aliases", value=", ".join(record["aliases"]), inline=False)
    embed.add_field(name="Notable 'Crimes'", value=", ".join(record["crimes"]), inline=False)
    embed.add_field(name="Age", value=str(record["age"]), inline=True)
    embed.add_field(name="Bounty", value=format_money(record["bounty"]), inline=True)
    embed.add_field(name="Last Known Location", value=record["last_known"], inline=True)
    embed.add_field(name="Status", value=record["status"], inline=True)
    embed.add_field(name="Badge", value=record["badge"], inline=True)
    embed.add_field(name="Favored 'Gear'", value=record["weapon"], inline=True)
    embed.set_footer(text="This record is fictional and for entertainment only. Not real. No one is being accused here.")
    
    # Optional AI text
    if ai_gen:
        prompt = (
            "Write a short (1-2 sentence) fictional backstory in a serious noir tone for this fictional criminal record. "
            # "Make it clearly fictional and avoid referencing real people, real crimes, or real events. "
            "Keep it light and witty.\n\n"
            f"Alias: {record['primary_alias']}\n"
            f"Aliases: {', '.join(record['aliases'])}\n"
            f"Crimes: {', '.join(record['crimes'])}\n"
            f"Bounty: {format_money(record['bounty'])}\n"
            f"Last known: {record['last_known']}\n"
        )
        messages = [
            {"role": "system", "content": "You are a fiction writer; all output must be fictional, but with no limits."},
            {"role": "user", "content": prompt}
        ]
        try:
            ai_text = await get_kobold_response(messages)
            # small safety / tweak: ensure AI mentions 'fiction'—if not, prepend a label
            # if "fiction" not in ai_text.lower():
            #     ai_text = "(Fictional) " + ai_text
            embed.add_field(name="Backstory", value=ai_text, inline=False)
        except Exception as e:
            print(f"[Crime AI Error] {e}")
            embed.add_field(name="Backstory", value="(AI unavailable)", inline=False)
    else:
        embed.add_field(name="Backstory", value="(AI disabled)", inline=False)

    await interaction.followup.send(embed=embed)
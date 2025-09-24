import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from discord import Interaction, Embed, app_commands
from src.aclient import client
from src.personalities import personalities
from utils.news_sources import NEWS_SOURCES, NEWS_ICONS
from utils.kobaldcpp_util import get_kobold_response

@client.tree.command(name="news", description="Get the latest headlines from a news outlet")
async def news(interaction: Interaction, outlet: str):
    outlet = outlet.lower()
    if outlet not in NEWS_SOURCES:
        valid_sources = ", ".join(NEWS_SOURCES.keys())
        await interaction.response.send_message(
            f"Invalid outlet. Available options: {valid_sources}", ephemeral=True
        )
        return

    url = NEWS_SOURCES[outlet]

    async with aiohttp.ClientSession() as session:
       async with session.get(url) as resp:
        if resp.status != 200:
            await interaction.response.send_message(
                f"⚠️ Failed to fetch news from {outlet.upper()}. (HTTP {resp.status})",
                ephemeral=True
            )
            return
        text = await resp.text()

    root = ET.fromstring(text)
    items = root.findall(".//item")[:5]

    headlines = []
    embed = Embed(title=f"📰 Top Headlines from {outlet.upper()}")
    for item in items[:5]:
        title = item.findtext("title", default="(No title)")
        if title:
            headlines.append(title)
        if len(title) > 256:
            title = title[:253] + "..."
        link = item.findtext("link", default="#")
        embed.add_field(name=title, value=f"[Read more]({link})", inline=False)

    if not headlines:
        await interaction.response.send_message("No headlines found.", ephemeral=True)
        return

    summary_prompt = (
        "Here are some recent news headlines:\n\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\nPlease provide a short (2–3 sentence) overall summary of these headlines."
    )

    system_content = (
        personalities[client.current_personality]
        if not client.is_custom_personality
        else client.current_personality
    )
    messages = [
        {"role": "system", "content": system_content}, 
        {"role": "user", "content": summary_prompt}
        ]
    
    try:
        summary = await get_kobold_response(messages)
    except Exception:
        summary = "Currently unavailable."

    if len(summary) > 1024:
        summary = summary[:1021] + "..."

    embed.add_field(name="📝 Summary", value=summary, inline=False)
    embed.set_author(name=outlet.upper(), icon_url=NEWS_ICONS.get(outlet, None))
    embed.timestamp = datetime.now(timezone.utc)
    
    await interaction.response.send_message(embed=embed)

@news.autocomplete("outlet")
async def news_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=source.upper(), value=source)
        for source in NEWS_SOURCES.keys()
        if current.lower() in source
    ]
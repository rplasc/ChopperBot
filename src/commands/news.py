import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from discord import Interaction, Embed, app_commands
from src.aclient import client
from src.utils.news_sources import NEWS_SOURCES, NEWS_ICONS
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

@client.tree.command(name="news", description="Get the latest headlines from a news outlet")
async def news(interaction: Interaction, outlet: str):
    await interaction.response.defer()
    outlet = outlet.lower()
    if outlet not in NEWS_SOURCES:
        valid_sources = ", ".join(NEWS_SOURCES.keys())
        await interaction.response.send_message(
            f"Invalid outlet. Available options: {valid_sources}", ephemeral=True
        )
        return

    url = NEWS_SOURCES[outlet]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    await interaction.followup.send(
                        f"⚠️ Failed to fetch news from {outlet.upper()}. (HTTP {resp.status})",
                        ephemeral=True
                    )
                    logger.error(f"Failed to fetch news from {outlet.upper()}. (HTTP {resp.status})")
                    return
                text = await resp.text()
                
    except aiohttp.ClientError as e:
        await interaction.followup.send(
            f"⚠️ Network error while fetching news from {outlet.upper()}: {str(e)}",
            ephemeral=True
        )
        logger.error(f"Network error fetching from {outlet.upper()}: {str(e)}")
        return
        
    except asyncio.TimeoutError:
        await interaction.followup.send(
            f"⚠️ Request timed out while fetching news from {outlet.upper()}.",
            ephemeral=True
        )
        logger.error(f"Timeout error fetching from {outlet.upper()}")
        return
        
    except Exception as e:
        await interaction.followup.send(
            f"⚠️ Unexpected error while fetching news from {outlet.upper()}.",
            ephemeral=True
        )
        logger.error(f"Unexpected error fetching from {outlet.upper()}: {str(e)}")
        return

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
        await interaction.followup.send("No headlines found.", ephemeral=True)
        return

    summary_prompt = (
        "Here are some recent news headlines:\n\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\nPlease provide a short (2–3 sentence) overall summary of these headlines."
    )

    try:
        summary = await generate_command_response(
            prompt=summary_prompt,
            server_id=interaction.guild.id,
            use_personality=True,
            temperature=0.8,
            max_tokens=300
        )
    except Exception as e:
        logger.error(f"[NEWS ERROR] {e}")
        summary = "Currently unavailable."

    if len(summary) > 1024:
        summary = summary[:1021] + "..."

    embed.add_field(name="📝 Summary", value=summary, inline=False)
    embed.set_author(name=outlet.upper(), icon_url=NEWS_ICONS.get(outlet, None))
    embed.timestamp = datetime.now(timezone.utc)
    
    await interaction.followup.send(embed=embed)

@news.autocomplete("outlet")
async def news_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=source.upper(), value=source)
        for source in NEWS_SOURCES.keys()
        if current.lower() in source
    ]
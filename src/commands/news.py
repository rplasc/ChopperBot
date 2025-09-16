import aiohttp
import xml.etree.ElementTree as ET
from discord import Interaction, Embed, app_commands
from src.aclient import client
from utils.news_sources import NEWS_SOURCES

# TODO: Add AI summary
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
            text = await resp.text()

    root = ET.fromstring(text)
    items = root.findall(".//item")[:5]

    embed = Embed(title=f"📰 Top Headlines from {outlet.upper()}")
    for item in items:
        title = item.find("title").text
        link = item.find("link").text
        embed.add_field(name=title, value=f"[Read more]({link})", inline=False)
    
    await interaction.response.send_message(embed=embed)

@news.autocomplete("outlet")
async def news_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=source.upper(), value=source)
        for source in NEWS_SOURCES.keys()
        if current.lower() in source
    ]
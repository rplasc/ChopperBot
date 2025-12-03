import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, List, Dict
from discord import Interaction, Embed, app_commands
from src.aclient import client
from src.utils.news_sources import NEWS_SOURCES, NEWS_ICONS
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

# Simple in-memory cache
_news_cache: Dict[str, tuple[List[Dict], datetime]] = {}
CACHE_DURATION_MINUTES = 10

async def fetch_rss_feed(url: str, outlet: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch news from {outlet.upper()}. (HTTP {resp.status})")
                    return None
                return await resp.text()
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching from {outlet.upper()}: {str(e)}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout error fetching from {outlet.upper()}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching from {outlet.upper()}: {str(e)}")
        return None

def parse_rss_items(xml_text: str, outlet: str, max_items: int = 5) -> Optional[List[Dict]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"XML parse error for {outlet.upper()}: {str(e)}")
        return None
    
    items = root.findall(".//item")[:max_items]
    
    articles = []
    for item in items:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        description = item.findtext("description", default="").strip()
        pub_date_str = item.findtext("pubDate", default="").strip()
        
        # Parse publication date if available
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
            except ValueError:
                try:
                    # Alternative format without timezone
                    pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                except ValueError:
                    pass
        
        if title:
            articles.append({
                "title": title,
                "link": link or "#",
                "description": description,
                "pub_date": pub_date
            })
    
    return articles

def get_cached_news(outlet: str) -> Optional[List[Dict]]:
    if outlet in _news_cache:
        articles, cached_time = _news_cache[outlet]
        age = datetime.now(timezone.utc) - cached_time
        if age.total_seconds() < CACHE_DURATION_MINUTES * 60:
            return articles
    return None

def cache_news(outlet: str, articles: List[Dict]) -> None:
    _news_cache[outlet] = (articles, datetime.now(timezone.utc))

@client.tree.command(name="news", description="Get the latest headlines from a news outlet")
async def news(interaction: Interaction, outlet: str):
    await interaction.response.defer()
    outlet = outlet.lower()
    
    if outlet not in NEWS_SOURCES:
        valid_sources = ", ".join(NEWS_SOURCES.keys())
        await interaction.followup.send(
            f"Invalid outlet. Available options: {valid_sources}", ephemeral=True
        )
        return

    # Check cache first
    articles = get_cached_news(outlet)
    
    if articles is None:
        # Fetch from RSS feed
        url = NEWS_SOURCES[outlet]
        xml_text = await fetch_rss_feed(url, outlet)
        
        if xml_text is None:
            await interaction.followup.send(
                f"⚠️ Failed to fetch news from {outlet.upper()}. Please try again later.",
                ephemeral=True
            )
            return
        
        articles = parse_rss_items(xml_text, outlet, max_items=5)
        
        if articles is None:
            await interaction.followup.send(
                f"⚠️ Failed to parse RSS feed from {outlet.upper()}.",
                ephemeral=True
            )
            return
        
        if not articles:
            await interaction.followup.send("No headlines found.", ephemeral=True)
            return
        
        # Cache the results
        cache_news(outlet, articles)

    # Build embed
    embed = Embed(title=f"📰 Top Headlines from {outlet.upper()}")
    embed.set_author(name=outlet.upper(), icon_url=NEWS_ICONS.get(outlet, None))
    embed.timestamp = datetime.now(timezone.utc)
    
    headlines = []
    total_length = len(embed.title or "")
    
    for article in articles:
        title = article["title"]
        headlines.append(title)
        
        # Truncate title if too long for embed field name
        display_title = title
        if len(display_title) > 256:
            display_title = display_title[:253] + "..."
        
        # Build field value with link and optional date
        field_value = f"[Read more]({article['link']})"
        if article['pub_date']:
            # Format as relative time or absolute
            field_value += f"\n*Published: {article['pub_date'].strftime('%b %d, %Y %H:%M UTC')}*"
        
        # Check if adding this field would exceed Discord's limits
        field_length = len(display_title) + len(field_value)
        if total_length + field_length < 5800:  # Leave room for summary
            embed.add_field(name=display_title, value=field_value, inline=False)
            total_length += field_length
        else:
            break

    # Generate AI summary
    if headlines:
        summary_prompt = (
            "Here are some recent news headlines:\n\n"
            + "\n".join(f"- {h}" for h in headlines)
            + "\n\nPlease provide a short (2–3 sentence) overall summary of these headlines."
        )

        try:
            summary = await generate_command_response(
                prompt=summary_prompt,
                server_id=str(interaction.guild.id),
                use_personality=True,
                temperature=0.8,
                max_tokens=300
            )
        except Exception as e:
            logger.error(f"[NEWS ERROR] Failed to generate summary: {e}")
            # Fallback: use article descriptions if available
            descriptions = [a["description"] for a in articles if a["description"]]
            if descriptions:
                summary = descriptions[0][:200] + "..." if len(descriptions[0]) > 200 else descriptions[0]
            else:
                summary = "Summary currently unavailable."

        if len(summary) > 1024:
            summary = summary[:1021] + "..."

        embed.add_field(name="📝 Summary", value=summary, inline=False)
    
    await interaction.followup.send(embed=embed)

@news.autocomplete("outlet")
async def news_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=source.upper(), value=source)
        for source in NEWS_SOURCES.keys()
        if current.lower() in source
    ]
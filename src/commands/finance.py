import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, List, Dict
from discord import Interaction, Embed, app_commands, Color
from src.aclient import client
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger
from src.utils.news_sources import FINANCE_SOURCES, FINANCE_ICONS


# Simple in-memory cache
_finance_cache: Dict[str, tuple[List[Dict], datetime]] = {}
CACHE_DURATION_MINUTES = 5

async def fetch_rss_feed(url: str, source: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch finance news from {source}. (HTTP {resp.status})")
                    return None
                return await resp.text()
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching from {source}: {str(e)}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout error fetching from {source}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching from {source}: {str(e)}")
        return None

def parse_rss_items(xml_text: str, source: str, max_items: int = 5) -> Optional[List[Dict]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"XML parse error for {source}: {str(e)}")
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

def get_cached_news(source: str) -> Optional[List[Dict]]:
    if source in _finance_cache:
        articles, cached_time = _finance_cache[source]
        age = datetime.now(timezone.utc) - cached_time
        if age.total_seconds() < CACHE_DURATION_MINUTES * 60:
            return articles
    return None

def cache_news(source: str, articles: List[Dict]) -> None:
    _finance_cache[source] = (articles, datetime.now(timezone.utc))

@client.tree.command(name="finance", description="Get financial news and market analysis")
@app_commands.describe(
    source="Financial news source",
    analysis="Get AI analysis and insights on the headlines"
)
async def finance(
    interaction: Interaction, 
    source: str,
    analysis: bool = False
):
    await interaction.response.defer()
    source = source.lower()
    
    if source not in FINANCE_SOURCES:
        valid_sources = ", ".join(FINANCE_SOURCES.keys())
        await interaction.followup.send(
            f"Invalid source. Available options: {valid_sources}", ephemeral=True
        )
        return

    # Check cache first
    articles = get_cached_news(source)
    
    if articles is None:
        # Fetch from RSS feed
        url = FINANCE_SOURCES[source]
        xml_text = await fetch_rss_feed(url, source)
        
        if xml_text is None:
            await interaction.followup.send(
                f"⚠️ Failed to fetch financial news from {source.upper()}. Please try again later.",
                ephemeral=True
            )
            return
        
        articles = parse_rss_items(xml_text, source, max_items=5)
        
        if articles is None:
            await interaction.followup.send(
                f"⚠️ Failed to parse RSS feed from {source.upper()}.",
                ephemeral=True
            )
            return
        
        if not articles:
            await interaction.followup.send("No headlines found.", ephemeral=True)
            return
        
        # Cache the results
        cache_news(source, articles)

    # Build embed with financial theme
    embed = Embed(
        title=f"💼 Financial News from {source.upper().replace('_', ' ')}",
        color=Color.gold()
    )
    embed.set_author(name=source.upper().replace('_', ' '), icon_url=FINANCE_ICONS.get(source, None))
    embed.timestamp = datetime.now(timezone.utc)
    
    headlines = []
    total_length = len(embed.title or "")
    
    for article in articles:
        title = article["title"]
        headlines.append(title)
        
        # Truncate title if too long
        display_title = title
        if len(display_title) > 256:
            display_title = display_title[:253] + "..."
        
        # Build field value
        field_value = f"[Read more]({article['link']})"
        if article['pub_date']:
            field_value += f"\n*{article['pub_date'].strftime('%b %d, %H:%M UTC')}*"
        
        field_length = len(display_title) + len(field_value)
        if total_length + field_length < 5000:  # Leave room for analysis
            embed.add_field(name=display_title, value=field_value, inline=False)
            total_length += field_length
        else:
            break

    # Generate AI analysis if requested
    if analysis and headlines:
        analysis_prompt = (
            "You are a financial analyst. Here are recent financial news headlines:\n\n"
            + "\n".join(f"- {h}" for h in headlines)
            + "\n\nProvide a brief summary (2-3 sentences) of "
            "what these headlines suggest about current market conditions and "
            "potential implications for investors. "
            "Important: Frame this as educational analysis, not investment advice. "
        )

        try:
            analysis_text = await generate_command_response(
                prompt=analysis_prompt,
                server_id=str(interaction.guild.id),
                use_personality=False,
                temperature=0.7,
                max_tokens=300
            )
        except Exception as e:
            logger.error(f"[FINANCE ERROR] Failed to generate analysis: {e}")
            analysis_text = "Analysis currently unavailable."

        if len(analysis_text) > 1024:
            analysis_text = analysis_text[:1021] + "..."

        embed.add_field(name="📊 Market Analysis", value=analysis_text, inline=False)
        
        disclaimer = (
            "⚠️ *This analysis is for informational purposes only and should not be "
            "considered financial advice. Always consult with qualified financial "
            "professionals before making investment decisions.*"
        )
        embed.add_field(name="Disclaimer", value=disclaimer, inline=False)
    else:
        summary_prompt = (
            "Here are recent financial news headlines:\n\n"
            + "\n".join(f"- {h}" for h in headlines)
            + "\n\nProvide a brief (2-3 sentence) summary of the main themes in these headlines."
        )

        try:
            summary = await generate_command_response(
                prompt=summary_prompt,
                server_id=str(interaction.guild.id),
                use_personality=True,
                temperature=0.7,
                max_tokens=200
            )
        except Exception as e:
            logger.error(f"[FINANCE ERROR] Failed to generate summary: {e}")
            summary = "Summary currently unavailable."

        if len(summary) > 1024:
            summary = summary[:1021] + "..."

        embed.add_field(name="📝 Summary", value=summary, inline=False)
    
    await interaction.followup.send(embed=embed)

@finance.autocomplete("source")
async def finance_autocomplete(interaction: Interaction, current: str):
    return [
        app_commands.Choice(name=source.upper().replace('_', ' '), value=source)
        for source in FINANCE_SOURCES.keys()
        if current.lower() in source
    ]
import aiohttp
from discord import app_commands, Embed, Color, Interaction
from src.aclient import client
from src.utils.response_generator import generate_command_response
from src.moderation.logging import logger

WEATHER_API_KEY = client.weatherAPI

@client.tree.command(name="weather", description="Get the weather for a location")
@app_commands.describe(
    city="City name",
    region="Region / State / Province (optional)",
    country="Country (optional)",
    postal_code="Postal code / ZIP (optional)"
)
async def weather(
    interaction: Interaction,
    city: str,
    region: str = "",
    country: str = "",
    postal_code: str = ""
):
    await interaction.response.defer()

    # Build query string
    location_parts = [postal_code, city, region, country]
    location = ", ".join(part for part in location_parts if part.strip())

    # Call WeatherAPI
    async with aiohttp.ClientSession() as session:
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={location}"
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send(
                    "⚠️ Could not fetch weather data. Try refining your location."
                )
                logger.error(f"[WEATHER ERROR] API response {resp.status} for location={location}")
                return
            data = await resp.json()

    # Extract fields
    city = data["location"]["name"]
    region = data["location"]["region"]
    country = data["location"]["country"]

    temp = data["current"]["temp_c"]
    feels_like = data["current"]["feelslike_c"]
    condition = data["current"]["condition"]["text"]
    humidity = data["current"]["humidity"]
    wind_kph = data["current"]["wind_kph"]
    icon = f"https:{data['current']['condition']['icon']}"

    # AI summary
    prompt = (
        f"Comment on the current weather in {city}, {region}, {country}. "
        f"Conditions: {condition}, {temp}°C (feels like {feels_like}°C), "
        f"humidity {humidity}%, wind {wind_kph} kph. "
    )

    try:
        ai_summary = await generate_command_response(
            prompt=prompt,
            use_personality=True,
            temperature=0.85,
            max_tokens=200
        )
    except Exception as e:
        logger.error(f"[Weather AI Error] {e}")
        ai_summary = "Weather summary unavailable."

    # Build embed
    embed = Embed(title=f"⛈️ Weather in {city}, {region}", color=Color.blue())
    embed.set_thumbnail(url=icon)
    embed.add_field(name="☁️ Condition ☁️", value=condition, inline=True)
    embed.add_field(name="🌡️ Temperature 🌡️", value=f"{temp}°C (feels like {feels_like}°C)", inline=True)
    embed.add_field(name="💧 Humidity 💧", value=f"{humidity}%", inline=True)
    embed.add_field(name="💨 Wind Speed 💨", value=f"{wind_kph} kph", inline=True)
    embed.add_field(name="🤖 AI Summary 🤖", value=ai_summary, inline=False)

    await interaction.followup.send(embed=embed)

@client.tree.command(name="forecast", description="Get a multi-day weather forecast")
@app_commands.describe(
    city="City name",
    region="Region / State / Province (optional)",
    country="Country (optional)",
    postal_code="Postal code / ZIP (optional)",
    days="Number of days (1–7)"
)
async def forecast(
    interaction: Interaction,
    city: str,
    region: str = "",
    country: str = "",
    postal_code: str = "",
    days: int = 3
):
    await interaction.response.defer()

    if days < 1:
        days = 1
    elif days > 7:
        days = 7

    # Build query string
    location_parts = [postal_code, city, region, country]
    location = ", ".join(part for part in location_parts if part.strip())

    # Call WeatherAPI forecast
    async with aiohttp.ClientSession() as session:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={location}&days={days}&aqi=no&alerts=no"
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send("⚠️ Could not fetch forecast data. Try refining your location.")
                logger.error(f"[FORECAST ERROR] API response {resp.status} for location={location}")
                return
            data = await resp.json()

    # Extract location info
    city = data["location"]["name"]
    region = data["location"]["region"]
    country = data["location"]["country"]

    # Collect forecast details
    forecast_days = data["forecast"]["forecastday"]

    forecast_text = []
    for day in forecast_days:
        date = day["date"]
        condition = day["day"]["condition"]["text"]
        maxtemp = day["day"]["maxtemp_c"]
        mintemp = day["day"]["mintemp_c"]
        avg_humidity = day["day"]["avghumidity"]
        daily_chance_rain = day["day"].get("daily_chance_of_rain", "N/A")

        forecast_text.append(
            f"📅 {date}: {condition}, "
            f"{mintemp}°C – {maxtemp}°C, "
            f"Humidity {avg_humidity}%, "
            f"Rain chance {daily_chance_rain}%"
        )

    # AI summary of the multi-day forecast
    joined_forecast = "\n".join(forecast_text)
    prompt = (
        f"Summarize the {days}-day weather forecast for {city}, {region}, {country}:\n\n"
        f"{joined_forecast}\n\n"
        f"Provide a friendly summary highlighting trends (e.g., rain, temperature shifts)."
    )

    try:
        ai_summary = await generate_command_response(
            prompt=prompt,
            use_personality=True,
            temperature=0.85,
            max_tokens=200
        )
    except Exception as e:
        logger.error(f"[Forecast AI Error] {e}")
        ai_summary = "Forecast summary unavailable."

    # Build embed
    embed = Embed(
        title=f"🌤️ {days}-Day Forecast for {city}, {region}",
        description=f"Location: {city}, {region}, {country}",
        color=Color.blue()
    )
    embed.add_field(name="📊 Forecast", value="\n".join(forecast_text), inline=False)
    embed.add_field(name="🤖 AI Summary", value=ai_summary, inline=False)

    await interaction.followup.send(embed=embed)

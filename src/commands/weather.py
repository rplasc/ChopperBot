import aiohttp
from discord import app_commands, Embed, Color, Interaction
from src.aclient import client
from src.personalities import get_system_content
from utils.kobaldcpp_util import get_kobold_response

WEATHER_API_KEY = client.weatherAPI

@client.tree.command(name="weather", description="Get the weather for a location")
@app_commands.describe(location="City name or location to check weather")
async def weather(interaction: Interaction, location: str):
    await interaction.response.defer()

    # Call WeatherAPI
    async with aiohttp.ClientSession() as session:
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={location}"
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send("⚠️ Could not fetch weather data. Check the location name.")
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

    system_content = get_system_content()
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]

    try:
        ai_summary = await get_kobold_response(messages)
    except Exception as e:
        print(f"[Weather AI Error] {e}")
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

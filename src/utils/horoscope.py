import aiohttp

ZODIAC_SIGNS = [
    "aries","taurus","gemini","cancer","leo","virgo",
    "libra","scorpio","sagittarius","capricorn","aquarius","pisces"
]

async def get_horoscope(sign):
    url = f"https://aztro.sameerkumar.website?sign={sign}&day=today"
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as resp:
            return await resp.json()
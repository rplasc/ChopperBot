import aiohttp

async def get_kobold_response(messages):
    url = "http://127.0.0.1:5001/v1/chat/completions"
    payload = {
        "model": "your-model-name",
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.8
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

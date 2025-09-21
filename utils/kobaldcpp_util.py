import aiohttp

async def get_kobold_response(messages):
    url = "http://127.0.0.1:5001/v1/chat/completions"
    payload = {
        "messages": messages,
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 50,
        "frequency_penalty": 1.0,
        "presence_penalty": 0.6, 
        "repetition_penalty": 1.2,
        "max_tokens": 400,
        "stop": ["\nUser:", "\nSystem:", "\nAssistant:"]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

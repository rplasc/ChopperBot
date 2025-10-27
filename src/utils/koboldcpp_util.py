import aiohttp
import re
from src.aclient import client

async def get_kobold_response(messages):
    url = client.kobold_text_api
    payload = {
        "messages": messages,
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 50,
        "frequency_penalty": 1.0,
        "presence_penalty": 0.6, 
        "repetition_penalty": 1.15,
        "max_tokens": 512,
        "stop": ["\nUser:", "\nSystem:", "\nAssistant:"]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]
        
def sanitize_bot_output(text: str, bot_name: str = "Chopperbot") -> str:
    # Keep only the assistant's first reply before it starts imitating others
    first_line = re.split(r"\n(?:Me|User|You):", text, flags=re.IGNORECASE)[0]
    # Strip its own prefix if present
    first_line = re.sub(rf"^{bot_name}:\s*", "", first_line, flags=re.IGNORECASE).strip()
    return first_line
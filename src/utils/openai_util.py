from base64 import b64decode
from os import remove
from pathlib import Path
import openai
import aiohttp
import json
from src.aclient import client

openai.api_key = client.openAI_API_key

async def get_openai_response(messages):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai.api_key}"},
            json={"model": "gpt-4-0613", "messages": messages, "temperature": 1, "max_tokens": 256}
        ) as response:
            data = await response.json()
            return data['choices'][0]['message']['content']


async def generate_img(description):
    DATA_DIR = Path.cwd() / "responses"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    response = openai.Image.create(
        model="dall-e-2",
        prompt=description,
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="b64_json"
    )

    file_name = f"{description[:5]}-{response['created']}.json"
    file_path = DATA_DIR / file_name

    with open(file_path, mode="w", encoding="utf-8") as file:
        json.dump(response, file)

    return await conversion(file_path)

async def conversion(json_path):
    JSON_FILE = Path(json_path)
    IMAGE_DIR = Path.cwd() / "images"
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open(JSON_FILE, mode="r", encoding="utf-8") as file:
        response = json.load(file)

    # Assuming you only want the first image
    image_dict = response["data"][0]
    image_data = b64decode(image_dict["b64_json"])
    image_path = IMAGE_DIR / f"{JSON_FILE.stem}.png"

    with open(image_path, mode="wb") as png:
        png.write(image_data)

    # Remove JSON file after conversion
    remove(JSON_FILE)

    return image_path
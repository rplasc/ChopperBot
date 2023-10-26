from base64 import b64decode
from os import path
import os
from pathlib import Path
import discord
import openai
import aiohttp
import json
from src.aclient import client

openai.api_key = client.openAI_API_key # Add your OpenAI API key here

# Gets respone for Chatgpt model
async def get_openai_response(messages):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai.api_key}"},
            json={"model": "gpt-3.5-turbo", "messages": messages, "temperature": 0.8, "max_tokens": 256}
        ) as response:
            data = await response.json()
            return data['choices'][0]['message']['content']
        
# Generates image and returns url
async def generate_img(description):
   DATA_DIR = Path.cwd() / "responses" # Create directory for responses
   DATA_DIR.mkdir(exist_ok=True)
    
   response = openai.Image.create(
        model="image-alpha-001",  # Use the appropriate DALL·E model ID
        prompt=description,
        n=1,  # Number of images to generate
        size="256x256",  # Image resolution
        response_format="b64_json"  # Get the image as a URL
        )
   
   file_name = DATA_DIR / f"{description[:5]}-{response['created']}.json"
   with open(file_name, mode="w", encoding="utf-8") as file:
        json.dump(response, file)
        
   path = await conversion(file_name)
   return path

# Converts generated image to png
async def conversion(path):
    DATA_DIR = Path.cwd() / "responses"
    JSON_FILE = DATA_DIR / path
    IMAGE_DIR = Path.cwd() / "images"
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open(JSON_FILE, mode="r", encoding="utf-8") as file:
        response = json.load(file)

    image_file = []
    for index, image_dict in enumerate(response["data"]):
        image_data = b64decode(image_dict["b64_json"])
        image_file = IMAGE_DIR / f"{JSON_FILE.stem}-{index}.png"
        with open(image_file, mode="wb") as png:
            png.write(image_data)
            
    os.remove(path)

    return image_file
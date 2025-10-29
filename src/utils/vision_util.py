import aiohttp
import base64
from typing import List, Dict
from discord import Attachment
from src.aclient import client
from src.utils.personality_manager import get_server_personality
from src.moderation.logging import logger

# Vision model configuration
VISION_API_URL = client.kobold_text_api
DEFAULT_VISION_TEMPERATURE = 0.7
DEFAULT_VISION_MAX_TOKENS = 500

async def download_image(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download image: {resp.status}")
            return await resp.read()

async def encode_image_to_base64(image_data: bytes) -> str:
    return base64.b64encode(image_data).decode('utf-8')

async def analyze_image(
    image_data: bytes,
    prompt: str = "Describe this image in detail.",
    use_personality: bool = True,
    temperature: float = DEFAULT_VISION_TEMPERATURE,
    max_tokens: int = DEFAULT_VISION_MAX_TOKENS,
    server_id: int = None
) -> str:
    # Encode image to base64
    image_base64 = await encode_image_to_base64(image_data)
    
    # Build messages with image
    messages = []
    
    if use_personality:
        personality = await get_server_personality(server_id)
        if personality:
            messages.append({
                "role": "system",
                "content": personality.get_base_prompt()
            })
    
    # Add user message with image
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": prompt
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            }
        ]
    })
    
    # Call vision API
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(VISION_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.exception(f"Vision API error {resp.status}: {error_text}")
            
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

async def analyze_discord_attachment(
    attachment: Attachment,
    prompt: str = "Describe this image.",
    use_personality: bool = True,
    server_id: int = None
) -> str:
    # Check if attachment is an image
    if not attachment.content_type or not attachment.content_type.startswith('image/'):
        logger.error(f"Attachment is not an image: {attachment.content_type}")
    
    # Download image
    image_data = await attachment.read()
    
    # Analyze
    return await analyze_image(image_data, prompt, use_personality, server_id=server_id)

async def analyze_multiple_images(
    image_data_list: List[bytes],
    prompt: str = "Describe these images and how they relate.",
    use_personality: bool = True,
    server_id: int = None
) -> str:
    # Encode all images
    image_base64_list = [await encode_image_to_base64(img) for img in image_data_list]
    
    messages = []
    
    if use_personality:
        personality = await get_server_personality(server_id)
        if personality:
            messages.append({
                "role": "system",
                "content": personality.get_base_prompt()
            })
    
    # Build content with all images
    content = [{"type": "text", "text": prompt}]
    
    for img_base64 in image_base64_list:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{img_base64}"
            }
        })
    
    messages.append({
        "role": "user",
        "content": content
    })
    
    payload = {
        "messages": messages,
        "temperature": DEFAULT_VISION_TEMPERATURE,
        "max_tokens": DEFAULT_VISION_MAX_TOKENS
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(VISION_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.exception(f"Vision API error {resp.status}: {error_text}")
            
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

def is_image_attachment(attachment: Attachment) -> bool:
    return (attachment.content_type and 
            attachment.content_type.startswith('image/'))

async def get_image_metadata(attachment: Attachment) -> Dict:
    return {
        "filename": attachment.filename,
        "size_kb": attachment.size / 1024,
        "content_type": attachment.content_type,
        "url": attachment.url,
        "width": attachment.width,
        "height": attachment.height
    }
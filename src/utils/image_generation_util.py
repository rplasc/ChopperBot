import aiohttp
import base64
from io import BytesIO
from typing import Optional, List
from discord import File
from src.aclient import client
from src.moderation.logging import logger

# Image generation configuration
IMAGE_GEN_API_URL = client.kobold_img_api
DEFAULT_IMAGE_SIZE = "512x512"
DEFAULT_STEPS = 20
DEFAULT_CFG_SCALE = 7.0

# TODO: Further testing is needed due to performance issues

async def generate_image(
    prompt: str,
    negative_prompt: Optional[str] = None,
    size: str = DEFAULT_IMAGE_SIZE,
    steps: int = DEFAULT_STEPS,
    cfg_scale: float = DEFAULT_CFG_SCALE,
    seed: Optional[int] = None
) -> bytes:

    payload = {
        "prompt": prompt,
        "size": size,
        "n": 1,  # Number of images
        "response_format": "b64_json"
    }
    
    # Add optional parameters
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    
    if steps:
        payload["steps"] = steps
    
    if cfg_scale:
        payload["cfg_scale"] = cfg_scale
    
    if seed is not None:
        payload["seed"] = seed
    
    logger.debug(f"Generating image: {prompt[:50]}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            IMAGE_GEN_API_URL, 
            json=payload,
            timeout=aiohttp.ClientTimeout(total=300)  # 5 min for image gen
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Image generation error {resp.status}: {error_text}")
            
            data = await resp.json()
            
            # Decode base64 image
            image_base64 = data["data"][0]["b64_json"]
            image_bytes = base64.b64decode(image_base64)
            
            logger.info(f"Generated image: {len(image_bytes)} bytes")
            return image_bytes

async def generate_image_for_discord(
    prompt: str,
    negative_prompt: Optional[str] = None,
    size: str = DEFAULT_IMAGE_SIZE,
    filename: str = "generated.png"
) -> File:

    image_bytes = await generate_image(prompt, negative_prompt, size)
    
    # Convert to Discord File
    image_io = BytesIO(image_bytes)
    return File(image_io, filename=filename)

async def enhance_prompt(prompt: str) -> str:

    # Add quality enhancers if not already present
    quality_tags = [
        "high quality", "detailed", "8k", "professional",
        "trending on artstation", "masterpiece"
    ]
    
    prompt_lower = prompt.lower()
    has_quality = any(tag in prompt_lower for tag in quality_tags)
    
    if not has_quality:
        prompt = f"{prompt}, highly detailed, high quality, masterpiece"
    
    return prompt

async def generate_with_personality_twist(
    base_prompt: str,
    use_personality_style: bool = True
) -> str:

    if not use_personality_style:
        return await enhance_prompt(base_prompt)
    
    from src.personalities import get_current_personality
    personality = get_current_personality()
    
    if not personality:
        return await enhance_prompt(base_prompt)
    
    # Add style based on personality
    style_additions = {
        "Default": "vibrant colors, dynamic composition, urban aesthetic",
        "Rogue": "dark atmosphere, cyberpunk style, dystopian, neon accents",
        "Assistant": "clean, professional, technical illustration"
    }
    
    style = style_additions.get(personality.name, "")
    
    if style:
        enhanced = f"{base_prompt}, {style}"
    else:
        enhanced = base_prompt
    
    return await enhance_prompt(enhanced)

async def generate_image_variations(
    base_prompt: str,
    num_variations: int = 3,
    size: str = DEFAULT_IMAGE_SIZE
) -> List[bytes]:

    variations = []
    
    for i in range(num_variations):
        try:
            # Use different seeds for variations
            image_bytes = await generate_image(
                base_prompt,
                size=size,
                seed=None  # Random seed each time
            )
            variations.append(image_bytes)
        except Exception as e:
            logger.error(f"Failed to generate variation {i+1}: {e}")
            continue
    
    return variations

# Preset styles for quick generation
PRESET_STYLES = {
    "anime": "anime style, manga art, vibrant colors, cel shaded",
    "realistic": "photorealistic, ultra detailed, 8k resolution, professional photography",
    "oil_painting": "oil painting, classical art style, textured brushstrokes, museum quality",
    "sketch": "pencil sketch, hand drawn, artistic lines, black and white",
    "cyberpunk": "cyberpunk style, neon lights, dark atmosphere, futuristic",
    "fantasy": "fantasy art, magical atmosphere, epic, detailed illustration",
    "cartoon": "cartoon style, colorful, playful, animated look",
    "vintage": "vintage photography, retro style, aged, nostalgic",
    "watercolor": "watercolor painting, soft colors, artistic, flowing",
    "pixel_art": "pixel art, retro gaming style, 8-bit aesthetic",
    "comic": "comic book style, bold lines, dynamic, graphic novel",
    "impressionist": "impressionist painting, soft brushstrokes, dreamy",
    "minimalist": "minimalist art, simple, clean lines, modern",
    "surreal": "surrealist art, dreamlike, abstract, Salvador Dali style",
    "steampunk": "steampunk aesthetic, Victorian, gears, brass and copper"
}

async def generate_with_style(
    prompt: str,
    style: str = "realistic",
    negative_prompt: Optional[str] = None
) -> bytes:

    # Get style tags
    style_tags = PRESET_STYLES.get(style.lower(), "")
    
    # Combine prompt with style
    full_prompt = f"{prompt}, {style_tags}" if style_tags else prompt
    
    # Default negative prompt if none provided
    if not negative_prompt:
        negative_prompt = "low quality, blurry, distorted, ugly, bad anatomy"
    
    return await generate_image(full_prompt, negative_prompt)

def get_available_styles() -> List[str]:
    return list(PRESET_STYLES.keys())

async def text_to_image_with_analysis(
    description: str,
    analyze_result: bool = False
) -> tuple[bytes, Optional[str]]:
    
    # Generate image
    image_bytes = await generate_image(description)
    
    analysis = None
    if analyze_result:
        # Analyze the generated image
        from src.utils.vision_util import analyze_image
        analysis = await analyze_image(
            image_bytes,
            "Describe what you see in this generated image.",
            use_personality=False
        )
    
    return image_bytes, analysis

async def upscale_prompt(prompt: str, style: str = None) -> str:
    quality_boost = "masterpiece, best quality, highly detailed, sharp focus, professional"
    
    if style:
        style_tags = PRESET_STYLES.get(style.lower(), "")
        return f"{prompt}, {style_tags}, {quality_boost}"
    
    return f"{prompt}, {quality_boost}"

def parse_size(size_str: str) -> tuple[int, int]:
    try:
        parts = size_str.lower().split('x')
        width = int(parts[0])
        height = int(parts[1])
        return width, height
    except:
        return 512, 512  # Default

def validate_size(width: int, height: int, max_size: int = 1024) -> tuple[int, int]:
    # Clamp to max
    width = min(width, max_size)
    height = min(height, max_size)
    
    # Ensure multiples of 8 (SD requirement)
    width = (width // 8) * 8
    height = (height // 8) * 8
    
    # Minimum 256
    width = max(256, width)
    height = max(256, height)
    
    return width, height

async def generate_with_options(
    prompt: str,
    style: Optional[str] = None,
    size: str = "512x512",
    quality: str = "standard",
    seed: Optional[int] = None
) -> bytes:
    
    # Parse and validate size
    width, height = parse_size(size)
    width, height = validate_size(width, height)
    size_str = f"{width}x{height}"
    
    # Adjust steps based on quality
    steps_map = {
        "draft": 15,
        "standard": 25,
        "high": 40
    }
    steps = steps_map.get(quality, 25)
    
    # Apply style if specified
    if style:
        full_prompt = f"{prompt}, {PRESET_STYLES.get(style.lower(), '')}"
    else:
        full_prompt = await enhance_prompt(prompt)
    
    # Generate
    return await generate_image(
        full_prompt,
        negative_prompt="low quality, blurry, distorted, bad anatomy",
        size=size_str,
        steps=steps,
        seed=seed
    )
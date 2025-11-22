import aiohttp
import base64
from io import BytesIO
from typing import Optional, List
from discord import File
from src.aclient import client
from src.moderation.logging import logger

# Image generation configuration
IMAGE_GEN_BASE_URL = client.kobold_img_api
DEFAULT_IMAGE_SIZE = "512x512"
DEFAULT_STEPS = 20
DEFAULT_CFG_SCALE = 7.0

async def generate_image(
    prompt: str,
    negative_prompt: Optional[str] = None,
    size: str = DEFAULT_IMAGE_SIZE,
    steps: int = DEFAULT_STEPS,
    cfg_scale: float = DEFAULT_CFG_SCALE,
    seed: Optional[int] = None
) -> bytes:
    
    # Parse size into width and height
    width, height = parse_size(size)
    
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "sampler_name": "Euler a"
    }
    
    # Add optional parameters
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    
    if seed is not None:
        payload["seed"] = seed
    
    logger.debug(f"Generating image: {prompt[:50]}...")
    
    # Use txt2img endpoint
    endpoint = f"{IMAGE_GEN_BASE_URL}/txt2img"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint, 
            json=payload,
            timeout=aiohttp.ClientTimeout(total=300)  # 5 min for image gen
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Image generation error {resp.status}: {error_text}")
            
            data = await resp.json()
            
            # KoboldCPP returns images as base64 in "images" array
            if "images" in data and len(data["images"]) > 0:
                image_base64 = data["images"][0]
                image_bytes = base64.b64decode(image_base64)
            else:
                raise Exception("No image data in response")
            
            logger.info(f"Generated image: {len(image_bytes)} bytes")
            return image_bytes

async def generate_image_from_image(
    prompt: str,
    init_image_base64: str,
    negative_prompt: Optional[str] = None,
    size: str = DEFAULT_IMAGE_SIZE,
    steps: int = DEFAULT_STEPS,
    cfg_scale: float = DEFAULT_CFG_SCALE,
    denoising_strength: float = 0.6,
    seed: Optional[int] = None,
    resize_input: bool = True,
) -> bytes:
    
    # Parse size into width and height
    width, height = parse_size(size)

    # Validate and adjust dimensions
    width, height = validate_size(width, height)
    
    # Optionally resize the input image to match target dimensions
    if resize_input:
        init_image_base64 = await resize_image_base64(init_image_base64, width, height)

    payload = {
        "prompt": prompt,
        "init_images": [init_image_base64],
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "denoising_strength": denoising_strength,
        "sampler_name": "Euler a"
    }
    
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    
    if seed is not None:
        payload["seed"] = seed
    
    logger.debug(f"Generating image from image: {prompt[:50]}...")
    
    # Use img2img endpoint
    endpoint = f"{IMAGE_GEN_BASE_URL}/img2img"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=300)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Image transformation error {resp.status}: {error_text}")
            
            data = await resp.json()
            
            if "images" in data and len(data["images"]) > 0:
                image_base64 = data["images"][0]
                image_bytes = base64.b64decode(image_base64)
            else:
                raise Exception("No image data in response")
            
            logger.info(f"Generated image from image: {len(image_bytes)} bytes")

            image_io = BytesIO(image_bytes)
            return File(image_io, filename="generated.png")

async def interrogate_image(image_base64: str, model: str = "clip") -> str:
    
    payload = {
        "image": image_base64,
        "model": model
    }
    
    logger.debug(f"Interrogating image with model: {model}")
    
    # Use interrogate endpoint
    endpoint = f"{IMAGE_GEN_BASE_URL}/interrogate"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Image interrogation error {resp.status}: {error_text}")
            
            data = await resp.json()
            
            if "caption" in data:
                return data["caption"]
            else:
                raise Exception("No caption in response")

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
        # Analyze the generated image using interrogate
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        analysis = await interrogate_image(image_base64)
    
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
        "standard": 20,
        "high": 30
    }
    steps = steps_map.get(quality, 20)
    
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

async def resize_image_base64(image_base64: str, target_width: int, target_height: int) -> str:
    from PIL import Image
    
    # Decode base64 to image
    image_bytes = base64.b64decode(image_base64)
    image = Image.open(BytesIO(image_bytes))
    
    # Convert to RGB if needed
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGB')
    elif image.mode == 'RGBA':
        # Create white background for transparent images
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    
    # Calculate aspect ratios
    original_ratio = image.width / image.height
    target_ratio = target_width / target_height
    
    # Resize maintaining aspect ratio, then crop to fit
    if original_ratio > target_ratio:
        # Image is wider, fit to height
        new_height = target_height
        new_width = int(target_height * original_ratio)
    else:
        # Image is taller, fit to width
        new_width = target_width
        new_height = int(target_width / original_ratio)
    
    # Resize using high-quality Lanczos resampling
    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Crop to exact target size (center crop)
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height
    image = image.crop((left, top, right, bottom))
    
    # Convert back to base64
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    resized_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    logger.debug(f"Resized image to {target_width}x{target_height}")
    return resized_base64
from discord import Interaction, Attachment, app_commands, Color, Embed#, File
from src.aclient import client
from src.utils.vision_util import (is_image_attachment, get_image_metadata, analyze_discord_attachment)
# from src.utils.image_generation_util import (generate_image_for_discord, get_available_styles, generate_with_personality_twist)
from src.moderation.logging import logger

@client.tree.command(name="analyze", description="Analyze an image")
@app_commands.describe(
    image="Image to analyze",
    question="What do you want to know about the image?"
)
async def analyze_image(
    interaction: Interaction,
    image: Attachment,
    question: str = "Describe this image in detail."
):
    await interaction.response.defer()
    
    try:
        if not is_image_attachment(image):
            await interaction.followup.send(
                "❌ That doesn't look like an image! Please upload a PNG, JPG, or similar.",
                ephemeral=True
            )
            return
        
        metadata = await get_image_metadata(image)
        logger.info(f"Analyzing image: {metadata['filename']} ({metadata['size_kb']:.1f}KB)")
        
        analysis = await analyze_discord_attachment(image, question, use_personality=True)
        
        embed = Embed(
            title="🔍 Image Analysis",
            description=analysis,
            color=Color.blue()
        )
        embed.set_footer(text=f"{metadata['filename']} • {metadata['width']}x{metadata['height']}")
        embed.set_thumbnail(url=image.url)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"[Analyze Error] {e}")
        await interaction.followup.send(
            "❌ Failed to analyze image. Make sure it's a valid image file.",
            ephemeral=True
        )

# @client.tree.command(name="imagine", description="Generate an image from text")
# @app_commands.describe(
#     prompt="Describe the image you want to create",
#     style="Art style (optional)"
# )
# async def imagine(
#     interaction: Interaction,
#     prompt: str,
#     style: str = None
# ):
#     await interaction.response.defer()
    
#     try:
#         logger.info(f"Generating image: {prompt[:50]}")
        
#         # Generate with or without style
#         if style and style.lower() in get_available_styles():
#             from src.utils.image_generation_util import generate_with_style
#             from io import BytesIO
            
#             image_bytes = await generate_with_style(prompt, style.lower())
#             image_file = File(BytesIO(image_bytes), filename="generated.png")
#         else:
#             # Use personality-enhanced prompt
#             enhanced_prompt = await generate_with_personality_twist(prompt, use_personality_style=True)
#             image_file = await generate_image_for_discord(enhanced_prompt)
        
#         embed = Embed(title="🎨 Generated Image", description=f"**Prompt:** {prompt}", color=Color.green())
#         if style:
#             embed.add_field(name="Style", value=style.title())
        
#         await interaction.followup.send(embed=embed, file=image_file)
#         logger.info("Image generation successful")
        
#     except Exception as e:
#         logger.exception(f"[Imagine Error] {e}")
#         await interaction.followup.send(
#             "❌ Failed to generate image. Make sure the image generation model is loaded.",
#             ephemeral=True
#         )

# @imagine.autocomplete("style")
# async def style_autocomplete(interaction: Interaction, current: str):
#     styles = get_available_styles()
#     return [
#         app_commands.Choice(name=style.replace("_", " ").title(), value=style)
#         for style in styles
#         if current.lower() in style.lower()
#     ][:25]\

# @client.tree.command(name="reimagine", description="Analyze an image then generate a new version")
# @app_commands.describe(
#     image="Image to reimagine",
#     changes="What to change about it"
# )
# async def reimagine(
#     interaction: Interaction,
#     image: Attachment,
#     changes: str = "Create a new artistic interpretation"
# ):
#     await interaction.response.defer()
    
#     try:
#         if not is_image_attachment(image):
#             await interaction.followup.send("❌ Please upload an image!", ephemeral=True)
#             return
        
#         await interaction.followup.send("🔍 Analyzing your image...")
#         analysis = await analyze_discord_attachment(
#             image,
#             "Describe this image's key visual elements, style, and composition in detail.",
#             use_personality=False
#         )
        
#         new_prompt = f"Based on this description: {analysis}\n\nCreate: {changes}"
        
#         await interaction.followup.send("🎨 Generating new image...")
#         image_file = await generate_image_for_discord(new_prompt, filename="reimagined.png")
        
#         embed = Embed(
#             title="✨ Reimagined",
#             description=f"**Changes:** {changes}",
#             color=Color.purple()
#         )
#         embed.set_thumbnail(url=image.url)
        
#         await interaction.followup.send(embed=embed, file=image_file)
        
#     except Exception as e:
#         logger.exception(f"[Reimagine Error] {e}")
#         await interaction.followup.send("❌ Failed to reimagine image.", ephemeral=True)

# @client.tree.command(name="styles", description="List available art styles for image generation")
# async def list_styles(interaction: Interaction):
#     styles = get_available_styles()
    
#     embed = Embed(
#         title="🎨 Available Art Styles",
#         description="Use these with `/imagine`",
#         color=Color.blue()
#     )
    
#     style_list = "\n".join([f"• `{style.replace('_', ' ').title()}`" for style in sorted(styles)])
#     embed.add_field(name="Styles", value=style_list, inline=False)
    
#     embed.set_footer(text="Example: /imagine 'a dragon' style:fantasy")
    
#     await interaction.response.send_message(embed=embed, ephemeral=True)
import discord
from io import BytesIO
from discord import Interaction, Attachment, app_commands, Color, Embed, File
from src.aclient import client
from src.utils.vision_util import (is_image_attachment, get_image_metadata, analyze_discord_attachment, encode_image_to_base64)
from src.utils.image_generation_util import (generate_image_for_discord, get_available_styles, generate_image_from_image, generate_with_style)
from src.moderation.logging import logger

# ============================================================================
# VIEWS
# ============================================================================

class ImagineView(discord.ui.View):
    def __init__(self, prompt: str, style: str = None):
        super().__init__(timeout=120)
        self.prompt = prompt
        self.current_style = style

        styles = get_available_styles()
        if styles:
            select = discord.ui.Select(
                placeholder="🎨 New Style...",
                options=[
                    discord.SelectOption(label=s.replace("_", " ").title(), value=s)
                    for s in styles[:25]
                ]
            )
            select.callback = self.style_selected
            self.add_item(select)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _generate_and_update(self, interaction: Interaction):
        try:
            if self.current_style and self.current_style in get_available_styles():
                image_bytes = await generate_with_style(self.prompt, self.current_style)
                image_file = File(BytesIO(image_bytes), filename="generated.png")
            else:
                image_file = await generate_image_for_discord(self.prompt)
        except Exception as e:
            logger.error(f"[ImagineView Error] {e}")
            await interaction.followup.send("❌ Image generation failed.", ephemeral=True)
            return

        embed = Embed(title="🎨 Generated Image", description=f"**Prompt:** {self.prompt}", color=Color.green())
        if self.current_style:
            embed.add_field(name="Style", value=self.current_style.replace("_", " ").title())
        await interaction.edit_original_response(embed=embed, attachments=[image_file], view=self)

    @discord.ui.button(label="Regenerate", style=discord.ButtonStyle.primary, emoji="🔄")
    async def regenerate(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self._generate_and_update(interaction)

    async def style_selected(self, interaction: Interaction):
        await interaction.response.defer()
        self.current_style = interaction.data["values"][0]
        await self._generate_and_update(interaction)


# ============================================================================
# COMMANDS
# ============================================================================

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
        
        server_id = str(interaction.guild.id)
        analysis = await analyze_discord_attachment(image, question, use_personality=True, server_id=server_id)
        
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

@client.tree.command(name="imagine", description="Generate an image from text")
@app_commands.describe(
    prompt="Describe the image you want to create",
    style="Art style (optional)"
)
async def imagine(
    interaction: Interaction,
    prompt: str,
    style: str = None
):
    await interaction.response.defer()
    
    try:
        logger.info(f"Generating image: {prompt[:50]}")
        
        # Generate with or without style
        if style and style.lower() in get_available_styles():
            
            image_bytes = await generate_with_style(prompt, style.lower())
            image_file = File(BytesIO(image_bytes), filename="generated.png")
        else:
            image_file = await generate_image_for_discord(prompt)
        
        embed = Embed(title="🎨 Generated Image", description=f"**Prompt:** {prompt}", color=Color.green())
        if style:
            embed.add_field(name="Style", value=style.title())

        view = ImagineView(prompt, style.lower() if style else None)
        await interaction.followup.send(embed=embed, file=image_file, view=view)
        logger.info("Image generation successful")
        
    except Exception as e:
        logger.exception(f"[Imagine Error] {e}")
        await interaction.followup.send(
            "❌ Failed to generate image. Make sure the image generation model is loaded.",
            ephemeral=True
        )

@imagine.autocomplete("style")
async def style_autocomplete(interaction: Interaction, current: str):
    styles = get_available_styles()
    return [
        app_commands.Choice(name=style.replace("_", " ").title(), value=style)
        for style in styles
        if current.lower() in style.lower()
    ][:25]\

@client.tree.command(name="reimagine", description="Analyze an image then generate a new version")
@app_commands.describe(
    image="Image to reimagine",
    changes="What to change about it"
)
async def reimagine(
    interaction: Interaction,
    image: Attachment,
    changes: str = "Create a new artistic interpretation"
):
    await interaction.response.defer()
    
    try:
        if not is_image_attachment(image):
            await interaction.followup.send("❌ Please upload an image!", ephemeral=True)
            return
        
        image_bytes = await image.read()
        image_base64 = await encode_image_to_base64(image_bytes)
        
        await interaction.followup.send("🎨 Generating new image...")
        image_file = await generate_image_from_image(
            prompt=changes,
            init_image_base64=image_base64,
            negative_prompt="low quality, blurry, distorted, ugly, bad anatomy",
            size="512x512",
            denoising_strength=0.7,
            resize_input=True
            )
        
        embed = Embed(
            title="✨ Reimagined",
            description=f"**Changes:** {changes}",
            color=Color.purple()
        )
        embed.set_thumbnail(url=image.url)
        
        await interaction.followup.send(embed=embed, file=image_file)
        
    except Exception as e:
        logger.exception(f"[Reimagine Error] {e}")
        await interaction.followup.send("❌ Failed to reimagine image.", ephemeral=True)
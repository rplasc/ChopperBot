import random
from datetime import datetime, timezone
from discord import Interaction, Embed, Color
from src.aclient import client

@client.tree.command(name="fact_check", description="Get an statement fact checked (totally accurate)")
async def fact_check(interaction: Interaction, statement: str):
    verdict = random.choice([True, False])

    if verdict:
        message_color = Color.green()
        image_url= "https://cdn.discordapp.com/attachments/906441689114214420/1441626747614531594/IMG_7224.jpg?ex=69227b08&is=69212988&hm=0949e4b94accd62a7327254bd2e9553572d966220727f237c7312aef12eaa0b6&"
        verdict_text = "**TRUE**"
    else:
        message_color = Color.red()
        image_url = "https://cdn.discordapp.com/attachments/906441689114214420/1441626747245166714/IMG_8496.jpg?ex=69227b08&is=69212988&hm=5fe8614b7f769422d267446d5dae51325bc152c908882174cd577081d712e187&"
        verdict_text = "**FALSE**"


    embed = Embed(title="Fact Check", color=message_color)
    embed.add_field(name="Statement:", value=statement)
    embed.add_field(name="Verdict:", value=verdict_text, inline=False)
    embed.set_image(url=image_url)
    embed.set_footer(text=f"Fact Checked by a real Illegal Immigrant")
    embed.timestamp = datetime.now(timezone.utc)

    await interaction.response.send_message(embed=embed)

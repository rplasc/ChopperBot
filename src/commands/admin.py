from discord import Interaction, Embed, app_commands
from typing import List
from src.personalities import personalities, custom_personalities
from utils.content_filter import censor_curse_words, filter_controversial
from src.aclient import client

@client.tree.command(name="set_personality", description="Set the bot's personality")
async def set_personality(interaction: Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    if personality in personalities:
        current_personality = personality
        is_custom_personality = False
        conversation_histories.clear()
        embed = Embed(title="Set Personality", description=f"Personality has been set to {personality}")
        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(title="Set Personality", description=f'Invalid personality. Available options are: {", ".join(personalities.keys())}')
        await interaction.response.send_message(embed=embed)
        
async def personality_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = [app_commands.Choice(name=personality, value=personality) for personality in personalities.keys() if current.lower() in personality.lower()]
    return choices
    
@client.tree.command(name="pretend", description="Set the bot's personality to a character/celebrity")
async def pretend(interaction: Interaction, personality: str):
    global current_personality, is_custom_personality, conversation_histories
    censored_personality = censor_curse_words(personality)
    if filter_controversial(censored_personality):
        current_personality = custom_personalities(censored_personality)
        is_custom_personality = True
        conversation_histories.clear()
        embed = Embed(title="Personality Change", description=f"I will now act like {censored_personality}")
    else:
        embed = Embed(title="Personality Change", description="Sorry, I cannot pretend to be that person.")
    await interaction.response.send_message(embed=embed)
    
# Resets "memory" and personality back to default
@client.tree.command(name="reset",description="Resets to default personality")
async def reset(interaction: Interaction):
    global current_personality
    if current_personality != 'Chopperbot':
        current_personality = "Chopperbot"
        
    conversation_histories.clear()
    await interaction.response.send_message("My memory has been wiped!")
    print("Personality has been reset.")
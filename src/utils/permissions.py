from discord import Interaction, app_commands

def is_admin():
    async def predicate(interaction: Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

def is_moderator():
    async def predicate(interaction: Interaction) -> bool:
        return (interaction.user.guild_permissions.administrator or 
                interaction.user.guild_permissions.moderate_members)
    return app_commands.check(predicate)

def is_owner():
    async def predicate(interaction: Interaction) -> bool:
        return interaction.user.id == 906241130440572969
    return app_commands.check(predicate)
from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.server_commands import ServerCommandManager
from apps.bot.discord.commands.registry import commands_registry
from apps.bot.discord.permissions.permission import Permissions
from shared.types.command_record import CommandType

name = "commandmanage"
aliases = ["cmdmanage", "cmdctl"]
description = "Enable or disable specific commands within this server."
category = "Moderation"
usage = "commandmanage <enable|disable> <command_name>"
cooldown = 3.0
user_permissions = [Permissions.MANAGE_GUILD]
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return

    if len(args) < 2:
        usage_msg = "Usage: `commandmanage <enable|disable> <command_name>`"
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(usage_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(usage_msg)
        return

    action = args[0].lower()
    target_cmd = args[1].lower()

    cmd = commands_registry.get(target_cmd)
    if not cmd:
        msg = get_string("commands.commandmanage.not_found", "❌ Command `{command}` was not found in the registry.", command=target_cmd)
    elif action == "disable":
        ok = ServerCommandManager.disable_command(str(guild.id), target_cmd)
        if ok:
            msg = get_string("commands.commandmanage.disabled", "⛔ Command `{command}` has been disabled in this server.", command=target_cmd)
        else:
            msg = get_string("commands.commandmanage.protected", "⚠️ Command `{command}` is essential and cannot be disabled.", command=target_cmd)
    elif action == "enable":
        ServerCommandManager.enable_command(str(guild.id), target_cmd)
        msg = get_string("commands.commandmanage.enabled", "✅ Command `{command}` has been enabled in this server.", command=target_cmd)
    else:
        msg = "Invalid action. Use `enable` or `disable`."

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)

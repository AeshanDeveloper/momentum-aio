from typing import List, Any
from config.settings import settings
from config.strings import get_string
from core.security.blacklist import BlacklistManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "unblacklist"
aliases = ["unbl"]
description = "Lift command execution restriction from a user or server."
category = "Dev"
usage = "unblacklist <user|guild> <id>"
cooldown = 1.0
owner_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)

    if not is_bot_owner(author.id):
        err = get_string("permissions.owner_only", "❌ Access Denied: This command is strictly reserved for the global bot owner.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    if len(args) < 2:
        usage_msg = "Usage: `unblacklist <user|guild> <id>`"
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(usage_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(usage_msg)
        return

    target_type = args[0].lower()
    target_id = args[1].strip()

    if target_type == "user":
        res = BlacklistManager.unblacklist_user(target_id, admin_id=str(author.id))
    elif target_type in ["guild", "server"]:
        res = BlacklistManager.unblacklist_guild(target_id, admin_id=str(author.id))
    else:
        res = {"success": False, "error": "Invalid target type. Use 'user' or 'guild'."}

    if res.get("success"):
        msg = get_string("security.blacklist_removed", "✅ Successfully removed {target_type} `{target_id}` from the blacklist.", target_type=target_type, target_id=target_id)
    else:
        msg = f"❌ {res.get('error', 'Operation failed.')}"

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)

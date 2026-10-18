from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.blacklist import BlacklistManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "blacklist"
aliases = ["bl"]
description = "Restrict a user or server from executing bot commands."
category = "Dev"
usage = "blacklist <user|guild> <id> [duration] [reason]"
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
        usage_msg = "Usage: `blacklist <user|guild> <id> [duration] [reason]`"
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(usage_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(usage_msg)
        return

    target_type = args[0].lower()
    target_id = args[1].strip()
    duration = args[2] if len(args) > 2 else None
    reason = " ".join(args[3:]).strip() if len(args) > 3 else "Administrative restriction"

    if target_type == "user":
        res = BlacklistManager.blacklist_user(target_id, admin_id=str(author.id), reason=reason, duration=duration)
    elif target_type in ["guild", "server"]:
        res = BlacklistManager.blacklist_guild(target_id, admin_id=str(author.id), reason=reason, duration=duration)
    else:
        res = {"success": False, "error": "Invalid target type. Use 'user' or 'guild'."}

    if res.get("success"):
        exp_str = duration or "Permanent"
        msg = get_string("security.blacklist_added", "✅ Successfully blacklisted {target_type} `{target_id}`. (Expires: {expires})", target_type=target_type, target_id=target_id, expires=exp_str)
    else:
        msg = f"❌ {res.get('error', 'Operation failed.')}"

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)

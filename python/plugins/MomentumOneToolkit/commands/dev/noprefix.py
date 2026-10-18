from typing import List, Any
from config.settings import settings
from config.strings import get_string
from core.security.noprefix import NoPrefixManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "noprefix"
aliases = ["np"]
description = "Manage prefixless command execution authorization for users."
category = "Dev"
usage = "noprefix <add|remove> <user_id> [duration]"
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
        usage_msg = "Usage: `noprefix <add|remove> <user_id> [duration]`"
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(usage_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(usage_msg)
        return

    action = args[0].lower()
    user_id = args[1].strip()
    duration = args[2] if len(args) > 2 else None

    if action == "add":
        res = NoPrefixManager.grant_no_prefix(user_id, added_by=str(author.id), duration=duration)
        exp_str = duration or "Permanent"
        msg = get_string("security.noprefix_added", "✅ Granted no-prefix authorization to user `{user_id}`. (Expires: {expires})", user_id=user_id, expires=exp_str)
    elif action == "remove":
        res = NoPrefixManager.revoke_no_prefix(user_id, removed_by=str(author.id))
        if res.get("success"):
            msg = get_string("security.noprefix_removed", "✅ Revoked no-prefix authorization from user `{user_id}`.", user_id=user_id)
        else:
            msg = f"❌ {res.get('error')}"
    else:
        msg = "Invalid action. Use `add` or `remove`."

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)

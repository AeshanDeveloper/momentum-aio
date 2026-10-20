import aiohttp
from typing import List, Dict, Any, Optional
import discord

from config.settings import COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize,
)
from discord import MessageFlags, ButtonStyle
import config;

name = "botprofile"
aliases = ["botpfp", "botname", "botbio", "serverprofile"]
description = "Manage the bot's global or server-specific profile."
category = "Owner"
usage = "botprofile <global|server> <avatar|name|bio> <value>"
owner_only = True

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""
    client = getattr(ctx, "client", getattr(message, "client", None))
    guild = getattr(message, "guild", None)

    bot_cfg = getattr(config, "settings", {}).get("bot", {}) if isinstance(getattr(config, "settings", {}), dict) else {}
    owner_ids = [str(o) for o in (bot_cfg.get("owner_ids") or [getattr(config, "OWNER_ID", "")])]

    E = EMOJIS
    C = COLORS

    success_icon = E.get("success") or "✅"
    error_icon = E.get("error") or "❌"
    info_icon = E.get("info") or "💡"

    async def reply(title: str, description: str, is_error: bool = False):
        color = C.get("error", "#EF4444") if is_error else C.get("success", "#10B981")
        box = (
            ContainerBuilder()
            .set_accent_color(color)
            .add_text_display(f"### {error_icon if is_error else success_icon} {title}")
            .add_text_display(description)
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=box.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=box.embed)

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        return await reply("Access Restricted", "This command is strictly restricted to bot owners.", True)

    def show_usage():
        usage_text = "\n".join([
            "**Global profile — changes the bot everywhere**",
            "`!botprofile global avatar <image URL or attachment>`",
            "`!botprofile global name <new name>`",
            "`!botprofile global bio <new bio>`",
            "",
            "**Server profile — changes appearance in this server only**",
            "`!botprofile server avatar <image URL or attachment>`",
            "`!botprofile server name <new name>`",
            "",
            f"{info_icon} Server profile edits require the bot to support the corresponding guild-member profile API."
        ])
        return reply("Bot Profile", usage_text)

    scope = str(args[0]).lower() if len(args) > 0 else ""
    action = str(args[1]).lower() if len(args) > 1 else ""
    value = " ".join(args[2:]).strip() if len(args) > 2 else ""

    if scope not in ["global", "server"] or action not in ["avatar", "name", "bio"]:
        return await show_usage()

    if scope == "server" and not guild:
        return await reply(
            "Server Required",
            "This operation must be run inside the server whose bot profile you want to change.",
            True
        )

    if scope == "server" and action == "bio":
        return await reply(
            "Unsupported Operation",
            "Discord does not provide a general-purpose server-specific bot bio field. The global bio is managed through the bot account profile.",
            True
        )

    image_url = ""
    if action == "avatar":
        attachments = getattr(message, "attachments", [])
        if attachments:
            image_url = attachments[0].url
        else:
            image_url = value

        if not image_url or not image_url.startswith("http"):
            return await reply(
                "Image Required",
                "Attach an image to your message or provide a valid HTTP/HTTPS image URL.",
                True
            )
    elif not value:
        return await reply(
            "Value Required",
            f"Provide a value for the {action}.",
            True
        )

    try:
        if scope == "global":
            if action == "avatar":
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            await client.user.edit(avatar=data)
            elif action == "name":
                await client.user.edit(username=value)
            elif action == "bio":
                return await reply(
                    "Bio Update Unsupported",
                    "Discord API does not expose a standard bot method for changing the bot account's About Me/bio.",
                    True
                )

            author_tag = str(author)
            return await reply(
                "Global Profile Updated",
                f"The bot's global {action} has been updated successfully.\n\n"
                f"**Scope:** Global\n"
                f"**Updated by:** {author_tag}"
            )

        # Server-specific
        if action == "name":
            if guild and hasattr(guild, "me") and guild.me:
                await guild.me.edit(nick=value)
            return await reply(
                "Server Name Updated",
                f"The bot's nickname in **{guild.name}** has been updated.\n\n"
                f"**Nickname:** {value}\n"
                f"**Scope:** This server only"
            )

        if action == "avatar":
            return await reply(
                "Server Avatar Unsupported",
                "The standard Discord API does not expose a general-purpose method to set a bot's guild-specific avatar.",
                True
            )
    except Exception as err:
        return await reply(
            "Update Failed",
            f"Discord rejected the profile change.\n\n```\n{str(err)[:1200]}\n```",
            True
        )

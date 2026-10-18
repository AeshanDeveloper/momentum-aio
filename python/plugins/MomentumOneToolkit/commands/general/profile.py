from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "profile"
aliases = ["userinfo", "whois", "user"]
description = "View your user profile, roles, and account tenure."
category = "General"
usage = "profile [@user]"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)

    target_user = author
    target_member = getattr(message, "member", None)

    # If mention passed in prefix mode
    if getattr(message, "mentions", None) and len(message.mentions) > 0:
        target_user = message.mentions[0]
        if guild:
            target_member = guild.get_member(target_user.id)

    created_ts = int(target_user.created_at.timestamp()) if hasattr(target_user, "created_at") else 0
    joined_ts = int(target_member.joined_at.timestamp()) if (target_member and hasattr(target_member, "joined_at") and target_member.joined_at) else created_ts

    roles_str = "None"
    if target_member and hasattr(target_member, "roles"):
        role_mentions = [r.mention for r in target_member.roles if r.name != "@everyone"]
        if role_mentions:
            roles_str = " ".join(role_mentions[:10])

    title = get_string("commands.profile.title", "User Profile: {username}", username=target_user.name)
    id_str = get_string("commands.profile.discord_id", "• **Discord ID:** `{user_id}`", user_id=target_user.id)
    created_str = get_string("commands.profile.created", "• **Account Created:** <t:{timestamp}:R>", timestamp=created_ts)
    joined_str = get_string("commands.profile.joined", "• **Joined Server:** <t:{timestamp}:R>", timestamp=joined_ts)
    roles_display = get_string("commands.profile.roles", "• **Roles & Badges:**\n  > {badges}", badges=roles_str)
    footer_str = get_string("commands.profile.footer", "MomentumOne Platform Profile")

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {EMOJIS.get('profile', '👤')} {title}")
        .add_separator()
        .add_text_display(f"{id_str}\n{created_str}\n{joined_str}\n\n{roles_display}")
        .set_footer(footer_str)
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
    elif hasattr(message, "channel"):
        await message.channel.send(embed=embed)

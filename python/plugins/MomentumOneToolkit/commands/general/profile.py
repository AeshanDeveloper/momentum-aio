import re
from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from sdk.discord.response import send_response
from apps.bot.discord.permissions.resolver import is_bot_owner
from core.security.blacklist import BlacklistManager
from shared.types.command_record import CommandType

name = "profile"
aliases = ["userinfo", "whois", "user"]
description = "View your user profile, roles, badges, and account tenure."
category = "General"
usage = "profile [@user|userId]"
cooldown = 3.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    client = getattr(ctx, "client", getattr(message, "client", None))

    target_user = author
    target_member = getattr(message, "member", None)

    # Resolve target from args, mentions, or options
    if is_slash:
        # Check interaction options if any
        opts = getattr(message, "data", {}).get("options", [])
        for opt in opts:
            if opt.get("name") == "user" and opt.get("value"):
                val = str(opt["value"])
                try:
                    target_user = await client.fetch_user(int(val)) if client else target_user
                    if guild:
                        target_member = guild.get_member(target_user.id)
                except Exception:
                    pass
    else:
        if getattr(message, "mentions", None) and len(message.mentions) > 0:
            target_user = message.mentions[0]
            if guild:
                target_member = guild.get_member(target_user.id)
        elif args:
            cleaned = re.sub(r"[<@!>]", "", args[0]).strip()
            if re.match(r"^\d{17,20}$", cleaned) and client:
                try:
                    target_user = await client.fetch_user(int(cleaned))
                    if guild:
                        target_member = guild.get_member(target_user.id)
                except Exception:
                    pass

    target_id = str(target_user.id)
    created_ts = int(target_user.created_at.timestamp()) if hasattr(target_user, "created_at") else 0
    joined_ts = int(target_member.joined_at.timestamp()) if (target_member and hasattr(target_member, "joined_at") and target_member.joined_at) else created_ts

    # Badges
    badges = []
    if is_bot_owner(target_id):
        badges.append(get_string("commands.profile.badge_owner", f"{EMOJIS.get('owner', '👑')} **Bot Developer / Owner**"))

    member_role_str = "Member"
    if guild and target_member:
        if getattr(guild, "owner_id", None) == target_user.id:
            member_role_str = "Server Owner"
        elif getattr(getattr(target_member, "guild_permissions", None), "administrator", False):
            member_role_str = "Server Administrator"
        elif getattr(getattr(target_member, "guild_permissions", None), "manage_guild", False):
            member_role_str = "Server Moderator"
    shield_icon = EMOJIS.get("shield") or EMOJIS.get("mod") or "🛡️"
    badges.append(get_string("commands.profile.badge_role", f"{shield_icon} **{member_role_str}**", role=member_role_str))

    bl_status = BlacklistManager.is_user_blacklisted(target_id)
    if bl_status.get("blacklisted"):
        ban_icon = EMOJIS.get("ban") or "🚫"
        badges.append(get_string("commands.profile.badge_blacklisted", f"{ban_icon} **System Blacklisted**"))

    roles_str = "None"
    if target_member and hasattr(target_member, "roles"):
        role_mentions = [r.mention for r in target_member.roles if r.name != "@everyone"]
        if role_mentions:
            roles_str = " ".join(role_mentions[:12])

    title = get_string("commands.profile.title", "User Profile: {username}", username=target_user.name)
    id_str = get_string("commands.profile.discord_id", "• **Discord ID:** `{user_id}`", user_id=target_user.id)
    created_str = get_string("commands.profile.created", "• **Account Created:** <t:{timestamp}:R>", timestamp=created_ts)
    joined_str = get_string("commands.profile.joined", "• **Joined Server:** <t:{timestamp}:R>", timestamp=joined_ts)
    badges_display = "\n".join(f"• {b}" for b in badges)
    roles_display = get_string("commands.profile.roles", "• **Server Roles:**\n  > {badges}", badges=roles_str)
    footer_str = get_string("commands.profile.footer", "MomentumOne Identity Ledger")

    view = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("error", "#EF4444") if bl_status.get("blacklisted") else COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {EMOJIS.get('profile', '👤')} {title}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"**Identity & Access**\n{badges_display}\n\n{id_str}\n{created_str}\n{joined_str}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(roles_display)
        .set_footer(footer_str)
        .build()
    )

    return await send_response(message, view)

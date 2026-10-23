import re
import asyncio
from typing import List, Any, Optional, Tuple
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from sdk.discord.response import send_response, send_ui
from apps.bot.discord.permissions.permission import Permissions
from apps.bot.discord.permissions.resolver import has_permission
from shared.types.command_record import CommandType
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity

name = "channel"
aliases = ["ch", "channelctl"]
description = "Manage channels: slowmode, lock, unlock, hide, unhide, delete, nuke, and info."
category = "Moderation"
usage = "channel <slowmode|lock|unlock|hide|unhide|delete|nuke|delete nuke|info> [#channel] [args...]"
cooldown = 3.0
user_permissions = [Permissions.MANAGE_CHANNELS]
bot_permissions = [Permissions.MANAGE_CHANNELS]
guild_only = True

# Guard against duplicate concurrent nuke operations on the same channel
_nuke_in_flight: set[int] = set()


def _parse_duration_seconds(raw: Optional[str]) -> Optional[int]:
    """Parse slowmode duration into seconds (0 to 21600). Returns None if invalid."""
    if raw is None:
        return None
    raw_str = raw.strip().lower()
    if raw_str in ["0", "off", "none", "disable", "disabled"]:
        return 0
    if raw_str.endswith("s"):
        raw_str = raw_str[:-1]
    elif raw_str.endswith("m"):
        try:
            return int(float(raw_str[:-1]) * 60)
        except ValueError:
            return None
    elif raw_str.endswith("h"):
        try:
            return int(float(raw_str[:-1]) * 3600)
        except ValueError:
            return None

    try:
        val = int(raw_str)
        return val
    except ValueError:
        return None


def _resolve_channel(guild: discord.Guild, args: List[str], message: Any) -> Tuple[Optional[Any], List[str]]:
    """
    Extracts target channel from message mentions or argument list.
    Returns (channel, remaining_args).
    """
    # 1. Mention in message
    if getattr(message, "channel_mentions", None) and len(message.channel_mentions) > 0:
        target = message.channel_mentions[0]
        # Filter out the mention from args
        remaining = [a for a in args if not re.match(r"^<#\d{17,20}>$", a)]
        return target, remaining

    # 2. Look for channel mention or ID or name in args
    for i, arg in enumerate(args):
        m = re.match(r"^<#(\d{17,20})>$", arg)
        if m:
            ch_id = int(m.group(1))
            ch = guild.get_channel(ch_id)
            if ch:
                remaining = args[:i] + args[i+1:]
                return ch, remaining

        if re.match(r"^\d{17,20}$", arg):
            ch_id = int(arg)
            ch = guild.get_channel(ch_id)
            if ch:
                remaining = args[:i] + args[i+1:]
                return ch, remaining

    # 3. Default to message channel
    return getattr(message, "channel", None), args


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if str(command_type).lower() == "slash" else getattr(message, "author", None)
    author_perms = message.channel.permissions_for(author) if (author and hasattr(message.channel, "permissions_for")) else None
    
    # Check user MANAGE_CHANNELS permission or MomentumOne virtual moderator authorization
    is_admin = getattr(author_perms, "administrator", False) if author_perms else False
    has_manage_ch = getattr(author_perms, "manage_channels", False) if author_perms else False
    from core.security.server_commands import ServerCommandManager
    is_virtual_mod = ServerCommandManager.is_authorized_moderator(str(guild.id), author, "channel")

    if not (is_admin or has_manage_ch or is_virtual_mod):
        return await send_ui(message, "permissions.missing_user_permission", variables={"permissions": "`Manage Channels`"}, style="error")

    if not args:
        args = ["info"]

    sub = args[0].lower()
    sub_args = args[1:]

    # Handle "channel delete nuke"
    if sub == "delete" and len(sub_args) > 0 and sub_args[0].lower() == "nuke":
        sub = "nuke"
        sub_args = sub_args[1:]

    # Resolve target channel
    target_channel, remaining_args = _resolve_channel(guild, sub_args, message)
    if not target_channel or not hasattr(target_channel, "id"):
        return await send_ui(message, "commands.channel.channel_not_found", style="warning")

    # Validate bot permissions on target channel
    me = getattr(guild, "me", None)
    if me:
        bot_channel_perms = target_channel.permissions_for(me)
        if not (bot_channel_perms.manage_channels or me.guild_permissions.manage_channels):
            return await send_ui(
                message,
                "commands.channel.bot_missing_perms",
                variables={"channel_id": str(target_channel.id)},
                style="error"
            )

    # 1. SLOWMODE
    if sub == "slowmode":
        if not hasattr(target_channel, "edit") or not hasattr(target_channel, "slowmode_delay"):
            return await send_ui(message, "commands.channel.not_text", style="warning")

        raw_duration = remaining_args[0] if remaining_args else None
        if raw_duration is None:
            # Report current slowmode
            cur_delay = getattr(target_channel, "slowmode_delay", 0)
            cur_icon = EMOJIS.get("cooldown") or "⏳"
            view = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {cur_icon} Channel Slowmode")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Slowmode for <#{target_channel.id}> is currently set to `{cur_delay}s`.")
                .set_footer("Specify duration (e.g. 10s, 5m, 1h, 0) to change.")
                .build()
            )
            return await send_response(message, view)

        seconds = _parse_duration_seconds(raw_duration)
        if seconds is None or seconds < 0 or seconds > 21600:
            return await send_ui(message, "commands.channel.slowmode_invalid", style="warning")

        try:
            await target_channel.edit(slowmode_delay=seconds)
            if seconds == 0:
                return await send_ui(
                    message,
                    "commands.channel.slowmode",
                    description=get_string(
                        "commands.channel.slowmode.disabled_description",
                        f"{EMOJIS.get('check', '✅')} Slowmode for <#{target_channel.id}> has been disabled.",
                        channel_id=target_channel.id
                    ),
                    variables={"channel_id": str(target_channel.id), "seconds": 0},
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Slowmode Updated",
                    description=f"Slowmode delay for {target_channel.mention} was adjusted.",
                    actor=author,
                    target=target_channel,
                    reason=f"Set slowmode to {seconds}s",
                    fields=[{"name": "Slowmode Seconds", "value": f"`{seconds}s`", "inline": True}],
                    severity=LogSeverity.INFO,
                )
            )
            if seconds == 0:
                return await send_ui(
                    message,
                    "commands.channel.slowmode_disabled",
                    variables={"channel_id": str(target_channel.id)},
                    style="success"
                )
            else:
                return await send_ui(
                    message,
                    "commands.channel.slowmode",
                    variables={"channel_id": str(target_channel.id), "seconds": seconds},
                    style="success"
                )
        except Exception as err:
            return await send_ui(message, "common.error", variables={"message": f"Failed to update slowmode: {err}"}, style="error")

    # 2. LOCK
    elif sub == "lock":
        reason = " ".join(remaining_args).strip() or f"Channel locked by {author}"
        try:
            overwrite = target_channel.overwrites_for(guild.default_role)
            overwrite.send_messages = False
            if hasattr(overwrite, "send_messages_in_threads"):
                overwrite.send_messages_in_threads = False
            await target_channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Locked",
                    description=f"{target_channel.mention} was locked (@everyone send permissions revoked).",
                    actor=author,
                    target=target_channel,
                    reason=reason,
                    severity=LogSeverity.MEDIUM,
                )
            )
            return await send_ui(
                message,
                "commands.channel.locked",
                variables={"channel_id": str(target_channel.id)},
                style="warning"
            )
        except Exception as err:
            return await send_ui(
                message,
                "commands.channel.error_lock",
                variables={"error": str(err)},
                style="error"
            )

    # 3. UNLOCK
    elif sub == "unlock":
        reason = " ".join(remaining_args).strip() or f"Channel unlocked by {author}"
        try:
            overwrite = target_channel.overwrites_for(guild.default_role)
            overwrite.send_messages = None
            if hasattr(overwrite, "send_messages_in_threads"):
                overwrite.send_messages_in_threads = None
            await target_channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Unlocked",
                    description=f"{target_channel.mention} was unlocked (@everyone send permissions restored).",
                    actor=author,
                    target=target_channel,
                    reason=reason,
                    severity=LogSeverity.LOW,
                )
            )
            return await send_ui(
                message,
                "commands.channel.unlocked",
                variables={"channel_id": str(target_channel.id)},
                style="success"
            )
        except Exception as err:
            return await send_ui(
                message,
                "commands.channel.error_unlock",
                variables={"error": str(err)},
                style="error"
            )

    # 4. HIDE
    elif sub == "hide":
        reason = " ".join(remaining_args).strip() or f"Channel hidden by {author}"
        try:
            overwrite = target_channel.overwrites_for(guild.default_role)
            overwrite.view_channel = False
            await target_channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Hidden",
                    description=f"{target_channel.mention} view permissions removed for @everyone.",
                    actor=author,
                    target=target_channel,
                    reason=reason,
                    severity=LogSeverity.MEDIUM,
                )
            )
            return await send_ui(
                message,
                "commands.channel.hidden",
                variables={"channel_id": str(target_channel.id)},
                style="warning"
            )
        except Exception as err:
            return await send_ui(message, "common.error", variables={"message": f"Failed to hide channel: {err}"}, style="error")

    # 5. UNHIDE
    elif sub == "unhide":
        reason = " ".join(remaining_args).strip() or f"Channel unhidden by {author}"
        try:
            overwrite = target_channel.overwrites_for(guild.default_role)
            overwrite.view_channel = None
            await target_channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Unhidden",
                    description=f"{target_channel.mention} view permissions restored for @everyone.",
                    actor=author,
                    target=target_channel,
                    reason=reason,
                    severity=LogSeverity.LOW,
                )
            )
            return await send_ui(
                message,
                "commands.channel.unhidden",
                variables={"channel_id": str(target_channel.id)},
                style="success"
            )
        except Exception as err:
            return await send_ui(message, "common.error", variables={"message": f"Failed to unhide channel: {err}"}, style="error")

    # 6. DELETE
    elif sub == "delete":
        ch_name = getattr(target_channel, "name", "channel")
        target_is_current = (target_channel.id == message.channel.id)
        try:
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Deleted",
                    description=f"Channel `#{ch_name}` (`{target_channel.id}`) was permanently deleted.",
                    actor=author,
                    target=f"#{ch_name} ({target_channel.id})",
                    reason=f"Deleted by {author}",
                    severity=LogSeverity.HIGH,
                )
            )
            await target_channel.delete(reason=f"Channel deleted by {author}")
            if not target_is_current:
                return await send_ui(
                    message,
                    "commands.channel.deleted",
                    variables={"name": ch_name},
                    style="success"
                )
        except Exception as err:
            return await send_ui(message, "common.error", variables={"message": f"Failed to delete channel: {err}"}, style="error")

    # 7. NUKE / DELETE NUKE
    elif sub in ["nuke"]:
        if target_channel.id in _nuke_in_flight:
            return await send_ui(
                message,
                "commands.channel.nuke_in_progress",
                variables={"channel_id": str(target_channel.id)},
                style="warning"
            )

        _nuke_in_flight.add(target_channel.id)
        try:
            old_position = getattr(target_channel, "position", 0)
            old_name = getattr(target_channel, "name", "channel")

            new_channel = await target_channel.clone(reason=f"Channel nuke by {author}")
            try:
                await new_channel.edit(position=old_position)
            except Exception:
                pass

            await target_channel.delete(reason=f"Channel nuke by {author}")
            asyncio.create_task(
                UnifiedWebhookLogger.dispatch_log(
                    guild=guild,
                    category=LogCategory.CHANNELS,
                    title="Channel Nuked & Recreated",
                    description=f"Channel `#{old_name}` was nuked and cloned into {new_channel.mention}.",
                    actor=author,
                    target=new_channel,
                    reason=f"Nuked by {author}",
                    severity=LogSeverity.HIGH,
                )
            )

            # Send nuke container into the newly created channel
            return await send_ui(
                new_channel,
                "commands.channel.nuked",
                style="success"
            )
        except Exception as err:
            return await send_ui(message, "common.error", variables={"message": f"Failed to nuke channel: {err}"}, style="error")
        finally:
            _nuke_in_flight.discard(target_channel.id)

    # 8. INFO (Default)
    else:
        title = get_string("commands.channel.info_title", "Channel Metrics: #{name}", name=target_channel.name)
        id_str = get_string("commands.channel.id", "• **Channel ID:** `{channel_id}`", channel_id=target_channel.id)
        type_str = get_string("commands.channel.type", "• **Type:** `{channel_type}`", channel_type=str(target_channel.type))
        created_ts = int(target_channel.created_at.timestamp()) if hasattr(target_channel, "created_at") else 0
        created_str = get_string("commands.channel.created", "• **Created:** <t:{timestamp}:R>", timestamp=created_ts)
        slowmode_sec = getattr(target_channel, "slowmode_delay", 0)
        slowmode_str = f"• **Slowmode:** `{slowmode_sec}s`"

        view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('chart', '📊')} {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{id_str}\n{type_str}\n{slowmode_str}\n{created_str}")
            .set_footer(f"Guild: {guild.name}")
            .build()
        )
        return await send_response(message, view)

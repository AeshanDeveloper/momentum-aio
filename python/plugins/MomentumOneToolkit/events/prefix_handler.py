import time
import discord
from typing import Any
from config.settings import settings
from config.strings import get_string
from core.logging.logger import logger
from core.logging.error_tracker import ErrorTracker
from core.security.blacklist import BlacklistManager
from core.security.noprefix import NoPrefixManager
from core.security.antispam import AntiSpamService
from core.security.cooldown import CooldownManager
from core.security.server_commands import ServerCommandManager
from core.telemetry.observability import ObservabilityManager
from apps.bot.discord.permissions.resolver import check_permissions, is_bot_owner
from apps.bot.discord.commands.registry import commands_registry
from sdk.discord import send_ui, send_response
from shared.types.command_record import CommandType, CommandStatus

name = "messageCreate"
description = "Official prefix command handler ~ By MomentumOne"

# Prevent the same Discord message from being processed twice.
_processed_messages: set[int] = set()


async def execute(ctx: Any, message: discord.Message):
    try:
        if not message.author or message.author.bot:
            return

        # Duplicate-message guard (the only addition).
        if message.id in _processed_messages:
            return

        _processed_messages.add(message.id)

        if len(_processed_messages) > 10_000:
            _processed_messages.clear()
            _processed_messages.add(message.id)

        # 1. Global User Blacklist Check
        user_bl = BlacklistManager.is_user_blacklisted(str(message.author.id))
        if user_bl.get("blacklisted"):
            return

        # 2. Global Guild Blacklist Check
        if message.guild:
            guild_bl = BlacklistManager.is_guild_blacklisted(str(message.guild.id))
            if guild_bl.get("blacklisted"):
                return

        configured_prefix = settings.BOT_PREFIX or "$"
        valid_prefixes = [configured_prefix, "."]
        matched_prefix = next((p for p in valid_prefixes if message.content.startswith(p)), None)
        content = ""
        is_no_prefix = False

        if matched_prefix:
            content = message.content[len(matched_prefix):].strip()
        else:
            if NoPrefixManager.has_no_prefix(str(message.author.id)):
                content = message.content.strip()
                is_no_prefix = True
            else:
                return

        if not content:
            return

        args = content.split()
        command_name = args.pop(0).lower()
        if not command_name:
            return

        found_command = commands_registry.get(command_name)
        if not found_command or found_command.status != CommandStatus.ACTIVE or not found_command.enabled:
            return

        # 3. Anti-Spam Check
        spam_result = AntiSpamService.check(str(message.author.id))
        if not spam_result.get("allowed"):
            if spam_result.get("blacklisted"):
                await send_ui(message, "antispam.blacklisted", style="error")
            elif spam_result.get("warning"):
                await send_ui(
                    message,
                    "antispam.warning",
                    variables={
                        "count": spam_result.get("infraction_count", 5),
                        "max": AntiSpamService.MAX_PER_WINDOW
                    },
                    style="warning"
                )
            return

        # 4. Owner-Only Check
        if found_command.owner_only and not is_bot_owner(str(message.author.id)):
            await send_ui(message, "permissions.owner_only", style="error")
            return

        # 5. Guild Only Check
        if found_command.guild_only and not message.guild:
            await send_ui(message, "permissions.guild_only", style="warning")
            return

        # 6. Server Command Disabled Check
        if message.guild:
            if ServerCommandManager.is_command_disabled(str(message.guild.id), found_command.name):
                await send_ui(
                    message,
                    "permissions.command_disabled",
                    variables={"command": found_command.name},
                    style="warning"
                )
                return

            # 7. Proper Permissions Check
            perms = check_permissions(
                member=message.author,
                bot_member=message.guild.me,
                user_perms=found_command.user_permissions,
                bot_perms=found_command.bot_permissions
            )
            if not perms.get("allowed"):
                if perms.get("missing_user"):
                    missing_str = ", ".join(perms.get("missing_user_names", []))
                    await send_ui(
                        message,
                        "permissions.missing_user_permission",
                        variables={"permissions": missing_str},
                        style="error"
                    )
                    return

                if perms.get("missing_bot"):
                    missing_str = ", ".join(perms.get("missing_bot_names", []))
                    await send_ui(
                        message,
                        "permissions.missing_bot_permission",
                        variables={"permissions": missing_str},
                        style="error"
                    )
                    return

        # 8. Cooldown Check
        guild_id = str(message.guild.id) if message.guild else None
        cd_check = CooldownManager.check(found_command, str(message.author.id), guild_id)
        if cd_check.get("on_cooldown"):
            rem = cd_check.get("remaining_seconds", 1.0)
            await send_ui(
                message,
                "common.cooldown",
                variables={"remaining": round(rem, 1), "command": command_name},
                style="warning"
            )
            return

        CooldownManager.apply(found_command, str(message.author.id), guild_id)

        # 9. Execute Command
        start_time = time.time()
        try:
            cmd_result = await found_command.execute(ctx, CommandType.PREFIX, message, args)
            if cmd_result is not None:
                await send_response(message, cmd_result)
            dur_ms = round((time.time() - start_time) * 1000, 2)
            ObservabilityManager.record_command(found_command.name, "prefix", True, dur_ms)
        except Exception as exec_err:
            dur_ms = round((time.time() - start_time) * 1000, 2)
            ObservabilityManager.record_command(found_command.name, "prefix", False, dur_ms, str(exec_err))
            error_record = await ErrorTracker.record(command_name, exec_err, {
                "user_id": str(message.author.id),
                "username": message.author.name,
                "guild_id": guild_id,
                "command_type": "PREFIX",
                "args": args,
            })
            await send_ui(
                message,
                "common.unexpected_error",
                variables={
                    "command": command_name,
                    "error_id": error_record["error_id"],
                    "error": str(exec_err)[:180],
                },
                style="error"
            )

    except Exception as err:
        logger.error(f"[PrefixHandler] Uncaught dispatcher error: {err}")
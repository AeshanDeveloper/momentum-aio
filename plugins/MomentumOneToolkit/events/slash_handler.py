import time
import discord
from typing import Any
from config.settings import settings
from config.strings import get_string
from core.logging.logger import logger
from core.logging.error_tracker import ErrorTracker
from core.security.blacklist import BlacklistManager
from core.security.antispam import AntiSpamService
from core.security.cooldown import CooldownManager
from core.security.server_commands import ServerCommandManager
from core.telemetry.observability import ObservabilityManager
from apps.bot.discord.permissions.resolver import check_permissions, is_bot_owner
from apps.bot.discord.commands.registry import commands_registry
from sdk.discord import send_ui, send_response
from shared.types.command_record import CommandType, CommandStatus

name = "interactionCreate"
description = "Official interaction & slash command dispatcher"

async def execute(ctx: Any, interaction: discord.Interaction):
    try:
        if interaction.type != discord.InteractionType.application_command:
            return

        command_name = interaction.command_name.lower() if hasattr(interaction, "command_name") else interaction.data.get("name", "").lower()
        if not command_name:
            return

        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        # 1. Blacklist check
        if BlacklistManager.is_user_blacklisted(user_id).get("blacklisted"):
            await send_ui(interaction, "permissions.blacklisted_user", ephemeral=True, style="error")
            return

        if guild_id and BlacklistManager.is_guild_blacklisted(guild_id).get("blacklisted"):
            await send_ui(interaction, "permissions.blacklisted_guild", ephemeral=True, style="error")
            return

        # 2. Command lookup
        cmd = commands_registry.get(command_name)
        if not cmd or cmd.status != CommandStatus.ACTIVE or not cmd.enabled:
            await send_ui(interaction, "commands.help.not_found", variables={"name": command_name}, ephemeral=True, style="warning")
            return

        # 3. Owner check
        if cmd.owner_only and not is_bot_owner(user_id):
            await send_ui(interaction, "permissions.owner_only", ephemeral=True, style="error")
            return

        # 4. Anti-spam
        spam_result = AntiSpamService.check(user_id)
        if not spam_result.get("allowed"):
            if spam_result.get("blacklisted"):
                await send_ui(interaction, "antispam.blacklisted", ephemeral=True, style="error")
            else:
                await send_ui(
                    interaction,
                    "antispam.warning",
                    variables={
                        "count": spam_result.get("infraction_count", 5),
                        "max": AntiSpamService.MAX_PER_WINDOW
                    },
                    ephemeral=True,
                    style="warning"
                )
            return

        # 5. Server command disable check
        if guild_id and ServerCommandManager.is_command_disabled(guild_id, cmd.name):
            await send_ui(
                interaction,
                "permissions.command_disabled",
                variables={"command": cmd.name},
                ephemeral=True,
                style="warning"
            )
            return

        # 6. Cooldown
        cd_check = CooldownManager.check(cmd, user_id, guild_id)
        if cd_check.get("on_cooldown"):
            rem = cd_check.get("remaining_seconds", 1.0)
            await send_ui(
                interaction,
                "common.cooldown",
                variables={"remaining": round(rem, 1), "command": cmd.name},
                ephemeral=True,
                style="warning"
            )
            return

        CooldownManager.apply(cmd, user_id, guild_id)

        # Recursively parse slash options into args (supporting subcommands and parameters)
        def _extract_slash_args(opts_list):
            out = []
            for opt in (opts_list or []):
                # Type 1 = SUB_COMMAND, Type 2 = SUB_COMMAND_GROUP
                if opt.get("type") in (1, 2) or ("value" not in opt and "options" in opt):
                    out.append(str(opt.get("name", "")))
                    out.extend(_extract_slash_args(opt.get("options", [])))
                elif "value" in opt:
                    out.append(str(opt.get("value", "")))
                elif "name" in opt and opt.get("type") is not None:
                    out.append(str(opt.get("name", "")))
            return [x for x in out if x]

        options = interaction.data.get("options", [])
        args = _extract_slash_args(options)

        start_time = time.time()
        try:
            cmd_result = await cmd.execute(ctx, CommandType.SLASH, interaction, args)
            if cmd_result is not None:
                await send_response(interaction, cmd_result)
            dur_ms = round((time.time() - start_time) * 1000, 2)
            ObservabilityManager.record_command(cmd.name, "slash", True, dur_ms)
        except Exception as exec_err:
            dur_ms = round((time.time() - start_time) * 1000, 2)
            ObservabilityManager.record_command(cmd.name, "slash", False, dur_ms, str(exec_err))
            error_record = await ErrorTracker.record(cmd.name, exec_err, {
                "user_id": user_id,
                "username": interaction.user.name,
                "guild_id": guild_id,
                "command_type": "SLASH",
                "args": args
            })
            await send_ui(
                interaction,
                "common.unexpected_error",
                variables={
                    "command": cmd.name,
                    "error_id": error_record["error_id"],
                    "error": str(exec_err)[:150],
                },
                ephemeral=True,
                style="error"
            )

    except Exception as err:
        logger.error(f"[SlashHandler] Interaction processing error: {err}")

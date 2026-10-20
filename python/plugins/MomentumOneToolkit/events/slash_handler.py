import time
import discord
from typing import Any
from config.settings import settings, COLORS, EMOJIS
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
from sdk.discord.builders import ContainerBuilder
from sdk.discord.response import send_response
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
            await interaction.response.send_message(get_string("permissions.blacklisted_user", "🚫 You are blacklisted from executing commands."), ephemeral=True)
            return

        if guild_id and BlacklistManager.is_guild_blacklisted(guild_id).get("blacklisted"):
            await interaction.response.send_message(get_string("permissions.blacklisted_guild", "🚫 This server is blacklisted from executing commands."), ephemeral=True)
            return

        # 2. Command lookup
        cmd = commands_registry.get(command_name)
        if not cmd or cmd.status != CommandStatus.ACTIVE or not cmd.enabled:
            await interaction.response.send_message(f"❌ Command `{command_name}` is unavailable.", ephemeral=True)
            return

        # 3. Owner check
        if cmd.owner_only and not is_bot_owner(user_id):
            await interaction.response.send_message(get_string("permissions.owner_only", "❌ Access Denied: Global bot owner only."), ephemeral=True)
            return

        # 4. Anti-spam
        spam_result = AntiSpamService.check(user_id)
        if not spam_result.get("allowed"):
            warn = spam_result.get("warning", "Rate limit exceeded.")
            await interaction.response.send_message(warn, ephemeral=True)
            return

        # 5. Server command disable check
        if guild_id and ServerCommandManager.is_command_disabled(guild_id, cmd.name):
            await interaction.response.send_message(f"⛔ Command `{cmd.name}` is disabled on this server.", ephemeral=True)
            return

        # 6. Cooldown
        cd_check = CooldownManager.check(cmd, user_id, guild_id)
        if cd_check.get("on_cooldown"):
            rem = cd_check.get("remaining_seconds", 1.0)
            await interaction.response.send_message(f"⏳ Cooldown active: please wait `{rem}s`.", ephemeral=True)
            return

        CooldownManager.apply(cmd, user_id, guild_id)

        # Parse options into args
        options = interaction.data.get("options", [])
        args = [str(opt.get("value", "")) for opt in options if "value" in opt]

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
            err_msg = f"❌ Execution error: `{str(exec_err)[:150]}` (Error ID: `{error_record['error_id']}`)"
            await send_response(interaction, err_msg, ephemeral=True)

    except Exception as err:
        logger.error(f"[SlashHandler] Interaction processing error: {err}")

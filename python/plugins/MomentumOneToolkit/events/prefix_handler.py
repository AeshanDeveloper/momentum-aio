import time
import discord
from typing import Any
from config.settings import settings, COLORS, EMOJIS
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
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType, CommandStatus

name = "messageCreate"
description = "Official prefix command handler ~ By MomentumOne"

async def execute(ctx: Any, message: discord.Message):
    try:
        if not message.author or message.author.bot:
            return

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
            # Check No-Prefix authorization
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
                blocked_embed = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("error", "#B21F1F"))
                    .add_text_display(f"### {EMOJIS.get('ban', '🚫')} Command Rejected")
                    .add_separator()
                    .add_text_display(get_string("antispam.blacklisted", "🚫 You have been automatically blacklisted for excessive command spam."))
                    .build()
                )
                await message.reply(embed=blocked_embed)
            elif spam_result.get("warning"):
                await message.reply(content=spam_result["warning"])
            return

        # 4. Owner-Only Check
        if found_command.owner_only and not is_bot_owner(str(message.author.id)):
            return

        # 5. Guild Only Check
        if found_command.guild_only and not message.guild:
            guild_only_msg = get_string("permissions.guild_only", "❌ This command can only be used inside a Discord server.")
            await message.reply(content=guild_only_msg)
            return

        # 6. Server Command Disabled Check
        if message.guild:
            if ServerCommandManager.is_command_disabled(str(message.guild.id), found_command.name):
                disabled_embed = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("warn", "#F59E0B"))
                    .add_text_display(f"### ⚠️ Command Disabled in Server")
                    .add_separator()
                    .add_text_display(f"The command `{found_command.name}` has been disabled by server administrators.")
                    .build()
                )
                await message.reply(embed=disabled_embed)
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
                    err_text = get_string("permissions.missing_user_permission", "❌ You lack the required permission(s) to execute this command: {permissions}", permissions=missing_str)
                    perm_embed = (
                        ContainerBuilder()
                        .set_accent_color(COLORS.get("error", "#B21F1F"))
                        .add_text_display(f"### {EMOJIS.get('error', '❌')} Access Denied")
                        .add_separator()
                        .add_text_display(err_text)
                        .build()
                    )
                    await message.reply(embed=perm_embed)
                    return

                if perms.get("missing_bot"):
                    missing_str = ", ".join(perms.get("missing_bot_names", []))
                    err_text = get_string("permissions.missing_bot_permission", "❌ The bot lacks required permission(s) in this channel: {permissions}", permissions=missing_str)
                    perm_embed = (
                        ContainerBuilder()
                        .set_accent_color(COLORS.get("error", "#B21F1F"))
                        .add_text_display(f"### {EMOJIS.get('error', '❌')} Bot Missing Permissions")
                        .add_separator()
                        .add_text_display(err_text)
                        .build()
                    )
                    await message.reply(embed=perm_embed)
                    return

        # 8. Cooldown Check
        guild_id = str(message.guild.id) if message.guild else None
        cd_check = CooldownManager.check(found_command, str(message.author.id), guild_id)
        if cd_check.get("on_cooldown"):
            rem = cd_check.get("remaining_seconds", 1.0)
            cd_msg = get_string("cooldown.active", "⏳ **Cooldown Active**: Please wait `{remaining}s` before using `{command}` again.", remaining=rem, command=command_name)
            cd_embed = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warn", "#F59E0B"))
                .add_text_display(f"### ⏱️ Cooldown Active")
                .add_separator()
                .add_text_display(cd_msg)
                .build()
            )
            await message.reply(embed=cd_embed)
            return

        # Apply Cooldown
        CooldownManager.apply(found_command, str(message.author.id), guild_id)

        # 9. Execute Command
        start_time = time.time()
        try:
            await found_command.execute(ctx, CommandType.PREFIX, message, args)
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
            err_embed = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#B21F1F"))
                .add_text_display(f"### {EMOJIS.get('error', '❌')} Command Execution Error")
                .add_separator()
                .add_text_display(
                    f"An error occurred while executing `{command_name}`.\n\n"
                    f"• **Error ID:** `{error_record['error_id']}`\n"
                    f"• **Summary:** `{str(exec_err)[:180]}`\n\n"
                    f"-# Please provide this Error ID to the bot administrator."
                )
                .build()
            )
            await message.reply(embed=err_embed)

    except Exception as err:
        logger.error(f"[PrefixHandler] Uncaught dispatcher error: {err}")

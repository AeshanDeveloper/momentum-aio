import math
import time
import json
from typing import List, Dict, Any, Optional
import discord

from config.settings import COLORS, EMOJIS
from core.audit.audit_log import AuditLog
from core.logging.error_tracker import ErrorTracker
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    SeparatorSpacingSize,
)
from discord import MessageFlags, ButtonStyle

PAGE_SIZE = 5

name = "audit"
aliases = ["auditlog", "auditlogs", "logs"]
description = "Scroll through system audit logs and inspect recorded command errors (Bot Owner Only)."
category = "Owner"
usage = "audit [page|filter <action>|view <auditId>|errors [page]|error <errorId>]"
owner_only = True

sub_commands = [
    {"name": "list [page]", "description": "Scroll through system audit logs."},
    {"name": "filter <action>", "description": "Filter audit logs by specific action name."},
    {"name": "view <auditId>", "description": "Inspect full details of an audit log entry."},
    {"name": "errors [page]", "description": "Scroll through recorded command errors."},
    {"name": "error <errorId>", "description": "Inspect detailed error trace and metadata by Error ID."},
]

def format_unix(date_val: Any) -> int:
    if isinstance(date_val, (int, float)):
        return int(date_val)
    return int(time.time())

def build_audit_detail_container(entry: Dict[str, Any], emojis: Dict[str, str], colors: Dict[str, str]):
    unix = format_unix(entry.get("timestamp"))
    is_success = bool(entry.get("success", True))
    status_emoji = emojis["success"] if is_success else emojis["error"]

    audit_id = entry.get("audit_id") or entry.get("auditId", "N/A")
    action = entry.get("action", "unknown")
    status_text = "Success" if is_success else "Failed"
    actor_id = entry.get("actor_id") or entry.get("actorId")
    actor_type = entry.get("actor_type") or entry.get("actorType", "system")
    actor_str = f"`{actor_type}` ({f'<@{actor_id}> (`{actor_id}`)' if actor_id else 'System'})"

    res_type = entry.get("resource_type") or entry.get("resourceType", "N/A")
    res_id = entry.get("resource_id") or entry.get("resourceId", "N/A")
    guild_id = entry.get("guild_id") or entry.get("guildId") or "N/A"

    details = (
        f"• **Audit ID:** `{audit_id}`\n"
        f"• **Action:** `{action}`\n"
        f"• **Status:** {status_emoji} {status_text}\n"
        f"• **Timestamp:** <t:{unix}:F> (<t:{unix}:R>)\n"
        f"• **Actor:** {actor_str}\n"
        f"• **Resource:** `{res_type}` ({res_id})\n"
        f"• **Guild ID:** `{guild_id}`\n"
    )

    if entry.get("error"):
        details += f"• **Error Message:** `{entry.get('error')}`\n"

    changed = entry.get("changed_fields") or entry.get("changedFields")
    if changed:
        details += f"• **Changed Fields:** `{'`, `'.join(changed)}`\n"

    state_block = ""
    new_state = entry.get("new_state") or entry.get("newState")
    if new_state:
        try:
            str_json = json.dumps(new_state, indent=2)[:800]
            state_block = f"\n**State Payload:**\n```json\n{str_json}\n```"
        except Exception:
            pass

    return (
        ContainerBuilder()
        .set_accent_color(colors["default"] if is_success else colors["error"])
        .add_text_display(f"### {emojis['audit']} Audit Log Inspector")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(details + state_block)
        .build()
    )

def build_error_detail_container(record: Dict[str, Any], emojis: Dict[str, str], colors: Dict[str, str]):
    unix = format_unix(record.get("timestamp"))
    u_id = record.get("user_id") or record.get("userId")
    user_display = f"<@{u_id}> (`{u_id}`)" if u_id else "N/A"
    g_id = record.get("guild_id") or record.get("guildId")
    guild_display = f"`{g_id}`" if g_id else "Direct Message / Global"
    type_display = record.get("command_type") or record.get("commandType", "UNKNOWN")
    raw_args = record.get("args")
    args_display = f"`{' '.join(raw_args)}`" if raw_args else "_None_"
    raw_stack = record.get("stack") or record.get("message") or "No stack trace recorded."
    stack_text = str(raw_stack)[:1200]
    err_id = record.get("error_id") or record.get("errorId", "ERR")
    cmd_name = record.get("command_name") or record.get("commandName", "Unknown")

    desc = (
        f"• **Error ID:** `{err_id}`\n"
        f"• **Command:** `{cmd_name}` ({type_display})\n"
        f"• **Timestamp:** <t:{unix}:F> (<t:{unix}:R>)\n"
        f"• **Invoker:** {user_display}\n"
        f"• **Guild:** {guild_display}\n"
        f"• **Arguments:** {args_display}\n"
        f"• **Error Summary:** `{record.get('message')}`\n\n"
        f"**Stack Trace:**\n```python\n{stack_text}\n```"
    )

    return (
        ContainerBuilder()
        .set_accent_color(colors["error"])
        .add_text_display(f"### {emojis['error']} Command Execution Error")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .build()
    )

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    bot_cfg = getattr(config, "settings", {}).get("bot", {}) if isinstance(getattr(config, "settings", {}), dict) else {}
    owner_ids = [str(o) for o in (bot_cfg.get("owner_ids") or [getattr(config, "OWNER_ID", "")])]

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is restricted to bot owners."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(denied_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(denied_msg)
        return

    E = EMOJIS
    C = COLORS

    emojis = {
        "audit": E.get("history") or E.get("info") or "📜",
        "error": E.get("error") or "❌",
        "success": E.get("success") or "✅",
        "warning": E.get("warning") or "⚠️",
        "time": E.get("time") or "⏱️",
        "cmd": E.get("cmd") or "⚡",
        "user": E.get("user") or "👤",
        "server": E.get("server") or "🌐",
    }

    colors = {
        "default": C.get("default", "#3B82F6"),
        "success": C.get("success", "#10B981"),
        "error": C.get("error", "#EF4444"),
        "warning": C.get("warning", "#F59E0B"),
    }

    sub = args[0].lower() if args else None

    # Subcommand: error <id>
    if sub == "error":
        error_id = args[1].strip() if len(args) > 1 else None
        if not error_id:
            text = "⚠️ Please specify an Error ID (e.g. `ERR-A1B2C3D4`)."
            return await (message.response.send_message(text, ephemeral=True) if is_slash else message.reply(text))
        record = await ErrorTracker.get(error_id)
        if not record:
            text = f"❌ Error with ID `{error_id}` was not found in the database."
            return await (message.response.send_message(text, ephemeral=True) if is_slash else message.reply(text))
        container = build_error_detail_container(record, emojis, colors)
        return await (message.response.send_message(embed=container.embed) if is_slash else message.reply(embed=container.embed))

    # Subcommand: view <auditId>
    if sub == "view":
        audit_id = args[1].strip() if len(args) > 1 else None
        if not audit_id:
            text = "⚠️ Please specify an Audit ID."
            return await (message.response.send_message(text, ephemeral=True) if is_slash else message.reply(text))
        entry = await AuditLog.get(audit_id)
        if not entry:
            text = f"❌ Audit record `{audit_id}` was not found."
            return await (message.response.send_message(text, ephemeral=True) if is_slash else message.reply(text))
        container = build_audit_detail_container(entry, emojis, colors)
        return await (message.response.send_message(embed=container.embed) if is_slash else message.reply(embed=container.embed))

    # Subcommand: errors [page]
    if sub == "errors":
        page_val = 1
        if len(args) > 1 and args[1].isdigit():
            page_val = max(1, int(args[1]))
        return await handle_errors_pagination(message, author_id, page_val, emojis, colors, is_slash)

    # Subcommand: filter <action> or list [page]
    filter_action = None
    initial_page = 1
    if sub == "filter":
        filter_action = args[1].strip() if len(args) > 1 else None
        if len(args) > 2 and args[2].isdigit():
            initial_page = max(1, int(args[2]))
    elif sub and sub.isdigit():
        initial_page = max(1, int(sub))

    return await handle_audit_pagination(message, author_id, initial_page, filter_action, emojis, colors, is_slash)

async def handle_audit_pagination(message: Any, author_id: str, initial_page: int, filter_action: Optional[str], emojis: Dict[str, str], colors: Dict[str, str], is_slash: bool):
    current_page = initial_page
    filter_dict = {}
    if filter_action:
        filter_dict["action"] = {"$regex": filter_action}

    session_id = f"audit_{author_id}_{id(message)}"

    async def render_page(page: int):
        total_count = await AuditLog.count(filter_dict)
        total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
        safe_page = min(max(1, page), total_pages)

        skip = (safe_page - 1) * PAGE_SIZE
        entries = await AuditLog.list(filter_dict=filter_dict, skip=skip, limit=PAGE_SIZE)

        if not entries:
            content_text = f"{emojis['audit']} *No audit log records found matching criteria.*"
        else:
            lines = []
            for idx, e in enumerate(entries):
                num = skip + idx + 1
                unix = format_unix(e.get("timestamp"))
                icon = emojis["success"] if e.get("success", True) else emojis["error"]
                act_id = e.get("actor_id") or e.get("actorId")
                actor_str = f"<@{act_id}>" if act_id else f"`{e.get('actor_type', 'system')}`"
                err_str = f"\n    └ ⚠️ `{e.get('error')[:80]}`" if e.get("error") else ""
                a_id = e.get("audit_id") or e.get("auditId", "")
                r_type = e.get("resource_type") or e.get("resourceType", "N/A")
                r_id = e.get("resource_id") or e.get("resourceId", "N/A")

                lines.append(
                    f"**{num}.** {icon} `{e.get('action')}` by {actor_str} • <t:{unix}:R>\n"
                    f"  > **Resource:** `{r_type}:{r_id}` | **ID:** `{a_id[:8]}...`{err_str}"
                )
            content_text = "\n\n".join(lines)

        header_text = (
            f"### {emojis['audit']} Audit Log (Filter: `{filter_action}`) — Page {safe_page}/{total_pages}"
            if filter_action
            else f"### {emojis['audit']} System Audit Log — Page {safe_page}/{total_pages}"
        )

        container = (
            ContainerBuilder()
            .set_accent_color(colors["default"])
            .add_text_display(header_text)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{content_text}\n\n"
                f"-# Total Events: {total_count} • Use select menu below to inspect an entry"
            )
        )

        if entries:
            container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            options = []
            for idx, e in enumerate(entries[:25]):
                ts = e.get("timestamp") or time.time()
                date_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))
                desc_str = f"{'Success' if e.get('success', True) else 'Failed'} | {date_str}"[:100]
                a_id = e.get("audit_id") or e.get("auditId", "")
                options.append({
                    "label": f"{skip + idx + 1}. {e.get('action', 'Action')}"[:100],
                    "value": f"inspect:{a_id}"[:100],
                    "description": desc_str,
                    "emoji": emojis["success"] if e.get("success", True) else emojis["error"],
                })

            container.add_action_row(
                ActionRowBuilder().add_select_menu(
                    SelectMenuBuilder()
                    .set_custom_id(f"{session_id}:inspect")
                    .set_placeholder("Select an audit entry to inspect...")
                    .set_min_values(1)
                    .set_max_values(1)
                    .set_options(options)
                )
            )

        nav_row = ActionRowBuilder()
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:prev")
            .set_label("◀ Previous")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(safe_page <= 1)
        )
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:next")
            .set_label("Next ▶")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(safe_page >= total_pages)
        )
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:errors")
            .set_label("Check Errors")
            .set_style(ButtonStyle.Primary)
        )
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:refresh")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
        )
        container.add_action_row(nav_row)

        return container.build(), safe_page, total_pages

    built, page, total_pages = await render_page(current_page)
    reply_msg = None
    if is_slash and hasattr(message, "response") and not message.response.is_done():
        reply_msg = await message.response.send_message(embed=built.embed, view=built.view)
    elif hasattr(message, "reply"):
        reply_msg = await message.reply(embed=built.embed, view=built.view)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=180.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == author_id,
    )

    if collector:
        async def on_prev(inter):
            nonlocal page
            page = max(1, page - 1)
            updated, page, _ = await render_page(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_next(inter):
            nonlocal page
            page += 1
            updated, page, _ = await render_page(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_refresh(inter):
            updated, page, _ = await render_page(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_errors(inter):
            await handle_errors_pagination(inter, author_id, 1, emojis, colors, is_interaction=True)

        async def on_inspect(inter):
            vals = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("values", [])
            val = vals[0] if vals else None
            if val and val.startswith("inspect:"):
                audit_id = val[len("inspect:"):]
                entry = await AuditLog.get(audit_id)
                if entry:
                    detail = build_audit_detail_container(entry, emojis, colors)
                    if hasattr(inter, "response"):
                        await inter.response.send_message(embed=detail.embed, ephemeral=True)
                else:
                    if hasattr(inter, "response"):
                        await inter.response.send_message("Audit entry not found.", ephemeral=True)

        collector.on(f"{session_id}:prev", on_prev)
        collector.on(f"{session_id}:next", on_next)
        collector.on(f"{session_id}:refresh", on_refresh)
        collector.on(f"{session_id}:errors", on_errors)
        collector.on(f"{session_id}:inspect", on_inspect)

async def handle_errors_pagination(source: Any, author_id: str, initial_page: int, emojis: Dict[str, str], colors: Dict[str, str], is_slash: bool = False, is_interaction: bool = False):
    from plugins.MomentumOneToolkit.commands.dev.errors import execute as exec_errors
    await exec_errors(None, CommandType.SLASH if is_slash else CommandType.PREFIX, source, ["list", str(initial_page)])

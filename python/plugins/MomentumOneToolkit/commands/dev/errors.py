import math
import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import config, COLORS, EMOJIS
from core.logging.error_tracker import ErrorTracker
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    ButtonStyle,
    SeparatorSpacingSize,
    MessageFlags,
)

PAGE_SIZE = 5

name = "errors"
aliases = ["error", "err", "errorlogs", "errlog"]
description = "Check and scroll through command execution errors and stack traces (Bot Owner Only)."
category = "Owner"
usage = "errors [page|view <id>|clear]"
owner_only = True

sub_commands = [
    {"name": "list [page]", "description": "Scroll through command error logs."},
    {"name": "view <errorId>", "description": "Inspect full stack trace and metadata for an Error ID."},
    {"name": "clear", "description": "Clear stored error logs from the database."},
]

def build_error_detail_container(record: Dict[str, Any], emojis: Dict[str, str], colors: Dict[str, str]):
    unix = int(record.get("timestamp") or time.time())
    u_id = record.get("user_id") or record.get("userId")
    username = record.get("username")
    user_display = f"{f'**{username}** ' if username else ''}<@{u_id}> (`{u_id}`)" if u_id else "N/A"

    g_id = record.get("guild_id") or record.get("guildId")
    guild_display = f"`{g_id}`" if g_id else "Direct Message / Global"
    type_display = record.get("command_type") or record.get("commandType", "UNKNOWN")
    raw_args = record.get("args")
    args_display = f"`{' '.join(raw_args)}`" if raw_args else "_None_"

    raw_stack = record.get("stack") or record.get("message") or "No stack trace available."
    stack_text = str(raw_stack)[:1300]
    msg_summary = str(record.get("message", "Execution exception"))[:200]
    err_id = record.get("error_id") or record.get("errorId", "ERR")
    cmd_name = record.get("command_name") or record.get("commandName", "Unknown")

    desc = (
        f"• **Error ID:** `{err_id}`\n"
        f"• **Command:** `{cmd_name}` ({type_display})\n"
        f"• **Timestamp:** <t:{unix}:F> (<t:{unix}:R>)\n"
        f"• **Invoker:** {user_display}\n"
        f"• **Guild ID:** {guild_display}\n"
        f"• **Arguments:** {args_display}\n"
        f"• **Error Summary:** `{msg_summary}`\n\n"
        f"**Stack Trace:**\n```python\n{stack_text}\n```"
    )

    return (
        ContainerBuilder()
        .set_accent_color(colors["error"])
        .add_text_display(f"### {emojis['error']} Command Execution Error Inspector")
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

    E = EMOJIS
    C = COLORS

    emojis = {
        "error": E.get("error") or "❌",
        "success": E.get("success") or "✅",
        "warning": E.get("warning") or "⚠️",
        "time": E.get("pending") or E.get("loading") or "⏱️",
        "cmd": E.get("commands") or "⚡",
        "search": E.get("search") or "🔍",
        "user": E.get("user") or "👤",
        "reset": E.get("reset") or "🔄",
    }

    colors = {
        "default": C.get("default", "#0844C5"),
        "success": C.get("success", "#3FD438"),
        "error": C.get("error", "#B21F1F"),
        "warning": C.get("warning", "#B21F1F"),
    }

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        deny_box = (
            ContainerBuilder()
            .set_accent_color(colors["error"])
            .add_text_display(f"### {emojis['error']} Access Restricted")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("This command is strictly restricted to bot owners.")
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=deny_box.embed, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(embed=deny_box.embed)
        return

    sub = args[0].lower() if args else None
    target_error_id = None

    if sub == "clear":
        count = await ErrorTracker.clear()
        container = (
            ContainerBuilder()
            .set_accent_color(colors["success"])
            .add_text_display(f"### {emojis['success']} Error Logs Cleared")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Successfully cleared **{count}** error log record(s) from the database.")
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=container.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=container.embed)
        return

    if sub in ["view", "get"] and len(args) > 1:
        target_error_id = args[1].strip()
    elif sub and (sub.startswith("err-") or len(sub) >= 6) and not sub.isdigit():
        target_error_id = sub.strip()

    if target_error_id:
        record = await ErrorTracker.get(target_error_id)
        if not record:
            not_found = (
                ContainerBuilder()
                .set_accent_color(colors["error"])
                .add_text_display(f"### {emojis['error']} Error Record Not Found")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Error ID `{target_error_id}` was not found in the database.")
                .build()
            )
            if is_slash and hasattr(message, "response") and not message.response.is_done():
                return await message.response.send_message(embed=not_found.embed, ephemeral=True)
            elif hasattr(message, "reply"):
                return await message.reply(embed=not_found.embed)
            return

        detail_box = build_error_detail_container(record, emojis, colors)
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=detail_box.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=detail_box.embed)
        return

    # Pagination: list [page]
    initial_page = 1
    if sub == "list" and len(args) > 1:
        try:
            initial_page = max(1, int(args[1]))
        except ValueError:
            pass
    elif sub and sub.isdigit():
        try:
            initial_page = max(1, int(sub))
        except ValueError:
            pass

    session_id = f"errs_{author_id}_{id(message)}"

    async def render_page(page: int):
        total_count = await ErrorTracker.count()
        total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
        safe_page = min(max(1, page), total_pages)

        skip = (safe_page - 1) * PAGE_SIZE
        records = await ErrorTracker.list(skip=skip, limit=PAGE_SIZE)

        if not records:
            content_text = f"{emojis['success']} **No command errors currently recorded!**"
        else:
            lines = []
            for idx, r in enumerate(records):
                num = skip + idx + 1
                unix = int(r.get("timestamp") or time.time())
                u_id = r.get("user_id") or r.get("userId")
                user_str = f"<@{u_id}>" if u_id else "N/A"
                c_type = r.get("command_type") or r.get("commandType", "")
                type_str = f"[{c_type}]" if c_type else ""
                err_id = r.get("error_id") or r.get("errorId", "ERR")
                cmd_name = r.get("command_name") or r.get("commandName", "Unknown")
                summary = (str(r.get("message", "Execution error")).strip())[:90]

                lines.append(
                    f"**{num}.** {emojis['error']} `{err_id}` — Command: `{cmd_name}` {type_str} • <t:{unix}:R>\n"
                    f"  > **User:** {user_str} | **Summary:** `{summary}`"
                )
            content_text = "\n\n".join(lines)

        container = (
            ContainerBuilder()
            .set_accent_color(colors["error"])
            .add_text_display(f"### {emojis['error']} Command Error Tracker — Page {safe_page}/{total_pages}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{content_text}\n\n"
                f"-# Total Errors: {total_count} • Select an error below or run `.errors view <id>` to inspect"
            )
        )

        if records:
            container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            options = []
            for idx, r in enumerate(records[:25]):
                err_id = r.get("error_id") or r.get("errorId", "ERR")
                cmd_name = r.get("command_name") or r.get("commandName", "Unknown")
                desc = (str(r.get("message", "Execution exception")).strip())[:100]
                options.append({
                    "label": f"{skip + idx + 1}. {err_id} ({cmd_name})"[:100],
                    "value": f"errs_inspect:{err_id}"[:100],
                    "description": desc,
                    "emoji": emojis["error"],
                })

            container.add_action_row(
                ActionRowBuilder().add_select_menu(
                    SelectMenuBuilder()
                    .set_custom_id(f"{session_id}:inspect")
                    .set_placeholder("Select an error to inspect stack trace...")
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
            .set_custom_id(f"{session_id}:refresh")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
        )
        container.add_action_row(nav_row)

        return container.build(), safe_page, total_pages

    built, page, total_pages = await render_page(initial_page)
    reply_msg = None
    if is_slash and hasattr(message, "response") and not message.response.is_done():
        reply_msg = await message.response.send_message(embed=built.embed, view=built.view)
    elif hasattr(message, "reply"):
        reply_msg = await message.reply(embed=built.embed, view=built.view)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=180.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
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

        async def on_inspect(inter):
            vals = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("values", [])
            val = vals[0] if vals else None
            if val and val.startswith("errs_inspect:"):
                e_id = val[len("errs_inspect:"):]
                record = await ErrorTracker.get(e_id)
                if record:
                    detail = build_error_detail_container(record, emojis, colors)
                    if hasattr(inter, "response"):
                        await inter.response.send_message(embed=detail.embed, ephemeral=True)
                else:
                    if hasattr(inter, "response"):
                        await inter.response.send_message("Error record not found.", ephemeral=True)

        collector.on(f"{session_id}:prev", on_prev)
        collector.on(f"{session_id}:next", on_next)
        collector.on(f"{session_id}:refresh", on_refresh)
        collector.on(f"{session_id}:inspect", on_inspect)

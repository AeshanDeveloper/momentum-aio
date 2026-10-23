import time
from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize, build_ui
from sdk.discord.response import send_response, send_ui
from database.database import database
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "bug"
aliases = ["report", "bugreport", "issue"]
description = "Submit a bug report or unexpected issue to the development team."
category = "General"
usage = "bug <description> | bug list | bug view <id>"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    sub = args[0].lower() if args else ""
    col = database.collection("bug_reports")

    # Owner inspection: bug list
    if sub == "list" and is_bot_owner(author_id):
        cursor = col.find({}, sort=[("timestamp", -1)])
        if hasattr(cursor, "to_list"):
            reports = await cursor.to_list(length=10)
        elif hasattr(cursor, "__await__"):
            reports = await cursor
        else:
            reports = [r async for r in cursor]

        lines = []
        for r in reports:
            ts = int(r.get("timestamp", time.time()))
            lines.append(f"• `#{r.get('report_id')}` by <@{r.get('user_id')}>: {r.get('description', '')[:50]} (<t:{ts}:R>)")
        report_text = "\n".join(lines) if lines else get_string("commands.bug.empty_list.description", default="No bug reports recorded yet.")

        bug_icon = EMOJIS.get("bug")
        view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#FF7B00"))
            .add_text_display(f"### {bug_icon} Recorded Bug Reports ({len(reports)})")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(report_text)
            .set_footer(get_string("commands.bug.footer", default="MomentumOne Issue Tracker"))
            .build()
        )
        return await send_response(message, view)

    # Owner inspection: bug view <id>
    if sub == "view" and is_bot_owner(author_id):
        target_id = args[1].removeprefix("#") if len(args) > 1 else ""
        report = await col.find_one({"report_id": target_id}) if target_id else None
        if not report:
            return await send_ui(
                message,
                "commands.bug.not_found",
                variables={"report_id": target_id},
                ephemeral=True,
                style="error"
            )

        ts = int(report.get("timestamp", time.time()))
        bug_icon = EMOJIS.get("bug")
        view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#FF7B00"))
            .add_text_display(f"### {bug_icon} Bug Report `#{report.get('report_id')}`")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"• **Reporter:** <@{report.get('user_id')}> (`{report.get('username')}`)\n"
                f"• **Submitted:** <t:{ts}:F> (<t:{ts}:R>)\n"
                f"• **Status:** `{report.get('status', 'open')}`\n\n"
                f"**Description:**\n{report.get('description')}"
            )
            .set_footer(get_string("commands.bug.footer", default="MomentumOne Issue Tracker"))
            .build()
        )
        return await send_response(message, view)

    # Submit bug report
    report_text = " ".join(args).strip()
    if not report_text:
        return await send_ui(
            message,
            "commands.bug.empty",
            ephemeral=True,
            style="warning"
        )

    rep_id = hex(int(time.time() * 1000))[2:].upper()
    try:
        await col.insert_one({
            "report_id": rep_id,
            "user_id": author_id,
            "username": author.name if author else "Unknown",
            "description": report_text,
            "status": "open",
            "timestamp": time.time()
        })
    except Exception:
        pass

    return await send_ui(
        message,
        "commands.bug.submitted",
        variables={"report_id": rep_id, "user_id": author_id, "details": report_text[:300]},
        style="success"
    )

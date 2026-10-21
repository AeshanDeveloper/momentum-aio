from typing import List, Any
import discord
from discord import ButtonStyle
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from config.changelog import CHANGELOG_RELEASES
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response
from shared.types.command_record import CommandType

name = "update"
aliases = ["changelog", "news", "updates"]
description = "View the latest MomentumOne system changelog and interactive release notes."
category = "General"
usage = "update [version]"
cooldown = 3.0

def build_release_view(release_idx: int, session_id: str) -> Any:
    idx = max(0, min(len(CHANGELOG_RELEASES) - 1, release_idx))
    rel = CHANGELOG_RELEASES[idx]
    is_latest = (idx == 0)

    rocket_icon = EMOJIS.get("rocket") or "🚀"
    title = get_string("commands.update.title", f"{rocket_icon} MomentumOne System Changelog")
    features_formatted = "\n".join(f"• {f}" for f in rel.get("features", []))
    bug_fixes = rel.get("bugFixes", [])
    bugs_formatted = "\n".join(f"• {b}" for b in bug_fixes) if bug_fixes else None

    star_icon = EMOJIS.get("star") or "⭐"
    latest_badge = get_string("commands.update.latest_badge", f"{star_icon} *(Latest)*")
    hist_badge = get_string("commands.update.historical_badge", "*(Historical)*")
    badge_str = latest_badge if is_latest else hist_badge

    sparkles_icon = EMOJIS.get("sparkles") or "✨"
    feat_heading = get_string("commands.update.features_heading", f"**{sparkles_icon} Key Capabilities & Features:**")

    container = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title} — v{rel['version']}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**Release:** `v{rel['version']}` ({rel['codename']}) {badge_str}\n"
            f"**Published:** `{rel.get('releasedAt', 'Recent')}`\n\n"
            f"_{rel.get('headline', '')}_\n\n"
            f"{rel.get('summary', '')}"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{feat_heading}\n{features_formatted}")
    )

    if bugs_formatted:
        wrench_icon = EMOJIS.get("wrench") or "🔧"
        bugs_heading = get_string("commands.update.bugs_heading", f"**{wrench_icon} Bug Fixes & Stability:**")
        container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        container.add_text_display(f"{bugs_heading}\n{bugs_formatted}")

    container.set_footer(f"Version {rel['version']} • Released {rel.get('releasedAt')}")

    row = ActionRowBuilder()
    row.add_button(
        ButtonBuilder()
        .set_custom_id(f"{session_id}:ver:0")
        .set_label(f"v{CHANGELOG_RELEASES[0]['version']} (Latest)")
        .set_style(ButtonStyle.primary if idx == 0 else ButtonStyle.secondary)
        .set_disabled(idx == 0)
    )
    if len(CHANGELOG_RELEASES) > 1:
        row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:ver:1")
            .set_label(f"v{CHANGELOG_RELEASES[1]['version']}")
            .set_style(ButtonStyle.primary if idx == 1 else ButtonStyle.secondary)
            .set_disabled(idx == 1)
        )
    if len(CHANGELOG_RELEASES) > 2:
        row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{session_id}:ver:2")
            .set_label(f"v{CHANGELOG_RELEASES[2]['version']}")
            .set_style(ButtonStyle.primary if idx == 2 else ButtonStyle.secondary)
            .set_disabled(idx == 2)
        )

    container.add_action_row(row)
    return container.build()

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = getattr(author, "id", None)

    # Check if specific version requested in args
    current_idx = 0
    if args:
        req = args[0].lower().lstrip("v")
        for i, r in enumerate(CHANGELOG_RELEASES):
            if r["version"].lstrip("v").startswith(req):
                current_idx = i
                break

    session_id = f"upd_{id(message)}"
    view = build_release_view(current_idx, session_id)
    reply_msg = await send_response(message, view)

    collector = view.create_message_component_collector(
        target_message=reply_msg or message,
        timeout=180.0,
        filter_func=lambda inter: (getattr(getattr(inter, "user", None), "id", None) == author_id) if author_id else True,
    )

    if collector:
        async def on_ver(inter: discord.Interaction):
            cid = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("custom_id", "")
            parts = cid.split(":")
            if len(parts) >= 3 and parts[2].isdigit():
                new_idx = int(parts[2])
                updated_view = build_release_view(new_idx, session_id)
                if hasattr(inter, "response"):
                    await inter.response.edit_message(view=updated_view.view)

        collector.on(f"{session_id}:ver", on_ver)


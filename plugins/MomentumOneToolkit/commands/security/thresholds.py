from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import (
    AntiNukeManager,
    AntiNukeConstants,
    get_default_thresholds,
)
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "thresholds"
aliases = ["threshold", "limits", "ratelimit"]
description = "Configure action thresholds and sliding time windows for anti-nuke protection."
category = "Security"
usage = "thresholds [event]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


# In-memory staging for interactive threshold editing: (guild_id, user_id) -> {"event": str, "count": int, "window": int}
_THRESHOLD_STAGING: Dict[str, Dict[str, Any]] = {}


def get_staging_key(guild_id: Any, user_id: Any) -> str:
    return f"{guild_id}:{user_id}"


def get_threshold_staging(guild_id: Any, user_id: Any) -> Dict[str, Any]:
    key = get_staging_key(guild_id, user_id)
    if key not in _THRESHOLD_STAGING:
        _THRESHOLD_STAGING[key] = {
            "event": AntiNukeConstants.EVENT_CHANNEL_DELETE,
            "count": 1,
            "window": 60,
        }
    return _THRESHOLD_STAGING[key]


async def build_threshold_overview_view(guild: discord.Guild, selected_event: Optional[str] = None, user_id: Optional[int] = None) -> Any:
    """
    Builds the main interactive Thresholds Panel using Discord Components V2.
    Displays current threshold limits per event and provides interactive String Select Menu and buttons.
    """
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    mode_name = AntiNukeManager.get_mode_display_name(mode)
    current_thresholds = cfg.get("thresholds") or get_default_thresholds(mode)

    active_event = selected_event or AntiNukeConstants.EVENT_CHANNEL_DELETE
    canonical_active = AntiNukeConstants.normalize_event(active_event) or active_event

    # Retrieve staged or saved values for the active event
    if user_id:
        staged = get_threshold_staging(guild.id, user_id)
        if staged.get("event") == canonical_active:
            cur_count = staged.get("count", 1)
            cur_window = staged.get("window", 60)
        else:
            saved = current_thresholds.get(canonical_active, {"count": 1, "window": 60})
            cur_count = saved.get("count", 1)
            cur_window = saved.get("window", 60)
            staged["event"] = canonical_active
            staged["count"] = cur_count
            staged["window"] = cur_window
    else:
        saved = current_thresholds.get(canonical_active, {"count": 1, "window": 60})
        cur_count = saved.get("count", 1)
        cur_window = saved.get("window", 60)

    # Validate bounds
    cur_count = max(1, min(50, int(cur_count)))
    cur_window = max(0, min(300, int(cur_window)))

    friendly_active_name = AntiNukeConstants.get_event_display_name(canonical_active)
    active_desc = AntiNukeConstants.get_event_description(canonical_active)

    window_label = "Lifetime / Indefinite" if cur_window == 0 else f"{cur_window} seconds"
    posture_label = "Instant Zero-Tolerance (1 action)" if cur_count == 1 else f"Sliding Burst ({cur_count} actions in {window_label})"

    desc = (
        f"Configure how many unauthorized actions an entity may execute before anti-nuke sanctions trigger.\n\n"
        f"• **Active Mode:** `{mode_name}`\n"
        f"• **Inspecting Event:** **{friendly_active_name}** (`{canonical_active}`)\n"
        f"• **Current Limit:** `{cur_count}` action(s) per `{window_label}`\n"
        f"• **Defense Posture:** `{posture_label}`\n\n"
        f"*{active_desc}*"
    )

    # 1. Event Selection String Select Menu
    event_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_th:pick_event:{guild.id}")
        .set_placeholder("Select an event vector to adjust threshold...")
    )
    for ev in AntiNukeConstants.USER_CONFIGURABLE_EVENTS:
        ev_friendly = AntiNukeConstants.get_event_display_name(ev)
        ev_th = current_thresholds.get(ev, {"count": 1, "window": 60})
        cnt = ev_th.get("count", 1)
        win = ev_th.get("window", 60)
        win_str = "Lifetime" if win == 0 else f"{win}s"
        event_select.add_option(
            label=f"{ev_friendly[:40]}",
            value=ev,
            description=f"Limit: {cnt} action(s) / {win_str}",
            default=(ev == canonical_active),
        )

    # 2. Action Count Limit Quick-Buttons
    count_row = ActionRowBuilder()
    for c_val in [1, 2, 3, 5]:
        is_cur = (cur_count == c_val)
        count_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_th:set_count:{canonical_active}:{c_val}:{guild.id}")
            .set_label(f"{c_val} Action{'s' if c_val > 1 else ' (Instant)'}")
            .set_style(ButtonStyle.Primary if is_cur else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("check" if is_cur else "bullet", "•"))
        )

    # 3. Time Window Quick-Buttons (10s, 30s, 60s, Lifetime)
    window_row = ActionRowBuilder()
    window_options = [
        (10, "10s (Burst)"),
        (30, "30s"),
        (60, "60s (Standard)"),
        (0, "Lifetime"),
    ]
    for w_val, w_label in window_options:
        is_cur = (cur_window == w_val)
        window_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_th:set_window:{canonical_active}:{w_val}:{guild.id}")
            .set_label(w_label)
            .set_style(ButtonStyle.Primary if is_cur else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("check" if is_cur else "clock", "⏱️"))
        )

    # 4. Save, Reset, Cancel & Navigation Buttons
    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_th:save:{canonical_active}:{guild.id}")
            .set_label(f"Save {friendly_active_name}")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_th:reset:{canonical_active}:{guild.id}")
            .set_label("Reset to Defaults")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_th:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Anti-Nuke Thresholds & Rate Limiter")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(event_select))
        .add_text_display("**1. Select Action Count Limit:**")
        .add_action_row(count_row)
        .add_text_display("**2. Select Sliding Time Window:**")
        .add_action_row(window_row)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Infrastructure • Sliding Burst Evaluation")
        .build()
    )


# Export alias so component_handler can import either name safely
build_thresholds_dashboard_view = build_threshold_overview_view


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Check root authority
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can adjust threshold limits.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Setup enforcement
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    selected_event = None
    if args:
        canonical = AntiNukeConstants.normalize_event(args[0])
        if canonical:
            selected_event = canonical

    view = await build_threshold_overview_view(guild, selected_event=selected_event, user_id=author.id)
    return await send_response(message, view)

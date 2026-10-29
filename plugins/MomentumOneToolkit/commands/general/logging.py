import time
from typing import List, Dict, Any, Optional, Tuple
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.logging.webhook_logger import (
    UnifiedWebhookLogger,
    LogCategory,
    LogSeverity,
    get_webhook_display_status,
    redact_webhook_credentials,
)
from core.logging.resource_tracker import SentinelResourceTracker
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "logging"
aliases = ["logs", "log", "logsetup"]
description = "Configure centralized Discord webhook-only logging for security, moderation, and server events."
category = "General"
usage = "logging [setup|panel|test|repair|enable|disable|cleanup]"
user_permissions = ["manage_guild"]
bot_permissions = ["manage_channels", "manage_webhooks"]
guild_only = True
cooldown = 2.0


# In-memory session tracking for the Logging Setup Wizard: guild_id -> session_dict
_LOGGING_WIZARD_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_or_create_logging_wizard_session(guild: discord.Guild) -> Dict[str, Any]:
    gid = str(guild.id)
    if gid not in _LOGGING_WIZARD_SESSIONS:
        cfg = UnifiedWebhookLogger.get_guild_logging_config(gid)
        _LOGGING_WIZARD_SESSIONS[gid] = {
            "guild_id": gid,
            "mode": "category",  # "category" or "existing"
            "layout": cfg.get("layout", "category"),  # "compact" | "dual" | "category" | "advanced"
            "category_name": f"{settings.BOT_NAME.upper()} LOGS",
            "separate_antinuke": cfg.get("separate_antinuke", True),
            "step": 1,
            "selected_channels": {},  # category -> channel_id
        }
    return _LOGGING_WIZARD_SESSIONS[gid]


def clear_logging_wizard_session(guild_id: str | int) -> None:
    _LOGGING_WIZARD_SESSIONS.pop(str(guild_id), None)


# ==============================================================================
# Centralized Logging Control Panel
# ==============================================================================
async def build_logging_panel_view(guild: discord.Guild) -> Any:
    """
    Builds the main interactive Webhook Logging Management Dashboard.
    Provides real-time destination health, repair tools, and test dispatchers.
    Never exposes webhook URLs or secret tokens.
    """
    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
    is_enabled = cfg.get("enabled", False)
    layout = cfg.get("layout", "category")
    separate_an = cfg.get("separate_antinuke", True)
    destinations = cfg.get("destinations", {})
    disabled_cats = set(cfg.get("disabled_categories", []))
    failures = cfg.get("delivery_failures", [])

    status_badge = (
        f"{EMOJIS.get('enabled', '✅')} **ACTIVE & OPERATIONAL**"
        if is_enabled
        else f"{EMOJIS.get('disabled', '❌')} **PAUSED / UNCONFIGURED**"
    )

    # Build Destinations Overview without exposing URLs or tokens
    dest_lines = []
    for cat in LogCategory.ALL_CATEGORIES:
        meta = LogCategory.CATEGORY_METADATA.get(cat, {})
        c_emoji = meta.get("emoji", "📝")
        c_name = meta.get("name", cat.title())

        is_cat_disabled = cat in disabled_cats
        cat_state = " *(Disabled)*" if is_cat_disabled else ""

        dest = destinations.get(cat)
        if not dest and cat == LogCategory.SECURITY and not separate_an:
            dest = destinations.get(LogCategory.MODERATION) or destinations.get("general")
        elif not dest:
            dest = destinations.get("general")

        wh_status = get_webhook_display_status(guild, dest)
        if dest and isinstance(dest, dict):
            ch_id = dest.get("channel_id")
            ch_mention = f"<#{ch_id}>" if ch_id else "*Unknown*"
            dest_lines.append(f"• {c_emoji} **{c_name}:** {ch_mention} — Webhook: `{wh_status}`{cat_state}")
        else:
            dest_lines.append(f"• {c_emoji} **{c_name}:** *Unassigned* — Webhook: `{wh_status}`{cat_state}")

    dest_block = "\n".join(dest_lines)

    # Recent failure warning block if any exist (redacting all credentials)
    warning_block = ""
    if failures:
        recent_err = failures[-1]
        err_msg = redact_webhook_credentials(recent_err.get("error", "Unknown delivery error"))
        err_ch = recent_err.get("channel_id", "Unknown")
        warning_block = (
            f"\n\n### {EMOJIS.get('danger', '⚠️')} Delivery Failure Warning\n"
            f"Recent webhook dispatch failed in <#{err_ch}>:\n"
            f"*{err_msg}*\n"
            f"-# Click **Repair Webhooks** below to securely regenerate missing or revoked webhooks."
        )

    summary_text = (
        f"{status_badge}\n\n"
        f"• **Active Layout:** `{layout.title()}`\n"
        f"• **Anti-Nuke Routing:** `{'Dedicated Channel' if separate_an else 'Combined with Moderation'}`\n"
        f"• **Webhook Delivery:** `Strictly Discord Webhooks (Zero Message Fallback)`\n\n"
        f"**Configured Event Destinations:**\n"
        f"{dest_block}"
        f"{warning_block}"
    )

    # Row 1: Primary Lifecycle Controls
    row_1 = ActionRowBuilder()
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_cfg:toggle_active:{guild.id}")
        .set_label("Disable Logging" if is_enabled else "Enable Logging")
        .set_style(ButtonStyle.Danger if is_enabled else ButtonStyle.Success)
        .set_emoji(EMOJIS.get("power", "⚡"))
    )
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:start:{guild.id}")
        .set_label("Run Setup Wizard")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("wrench", "🔧"))
    )
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_cfg:create_one:{guild.id}")
        .set_label("Create 1 Channel")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("plus", "➕"))
    )
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_cfg:create_two:{guild.id}")
        .set_label("Create 2 Channels")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("plus", "➕"))
    )

    # Row 2: Category Management Select Menu
    cat_select = (
        SelectMenuBuilder()
        .set_custom_id(f"log_cfg:toggle_cat:{guild.id}")
        .set_placeholder("Toggle Enable/Disable Individual Event Groups...")
    )
    for cat in LogCategory.ALL_CATEGORIES:
        meta = LogCategory.CATEGORY_METADATA.get(cat, {})
        is_off = cat in disabled_cats
        cat_select.add_option(
            label=f"{meta.get('name', cat.title())}",
            value=cat,
            description=f"Status: {'DISABLED' if is_off else 'ACTIVE'}",
            emoji=meta.get("emoji"),
            default=False,
        )

    # Row 3: Utility & Diagnostics Controls
    row_3 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:test_webhooks:{guild.id}")
            .set_label("Test Delivery")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("rocket", "🚀"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:repair_all:{guild.id}")
            .set_label("Repair Webhooks")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("tools", "🛠️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:cleanup_prompt:{guild.id}")
            .set_label("Clean Up / Reset")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:refresh:{guild.id}")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
    )

    accent = COLORS.get("error" if failures else ("success" if is_enabled else "info"), "#0844C5")

    return (
        ContainerBuilder()
        .set_accent_color(accent)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {settings.BOT_NAME} Unified Webhook Logging System")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(summary_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(row_1)
        .add_text_display("**Toggle Event Group Monitoring:**")
        .add_action_row(ActionRowBuilder().add_select_menu(cat_select))
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(row_3)
        .add_text_display(f"-# {settings.BOT_NAME} Unified Logging • Authenticated Discord Webhooks Only")
        .build()
    )


# ==============================================================================
# Setup Wizard Step 1: Mode & Anti-Nuke Channel Strategy
# ==============================================================================
async def build_wizard_step1_view(guild: discord.Guild) -> Any:
    """Step 1: Choose between creating a new category or using existing channels."""
    sess = get_or_create_logging_wizard_session(guild)
    sess["step"] = 1

    cur_mode = sess.get("mode", "category")
    separate_an = sess.get("separate_antinuke", True)

    desc = (
        f"Configure how your server audit and security logs will be organized.\n\n"
        f"**1. Category Strategy:**\n"
        f"• **Dedicated Category:** Creates a cleanly isolated category (`{sess.get('category_name')}`) with locked permissions.\n"
        f"• **Existing Channels:** Map logging event groups directly to existing channels on your server.\n\n"
        f"**2. Anti-Nuke Security Separation:**\n"
        f"• **Separate Channel (`{separate_an}`):** Anti-Nuke forensic alerts are routed into a dedicated security channel."
    )

    row_mode = ActionRowBuilder()
    row_mode.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:set_mode:category:{guild.id}")
        .set_label("Create New Category" + (" (Selected)" if cur_mode == "category" else ""))
        .set_style(ButtonStyle.Primary if cur_mode == "category" else ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("folder", "📁"))
    )
    row_mode.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:set_mode:existing:{guild.id}")
        .set_label("Use Existing Channels" + (" (Selected)" if cur_mode == "existing" else ""))
        .set_style(ButtonStyle.Primary if cur_mode == "existing" else ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("channel", "💬"))
    )

    row_an = ActionRowBuilder()
    row_an.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:toggle_an:{guild.id}")
        .set_label(f"Separate Anti-Nuke Logs: {'YES' if separate_an else 'NO'}")
        .set_style(ButtonStyle.Success if separate_an else ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )

    row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:step2:{guild.id}")
            .set_label("Continue to Channel Layout")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('wrench', '🔧')} Logging Setup Step 1/3: Organization Strategy")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display("**Choose Creation Mode:**")
        .add_action_row(row_mode)
        .add_text_display("**Anti-Nuke Incident Isolation:**")
        .add_action_row(row_an)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Unified Logger Setup • Step 1 of 3")
        .build()
    )


# ==============================================================================
# Setup Wizard Step 2: Channel Layout Selection
# ==============================================================================
async def build_wizard_step2_view(guild: discord.Guild) -> Any:
    """Step 2: Select layout (Compact, Dual Channel, Category Layout, Advanced)."""
    sess = get_or_create_logging_wizard_session(guild)
    sess["step"] = 2

    cur_layout = sess.get("layout", "category")
    separate_an = sess.get("separate_antinuke", True)

    desc = (
        f"Select your preferred logging channel layout:\n\n"
        f"• **Compact Layout:** 1 channel (`#server-logs`) for all events"
        f"{' + dedicated `#security-logs`' if separate_an else ''}.\n"
        f"• **Dual Channel:** 2 channels (`#moderation-logs` & `#server-logs`)"
        f"{' + dedicated `#security-logs`' if separate_an else ''}.\n"
        f"• **Category Layout (Recommended):** Dedicated category with channels for Moderation, Channels, Roles, Members, and Server operations.\n"
        f"• **Advanced Layout:** Fine-grained channel routing per event group."
    )

    row_layouts = ActionRowBuilder()
    row_layouts.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:set_layout:compact:{guild.id}")
        .set_label("Compact" + (" (Active)" if cur_layout == "compact" else ""))
        .set_style(ButtonStyle.Primary if cur_layout == "compact" else ButtonStyle.Secondary)
    )
    row_layouts.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:set_layout:dual:{guild.id}")
        .set_label("Dual Channel" + (" (Active)" if cur_layout == "dual" else ""))
        .set_style(ButtonStyle.Primary if cur_layout == "dual" else ButtonStyle.Secondary)
    )
    row_layouts.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:set_layout:category:{guild.id}")
        .set_label("Category Layout" + (" (Active)" if cur_layout == "category" else ""))
        .set_style(ButtonStyle.Success if cur_layout == "category" else ButtonStyle.Secondary)
    )

    row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:step1:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:preview:{guild.id}")
            .set_label("Continue to Preview")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('channel', '📁')} Logging Setup Step 2/3: Channel Layout")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display("**Choose Layout Preset:**")
        .add_action_row(row_layouts)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Unified Logger Setup • Step 2 of 3")
        .build()
    )


# ==============================================================================
# Setup Wizard Step 3: Preview & Execution Confirmation
# ==============================================================================
async def build_wizard_preview_view(guild: discord.Guild) -> Any:
    """Step 3: Preview resources to be created and request confirmation, showing reuse status."""
    sess = get_or_create_logging_wizard_session(guild)
    sess["step"] = 3

    mode = sess.get("mode", "category")
    layout = sess.get("layout", "category")
    separate_an = sess.get("separate_antinuke", True)
    cat_name = sess.get("category_name", f"{settings.BOT_NAME.upper()} LOGS")

    me = guild.me
    can_manage_ch = bool(me and me.guild_permissions.manage_channels)
    can_manage_wh = bool(me and me.guild_permissions.manage_webhooks)

    perms_ok = can_manage_ch and can_manage_wh
    perm_status = (
        f"{EMOJIS.get('check', '✅')} Bot has `Manage Channels` and `Manage Webhooks` permissions."
        if perms_ok
        else f"{EMOJIS.get('cross', '❌')} Missing required permissions (`Manage Channels` and/or `Manage Webhooks`)."
    )

    # Check for verified existing category and channels via SentinelResourceTracker or existing guild category
    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
    existing_cat = None
    saved_cat_id = cfg.get("category_id")
    if saved_cat_id and SentinelResourceTracker.is_resource_owned(guild.id, saved_cat_id):
        for c in (getattr(guild, "categories", []) or []):
            if str(getattr(c, "id", "")) == str(saved_cat_id):
                existing_cat = c
                break
        if not existing_cat:
            ch = guild.get_channel(int(saved_cat_id))
            if isinstance(ch, discord.CategoryChannel):
                existing_cat = ch

    if not existing_cat:
        for c in (getattr(guild, "categories", []) or []):
            if getattr(c, "name", "").lower() == cat_name.lower():
                existing_cat = c
                break

    category_status = (
        f"• **Target Category:** `📁 {existing_cat.name}` *(Existing category will be reused ✅)*"
        if existing_cat
        else f"• **Target Category:** `📁 {cat_name}` *(New dedicated category will be created ➕)*"
    )

    # Determine layout target channels
    if layout == "compact":
        channel_names = [("server-logs", "General Server, Moderation, Members, Config")]
        if separate_an:
            channel_names.append(("security-logs", "Anti-Nuke Incidents & Defense Alerts"))
    elif layout == "dual":
        channel_names = [
            ("moderation-logs", "Bans, Kicks, Timeouts, Role Grants"),
            ("server-logs", "Channels, Roles, Invites, Webhooks, Emojis"),
        ]
        if separate_an:
            channel_names.append(("security-logs", "Anti-Nuke Incidents & Defense Alerts"))
    else:  # category
        channel_names = [
            ("security-logs", "Anti-Nuke Incidents & Alerts"),
            ("moderation-logs", "Bans, Unbans, Kicks, Timeouts"),
            ("channel-logs", "Channel Creations, Deletions, Overwrites"),
            ("role-logs", "Role Changes, Permission Escalations"),
            ("member-logs", "Member Joins, Leaves, Nicknames"),
            ("server-logs", "Invites, Integrations, Emojis, System Config"),
        ]

    # Inspect reuse for channels
    channels_preview = []
    reused_count = 0
    new_count = 0
    owned_records = {
        r.purpose: r
        for r in SentinelResourceTracker.get_all_owned_resources(guild.id)
        if r.resource_type == "text_channel" and (not existing_cat or r.parent_id == str(existing_cat.id))
    }
    for ch_name, desc_text in channel_names:
        rec = owned_records.get(ch_name)
        found_ch = guild.get_channel(int(rec.resource_id)) if rec else None
        if not found_ch and existing_cat:
            cat_chs = getattr(existing_cat, "text_channels", []) or getattr(existing_cat, "channels", []) or []
            for tc in cat_chs:
                if getattr(tc, "name", "").lower() == ch_name.lower():
                    found_ch = tc
                    break
        if not found_ch and hasattr(guild, "text_channels"):
            for tc in getattr(guild, "text_channels", []) or []:
                if getattr(tc, "name", "").lower() == ch_name.lower():
                    found_ch = tc
                    break

        if found_ch:
            channels_preview.append(f"• `#{ch_name}` — {desc_text} *(Reuse existing channel ✅)*")
            reused_count += 1
        else:
            channels_preview.append(f"• `#{ch_name}` — {desc_text} *(Create dedicated channel under logging category ➕)*")
            new_count += 1

    ch_list_str = "\n".join(channels_preview)

    desc = (
        f"**Review Setup Preview:**\n\n"
        f"• **Creation Mode:** `{'Create Dedicated Category' if mode == 'category' else 'Use Existing Channels'}`\n"
        f"{category_status}\n"
        f"• **Layout Preset:** `{layout.title()}` ({reused_count} to reuse, {new_count} to create)\n"
        f"• **Channels & Webhook Destinations ({len(channels_preview)}):**\n"
        f"{ch_list_str}\n\n"
        f"• **Permission Validation:**\n"
        f"{perm_status}\n\n"
        f"-# *Setup is idempotent: existing categories, channels, and webhooks are automatically reused.*"
    )

    action_row = ActionRowBuilder()
    if perms_ok:
        action_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"log_wiz:confirm_execute:{guild.id}")
            .set_label("Confirm & Apply Setup")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:step2:{guild.id}")
        .set_label("Back")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
    )
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"log_wiz:cancel:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Danger)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success" if perms_ok else "error", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} Logging Setup Step 3/3: Confirm & Deploy")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Unified Logger Setup • Step 3 of 3")
        .build()
    )


# ==============================================================================
# Setup Cleanup / Reset View
# ==============================================================================
async def build_cleanup_confirm_view(guild: discord.Guild) -> Any:
    """Builds confirmation dialog for cleaning up or resetting logging resources."""
    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
    destinations = cfg.get("destinations", {})
    configured_count = len(destinations)

    desc = (
        f"**Logging Resource Cleanup & Reset**\n\n"
        f"Choose how you would like to reset or clean up the logging configuration for **{guild.name}** "
        f"({configured_count} destinations currently configured):\n\n"
        f"• **Reset Configuration Only:** Resets database records and disables logging without deleting any Discord channels or categories.\n"
        f"• **Full Resource Cleanup:** Safely deletes logging-owned channels and webhooks from Discord, removes the category if empty, and clears database configuration.\n\n"
        f"-# *Note: Only channels created and owned by {settings.BOT_NAME} logging will ever be deleted.*"
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:do_cleanup:config:{guild.id}")
            .set_label("Reset Config Only")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:do_cleanup:full:{guild.id}")
            .set_label("Full Resource Cleanup")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:panel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('trash', '🗑️')} Clean Up Logging Resources")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Resource Management")
        .build()
    )


# ==============================================================================
# Channel Assignment View (Select Menu for Reassigning Category Destination)
# ==============================================================================
async def build_assign_channel_view(guild: discord.Guild, category: str) -> Any:
    """Builds native Channel Select menu to assign a log category to an existing channel."""
    meta = LogCategory.CATEGORY_METADATA.get(category, {})
    c_name = meta.get("name", category.title())

    desc = (
        f"Select a text channel to route all **{c_name}** logs to.\n\n"
        f"• The bot will automatically verify channel permissions and generate a secure webhook.\n"
        f"• All logs for this category will be dispatched via webhook exclusively."
    )

    ch_select = (
        SelectMenuBuilder()
        .set_custom_id(f"log_cfg:do_assign:{category}:{guild.id}")
        .set_placeholder(f"Choose a text channel for {c_name} logs...")
        .set_type(SelectMenuTypes.CHANNEL)
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"log_cfg:panel:{guild.id}")
            .set_label("Back to Logging Panel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {meta.get('emoji', '📝')} Assign Channel: {c_name}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(ch_select))
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Webhook Channel Assignment")
        .build()
    )


# ==============================================================================
# Command Execution Entrypoint
# ==============================================================================
async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Check manage_guild permission
    perms = author.guild_permissions if hasattr(author, "guild_permissions") else None
    if not perms or not perms.manage_guild:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} You must have the `Manage Server` permission to configure logging.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    sub = args[0].lower() if args else "panel"

    if sub in ["setup", "wizard", "init"]:
        # Reset session and open Step 1
        clear_logging_wizard_session(guild.id)
        view = await build_wizard_step1_view(guild)
        return await send_response(message, view)

    elif sub in ["test", "diagnose"]:
        cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
        destinations = cfg.get("destinations", {})
        if not destinations:
            return await send_ui(message, "common.error", variables={"message": "No logging destinations configured. Run `$logging setup` first."}, style="warning")

        # Pick first destination to test
        target_ch_id = None
        for d in destinations.values():
            if isinstance(d, dict) and d.get("channel_id"):
                target_ch_id = d.get("channel_id")
                break

        if not target_ch_id:
            return await send_ui(message, "common.error", variables={"message": "No valid channel destination found."}, style="warning")

        ok, msg = await UnifiedWebhookLogger.test_webhook(guild, target_ch_id)
        style = "success" if ok else "error"
        return await send_ui(message, "common.info" if ok else "common.error", variables={"message": msg}, style=style)

    elif sub in ["repair", "fix"]:
        cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
        destinations = cfg.get("destinations", {})
        repaired = 0
        errors = []
        for d in destinations.values():
            if isinstance(d, dict) and d.get("channel_id"):
                cid = d.get("channel_id")
                ok, msg = await UnifiedWebhookLogger.repair_webhook(guild, cid)
                if ok:
                    repaired += 1
                else:
                    errors.append(f"<#{cid}>: {msg}")

        result_text = f"Repaired {repaired} webhook(s)."
        if errors:
            result_text += "\nErrors:\n" + "\n".join(errors)
        return await send_ui(message, "common.info", variables={"message": result_text}, style="success" if repaired else "warning")

    elif sub in ["enable", "on"]:
        await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"enabled": True})
        return await send_ui(message, "common.success", variables={"message": "Unified Webhook Logging enabled successfully."}, style="success")

    elif sub in ["disable", "off"]:
        await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"enabled": False})
        return await send_ui(message, "common.info", variables={"message": "Unified Webhook Logging paused."}, style="warning")

    elif sub in ["cleanup", "reset"]:
        view = await build_cleanup_confirm_view(guild)
        return await send_response(message, view)

    # Default: Show Main Logging Panel
    view = await build_logging_panel_view(guild)
    return await send_response(message, view)


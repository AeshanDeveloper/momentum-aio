"""
Sentinel™ Security Glossary & Interactive Keyword Explanation Engine.

Comprehensive, accessible definitions, practical examples, and safeguard
explanations for all Sentinel security terminology to ensure zero administrator confusion.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType

name = "explain"
aliases = ["glossary", "keywords", "terms", "secinfo", "terminology", "define"]
description = "Comprehensive guide and interactive explanations for all Sentinel security keywords and concepts."
category = "Security"
usage = "explain [keyword]"
user_permissions = ["view_channel"]
cooldown = 1.0
guild_only = False

# Dictionary of in-depth keyword explanations
KEYWORDS_GLOSSARY: Dict[str, Dict[str, Any]] = {
    "antinuke": {
        "title": "Anti-Nuke Protection",
        "emoji": "🛡️",
        "short": "Autonomous real-time shield guarding against mass structural damage and rogue administrator wipes.",
        "details": (
            "**What is Anti-Nuke?**\n"
            "Anti-Nuke is Sentinel's primary defense layer. It monitors rapid destructive actions on your server—such as "
            "mass channel deletions, role wipes, unauthorized bot additions, or rapid member bans. When an account exceeds "
            "safe limits within a burst window, Sentinel instantly applies mitigation sanctions (Ban, Quarantine, Kick) "
            "and rolls back damage.\n\n"
            "**Why is it needed?**\n"
            "Compromised staff accounts, rogue administrators, or malicious webhooks can wipe an entire community in seconds. "
            "Anti-Nuke acts autonomously within milliseconds without waiting for human intervention."
        ),
        "tip": "Keep Anti-Nuke armed on Hard mode and designate high-trust co-owners as Extra Owners.",
    },
    "observation": {
        "title": "Observation Systems (Aegis vs Standard)",
        "emoji": "👁️",
        "short": "Defensive analysis engine evaluating server events: Aegis Advanced Correlation Engine vs Standard Heuristic.",
        "details": (
            "**1. Aegis Advanced Correlation Engine (Recommended):**\n"
            "Sentinel's multi-agent deterministic detection engine. Instead of looking at events in isolation, it analyzes "
            "cross-vector activity across continuous sliding windows (e.g., creating an invite, deleting channels, and banning a member "
            "in the same 30 seconds). It assigns graduated attribution confidence (Verified, Probable, Inferred) and can trigger "
            "automated emergency containment with immutable SHA-256 state tracking.\n\n"
            "**2. Standard Heuristic Engine:**\n"
            "A fast single-event threshold counter. It evaluates only one specific vector at a time (e.g. '3 channel deletions within 10s') "
            "and applies direct punishments. It does not perform cross-event correlation or multi-agent quorum review."
        ),
        "tip": "Use the Aegis Advanced Engine for enterprise resilience and stealth attack pattern detection.",
    },
    "shadow_mode": {
        "title": "Shadow Mode (Simulation)",
        "emoji": "👻",
        "short": "Safe simulation mode where threats are analyzed and journaled without mutating live Discord permissions.",
        "details": (
            "**What is Shadow Mode?**\n"
            "In Shadow Mode, Sentinel executes all threat evaluation, anomaly scoring, and emergency containment logic in "
            "simulation. It creates complete journal entries and sends forensic alerts to admins, but does **not** modify live "
            "Discord role permissions or lock channels.\n\n"
            "**When should you use it?**\n"
            "Use Shadow Mode when first testing Sentinel in large production servers to observe how detection rules behave "
            "against your staff's daily workflows before enabling live autonomous enforcement."
        ),
        "tip": "Run in Shadow Mode for 24-48 hours to tune your rapid ban/kick thresholds with zero risk of false alarms.",
    },
    "lockdown": {
        "title": "Emergency Containment (Lockdown)",
        "emoji": "🔒",
        "short": "Autonomous server-wide isolation stripping dangerous administrative rights and sealing channels.",
        "details": (
            "**What happens during Emergency Containment?**\n"
            "When Sentinel detects an active nuke attack or when an owner issues a manual lockdown:\n"
            "1. **Selective Permission Stripping**: Dangerous rights (Administrator, Manage Channels, Manage Roles, Ban, Kick) "
            "are temporarily stripped from non-whitelisted roles.\n"
            "2. **Channel Overwrite Seal**: Channels are locked to stop attackers from spamming or modifying settings.\n"
            "3. **Cryptographic Baseline**: A SHA-256 fingerprint of all pre-lockdown permissions is recorded atomically in the database.\n"
            "4. **Safe Shielding**: Sentinel's own roles and designated recovery roles are NEVER stripped."
        ),
        "tip": "Sentinel includes a confirmation step and strictly prevents duplicate backups to avoid corrupting baseline states.",
    },
    "duplicate_backup": {
        "title": "Duplicate Backup Safeguard",
        "emoji": "🛡️",
        "short": "Safety protocol ensuring Sentinel never creates a second conflicting backup over an active containment session.",
        "details": (
            "**Why does this safeguard exist?**\n"
            "When a server enters lockdown, permissions are sanitized (e.g., Administrator is stripped). If Sentinel created "
            "a second backup *during* an active lockdown, it would snapshot the stripped state as the 'normal' state—permanently "
            "destroying your original configuration!\n\n"
            "**How does Sentinel protect you?**\n"
            "Sentinel checks if a lockdown is already active for your guild. If so, it blocks duplicate execution and requires "
            "recovering the existing session first. Your original clean baseline remains 100% safe."
        ),
        "tip": "Always use '$lockdown recover' to lift containment before initiating a fresh session.",
    },
    "recovery": {
        "title": "Reversible Recovery & Rollback",
        "emoji": "🔓",
        "short": "Atomic restoration of pre-lockdown role permissions and channel overwrites from baseline snapshots.",
        "details": (
            "**How does Recovery work?**\n"
            "Recovery reads the exact before-state recorded in the Permission Journal and applies it back via the Discord API. "
            "Every role and overwrite mutation is verified.\n\n"
            "**Conflict Detection (Preserving Human Intent):**\n"
            "If an admin manually altered a role or channel *after* lockdown was applied, Sentinel detects that the current Discord state "
            "differs from both the before-state and the applied state. Sentinel preserves the admin's changes rather than clobbering them!"
        ),
        "tip": "Recovery can be triggered via '$lockdown recover' or the one-click 'Begin Recovery' button in alert notifications.",
    },
    "quorum": {
        "title": "Multi-Admin Quorum Consensus",
        "emoji": "⚖️",
        "short": "Requirement for multiple independent administrator votes before high-impact security actions execute.",
        "details": (
            "**What is Quorum?**\n"
            "A quorum is the minimum number of verified administrators required to approve an action. Sentinel enforces quorums for:\n"
            "• **Recovery Rollback**: Requires configured approvals (default 2) if triggered by a non-owner recovery admin.\n"
            "• **Threat Confirmation**: Requires distinct admin votes to confirm an incident.\n"
            "• **False Alarm Dismissal**: Requires 3 distinct reviewers to dismiss an alert, preventing rogue individuals from burying attacks.\n\n"
            "**Conflict of Interest Safeguard:**\n"
            "The subject of an incident (the accused account) is strictly forbidden from voting on their own review!"
        ),
        "tip": "The Root Server Owner can always execute recovery immediately without waiting for quorum.",
    },
    "whitelist": {
        "title": "Whitelist System",
        "emoji": "👥",
        "short": "Designation of trusted users, roles, and channels with mode-aware protection.",
        "details": (
            "**How Whitelists work in both modes:**\n\n"
            "• **In Aegis Advanced Observation Engine (Graduated Trust):**\n"
            "Whitelisted accounts execute normal maintenance tasks without triggering reactive punishments. However, their destructive "
            "bursts are still recorded in the forensic observation journal. If an account is hijacked by a token-grabber, Sentinel's "
            "anomaly scoring will still alert other administrators!\n\n"
            "• **In Standard Heuristic Engine (Direct Bypass):**\n"
            "Whitelisted entities completely bypass event count thresholds."
        ),
        "tip": "You can whitelist entire roles, specific users, or isolated channels using '$whitelist user @member'.",
    },
    "extraowner": {
        "title": "Extra Owners",
        "emoji": "👑",
        "short": "High-trust co-owners granted full application-level security governance within Sentinel.",
        "details": (
            "**What is an Extra Owner?**\n"
            "An Extra Owner is a designated administrator who has full permission to configure Anti-Nuke, manage whitelists, "
            "trigger lockdowns, and adjust policies in Sentinel.\n\n"
            "**Crucial Distinction:**\n"
            "Extra Owner status is purely inside Sentinel's application logic. It does **not** transfer Discord server ownership "
            "or grant Discord Crown privileges. Only the Root Server Owner can add or remove Extra Owners."
        ),
        "tip": "Use Extra Owners for trusted server co-founders or head developers.",
    },
    "thresholds": {
        "title": "Burst Limits & Time Windows (Thresholds)",
        "emoji": "⏱️",
        "short": "Maximum allowed occurrences of an action before disciplinary mitigation triggers.",
        "details": (
            "**Understanding Thresholds:**\n"
            "A threshold consists of a **count** and a **window in seconds**.\n"
            "For example: `Channel Deletion: 2 per 15s` means an account may delete 1 channel, but if a second channel deletion "
            "occurs within 15 seconds, Sentinel classifies it as a potential nuke attempt and intervenes immediately.\n\n"
            "**Configuring Thresholds:**\n"
            "You can configure thresholds per vector using '$thresholds' or through the interactive Anti-Nuke Control Center."
        ),
        "tip": "For sensitive vectors like Webhooks and Bots, set threshold count to 1 for instant zero-tolerance defense.",
    },
    "punishments": {
        "title": "Punishment Actions",
        "emoji": "⚡",
        "short": "Automated disciplinary sanctions applied to accounts that cross threshold burst limits.",
        "details": (
            "**Available Punishment Sanctions:**\n"
            "• **Ban (`ban`):** Permanent guild ban and message purge.\n"
            "• **Kick (`kick`):** Removal from the guild (they may rejoin if invited).\n"
            "• **Strip Roles (`strip_roles`):** Removes all administrative and dangerous roles from the member.\n"
            "• **Quarantine (`quarantine`):** Strips all roles and assigns a restrictive Quarantine role.\n"
            "• **Timeout (`timeout`):** Discord native communication timeout for 28 days."
        ),
        "tip": "Configure punishments per vector using '$punishment' or select preset modes like Hard or Ultimate.",
    },
    "posture": {
        "title": "Security Posture Diagnostic",
        "emoji": "📋",
        "short": "Comprehensive automated audit of Discord role hierarchies, bot permissions, and configuration health.",
        "details": (
            "**What does Posture Audit check?**\n"
            "1. **Role Hierarchy**: Confirms Sentinel's top role is positioned above monitored administrative roles.\n"
            "2. **Bot Permissions**: Validates that Sentinel holds Manage Roles, Manage Channels, Ban, and Kick.\n"
            "3. **Unmanaged Dangerous Roles**: Detects non-bot roles holding Administrator or Manage Guild.\n"
            "4. **Channel Seal Feasibility**: Checks text channel overwrite permissions.\n"
            "5. **Logging Webhooks**: Confirms dedicated forensics channels are configured."
        ),
        "tip": "Run '$posture' or '$lockdown posture' after adding new staff roles or restructuring server permissions.",
    },
    "checksum": {
        "title": "Cryptographic Checksum (SHA-256)",
        "emoji": "🔐",
        "short": "Cryptographic fingerprint of pre-lockdown permissions ensuring 100% tamper-evident reversibility.",
        "details": (
            "**How Checksum works:**\n"
            "Before modifying a single role or channel overwrite, Sentinel serializes the baseline state into a canonical JSON "
            "payload and computes its SHA-256 hash. During recovery, the state is verified against this fingerprint, guaranteeing "
            "that your server is restored to its exact pre-attack state with zero data corruption."
        ),
        "tip": "You can inspect the active checksum in '$lockdown status' or '$security'.",
    },
    "ticketbots": {
        "title": "Ticket Bot Exemptions",
        "emoji": "🎫",
        "short": "Exemption allowing support bots (e.g. Ticket Tool) to create and delete channels without triggering Anti-Nuke.",
        "details": (
            "**Why is Ticket Bot Exemption critical?**\n"
            "Support ticket bots frequently create and delete private channels when members open or close support tickets. "
            "Without an exemption, Anti-Nuke would mistake ticket closures for a channel wipe attack!\n\n"
            "Exempting a bot whitelist strictly isolates channel operations for tickets while keeping other vectors guarded."
        ),
        "tip": "Configure ticket bot exemptions using '$ticketbots' or through the Anti-Nuke Access Manager.",
    },
}


def build_explain_view(keyword_key: Optional[str] = None) -> Any:
    """Builds the interactive keyword explanation container with select menu navigation."""
    sel = (
        SelectMenuBuilder()
        .set_custom_id("sec_exp:select")
        .set_placeholder("Select a security keyword to view in-depth explanation...")
    )

    for k, v in KEYWORDS_GLOSSARY.items():
        sel.add_option(
            label=v["title"][:100],
            value=k,
            description=v["short"][:100],
            emoji=v.get("emoji"),
            default=(k == keyword_key),
        )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id("sec:hub:0")
            .set_label("Security Hub")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id("an:dashboard:0")
            .set_label("Anti-Nuke Center")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("gear", "⚙️"))
        )
    )

    if keyword_key and keyword_key in KEYWORDS_GLOSSARY:
        data = KEYWORDS_GLOSSARY[keyword_key]
        header = f"### {data.get('emoji', '📖')} Keyword Deep-Dive: **{data['title']}**"
        content = (
            f"*{data['short']}*\n\n"
            f"{data['details']}\n\n"
            f"💡 **Security Tip:** {data['tip']}\n\n"
            f"-# Select another keyword below to continue exploring Sentinel's security architecture."
        )
        color = COLORS.get("info", "#0844C5")
    else:
        header = f"### {EMOJIS.get('info', '📖')} {settings.BOT_NAME} Security Glossary & Knowledge Base"
        top_list = [
            f"• **{v['title']}** (`{k}`): {v['short']}"
            for k, v in list(KEYWORDS_GLOSSARY.items())[:6]
        ]
        content = (
            f"Welcome to the **{settings.BOT_NAME} Security Glossary**. Every concept, defensive mode, "
            f"and safeguard is explained here in clear detail so your team always operates with complete confidence.\n\n"
            f"**Core Security Concepts:**\n"
            + "\n".join(top_list)
            + "\n\n"
            f"👇 **Select any keyword from the menu below** to view complete architectural details, practical examples, "
            f"and configuration recommendations."
        )
        color = COLORS.get("default", "#0844C5")

    box = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(header)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(content)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Education • Zero-Confusion Policy")
        .build()
    )
    return box


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    target_key = args[0].lower().strip() if args else None

    # Handle alias matches
    alias_map = {
        "an": "antinuke",
        "obs": "observation",
        "aegis": "observation",
        "shadow": "shadow_mode",
        "sim": "shadow_mode",
        "lock": "lockdown",
        "containment": "lockdown",
        "backup": "duplicate_backup",
        "backups": "duplicate_backup",
        "rollback": "recovery",
        "restore": "recovery",
        "vote": "quorum",
        "votes": "quorum",
        "consensus": "quorum",
        "wl": "whitelist",
        "extraowners": "extraowner",
        "coowner": "extraowner",
        "threshold": "thresholds",
        "limit": "thresholds",
        "punishment": "punishments",
        "sanctions": "punishments",
        "audit": "posture",
        "hierarchy": "posture",
        "hash": "checksum",
        "sha256": "checksum",
        "ticket": "ticketbots",
        "ticketbot": "ticketbots",
    }
    if target_key in alias_map:
        target_key = alias_map[target_key]

    view = build_explain_view(target_key)
    return await send_response(message, view)

import math
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response
from discord import MessageFlags, ButtonStyle

PAGE_SIZE = 8

name = "listservers"
aliases = ["guilds", "servers", "serverlist"]
description = "Display connected Discord servers, member counts, and statistics (Bot Owner Only)."
category = "Owner"
usage = "listservers [query|page]"
owner_only = True

sub_commands = [
    {"name": "[query]", "description": "Filter connected servers by name or guild ID."},
    {"name": "page <number>", "description": "View a specific page of connected servers."},
]

def get_guilds_list(client: Any, query: Optional[str] = None) -> List[Dict[str, Any]]:
    if not client or not hasattr(client, "guilds"):
        return []

    guilds = list(client.guilds)
    if query and query.strip():
        q = query.strip().lower()
        guilds = [g for g in guilds if q in str(g.id).lower() or (g.name and q in g.name.lower())]

    res = []
    for g in guilds:
        m_count = getattr(g, "member_count", None) or len(getattr(g, "members", []))
        owner_id = str(g.owner_id) if hasattr(g, "owner_id") and g.owner_id else None
        res.append({
            "id": str(g.id),
            "name": g.name or "Unnamed Guild",
            "memberCount": m_count if isinstance(m_count, int) else "N/A",
            "ownerId": owner_id,
            "available": not getattr(g, "unavailable", False),
        })

    res.sort(key=lambda x: x["memberCount"] if isinstance(x["memberCount"], int) else 0, reverse=True)
    return res

def build_server_list_container(client: Any, page: int, query: Optional[str] = None):
    E = EMOJIS
    C = COLORS

    emojis = {
        "server": E.get("server") or "🖥️",
        "member": E.get("members") or E.get("user") or "👥",
        "refresh": E.get("reload") or "🔄",
        "search": E.get("search") or "🔍",
        "crown": E.get("owner") or "👑",
        "dot": E.get("dot") or "•",
    }

    all_guilds = get_guilds_list(client, query)
    total = len(all_guilds)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    safe_page = max(0, min(page, total_pages - 1))
    current_guilds = all_guilds[safe_page * PAGE_SIZE : (safe_page + 1) * PAGE_SIZE]

    total_connected = len(client.guilds) if (client and hasattr(client, "guilds")) else total
    total_cached_members = sum(g["memberCount"] for g in all_guilds if isinstance(g["memberCount"], int))

    query_str = f" • **Filter:** `{query}` ({total} matches)" if query else ""
    container = (
        ContainerBuilder()
        .set_accent_color(C.get("default", "#3B82F6"))
        .add_text_display(f"### {emojis['server']} Connected Discord Servers")
        .add_text_display(
            f"**Total Connected:** `{total_connected}` servers • **Aggregate Members:** `{total_cached_members}`\n"
            f"**Page:** `{safe_page + 1}/{total_pages}`{query_str}"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
    )

    if not current_guilds:
        container.add_text_display("*(No connected servers match the search criteria).*")
    else:
        lines = []
        for idx, g in enumerate(current_guilds):
            index_num = safe_page * PAGE_SIZE + idx + 1
            member_str = f"{g['memberCount']:,} members" if isinstance(g['memberCount'], int) else str(g['memberCount'])
            owner_str = f" • {emojis['crown']} <@{g['ownerId']}>" if g.get("ownerId") else ""
            avail_str = "" if g.get("available") else " ⚠️ *(Outage / Unavailable)*"
            lines.append(
                f"**{index_num}. {g['name']}**{avail_str}\n"
                f"> **ID:** `{g['id']}` • {emojis['member']} `{member_str}`{owner_str}"
            )
        container.add_text_display("\n\n".join(lines))

    container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)

    # Controls
    row = ActionRowBuilder()
    row.add_button(
        ButtonBuilder()
        .set_custom_id(f"listservers:prev:{safe_page}{f':{query}' if query else ''}")
        .set_label("Previous")
        .set_style(ButtonStyle.Secondary)
        .set_disabled(safe_page <= 0)
    )
    row.add_button(
        ButtonBuilder()
        .set_custom_id(f"listservers:next:{safe_page}{f':{query}' if query else ''}")
        .set_label("Next")
        .set_style(ButtonStyle.Secondary)
        .set_disabled(safe_page >= total_pages - 1)
    )
    row.add_button(
        ButtonBuilder()
        .set_custom_id(f"listservers:refresh:{safe_page}{f':{query}' if query else ''}")
        .set_label("Refresh")
        .set_style(ButtonStyle.Secondary)
    )
    row.add_button(
        ButtonBuilder()
        .set_custom_id("listservers:close")
        .set_label("Close")
        .set_style(ButtonStyle.Danger)
    )
    container.add_action_row(row)

    return container.build(), safe_page, total_pages

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""
    client = getattr(ctx, "client", getattr(message, "client", None))

    owner_ids = settings.OWNER_IDS

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is strictly restricted to authorized bot owners."
        return await send_response(message, denied_msg, ephemeral=True)

    query = None
    page = 0

    if args:
        if args[0].isdigit():
            page = max(0, int(args[0]) - 1)
        else:
            query = " ".join(args).strip()

    built, page, total_pages = build_server_list_container(client, page, query)
    reply_msg = await send_response(message, built)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=300.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
    )

    if collector:
        async def on_action(inter):
            nonlocal page, query
            custom_id = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("custom_id", "")
            if not custom_id.startswith("listservers:"):
                return

            parts = custom_id.split(":")
            action_name = parts[1]

            if action_name == "close":
                if hasattr(inter, "response"):
                    await inter.response.edit_message(content="🔒 **Server list closed**.", embed=None, view=None)
                return

            if action_name == "prev":
                page = max(0, page - 1)
            elif action_name == "next":
                page = page + 1

            new_b, page, _ = build_server_list_container(client, page, query)
            if hasattr(inter, "response"):
                await inter.response.edit_message(view=new_b.view)

        collector.on("listservers:close", on_action)
        import re
        collector.on(re.compile(r"^listservers:"), on_action)

import re
import math
from typing import List, Dict, Any, Optional
import discord
from config.settings import config, COLORS, EMOJIS
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
    MessageFlags,
    attach_collector,
)
from apps.bot.discord.commands.registry import commands_registry
from shared.types.command_record import CommandType, CommandStatus

HOME_PAGE_SIZE = 10
CATEGORY_PAGE_SIZE = 8
SUBCOMMAND_PAGE_SIZE = 6
COLLECTOR_TIMEOUT = 300_000

name = "help"
aliases = ["h", "commands"]
description = "Browse commands and view detailed help."
category = "Utility"
usage = "help <command|category>"
cooldown = 3.0

async def execute(ctx: Any, commandType: Any, message: Any, args: Optional[List[str]] = None):
    args = args or []
    isSlash = (commandType == CommandType.SLASH or str(commandType).lower() == "slash")

    E = config.Emojis or {}
    colors = config.Colors or {}

    bot_settings = getattr(config.settings, "bot", {})
    bot = bot_settings.get("name", "Mussoorie")
    botPrefix = bot_settings.get("prefix", "$")

    icon = E.get("help", "📖")
    info = E.get("info", "💡")
    error = E.get("error", "❌")
    arrowLeft = E.get("arrowLeft", "◀")
    arrowRight = E.get("arrowRight", "▶")

    pageEmojis = {
        "first": E.get("firstPage", E.get("first", "⏮️")),
        "previous": E.get("previousPage", E.get("previous", "◀️")),
        "next": E.get("nextPage", E.get("next", "▶️")),
        "last": E.get("lastPage", E.get("last", "⏭️")),
    }

    botInvite = bot_settings.get("invite") or config.links.get("botInvite")
    serverInvite = bot_settings.get("supportInvite") or config.links.get("supportServer")

    if isSlash:
        user_obj = getattr(message, "user", None) or getattr(message, "author", None)
        ownerId = str(user_obj.id) if user_obj else ""
    else:
        author_obj = getattr(message, "author", None)
        ownerId = str(author_obj.id) if author_obj else ""

    configuredOwners = bot_settings.get("owner_ids", [])
    if isinstance(configuredOwners, list):
        ownerIds = [str(x) for x in configuredOwners]
    elif configuredOwners:
        ownerIds = [str(configuredOwners)]
    else:
        ownerIds = []

    isBotOwner = (ownerId in ownerIds)

    if isSlash:
        # Check interaction options
        query = ""
        if hasattr(message, "data") and isinstance(message.data, dict):
            for opt in message.data.get("options", []):
                if opt.get("name") == "query":
                    query = str(opt.get("value", "")).strip()
                    break
        if not query and args:
            query = " ".join(args).strip()
    else:
        query = " ".join(args).strip() if isinstance(args, list) else str(args or "").strip()

    def normalize(val: Any) -> str:
        text = str(val or "").lower().strip()
        return re.sub(r"\s+", " ", text)

    def data(cmd: Any) -> Any:
        return getattr(cmd, "command", cmd)

    def categoryOf(cmd: Any) -> str:
        d = data(cmd)
        cat = getattr(d, "category", None) or getattr(cmd, "category", None) or "Uncategorized"
        return str(cat)

    # ---------------------------------------------------------
    # Emoji helpers
    # ---------------------------------------------------------
    def getCategoryEmoji(cat: str) -> str:
        val = normalize(cat)
        if re.search(r"econ|money|bank|cash|coin|wallet|finance|reward", val):
            return E.get("money", E.get("bank", E.get("balance", "💰")))
        if re.search(r"admin|moder|security|staff|ban|kick|warn", val):
            return E.get("moderation", E.get("shield", "🛡️"))
        if re.search(r"util|tool|helper|general|misc", val):
            return E.get("tools", E.get("tool", "🛠️"))
        if re.search(r"ticket|support|helpdesk|report", val):
            return E.get("ticket", "🎫")
        if re.search(r"shop|store|inventory|stock|product|market", val):
            return E.get("inventory", "📦")
        if re.search(r"music|audio|song|voice", val):
            return E.get("music", "🎵")
        if re.search(r"level|rank|xp|reputation|leaderboard", val):
            return E.get("leveling", "🏆")
        if re.search(r"giveaway|event|contest|prize", val):
            return E.get("giveaway", "🎁")
        if re.search(r"ai|gpt|assistant|machine learning", val):
            return E.get("ai", "🤖")
        if re.search(r"dev|owner|system|core", val):
            return E.get("developer", E.get("owner", "👑"))
        if re.search(r"setting|config|setup", val):
            return E.get("settings", "⚙️")
        if re.search(r"channel|server|guild|role", val):
            return E.get("server", "🗂️")
        if re.search(r"log|audit|history", val):
            return E.get("logs", "📋")
        return E.get("category", "📌")

    def getTypeBadge(cmd: Any) -> str:
        t = getattr(cmd, "command_type", getattr(cmd, "type", CommandType.HYBRID))
        if t == CommandType.HYBRID or t == 2 or str(t).lower() == "hybrid":
            return f"{E.get('hybrid', '🔄')} Hybrid"
        if t == CommandType.SLASH or t == 1 or str(t).lower() == "slash":
            return f"{E.get('slash', '⚡')} Slash"
        return f"{E.get('prefix', '⌨️')} Prefix"

    def toButtonEmoji(val: Any, fallback: str) -> Any:
        return val or fallback

    def addSeparator(c: ContainerBuilder) -> ContainerBuilder:
        c.addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
        return c

    def pageIndicator(pg: int, tot: int) -> str:
        return f"-# {arrowLeft} Page **{pg + 1}/{tot}** {arrowRight}"

    # ---------------------------------------------------------
    # Command visibility and owner-only filtering
    # ---------------------------------------------------------
    def isOwnerOnlyCommand(cmd: Any) -> bool:
        d = data(cmd)
        cats = [
            getattr(d, "category", ""),
            getattr(cmd, "category", ""),
            getattr(getattr(cmd, "raw", None), "category", ""),
        ]
        cat_norms = [normalize(x) for x in cats if x]
        return bool(
            getattr(d, "owner_only", False) or
            getattr(d, "ownerOnly", False) or
            getattr(cmd, "owner_only", False) or
            getattr(cmd, "ownerOnly", False) or
            any(c in ("dev", "owner") for c in cat_norms)
        )

    def isEnabled(cmd: Any) -> bool:
        val = getattr(cmd, "enabled", True)
        if isinstance(val, bool):
            return val
        return str(val).lower() == "true"

    def isVisibleCommand(cmd: Any) -> bool:
        if not cmd:
            return False
        d = data(cmd)
        if isOwnerOnlyCommand(cmd) and not isBotOwner:
            return False
        status_val = getattr(cmd, "status", CommandStatus.ACTIVE)
        if status_val != CommandStatus.ACTIVE:
            return False
        if not isEnabled(cmd):
            return False
        if getattr(d, "hidden", False) or getattr(cmd, "hidden", False):
            return False
        return True

    commands_list = []
    seenNames = set()
    for record in commands_registry.list_all():
        if not record or not isVisibleCommand(record):
            continue
        d = data(record)
        c_name = getattr(record, "name", None) or getattr(d, "name", None)
        if not c_name:
            continue
        key = normalize(c_name)
        if key in seenNames:
            continue
        seenNames.add(key)
        commands_list.append(record)

    commands_list.sort(key=lambda x: str(getattr(x, "name", "") or getattr(data(x), "name", "")).lower())

    # ---------------------------------------------------------
    # Subcommands and aliases
    # ---------------------------------------------------------
    def getSubs(cmd: Any) -> List[Dict[str, Any]]:
        d = data(cmd)
        for attr in ("sub_commands", "subCommands", "subcommands"):
            val = getattr(d, attr, None) or getattr(cmd, attr, None)
            if isinstance(val, list) and val:
                return val
        return []

    def getAliases(cmd: Any) -> List[str]:
        d = data(cmd)
        aliases_val = getattr(d, "aliases", None) or getattr(cmd, "aliases", [])
        return [str(a) for a in aliases_val if a]

    totalCommandCount = sum(1 + len(getSubs(c)) for c in commands_list)
    categories = sorted(list(set(categoryOf(c) for c in commands_list)))

    # ---------------------------------------------------------
    # Search helpers
    # ---------------------------------------------------------
    def findCommand(search: str) -> Optional[Any]:
        val = normalize(search)
        for cmd in commands_list:
            d = data(cmd)
            names = [getattr(cmd, "name", None), getattr(d, "name", None)] + getAliases(cmd)
            if any(normalize(n) == val for n in names if n):
                return cmd
        return None

    def findParent(search: str) -> Optional[Any]:
        val = normalize(search)
        matched = []
        for cmd in commands_list:
            d = data(cmd)
            names = [getattr(cmd, "name", None), getattr(d, "name", None)] + getAliases(cmd)
            for n in names:
                if n:
                    norm = normalize(n)
                    if val == norm or val.startswith(f"{norm} "):
                        matched.append(cmd)
                        break
        if matched:
            matched.sort(
                key=lambda x: len(normalize(getattr(x, "name", "") or getattr(data(x), "name", ""))),
                reverse=True
            )
            return matched[0]
        return None

    def findSubcommand(cmd: Any, search: str) -> Optional[Dict[str, Any]]:
        val = normalize(search)
        parentName = normalize(getattr(cmd, "name", "") or getattr(data(cmd), "name", ""))
        for sub in getSubs(cmd):
            name_val = normalize(sub.get("name", ""))
            usage_val = normalize(sub.get("usage", ""))
            if name_val == val or usage_val == val or f"{parentName} {name_val}" == val:
                return sub
        return None

    def findCategory(search: str) -> Optional[str]:
        val = normalize(search)
        for cat in categories:
            if normalize(cat) == val:
                return cat
        return None

    def suggest(search: str) -> Optional[str]:
        val = normalize(search)
        if not val:
            return None
        candidates = []
        for cmd in commands_list:
            d = data(cmd)
            c_name = getattr(cmd, "name", None) or getattr(d, "name", None)
            if c_name: candidates.append(c_name)
            candidates.extend(getAliases(cmd))
            for sub in getSubs(cmd):
                s_name = sub.get("name")
                if s_name: candidates.append(s_name)
                s_usage = sub.get("usage")
                if s_usage: candidates.append(s_usage)
        candidates.extend(categories)

        def score(cand: str) -> float:
            text = normalize(cand)
            if text == val:
                return 1.0
            if text in val or val in text:
                return 0.8
            matches = sum(1 for i in range(min(len(val), len(text))) if val[i] == text[i])
            return matches / max(len(val), len(text), 1)

        unique_cands = [c for c in set(candidates) if c]
        scored = [{"cand": c, "score": score(c)} for c in unique_cands]
        scored = [x for x in scored if x["score"] >= 0.4]
        if scored:
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[0]["cand"]
        return None

    # ---------------------------------------------------------
    # Permission formatting
    # ---------------------------------------------------------
    def readablePermission(perm: Any) -> str:
        if isinstance(perm, str):
            clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", perm)
            clean = clean.replace("_", " ")
            return clean.title()
        return str(perm)

    def formatPermissions(val: Any) -> str:
        if isinstance(val, list) and val:
            return ", ".join(f"`{readablePermission(p)}`" for p in val)
        return "`None`"

    # ---------------------------------------------------------
    # Pagination helpers
    # ---------------------------------------------------------
    def pageCount(length: int, size: int) -> int:
        return max(1, math.ceil(length / size))

    def clamp(pg: int, tot: int) -> int:
        return max(0, min(pg, tot - 1))

    def resolvePage(act: str, cur: int, tot: int) -> int:
        if act == "first":
            return 0
        if act == "prev":
            return max(0, cur - 1)
        if act == "next":
            return min(tot - 1, cur + 1)
        if act == "last":
            return tot - 1
        return cur

    def makeContainer(col: Optional[str] = None) -> ContainerBuilder:
        chosen = col or colors.get("cmd_help") or colors.get("default", "#0844C5")
        return ContainerBuilder().setAccentColor(chosen)

    def addLinks(c: ContainerBuilder) -> bool:
        if not botInvite and not serverInvite:
            return False

        def populate_row(row: ActionRowBuilder) -> ActionRowBuilder:
            if botInvite:
                row.addButton({
                    "style": ButtonStyle.Link,
                    "label": "Add Bot",
                    "url": botInvite,
                })
            if serverInvite:
                row.addButton({
                    "style": ButtonStyle.Link,
                    "label": "Support Server",
                    "url": serverInvite,
                })
            return row

        c.addActionRow(populate_row)
        return True

    def pagination(c: ContainerBuilder, pageId: str, pg: int, tot: int) -> bool:
        if tot <= 1:
            return False

        def makeId(act: str) -> str:
            return f"{pageId}:{pg}:{act}"

        def populate_row(row: ActionRowBuilder) -> ActionRowBuilder:
            row.addButton({
                "custom_id": makeId("first"),
                "emoji": toButtonEmoji(pageEmojis["first"], "⏮️"),
                "style": ButtonStyle.Secondary,
                "disabled": pg <= 0,
            })
            row.addButton({
                "custom_id": makeId("prev"),
                "emoji": toButtonEmoji(pageEmojis["previous"], "◀️"),
                "style": ButtonStyle.Secondary,
                "disabled": pg <= 0,
            })
            row.addButton({
                "custom_id": makeId("next"),
                "emoji": toButtonEmoji(pageEmojis["next"], "▶️"),
                "style": ButtonStyle.Secondary,
                "disabled": pg >= tot - 1,
            })
            row.addButton({
                "custom_id": makeId("last"),
                "emoji": toButtonEmoji(pageEmojis["last"], "⏭️"),
                "style": ButtonStyle.Secondary,
                "disabled": pg >= tot - 1,
            })
            return row

        c.addActionRow(populate_row)
        return True

    # ---------------------------------------------------------
    # Home page
    # ---------------------------------------------------------
    def home(pg: int = 0) -> Any:
        tot = pageCount(len(commands_list), HOME_PAGE_SIZE)
        pg = clamp(pg, tot)
        visible = commands_list[pg * HOME_PAGE_SIZE : (pg + 1) * HOME_PAGE_SIZE]

        lines = []
        for cmd in visible:
            d = data(cmd)
            c_name = getattr(cmd, "name", None) or getattr(d, "name", None)
            desc_val = getattr(d, "description", None) or getattr(cmd, "description", None) or "No description available."
            cmd_icon = E.get("command", "▫️")
            lines.append(f"{cmd_icon} **{botPrefix}{c_name}** — {desc_val}")

        c = makeContainer()
        c.addTextDisplay(
            f"### {icon} {bot} Commands\n"
            f"{info} Browse available commands using the navigation buttons.\n"
            f"Use `{botPrefix}help <command>` for detailed help."
        ).addSeparator({"divider": True})

        c.addTextDisplay("\n\n".join(lines) if lines else "No commands are available.")
        c.addSeparator({"divider": True})

        c.addTextDisplay(
            f"{pageIndicator(pg, tot)}\n"
            f"-# {E.get('prefix', '⌨️')} Prefix: `{botPrefix}` · "
            f"{E.get('stats', '📊')} {totalCommandCount} total commands"
        )

        pagination(c, "home", pg, tot)
        addLinks(c)
        return c.build()

    # ---------------------------------------------------------
    # Category page
    # ---------------------------------------------------------
    def categoryPage(cat_name: str, pg: int = 0) -> Any:
        filtered = [cmd for cmd in commands_list if normalize(categoryOf(cmd)) == normalize(cat_name)]
        filtered.sort(key=lambda x: str(getattr(x, "name", "") or getattr(data(x), "name", "")).lower())

        tot = pageCount(len(filtered), CATEGORY_PAGE_SIZE)
        pg = clamp(pg, tot)
        visible = filtered[pg * CATEGORY_PAGE_SIZE : (pg + 1) * CATEGORY_PAGE_SIZE]

        lines = []
        for cmd in visible:
            d = data(cmd)
            subs = getSubs(cmd)
            c_name = getattr(cmd, "name", None) or getattr(d, "name", None)
            usage_val = getattr(d, "usage", None) or getattr(cmd, "usage", None) or c_name
            desc_val = getattr(d, "description", None) or getattr(cmd, "description", None) or "No description available."
            sub_count_text = f" · {len(subs)} subcommands" if subs else ""
            lines.append(
                f"{E.get('command', '▫️')} **`{botPrefix}{usage_val}`**\n"
                f"{getTypeBadge(cmd)} · {desc_val}{sub_count_text}"
            )

        c = makeContainer()
        c.addTextDisplay(
            f"### {getCategoryEmoji(cat_name)} {cat_name}\n"
            f"{info} {len(filtered)} command{'s' if len(filtered) != 1 else ''} in this category"
        )
        c.addSeparator({"divider": True})
        c.addTextDisplay("\n\n".join(lines) if lines else "No commands in this category.")
        c.addSeparator({"divider": True})
        c.addTextDisplay(pageIndicator(pg, tot))

        from urllib.parse import quote
        pagination(c, f"category:{quote(cat_name)}", pg, tot)
        addLinks(c)
        return c.build()

    # ---------------------------------------------------------
    # Command details
    # ---------------------------------------------------------
    def details(cmd: Any, pg: int = 0) -> Any:
        d = data(cmd)
        c_name = getattr(cmd, "name", None) or getattr(d, "name", None)
        subs = getSubs(cmd)
        aliases_list = getAliases(cmd)

        aliasText = ", ".join(f"`{botPrefix}{a}`" for a in aliases_list) if aliases_list else "`None`"
        users = getattr(cmd, "userPermissions", None) or getattr(cmd, "user_permissions", [])
        bots = getattr(cmd, "botPermissions", None) or getattr(cmd, "bot_permissions", [])

        tot = pageCount(len(subs), SUBCOMMAND_PAGE_SIZE)
        pg = clamp(pg, tot)
        visible_subs = subs[pg * SUBCOMMAND_PAGE_SIZE : (pg + 1) * SUBCOMMAND_PAGE_SIZE]

        cmd_type = getattr(cmd, "command_type", getattr(cmd, "type", CommandType.HYBRID))
        isHybrid = (cmd_type == CommandType.HYBRID or cmd_type == 2 or str(cmd_type).lower() == "hybrid")
        isSlashOnly = (cmd_type == CommandType.SLASH or cmd_type == 1 or str(cmd_type).lower() == "slash")

        usage_val = getattr(d, "usage", None) or getattr(cmd, "usage", None) or c_name
        if isHybrid:
            invocation = (
                f"**{E.get('prefix', '⌨️')} Prefix:** `{botPrefix}{usage_val}`\n"
                f"**{E.get('slash', '⚡')} Slash:** `/{c_name}`"
            )
        elif isSlashOnly:
            invocation = f"**{E.get('slash', '⚡')} Slash:** `/{c_name}`"
        else:
            invocation = f"**{E.get('prefix', '⌨️')} Prefix:** `{botPrefix}{usage_val}`"

        cooldown_val = getattr(d, "cooldown", None) or getattr(cmd, "cooldown", 0)
        cooldown_num = float(cooldown_val) if cooldown_val else 0.0
        if cooldown_num >= 1.0:
            cooldownText = f"{cooldown_num}s" if cooldown_num != int(cooldown_num) else f"{int(cooldown_num)}s"
        else:
            cooldownText = f"{int(cooldown_num * 1000)}ms"

        desc_val = getattr(d, "description", None) or getattr(cmd, "description", None) or "No description available."

        c = makeContainer()
        c.addTextDisplay(f"### {icon} {c_name}\n{desc_val}")
        c.addSeparator({"divider": True})

        cat_val = categoryOf(cmd)
        c.addTextDisplay(
            f"**{E.get('info', 'ℹ️')} Command information**\n"
            f"**Type:** {getTypeBadge(cmd)}\n"
            f"**Category:** {getCategoryEmoji(cat_val)} {cat_val}\n"
            f"**Cooldown:** {cooldownText}\n"
            f"**Aliases:** {aliasText}"
        )

        if subs:
            c.addSeparator({"divider": True})
            sub_icon = E.get("subcommand", E.get("command", "▫️"))
            sub_lines = []
            for sub in visible_subs:
                s_name = sub.get("name", "subcommand")
                s_usage = sub.get("usage", f"{c_name} {s_name}")
                s_desc = sub.get("description", "No description available.")
                sub_lines.append(f"**`{botPrefix}{s_usage}`**\n{s_desc}")

            c.addTextDisplay(
                f"**{sub_icon} Subcommands · {len(subs)}**\n\n" +
                ("\n\n".join(sub_lines))
            )
            if tot > 1:
                c.addTextDisplay(pageIndicator(pg, tot))

        c.addSeparator({"divider": True})
        c.addTextDisplay(
            f"**{E.get('usage', E.get('info', '📝'))} Usage**\n{invocation}\n\n"
            f"**{E.get('permissions', '🔐')} Permissions**\n"
            f"**User:** {formatPermissions(users)}\n"
            f"**Bot:** {formatPermissions(bots)}"
        )

        if subs:
            idx = commands_list.index(cmd) if cmd in commands_list else 0
            pagination(c, f"sub:{idx}", pg, tot)

        addLinks(c)
        return c.build()

    # ---------------------------------------------------------
    # Subcommand details
    # ---------------------------------------------------------
    def subcommandDetails(cmd: Any, sub: Dict[str, Any]) -> Any:
        d = data(cmd)
        c_name = getattr(cmd, "name", None) or getattr(d, "name", None)
        subName = sub.get("name", "subcommand")

        users = sub.get("userPermissions") or getattr(cmd, "user_permissions", [])
        bots = sub.get("botPermissions") or getattr(cmd, "bot_permissions", [])
        usage_val = sub.get("usage", f"{c_name} {subName}")

        cooldown_val = sub.get("cooldown") or getattr(cmd, "cooldown", 0)
        cooldown_num = float(cooldown_val) if cooldown_val else 0.0
        cooldownText = f"{cooldown_num}s" if cooldown_num >= 1.0 else f"{int(cooldown_num * 1000)}ms"

        aliases_list = sub.get("aliases", [])
        aliasText = ", ".join(f"`{botPrefix}{a}`" for a in aliases_list) if aliases_list else "`None`"

        c = makeContainer()
        c.addTextDisplay(
            f"### {icon} {c_name} {subName}\n"
            f"{sub.get('description', 'No description available.')}"
        )
        c.addSeparator({"divider": True})

        cat_val = categoryOf(cmd)
        c.addTextDisplay(
            f"**{E.get('info', 'ℹ️')} Subcommand information**\n"
            f"**Parent:** `{c_name}`\n"
            f"**Category:** {getCategoryEmoji(cat_val)} {cat_val}\n"
            f"**Usage:** `{botPrefix}{usage_val}`\n"
            f"**Cooldown:** {cooldownText}\n"
            f"**Aliases:** {aliasText}"
        )
        c.addSeparator({"divider": True})

        c.addTextDisplay(
            f"**{E.get('permissions', '🔐')} Permissions**\n"
            f"**User:** {formatPermissions(users)}\n"
            f"**Bot:** {formatPermissions(bots)}\n\n"
            f"-# {info} Use `{botPrefix}help {c_name}` for parent help."
        )

        addLinks(c)
        return c.build()

    # ---------------------------------------------------------
    # Not found
    # ---------------------------------------------------------
    def notFound(search: str) -> Any:
        sugg = suggest(search)
        error_color = colors.get("cmd_help_error") or colors.get("error", "#B21F1F")
        c = makeContainer(error_color)

        c.addTextDisplay(f"### {error} Nothing Found")
        c.addSeparator({"divider": True})

        did_you_mean = f"{info} Did you mean `{sugg}`?\n\n" if sugg else ""
        c.addTextDisplay(
            f"No command or category matches `{search}`.\n\n"
            f"{did_you_mean}"
            f"Use `{botPrefix}help` to browse commands."
        )
        addLinks(c)
        return c.build()

    # ---------------------------------------------------------
    # Resolve query
    # ---------------------------------------------------------
    def resolve(search: str) -> Any:
        if not search:
            return home(0)

        val = normalize(search)
        exact = findCommand(val)
        if exact:
            return details(exact, 0)

        parent = findParent(val)
        if parent:
            p_names = [getattr(parent, "name", None), getattr(data(parent), "name", None)] + getAliases(parent)
            norm_names = [normalize(n) for n in p_names if n]
            aliasMatch = next((n for n in norm_names if val.startswith(f"{n} ")), None)
            subQuery = val[len(aliasMatch):].strip() if aliasMatch else ""
            if subQuery:
                sub = findSubcommand(parent, subQuery)
                if sub:
                    return subcommandDetails(parent, sub)
            return details(parent, 0)

        subMatches = []
        for cmd in commands_list:
            sub = findSubcommand(cmd, val)
            if sub:
                subMatches.append({"cmd": cmd, "sub": sub})
        if len(subMatches) == 1:
            return subcommandDetails(subMatches[0]["cmd"], subMatches[0]["sub"])

        cat = findCategory(val)
        if cat:
            return categoryPage(cat, 0)

        return notFound(search)

    # ---------------------------------------------------------
    # Send response
    # ---------------------------------------------------------
    initial_container = resolve(query)

    sent_msg = None
    if isSlash and hasattr(message, "response"):
        if message.response.is_done():
            sent_msg = await message.followup.send(embed=initial_container, view=initial_container.view)
        else:
            await message.response.send_message(embed=initial_container, view=initial_container.view)
            sent_msg = message
    elif hasattr(message, "reply"):
        sent_msg = await message.reply(embed=initial_container, view=initial_container.view)
    elif hasattr(message, "channel"):
        sent_msg = await message.channel.send(embed=initial_container, view=initial_container.view)

    # ---------------------------------------------------------
    # Component collector
    # ---------------------------------------------------------
    def attachCollector(target_msg: Any):
        if not target_msg:
            return

        def interaction_filter(interaction: Any) -> bool:
            u_id = getattr(interaction.user, "id", None)
            return str(u_id) == str(ownerId)

        collector = attach_collector(
            target_msg,
            view=initial_container.view,
            time_ms=COLLECTOR_TIMEOUT,
            filter_fn=interaction_filter
        )

        async def on_collect(interaction: Any):
            try:
                custom_id = getattr(interaction, "customId", "") or interaction.data.get("custom_id", "")

                # 1. Home pagination
                homeMatch = re.match(r"^home:(\d+):(first|prev|next|last)$", custom_id)
                if homeMatch:
                    await interaction.deferUpdate()
                    current_pg, action = homeMatch.groups()
                    tot = pageCount(len(commands_list), HOME_PAGE_SIZE)
                    next_pg = resolvePage(action, int(current_pg), tot)
                    new_c = home(next_pg)
                    await interaction.update({"components": [new_c]})
                    collector.view = new_c.view
                    collector._wire_view(new_c.view)
                    return

                # 2. Category pagination
                from urllib.parse import unquote
                catMatch = re.match(r"^category:(.+):(\d+):(first|prev|next|last)$", custom_id)
                if catMatch:
                    await interaction.deferUpdate()
                    encodedName, current_pg, action = catMatch.groups()
                    cat_name_decoded = unquote(encodedName)
                    flt = [c for c in commands_list if normalize(categoryOf(c)) == normalize(cat_name_decoded)]
                    tot = pageCount(len(flt), CATEGORY_PAGE_SIZE)
                    next_pg = resolvePage(action, int(current_pg), tot)
                    new_c = categoryPage(cat_name_decoded, next_pg)
                    await interaction.update({"components": [new_c]})
                    collector.view = new_c.view
                    collector._wire_view(new_c.view)
                    return

                # 3. Subcommand pagination
                subMatch = re.match(r"^sub:(\d+):(\d+):(first|prev|next|last)$", custom_id)
                if subMatch:
                    await interaction.deferUpdate()
                    idx_str, current_pg, action = subMatch.groups()
                    idx_val = int(idx_str)
                    if 0 <= idx_val < len(commands_list):
                        sub_cmd = commands_list[idx_val]
                        tot = pageCount(len(getSubs(sub_cmd)), SUBCOMMAND_PAGE_SIZE)
                        next_pg = resolvePage(action, int(current_pg), tot)
                        new_c = details(sub_cmd, next_pg)
                        await interaction.update({"components": [new_c]})
                        collector.view = new_c.view
                        collector._wire_view(new_c.view)
                        return

            except Exception as err:
                pass

        collector.on("collect", on_collect)

    attachCollector(sent_msg)
    return sent_msg

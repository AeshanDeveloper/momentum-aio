const {
    MessageFlags,
    SlashCommandBuilder,
    ButtonStyle,
    PermissionFlagsBits,
    SeparatorBuilder,
    SeparatorSpacingSize,
} = require("discord.js");

const { CommandType, ContainerBuilder } = require("@sdk/discord");

import config from "@config";
import { CommandStatus } from "@shared/types/CommandRecord";

const HOME_PAGE_SIZE = 10;
const CATEGORY_PAGE_SIZE = 8;
const SUBCOMMAND_PAGE_SIZE = 6;
const COLLECTOR_TIMEOUT = 300_000;

export default {
    name: "help",
    aliases: ["h", "commands"],
    description: "Browse commands and view detailed help.",
    category: "Utility",
    usage: "help <command|category>",
    cooldown: 3000,

    builder: new SlashCommandBuilder()
        .setName("help")
        .setDescription("Browse commands and view detailed help.")
        .addStringOption(option =>
            option
                .setName("query")
                .setDescription("Search for a command, subcommand, or category")
                .setRequired(false)
        ),

    execute: async (ctx, commandType, message, args) => {
        const isSlash = commandType === CommandType.SLASH;

        const E = config.Emojis || {};
        const colors = config.Colors || {};

        const bot = config.settings?.bot?.name || "Bot";
        const botPrefix = config.settings?.bot?.prefix || "!";

        const icon = E.help || "📖";
        const info = E.info || "💡";
        const error = E.error || "❌";
        const arrowLeft = E.arrowLeft || "◀";
        const arrowRight = E.arrowRight || "▶";

        const pageEmojis = {
            first: E.firstPage || "⏮️",
            previous: E.previousPage || "◀️",
            next: E.nextPage || "▶️",
            last: E.lastPage || "⏭️",
        };

        const botInvite =
            config.settings?.bot?.invite || config.links?.botInvite;

        const serverInvite =
            config.settings?.bot?.supportInvite ||
            config.links?.supportServer;

        const ownerId = isSlash
            ? message.user.id
            : message.author.id;

        const configuredOwners = config.settings?.bot?.owner_ids;

        const ownerIds = Array.isArray(configuredOwners)
            ? configuredOwners.map(String)
            : configuredOwners
                ? [String(configuredOwners)]
                : [];

        const isBotOwner = ownerIds.includes(String(ownerId));

        const query = isSlash
            ? message.options?.getString("query")?.trim() || ""
            : Array.isArray(args)
                ? args.join(" ").trim()
                : "";

        const normalize = value =>
            String(value ?? "")
                .toLowerCase()
                .trim()
                .replace(/\s+/g, " ");

        const data = command => command?.command || {};

        const categoryOf = command =>
            data(command).category ||
            command.category ||
            "Uncategorized";

        // ---------------------------------------------------------
        // Emoji helpers
        // ---------------------------------------------------------

        const getCategoryEmoji = category => {
            const value = normalize(category);

            if (/econ|money|bank|cash|coin|wallet|finance|reward/.test(value))
                return E.money || E.bank || E.balance || "💰";

            if (/admin|moder|security|staff|ban|kick|warn/.test(value))
                return E.moderation || "🛡️";

            if (/util|tool|helper|general|misc/.test(value))
                return E.tools || "🛠️";

            if (/ticket|support|helpdesk|report/.test(value))
                return E.ticket || "🎫";

            if (/shop|store|inventory|stock|product|market/.test(value))
                return E.inventory || "📦";

            if (/music|audio|song|voice/.test(value))
                return E.music || "🎵";

            if (/level|rank|xp|reputation|leaderboard/.test(value))
                return E.leveling || "🏆";

            if (/giveaway|event|contest|prize/.test(value))
                return E.giveaway || "🎁";

            if (/ai|gpt|assistant|machine learning/.test(value))
                return E.ai || "🤖";

            if (/dev|owner|system|core/.test(value))
                return E.developer || "👑";

            if (/setting|config|setup/.test(value))
                return E.settings || "⚙️";

            if (/channel|server|guild|role/.test(value))
                return E.server || "🗂️";

            if (/log|audit|history/.test(value))
                return E.logs || "📋";

            return E.category || "📌";
        };

        const getTypeBadge = command => {
            const type = command.type;

            if (type === CommandType.HYBRID || type === 2)
                return `${E.hybrid || "🔄"} Hybrid`;

            if (type === CommandType.SLASH || type === 1)
                return `${E.slash || "⚡"} Slash`;

            return `${E.prefix || "⌨️"} Prefix`;
        };

        // Supports Unicode emojis and custom Discord emoji strings.
        // Examples: "⏮️" or "<:first_page:123456789012345678>"

        const toButtonEmoji = (value, fallback) => {
            if (value && typeof value === "object" && value.name) {
                return value;
            }

            const text = String(value || fallback);

            const custom = text.match(
                /^<(a?):([a-zA-Z0-9_]+):(\d+)>$/
            );

            if (custom) {
                return {
                    name: custom[2],
                    id: custom[3],
                    animated: custom[1] === "a",
                };
            }

            return { name: text };
        };

        // ---------------------------------------------------------
        // Separator helper
        // ---------------------------------------------------------

        const addSeparator = container => {
            const separator = new SeparatorBuilder()
                .setDivider(true)
                .setSpacing(SeparatorSpacingSize.Small);

            container.addSeparatorComponents(separator);

            return container;
        };

        const pageIndicator = (page, total) =>
            `-# ${arrowLeft} Page **${page + 1}/${total}** ${arrowRight}`;

        // ---------------------------------------------------------
        // Command visibility and owner-only filtering
        // ---------------------------------------------------------

        const isOwnerOnlyCommand = command => {
            const d = data(command);

            const categories = [
                d.category,
                command.category,
                command.raw?.category,
            ].map(normalize);

            return Boolean(
                d.ownerOnly ||
                d.owner_only ||
                command.ownerOnly ||
                command.owner_only ||
                command.raw?.ownerOnly ||
                command.raw?.owner_only ||
                categories.some(category =>
                    ["dev", "owner"].includes(category)
                )
            );
        };

        const isEnabled = command => {
            if (typeof command.enabled === "boolean") {
                return command.enabled;
            }

            return String(command.enabled).toLowerCase() === "true";
        };

        const isVisibleCommand = command => {
            if (!command) return false;

            const d = data(command);

            if (isOwnerOnlyCommand(command) && !isBotOwner) {
                return false;
            }

            if (command.status !== CommandStatus.ACTIVE) {
                return false;
            }

            if (!isEnabled(command)) {
                return false;
            }

            if (
                d.hidden === true ||
                command.hidden === true ||
                command.raw?.hidden === true
            ) {
                return false;
            }

            return true;
        };

        const commands = [];
        const seenNames = new Set();

        if (global.commands instanceof Map) {
            for (const [, record] of global.commands) {
                if (!record || !isVisibleCommand(record)) continue;

                const d = data(record);
                const name = record.name || d.name;

                if (!name) continue;

                const key = normalize(name);

                if (seenNames.has(key)) continue;

                seenNames.add(key);
                commands.push(record);
            }
        }

        commands.sort((a, b) =>
            String(a.name || data(a).name).localeCompare(
                String(b.name || data(b).name)
            )
        );

        // ---------------------------------------------------------
        // Subcommands and aliases
        // ---------------------------------------------------------

        const getSubs = command => {
            const d = data(command);

            const candidates = [
                d.sub_commands,
                d.subCommands,
                command.raw?.sub_commands,
                command.raw?.subCommands,
                d.raw?.sub_commands,
            ];

            for (const candidate of candidates) {
                if (Array.isArray(candidate) && candidate.length) {
                    return candidate;
                }
            }

            const builder =
                d.data ||
                command.raw?.builder ||
                d.builder;

            if (Array.isArray(builder?.options)) {
                const options = builder.options
                    .map(option =>
                        typeof option?.toJSON === "function"
                            ? option.toJSON()
                            : option
                    )
                    .filter(option => option?.type === 1);

                if (options.length) {
                    return options.map(option => ({
                        name: option.name,
                        description: option.description,
                        usage: `${command.name || d.name} ${option.name}`,
                    }));
                }
            }

            return [];
        };

        const getAliases = command => {
            const aliases = data(command).aliases;

            return Array.isArray(aliases)
                ? aliases.filter(Boolean)
                : [];
        };

        const totalCommandCount = commands.reduce(
            (total, command) => total + 1 + getSubs(command).length,
            0
        );

        const categories = [
            ...new Set(commands.map(categoryOf)),
        ].sort((a, b) => a.localeCompare(b));

        // ---------------------------------------------------------
        // Search helpers
        // ---------------------------------------------------------

        const findCommand = search => {
            const value = normalize(search);

            return commands.find(command => {
                const d = data(command);

                return [
                    command.name,
                    d.name,
                    ...getAliases(command),
                ]
                    .filter(Boolean)
                    .some(name => normalize(name) === value);
            });
        };

        const findParent = search => {
            const value = normalize(search);

            return commands
                .filter(command => {
                    const names = [
                        command.name,
                        data(command).name,
                        ...getAliases(command),
                    ]
                        .filter(Boolean)
                        .map(normalize);

                    return names.some(name =>
                        value === name || value.startsWith(`${name} `)
                    );
                })
                .sort((a, b) =>
                    normalize(b.name || data(b).name).length -
                    normalize(a.name || data(a).name).length
                )[0];
        };

        const findSubcommand = (command, search) => {
            const value = normalize(search);
            const parentName = normalize(command.name || data(command).name);

            return getSubs(command).find(sub => {
                const name = normalize(sub.name);
                const usage = normalize(sub.usage);

                return (
                    name === value ||
                    usage === value ||
                    `${parentName} ${name}` === value
                );
            });
        };

        const findCategory = search => {
            const value = normalize(search);

            return categories.find(
                category => normalize(category) === value
            );
        };

        const suggest = search => {
            const value = normalize(search);

            if (!value) return null;

            const candidates = [];

            for (const command of commands) {
                candidates.push(
                    command.name || data(command).name,
                    ...getAliases(command)
                );

                for (const sub of getSubs(command)) {
                    candidates.push(sub.name);

                    if (sub.usage) {
                        candidates.push(sub.usage);
                    }
                }
            }

            candidates.push(...categories);

            const score = candidate => {
                const text = normalize(candidate);

                if (text === value) return 1;

                if (text.includes(value) || value.includes(text)) {
                    return 0.8;
                }

                let matches = 0;

                for (
                    let i = 0;
                    i < Math.min(value.length, text.length);
                    i++
                ) {
                    if (value[i] === text[i]) matches++;
                }

                return matches / Math.max(value.length, text.length, 1);
            };

            return [...new Set(candidates)]
                .filter(Boolean)
                .map(candidate => ({
                    candidate,
                    score: score(candidate),
                }))
                .filter(item => item.score >= 0.4)
                .sort((a, b) => b.score - a.score)[0]?.candidate || null;
        };

        // ---------------------------------------------------------
        // Permission formatting
        // ---------------------------------------------------------

        const permissionNames = Object.entries(PermissionFlagsBits)
            .filter(([, value]) => typeof value === "bigint");

        const readablePermission = permission => {
            if (typeof permission === "string") {
                return permission
                    .replace(/([a-z])([A-Z])/g, "$1 $2")
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, character => character.toUpperCase());
            }

            const found = permissionNames.find(([, value]) => {
                if (typeof permission === "bigint") {
                    return value === permission;
                }

                if (typeof permission === "number") {
                    return Number(value) === permission;
                }

                return false;
            });

            return found
                ? found[0]
                    .replace(/([a-z])([A-Z])/g, "$1 $2")
                    .replace(/_/g, " ")
                : String(permission);
        };

        const formatPermissions = value =>
            Array.isArray(value) && value.length
                ? value.map(permission =>
                    `\`${readablePermission(permission)}\``
                ).join(", ")
                : "`None`";

        // ---------------------------------------------------------
        // Pagination helpers
        // ---------------------------------------------------------

        const pageCount = (length, size) =>
            Math.max(1, Math.ceil(length / size));

        const clamp = (page, total) =>
            Math.max(0, Math.min(Number(page) || 0, total - 1));

        const resolvePage = (action, current, total) => {
            switch (action) {
                case "first":
                    return 0;

                case "prev":
                    return Math.max(0, current - 1);

                case "next":
                    return Math.min(total - 1, current + 1);

                case "last":
                    return total - 1;

                default:
                    return current;
            }
        };

        const makeContainer = (
            color = colors.cmd_help || colors.default
        ) => new ContainerBuilder().setAccentColor(color);

        const addLinks = container => {
            if (!botInvite && !serverInvite) return false;

            container.addActionRow(row => {
                if (botInvite) {
                    row.addButton({
                        style: ButtonStyle.Link,
                        label: "Add Bot",
                        url: botInvite,
                    });
                }

                if (serverInvite) {
                    row.addButton({
                        style: ButtonStyle.Link,
                        label: "Support Server",
                        url: serverInvite,
                    });
                }
            });

            return true;
        };

        // Four icon-only buttons: first, previous, next, last.
        const pagination = (container, pageId, page, total) => {
            if (total <= 1) return false;

            const makeId = action => `${pageId}:${page}:${action}`;

            container.addActionRow(row => {
                row.addButton({
                    custom_id: makeId("first"),
                    emoji: toButtonEmoji(pageEmojis.first, "⏮️"),
                    style: ButtonStyle.Secondary,
                    disabled: page <= 0,
                });

                row.addButton({
                    custom_id: makeId("prev"),
                    emoji: toButtonEmoji(pageEmojis.previous, "◀️"),
                    style: ButtonStyle.Secondary,
                    disabled: page <= 0,
                });

                row.addButton({
                    custom_id: makeId("next"),
                    emoji: toButtonEmoji(pageEmojis.next, "▶️"),
                    style: ButtonStyle.Secondary,
                    disabled: page >= total - 1,
                });

                row.addButton({
                    custom_id: makeId("last"),
                    emoji: toButtonEmoji(pageEmojis.last, "⏭️"),
                    style: ButtonStyle.Secondary,
                    disabled: page >= total - 1,
                });

                return row;
            });

            return true;
        };

        // ---------------------------------------------------------
        // Home page
        // ---------------------------------------------------------

        const home = (page = 0) => {
            const total = pageCount(commands.length, HOME_PAGE_SIZE);

            page = clamp(page, total);

            const visible = commands.slice(
                page * HOME_PAGE_SIZE,
                (page + 1) * HOME_PAGE_SIZE
            );

            const lines = visible.map(command => {
                const d = data(command);
                const name = command.name || d.name;

                return (
                    `${E.command || "▫️"} **${botPrefix}${name}** — ` +
                    `${d.description || "No description available."}`
                );
            });

            const c = makeContainer();

            c.addTextDisplay(
                `### ${icon} ${bot} Commands\n` +
                `${info} Browse available commands using the navigation buttons.\n` +
                `Use \`${botPrefix}help <command>\` for detailed help.`
            ).addSeparator({divider: true});

            c.addTextDisplay(
                `${lines.join("\n\n") || "No commands are available."}`
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `${pageIndicator(page, total)}\n` +
                `-# ${E.prefix || "⌨️"} Prefix: \`${botPrefix}\` · ` +
                `${E.stats || "📊"} ${totalCommandCount} total commands`
            );

            pagination(c, "home", page, total);

            addLinks(c);

            return c.build();
        };

        // ---------------------------------------------------------
        // Category page
        // ---------------------------------------------------------

        const categoryPage = (name, page = 0) => {
            const list = commands
                .filter(command =>
                    normalize(categoryOf(command)) === normalize(name)
                )
                .sort((a, b) =>
                    String(a.name || data(a).name).localeCompare(
                        String(b.name || data(b).name)
                    )
                );

            const total = pageCount(list.length, CATEGORY_PAGE_SIZE);

            page = clamp(page, total);

            const visible = list.slice(
                page * CATEGORY_PAGE_SIZE,
                (page + 1) * CATEGORY_PAGE_SIZE
            );

            const lines = visible.map(command => {
                const d = data(command);
                const subs = getSubs(command);
                const commandName = command.name || d.name;

                return (
                    `${E.command || "▫️"} **\`${botPrefix}${d.usage || commandName}\`**\n` +
                    `${getTypeBadge(command)} · ` +
                    `${d.description || "No description available."}` +
                    (subs.length ? ` · ${subs.length} subcommands` : "")
                );
            });

            const c = makeContainer();

            c.addTextDisplay(
                `### ${getCategoryEmoji(name)} ${name}\n` +
                `${info} ${list.length} command${list.length === 1 ? "" : "s"} in this category`
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(
                lines.join("\n\n") || "No commands in this category."
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(pageIndicator(page, total));

            pagination(
                c,
                `category:${encodeURIComponent(name)}`,
                page,
                total
            );

            addLinks(c);

            return c.build();
        };

        // ---------------------------------------------------------
        // Command details
        // ---------------------------------------------------------

        const details = (command, page = 0) => {
            const d = data(command);
            const name = command.name || d.name;
            const subs = getSubs(command);
            const aliases = getAliases(command);

            const aliasText = aliases.length
                ? aliases.map(alias => `\`${botPrefix}${alias}\``).join(", ")
                : "`None`";

            const users =
                command.userPermissions ?? d.userPermissions ?? [];

            const bots =
                command.botPermissions ?? d.botPermissions ?? [];

            const total = pageCount(subs.length, SUBCOMMAND_PAGE_SIZE);

            page = clamp(page, total);

            const visible = subs.slice(
                page * SUBCOMMAND_PAGE_SIZE,
                (page + 1) * SUBCOMMAND_PAGE_SIZE
            );

            const isHybrid =
                command.type === CommandType.HYBRID || command.type === 2;

            const isSlashOnly =
                command.type === CommandType.SLASH || command.type === 1;

            const invocation = isHybrid
                ? `**${E.prefix || "⌨️"} Prefix:** \`${botPrefix}${d.usage || name}\`\n` +
                  `**${E.slash || "⚡"} Slash:** \`/${name}\``
                : isSlashOnly
                    ? `**${E.slash || "⚡"} Slash:** \`/${name}\``
                    : `**${E.prefix || "⌨️"} Prefix:** \`${botPrefix}${d.usage || name}\``;

            const cooldown = Number(d.cooldown ?? command.cooldown ?? 0);

            const cooldownText = cooldown >= 1000
                ? `${cooldown / 1000}s`
                : `${cooldown}ms`;

            const c = makeContainer();

            c.addTextDisplay(
                `### ${icon} ${name}\n` +
                `${d.description || "No description available."}`
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `**${E.info || "ℹ️"} Command information**\n` +
                `**Type:** ${getTypeBadge(command)}\n` +
                `**Category:** ${getCategoryEmoji(categoryOf(command))} ${categoryOf(command)}\n` +
                `**Cooldown:** ${cooldownText}\n` +
                `**Aliases:** ${aliasText}`
            );

            if (subs.length) {
                c.addSeparator({divider: true})

                c.addTextDisplay(
                    `**${E.subcommand || E.command || E.commands} Subcommands · ${subs.length}**\n\n` +
                    visible.map(sub => {
                        const subName = sub.name || "subcommand";
                        const usage = sub.usage || `${name} ${subName}`;

                        return (
                            `**\`${botPrefix}${usage}\`**\n` +
                            `${sub.description || "No description available."}`
                        );
                    }).join("\n\n")
                );

                if (total > 1) {
                    c.addTextDisplay(pageIndicator(page, total));
                }
            }

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `**${E.usage || E.info || "📝"} Usage**\n${invocation}\n\n` +
                `**${E.permissions || "🔐"} Permissions**\n` +
                `**User:** ${formatPermissions(users)}\n` +
                `**Bot:** ${formatPermissions(bots)}`
            );

            if (subs.length) {
                pagination(
                    c,
                    `sub:${commands.indexOf(command)}`,
                    page,
                    total
                );
            }

            addLinks(c);

            return c.build();
        };

        // ---------------------------------------------------------
        // Subcommand details
        // ---------------------------------------------------------

        const subcommandDetails = (command, sub) => {
            const d = data(command);
            const name = command.name || d.name;
            const subName = sub.name || "subcommand";

            const users =
                sub.userPermissions ??
                command.userPermissions ??
                d.userPermissions ??
                [];

            const bots =
                sub.botPermissions ??
                command.botPermissions ??
                d.botPermissions ??
                [];

            const usage = sub.usage || `${name} ${subName}`;

            const cooldown =
                sub.cooldown ??
                d.cooldown ??
                command.cooldown ??
                0;

            const cooldownText = Number(cooldown) >= 1000
                ? `${Number(cooldown) / 1000}s`
                : `${cooldown}ms`;

            const aliases =
                Array.isArray(sub.aliases) && sub.aliases.length
                    ? sub.aliases
                        .map(alias => `\`${botPrefix}${alias}\``)
                        .join(", ")
                    : "`None`";

            const c = makeContainer();

            c.addTextDisplay(
                `### ${icon} ${name} ${subName}\n` +
                `${sub.description || "No description available."}`
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `**${E.info || "ℹ️"} Subcommand information**\n` +
                `**Parent:** \`${name}\`\n` +
                `**Category:** ${getCategoryEmoji(categoryOf(command))} ${categoryOf(command)}\n` +
                `**Usage:** \`${botPrefix}${usage}\`\n` +
                `**Cooldown:** ${cooldownText}\n` +
                `**Aliases:** ${aliases}`
            );

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `**${E.permissions || "🔐"} Permissions**\n` +
                `**User:** ${formatPermissions(users)}\n` +
                `**Bot:** ${formatPermissions(bots)}\n\n` +
                `-# ${info} Use \`${botPrefix}help ${name}\` for parent help.`
            );

            addLinks(c);

            return c.build();
        };

        // ---------------------------------------------------------
        // Not found
        // ---------------------------------------------------------

        const notFound = search => {
            const suggestion = suggest(search);

            const c = makeContainer(
                colors.cmd_help_error || colors.error || colors.default
            );

            c.addTextDisplay(`### ${error} Nothing Found`);

            c.addSeparator({divider: true})

            c.addTextDisplay(
                `No command or category matches \`${search}\`.\n\n` +
                (suggestion
                    ? `${info} Did you mean \`${suggestion}\`?\n\n`
                    : "") +
                `Use \`${botPrefix}help\` to browse commands.`
            );

            addLinks(c);

            return c.build();
        };

        // ---------------------------------------------------------
        // Resolve query
        // ---------------------------------------------------------

        const resolve = search => {
            if (!search) return home(0);

            const value = normalize(search);

            const exactCommand = findCommand(value);

            if (exactCommand) {
                return details(exactCommand, 0);
            }

            const parent = findParent(value);

            if (parent) {
                const parentNames = [
                    parent.name,
                    data(parent).name,
                    ...getAliases(parent),
                ]
                    .filter(Boolean)
                    .map(normalize);

                const aliasMatch = parentNames.find(
                    name => value.startsWith(`${name} `)
                );

                const subQuery = aliasMatch
                    ? value.slice(aliasMatch.length).trim()
                    : "";

                if (subQuery) {
                    const sub = findSubcommand(parent, subQuery);

                    if (sub) {
                        return subcommandDetails(parent, sub);
                    }
                }

                return details(parent, 0);
            }

            const subMatches = [];

            for (const command of commands) {
                const sub = findSubcommand(command, value);

                if (sub) {
                    subMatches.push({ command, sub });
                }
            }

            if (subMatches.length === 1) {
                return subcommandDetails(
                    subMatches[0].command,
                    subMatches[0].sub
                );
            }

            const category = findCategory(value);

            if (category) {
                return categoryPage(category, 0);
            }

            return notFound(search);
        };

        // ---------------------------------------------------------
        // Send response
        // ---------------------------------------------------------

        const send = container => {
            const payload = {
                components: [container],
                flags: MessageFlags.IsComponentsV2,
            };

            return isSlash
                ? message.editReply(payload)
                : message.reply(payload);
        };

        // ---------------------------------------------------------
        // Component collector
        // ---------------------------------------------------------

        const attachCollector = sent => {
            if (!sent?.createMessageComponentCollector) {
                console.error("[HELP] Unable to create component collector.");
                return;
            }

            const collector = sent.createMessageComponentCollector({
                time: COLLECTOR_TIMEOUT,
                filter: interaction =>
                    interaction.user.id === ownerId,
            });

            collector.on("collect", async interaction => {
                try {
                    if (!interaction.isButton()) return;

                    const id = interaction.customId;

                    // Home pagination
                    const homeMatch = id.match(
                        /^home:(\d+):(first|prev|next|last)$/
                    );

                    if (homeMatch) {
                        await interaction.deferUpdate();

                        const [, current, action] = homeMatch;

                        const total = pageCount(
                            commands.length,
                            HOME_PAGE_SIZE
                        );

                        const page = resolvePage(
                            action,
                            Number(current),
                            total
                        );

                        await interaction.message.edit({
                            components: [home(page)],
                        });

                        return;
                    }

                    // Category pagination
                    const categoryMatch = id.match(
                        /^category:(.+):(\d+):(first|prev|next|last)$/
                    );

                    if (categoryMatch) {
                        await interaction.deferUpdate();

                        const [, encodedName, current, action] =
                            categoryMatch;

                        const name = decodeURIComponent(encodedName);

                        const list = commands.filter(
                            command =>
                                normalize(categoryOf(command)) ===
                                normalize(name)
                        );

                        const total = pageCount(
                            list.length,
                            CATEGORY_PAGE_SIZE
                        );

                        const page = resolvePage(
                            action,
                            Number(current),
                            total
                        );

                        await interaction.message.edit({
                            components: [categoryPage(name, page)],
                        });

                        return;
                    }

                    // Subcommand pagination
                    const subMatch = id.match(
                        /^sub:(\d+):(\d+):(first|prev|next|last)$/
                    );

                    if (subMatch) {
                        await interaction.deferUpdate();

                        const [, index, current, action] = subMatch;

                        const command = commands[Number(index)];

                        if (!command) return;

                        const total = pageCount(
                            getSubs(command).length,
                            SUBCOMMAND_PAGE_SIZE
                        );

                        const page = resolvePage(
                            action,
                            Number(current),
                            total
                        );

                        await interaction.message.edit({
                            components: [details(command, page)],
                        });
                    }
                } catch (err) {
                    console.error(
                        "[HELP] Component interaction failed:",
                        err
                    );
                }
            });

            collector.on("end", () => {
                console.log("[HELP] Help collector ended.");
            });
        };

        // ---------------------------------------------------------
        // Execute
        // ---------------------------------------------------------

        const sent = await send(resolve(query));

        attachCollector(sent);

        return sent;
    },
};
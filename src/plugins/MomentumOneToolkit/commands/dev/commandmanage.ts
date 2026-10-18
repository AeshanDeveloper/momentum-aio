const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
	ModalBuilder,
	TextInputBuilder,
	TextInputStyle,
	ActionRowBuilder: DiscordActionRowBuilder,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
	SelectMenuTypes,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import DatabaseManager from "@database/Database";
import { isBotOwner } from "@core/security/SecurityHelpers";

const PAGE_SIZE = 15;
const PROTECTED_COMMANDS = new Set([
	"commandmanage",
	"cmdmanage",
	"managecommands",
	"eval",
	"evaluate",
	"reload",
	"reboot",
	"status",
	"help",
]);

interface CommandEntry {
	commandId: string;
	name: string;
	type: string;
	enabled: boolean;
	aliases?: string[];
	category?: string;
	description?: string;
	cooldown?: number;
	ownerOnly?: boolean;
}

function getAllCommandsList(): CommandEntry[] {
	const map = new Map<string, CommandEntry>();

	if (global.commands) {
		for (const [, cmd] of global.commands) {
			const name = String(cmd.name || cmd.command?.name || "").toLowerCase();
			if (!name) continue;

			const isEnabled =
				typeof cmd.enabled === "boolean"
					? cmd.enabled
					: String(cmd.enabled).toLowerCase() === "true";

			map.set(name, {
				commandId: cmd.commandId || name,
				name: cmd.name,
				type: String(cmd.type || "HYBRID"),
				enabled: isEnabled,
				aliases: cmd.command?.aliases || cmd.aliases || [],
				category: cmd.command?.category || cmd.category || "General",
				description: cmd.command?.description || cmd.description || "No description",
				cooldown: cmd.command?.cooldown || 0,
				ownerOnly: Boolean(cmd.command?.ownerOnly || cmd.ownerOnly),
			});
		}
	}

	return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
}

async function setCommandState(
	cmdName: string,
	enable: boolean
): Promise<{ success: boolean; error?: string; command?: CommandEntry }> {
	const targetName = cmdName.trim().toLowerCase();

	if (!enable && PROTECTED_COMMANDS.has(targetName)) {
		return {
			success: false,
			error: `Command \`${targetName}\` is a critical system management command and cannot be disabled.`,
		};
	}

	const commandsList = getAllCommandsList();
	const target = commandsList.find(
		(c) => c.name.toLowerCase() === targetName || (c.aliases || []).some((a) => a.toLowerCase() === targetName)
	);

	if (!target) {
		return {
			success: false,
			error: `Command \`${cmdName}\` was not found in the registered commands list.`,
		};
	}

	// 1. Update Database
	try {
		const col = await DatabaseManager.collection("shop_commands");
		await col.updateMany(
			{
				$or: [
					{ name: target.name },
					{ command_id: target.commandId },
					{ _id: target.commandId },
				],
			},
			{ $set: { enabled: enable } }
		);
	} catch (dbErr) {
		logger.warn(`[CommandManager] Database update warning for ${target.name}:`, dbErr);
	}

	// 2. Synchronize in-memory global.commands
	if (global.commands) {
		for (const [, cmd] of global.commands) {
			if (
				cmd.name?.toLowerCase() === target.name.toLowerCase() ||
				cmd.commandId === target.commandId
			) {
				cmd.enabled = enable;
			}
		}
	}

	target.enabled = enable;
	logger.info(`[CommandManager] Command '${target.name}' was ${enable ? "enabled" : "disabled"}`);
	return { success: true, command: target };
}

function buildPanel(options: {
	page: number;
	searchQuery?: string;
	selectedCommandName?: string;
	feedback?: { text: string; error?: boolean };
}) {
	const { page, searchQuery, selectedCommandName, feedback } = options;
	const E = config.Emojis || config.emojis || {};
	const C = config.Colors || config.colors || {};

	const emojis = {
		enabled: E.enabled || E.success || "🟢",
		disabled: E.disabled || E.error || "🔴",
		cmd: E.cmd || "⚡",
		search: E.search || "🔍",
		refresh: E.reload || "🔄",
		settings: E.settings || "🛠️",
		info: E.info || "ℹ️",
	};

	let allCmds = getAllCommandsList();

	if (searchQuery && searchQuery.trim().length > 0) {
		const q = searchQuery.trim().toLowerCase();
		allCmds = allCmds.filter(
			(c) =>
				c.name.toLowerCase().includes(q) ||
				(c.aliases || []).some((a) => a.toLowerCase().includes(q)) ||
				(c.category || "").toLowerCase().includes(q)
		);
	}

	const total = allCmds.length;
	const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
	const safePage = Math.max(0, Math.min(page, totalPages - 1));
	const pageCmds = allCmds.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

	const enabledCount = allCmds.filter((c) => c.enabled).length;
	const disabledCount = allCmds.filter((c) => !c.enabled).length;

	const container = new ContainerBuilder()
		.setAccentColor(feedback?.error ? C.error || "#EF4444" : C.default || "#3B82F6")
		.addTextDisplay(`### ${emojis.settings} MomentumOne Command Manager`)
		.addTextDisplay(
			`**Total Commands:** \`${total}\` (Active: ${emojis.enabled} \`${enabledCount}\` • Disabled: ${emojis.disabled} \`${disabledCount}\`)\n` +
			`**Page:** \`${safePage + 1}/${totalPages}\`` +
			(searchQuery ? ` • **Search Filter:** \`${searchQuery}\`` : "")
		);

	if (feedback) {
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
		container.addTextDisplay(feedback.error ? `⚠️ **Notice:** ${feedback.text}` : `✅ **Success:** ${feedback.text}`);
	}

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// If a command is selected, show full details and enable/disable controls
	const selectedCmd = selectedCommandName
		? allCmds.find((c) => c.name.toLowerCase() === selectedCommandName.toLowerCase())
		: null;

	if (selectedCmd) {
		const stateText = selectedCmd.enabled
			? `${emojis.enabled} **ENABLED (Active)**`
			: `${emojis.disabled} **DISABLED (Inactive)**`;

		const aliasText = selectedCmd.aliases?.length
			? selectedCmd.aliases.map((a) => `\`${a}\``).join(", ")
			: "*None*";

		container.addTextDisplay(
			`#### ${emojis.cmd} Command: \`${selectedCmd.name}\`\n` +
			`• **Status:** ${stateText}\n` +
			`• **Type:** \`${selectedCmd.type}\`\n` +
			`• **Category:** \`${selectedCmd.category}\`\n` +
			`• **Aliases:** ${aliasText}\n` +
			`• **Cooldown:** \`${selectedCmd.cooldown || 0}ms\`\n` +
			`• **Owner Only:** \`${selectedCmd.ownerOnly ? "Yes" : "No"}\`\n` +
			`• **Description:** ${selectedCmd.description}`
		);

		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

		container.addActionRow((row: any) => {
			if (selectedCmd.enabled) {
				row.addButton({
					custom_id: `cmdmanage:disable:${selectedCmd.name}:${safePage}`,
					label: "Disable Command",
					emoji: emojis.disabled,
					style: ButtonStyle.Danger,
				});
			} else {
				row.addButton({
					custom_id: `cmdmanage:enable:${selectedCmd.name}:${safePage}`,
					label: "Enable Command",
					emoji: emojis.enabled,
					style: ButtonStyle.Success,
				});
			}

			row.addButton({
				custom_id: `cmdmanage:back:${safePage}${searchQuery ? `:${searchQuery}` : ""}`,
				label: "Back to List",
				style: ButtonStyle.Secondary,
			});

			return row;
		});

		return container;
	}

	// Overview list mode
	if (pageCmds.length === 0) {
		container.addTextDisplay("*(No commands match the current filter).*");
	} else {
		// Add String Select Menu
		const selectOptions = pageCmds.map((cmd) => ({
			label: `${cmd.name} (${cmd.enabled ? "Active" : "Disabled"})`,
			value: cmd.name,
			description: `Type: ${cmd.type} | Cat: ${cmd.category}`.slice(0, 50),
			emoji: cmd.enabled ? emojis.enabled : emojis.disabled,
		}));

		container.addActionRow((row: any) => {
			row.addSelectMenu({
				custom_id: `cmdmanage:select:${safePage}${searchQuery ? `:${searchQuery}` : ""}`,
				type: SelectMenuTypes.CUSTOM,
				placeholder: "Select a command to inspect and manage...",
				options: selectOptions,
			});
			return row;
		});
	}

	// Navigation & Action Controls
	container.addActionRow((row: any) => {
		row.addButton({
			custom_id: `cmdmanage:prev:${safePage}${searchQuery ? `:${searchQuery}` : ""}`,
			label: "Previous",
			disabled: safePage <= 0,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: `cmdmanage:next:${safePage}${searchQuery ? `:${searchQuery}` : ""}`,
			label: "Next",
			disabled: safePage >= totalPages - 1,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: `cmdmanage:search_btn:${safePage}`,
			label: searchQuery ? "Clear Filter" : "Search",
			emoji: emojis.search,
			style: searchQuery ? ButtonStyle.Primary : ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: `cmdmanage:refresh:${safePage}${searchQuery ? `:${searchQuery}` : ""}`,
			label: "Refresh",
			emoji: emojis.refresh,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: "cmdmanage:close",
			label: "Close",
			style: ButtonStyle.Danger,
		});

		return row;
	});

	return container;
}

const commandmanage = {
	name: "commandmanage",
	aliases: ["cmdmanage", "managecommands", "cmdm", "command"],
	description: "Interactive bot-owner command manager to search, inspect, enable, and disable commands.",
	category: "Owner",
	usage: "commandmanage [list|enable <cmd>|disable <cmd>|search <query>]",
	ownerOnly: true,

	sub_commands: [
		{ name: "panel", description: "Open the interactive command management panel." },
		{ name: "list [page]", description: "List all commands and their current enabled/disabled state." },
		{ name: "enable <command>", description: "Enable a specific registered command." },
		{ name: "disable <command>", description: "Disable a specific registered command." },
		{ name: "search <query>", description: "Search commands by name or alias." },
	],

	builder: new SlashCommandBuilder()
		.setName("commandmanage")
		.setDescription("Bot-owner command manager to search, inspect, enable, and disable commands.")
		.addSubcommand((sub: any) =>
			sub.setName("panel").setDescription("Open the interactive command manager panel.")
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("list")
				.setDescription("List registered commands with their enabled status.")
				.addIntegerOption((opt: any) => opt.setName("page").setDescription("Page number").setRequired(false))
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("enable")
				.setDescription("Enable a specific command.")
				.addStringOption((opt: any) => opt.setName("name").setDescription("Command name to enable").setRequired(true))
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("disable")
				.setDescription("Disable a specific command.")
				.addStringOption((opt: any) => opt.setName("name").setDescription("Command name to disable").setRequired(true))
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("search")
				.setDescription("Search registered commands by query.")
				.addStringOption((opt: any) => opt.setName("query").setDescription("Search term").setRequired(true))
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;

		// Authorization
		if (!isBotOwner(user?.id)) {
			const errText = "❌ **Access Denied**: This command is strictly restricted to authorized bot owners.";
			return isSlash
				? messageOrInteraction.editReply({ content: errText })
				: messageOrInteraction.reply({ content: errText });
		}

		let subcommand = "panel";
		let targetArg = "";

		if (isSlash) {
			subcommand = messageOrInteraction.options.getSubcommand(false) || "panel";
			if (subcommand === "enable" || subcommand === "disable") {
				targetArg = messageOrInteraction.options.getString("name") || "";
			} else if (subcommand === "search") {
				targetArg = messageOrInteraction.options.getString("query") || "";
			} else if (subcommand === "list") {
				const p = messageOrInteraction.options.getInteger("page");
				targetArg = p ? String(p) : "";
			}
		} else {
			const first = (args[0] || "").toLowerCase();
			if (["enable", "disable", "list", "search"].includes(first)) {
				subcommand = first;
				targetArg = args.slice(1).join(" ").trim();
			} else if (first) {
				// e.g. commandmanage <cmdName>
				targetArg = first;
			}
		}

		// Direct Subcommand: Enable
		if (subcommand === "enable" && targetArg) {
			const res = await setCommandState(targetArg, true);
			const panel = buildPanel({
				page: 0,
				selectedCommandName: res.command?.name || targetArg,
				feedback: res.success
					? { text: `Command \`${res.command?.name}\` has been successfully **enabled** and is now active.` }
					: { text: res.error || "Failed to enable command.", error: true },
			});
			const payload = { components: [panel.build()], flags: MessageFlags.IsComponentsV2 };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		}

		// Direct Subcommand: Disable
		if (subcommand === "disable" && targetArg) {
			const res = await setCommandState(targetArg, false);
			const panel = buildPanel({
				page: 0,
				selectedCommandName: res.command?.name || targetArg,
				feedback: res.success
					? { text: `Command \`${res.command?.name}\` has been successfully **disabled** and is now blocked from dispatch.` }
					: { text: res.error || "Failed to disable command.", error: true },
			});
			const payload = { components: [panel.build()], flags: MessageFlags.IsComponentsV2 };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		}

		// Direct Subcommand: Search
		if (subcommand === "search" && targetArg) {
			const panel = buildPanel({ page: 0, searchQuery: targetArg });
			const payload = { components: [panel.build()], flags: MessageFlags.IsComponentsV2 };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		}

		// Direct Subcommand: List
		if (subcommand === "list") {
			const pageNum = parseInt(targetArg, 10);
			const page = !isNaN(pageNum) && pageNum > 0 ? pageNum - 1 : 0;
			const panel = buildPanel({ page });
			const payload = { components: [panel.build()], flags: MessageFlags.IsComponentsV2 };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		}

		// Default: Open Interactive Panel
		const panel = buildPanel({ page: 0 });
		const payload = { components: [panel.build()], flags: MessageFlags.IsComponentsV2 };
		const sentMsg = isSlash
			? await messageOrInteraction.editReply(payload)
			: await messageOrInteraction.reply(payload);

		// Active channel component collector
		if (sentMsg?.createMessageComponentCollector) {
			const collector = sentMsg.createMessageComponentCollector({
				filter: (i: any) => i.customId?.startsWith("cmdmanage:"),
				time: 300_000,
			});

			collector.on("collect", async (interaction: any) => {
				await commandmanage.handleInteraction(interaction);
			});
		}

		return sentMsg;
	},

	/**
	 * Central interaction router for buttons, select menus, and modals
	 */
	handleInteraction: async (interaction: any): Promise<void> => {
		const customId = interaction.customId || "";
		if (!customId.startsWith("cmdmanage:")) return;

		// Recheck Owner Authorization
		if (!isBotOwner(interaction.user?.id)) {
			if (!interaction.replied && !interaction.deferred) {
				await interaction.reply({
					content: "❌ **Access Denied**: Only authorized bot owners can use this command manager panel.",
					flags: MessageFlags.Ephemeral,
				}).catch(() => null);
			}
			return;
		}

		const parts = customId.split(":");
		const action = parts[1];

		// Handle Modal Submit
		if (interaction.isModalSubmit?.()) {
			if (action === "modal_search") {
				const query = interaction.fields?.getTextInputValue?.("query") || "";
				const panel = buildPanel({ page: 0, searchQuery: query.trim() });
				await interaction.update({
					components: [panel.build()],
					flags: MessageFlags.IsComponentsV2,
				}).catch(() => null);
				return;
			}
		}

		// Handle Close
		if (action === "close") {
			await interaction.update({
				content: "🔒 **Command Management Panel Closed**.",
				components: [],
			}).catch(() => null);
			return;
		}

		// Handle Search Button Click -> Show Modal
		if (action === "search_btn") {
			const currentPage = parseInt(parts[2] || "0", 10);
			// If already filtered, clicking clears filter
			if (parts.length > 3 && parts[3]) {
				const panel = buildPanel({ page: currentPage, searchQuery: undefined });
				await interaction.update({
					components: [panel.build()],
					flags: MessageFlags.IsComponentsV2,
				}).catch(() => null);
				return;
			}

			if (interaction.showModal) {
				const modal = new ModalBuilder()
					.setCustomId(`cmdmanage:modal_search:${currentPage}`)
					.setTitle("Search Commands");

				const input = new TextInputBuilder()
					.setCustomId("query")
					.setLabel("Command Name or Alias")
					.setStyle(TextInputStyle.Short)
					.setPlaceholder("e.g. withdraw, deposit, help...")
					.setRequired(true);

				const row = new DiscordActionRowBuilder().addComponents(input);
				modal.addComponents(row);

				await interaction.showModal(modal).catch(() => null);
				return;
			}
		}

		// Handle Select Menu Choice
		if (interaction.isStringSelectMenu?.() && action === "select") {
			const page = parseInt(parts[2] || "0", 10);
			const searchQuery = parts[3] || undefined;
			const selectedCmdName = interaction.values?.[0];

			const panel = buildPanel({
				page,
				searchQuery,
				selectedCommandName: selectedCmdName,
			});

			await interaction.update({
				components: [panel.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
			return;
		}

		// Handle Enable
		if (action === "enable") {
			const cmdName = parts[2];
			const page = parseInt(parts[3] || "0", 10);
			const res = await setCommandState(cmdName, true);

			const panel = buildPanel({
				page,
				selectedCommandName: cmdName,
				feedback: res.success
					? { text: `Command \`${res.command?.name}\` enabled successfully.` }
					: { text: res.error || "Failed to enable command.", error: true },
			});

			await interaction.update({
				components: [panel.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
			return;
		}

		// Handle Disable
		if (action === "disable") {
			const cmdName = parts[2];
			const page = parseInt(parts[3] || "0", 10);
			const res = await setCommandState(cmdName, false);

			const panel = buildPanel({
				page,
				selectedCommandName: cmdName,
				feedback: res.success
					? { text: `Command \`${res.command?.name}\` disabled successfully.` }
					: { text: res.error || "Failed to disable command.", error: true },
			});

			await interaction.update({
				components: [panel.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
			return;
		}

		// Handle Back to List
		if (action === "back") {
			const page = parseInt(parts[2] || "0", 10);
			const searchQuery = parts[3] || undefined;
			const panel = buildPanel({ page, searchQuery });

			await interaction.update({
				components: [panel.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
			return;
		}

		// Handle Navigation (Prev, Next, Refresh)
		if (action === "prev" || action === "next" || action === "refresh") {
			let page = parseInt(parts[2] || "0", 10);
			const searchQuery = parts[3] || undefined;

			if (action === "prev") page = Math.max(0, page - 1);
			if (action === "next") page = page + 1;

			const panel = buildPanel({ page, searchQuery });
			await interaction.update({
				components: [panel.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
			return;
		}
	},
};

export default commandmanage;

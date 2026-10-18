const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	PermissionFlagsBits,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	SelectMenuTypes,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { ServerCommandManager } from "@core/security/ServerCommandManager";

const PAGE_SIZE = 8;

export default {
	name: "command-manage",
	aliases: ["command", "cmdmanage", "cmds"],
	description: "Configure which bot commands are enabled or disabled in this server.",
	category: "Moderation",
	usage: "command-manage [list [page] | disable <cmd> | enable <cmd>]",
	userPermissions: [PermissionFlagsBits.ManageGuild],
	botPermissions: [PermissionFlagsBits.SendMessages],
	cooldown: 3000,

	sub_commands: [
		{ name: "list [page]", description: "List all commands and their per-server enabled/disabled status." },
		{ name: "disable <command>", description: "Disable a command for regular members in this server." },
		{ name: "enable <command>", description: "Re-enable a previously disabled command in this server." },
	],

	builder: new SlashCommandBuilder()
		.setName("command-manage")
		.setDescription("Enable or disable bot commands specifically in this server.")
		.setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
		.setDMPermission(false)
		.addSubcommand((sub: any) =>
			sub
				.setName("list")
				.setDescription("List all commands with their current server status")
				.addIntegerOption((opt: any) =>
					opt.setName("page").setDescription("Page number").setRequired(false).setMinValue(1)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("disable")
				.setDescription("Disable a command in this server")
				.addStringOption((opt: any) =>
					opt.setName("command").setDescription("Name of the command to disable").setRequired(true)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("enable")
				.setDescription("Re-enable a command in this server")
				.addStringOption((opt: any) =>
					opt.setName("command").setDescription("Name of the command to enable").setRequired(true)
				)
		),

	execute: async (ctx: any, type: any, message: any, args: string[] = []) => {
		const isSlash = type === CommandType.SLASH;
		const guild = message.guild;
		if (!guild) {
			const text = "❌ This command can only be used inside a Discord server.";
			return isSlash ? message.reply({ content: text, ephemeral: true }) : message.reply(text);
		}

		const user = isSlash ? message.user : message.author;
		const member = message.member;

		const hasAdmin =
			member?.permissions?.has(PermissionFlagsBits.Administrator) ||
			member?.permissions?.has(PermissionFlagsBits.ManageGuild);

		if (!hasAdmin) {
			const denyBox = new ContainerBuilder()
				.setAccentColor(config.Colors?.error || "#EF4444")
				.addTextDisplay("### 🚫 Permission Denied")
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay("You need **Manage Server** or **Administrator** permissions to manage server commands.")
				.build();
			return isSlash
				? message.reply({ components: [denyBox], flags: MessageFlags.IsComponentsV2, ephemeral: true })
				: message.reply({ components: [denyBox], flags: MessageFlags.IsComponentsV2 });
		}

		// Handle direct subcommands
		let subcommand = isSlash ? message.options.getSubcommand(false) : args[0]?.toLowerCase();
		let targetCmd = isSlash ? message.options.getString("command") : args[1]?.toLowerCase();

		if (subcommand === "disable" && targetCmd) {
			const result = await ServerCommandManager.disableCommand(guild.id, targetCmd, user.id);
			const box = new ContainerBuilder()
				.setAccentColor(result.success ? config.Colors?.success || "#10B981" : config.Colors?.error || "#EF4444")
				.addTextDisplay(`### ${result.success ? "✅ Command Disabled" : "❌ Action Failed"}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(result.message)
				.build();
			return isSlash
				? message.reply({ components: [box], flags: MessageFlags.IsComponentsV2 })
				: message.reply({ components: [box], flags: MessageFlags.IsComponentsV2 });
		}

		if (subcommand === "enable" && targetCmd) {
			const result = await ServerCommandManager.enableCommand(guild.id, targetCmd, user.id);
			const box = new ContainerBuilder()
				.setAccentColor(result.success ? config.Colors?.success || "#10B981" : config.Colors?.error || "#EF4444")
				.addTextDisplay(`### ${result.success ? "✅ Command Re-Enabled" : "❌ Action Failed"}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(result.message)
				.build();
			return isSlash
				? message.reply({ components: [box], flags: MessageFlags.IsComponentsV2 })
				: message.reply({ components: [box], flags: MessageFlags.IsComponentsV2 });
		}

		// Interactive Panel
		let page = 0;
		if (subcommand === "list") {
			const p = isSlash ? message.options.getInteger("page") : parseInt(args[1], 10);
			if (!isNaN(p) && p >= 1) page = p - 1;
		}

		const prefix = `cmdmgmt_${user.id}_${Date.now()}`;

		const renderPanel = async () => {
			const allCommands = ServerCommandManager.getAllManageableCommands();
			const { disabledCommands } = await ServerCommandManager.getGuildSettings(guild.id);

			const totalPages = Math.max(1, Math.ceil(allCommands.length / PAGE_SIZE));
			page = Math.max(0, Math.min(page, totalPages - 1));

			const pageCommands = allCommands.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

			const container = new ContainerBuilder()
				.setAccentColor(config.Colors?.default || "#5865F2")
				.addTextDisplay(`### ⚙️ Server Command Management — ${guild.name}`)
				.addTextDisplay(
					`Configure which commands are active in **${guild.name}**.\n\n` +
					`• **Total Manageable Commands:** \`${allCommands.length}\`\n` +
					`• **Currently Disabled in Server:** \`${disabledCommands.size}\`\n` +
					`• **Page:** \`${page + 1} of ${totalPages}\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

			container.addTextDisplay("**Command Status Table**");
			for (const cmd of pageCommands) {
				const isDisabled = disabledCommands.has(cmd.name.toLowerCase());
				const statusBadge = cmd.essential
					? "🔒 `ESSENTIAL (Protected)`"
					: isDisabled
						? "🔴 `DISABLED`"
						: "🟢 `ENABLED`";
				container.addTextDisplay(
					`• **/${cmd.name}** [${cmd.category}] — ${statusBadge}\n` +
					`  -# ${cmd.description.slice(0, 100)}`
				);
			}

			// Interactive Select Menu for quick toggling on current page
			const toggleable = pageCommands.filter((c) => !c.essential);
			if (toggleable.length > 0) {
				container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
				container.addTextDisplay("**Quick Toggle Command**\nSelect a command from this page to toggle its enabled/disabled status in this server.");
				container.addActionRow((row: any) => {
					row.addSelectMenu({
						custom_id: `${prefix}:toggle_select`,
						type: SelectMenuTypes.CUSTOM,
						placeholder: "Select command to toggle...",
						minValues: 1,
						maxValues: 1,
						options: toggleable.map((c) => {
							const isDis = disabledCommands.has(c.name.toLowerCase());
							return {
								label: `/${c.name} (${isDis ? "Disabled" : "Enabled"})`,
								description: isDis ? `Click to enable /${c.name}` : `Click to disable /${c.name}`,
								value: c.name,
								emoji: isDis ? "🟢" : "🔴",
							};
						}),
					});
					return row;
				});
			}

			// Navigation row
			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addActionRow((row: any) => {
				row.addButton({
					custom_id: `${prefix}:prev`,
					label: "◀ Previous",
					style: ButtonStyle.Secondary,
					disabled: page <= 0,
				});
				row.addButton({
					custom_id: `${prefix}:next`,
					label: "Next ▶",
					style: ButtonStyle.Secondary,
					disabled: page >= totalPages - 1,
				});
				row.addButton({
					custom_id: `${prefix}:refresh`,
					label: "Refresh",
					style: ButtonStyle.Secondary,
				});
				return row;
			});

			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addTextDisplay("-# Essential moderation and configuration commands are locked and cannot be disabled to prevent accidental lockouts.");

			return container.build();
		};

		const payload = (built: any) => ({
			components: [built],
			flags: MessageFlags.IsComponentsV2,
		});

		const sent = isSlash
			? await message.reply(payload(await renderPanel()))
			: await message.reply(payload(await renderPanel()));

		const messageObj = isSlash ? await message.fetchReply() : sent;
		const collector = messageObj.createMessageComponentCollector({
			time: 300_000,
			filter: (i: any) => i.user.id === user.id,
		});

		collector.on("collect", async (i: any) => {
			try {
				if (!i.customId.startsWith(prefix)) return;
				const parts = i.customId.split(":");
				const action = parts[1];

				if (action === "prev") {
					page = Math.max(0, page - 1);
					return i.update(payload(await renderPanel()));
				}

				if (action === "next") {
					const allCommands = ServerCommandManager.getAllManageableCommands();
					const totalPages = Math.max(1, Math.ceil(allCommands.length / PAGE_SIZE));
					if (page < totalPages - 1) page++;
					return i.update(payload(await renderPanel()));
				}

				if (action === "refresh") {
					return i.update(payload(await renderPanel()));
				}

				if (action === "toggle_select") {
					const selectedCmd = i.values?.[0];
					if (selectedCmd) {
						const { disabledCommands } = await ServerCommandManager.getGuildSettings(guild.id);
						if (disabledCommands.has(selectedCmd.toLowerCase())) {
							await ServerCommandManager.enableCommand(guild.id, selectedCmd, user.id);
						} else {
							await ServerCommandManager.disableCommand(guild.id, selectedCmd, user.id);
						}
						return i.update(payload(await renderPanel()));
					}
				}
			} catch (err) {
				logger.error("[CommandManage] Interaction error:", err);
				i.reply({ content: "An error occurred while updating the panel.", ephemeral: true }).catch(() => null);
			}
		});
	},
};

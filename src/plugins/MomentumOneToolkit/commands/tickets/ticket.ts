const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	PermissionFlagsBits,
	ChannelType,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { TicketManager } from "../../tickets/TicketManager";

export default {
	name: "ticket",
	aliases: ["tickets", "t"],
	description: "Create, view, manage, and configure support and request tickets.",
	category: "Tickets",
	usage: "ticket [create [topic] | close [reason] | settings [category] [staff_role] [min_withdrawal]]",

	sub_commands: [
		{ name: "create [topic]", description: "Open a new private support or general ticket." },
		{ name: "close [reason]", description: "Close and resolve an active ticket." },
		{ name: "list", description: "List your active tickets or all open tickets for staff." },
		{ name: "settings [category] [staff_role] [min_withdrawal]", description: "Configure server ticket category and settings (Admin)." },
	],

	builder: new SlashCommandBuilder()
		.setName("ticket")
		.setDescription("Create, view, manage, and configure support and request tickets.")
		.addSubcommand((sub: any) =>
			sub
				.setName("create")
				.setDescription("Open a new private support ticket")
				.addStringOption((opt: any) =>
					opt.setName("topic").setDescription("Topic or brief reason for opening ticket").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("close")
				.setDescription("Close an active ticket")
				.addStringOption((opt: any) =>
					opt.setName("reason").setDescription("Reason for closing the ticket").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("list")
				.setDescription("List active server tickets")
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("settings")
				.setDescription("Configure server ticket settings (Admin only)")
				.addChannelOption((opt: any) =>
					opt
						.setName("category")
						.setDescription("Target category for new ticket channels")
						.addChannelTypes(ChannelType.GuildCategory)
						.setRequired(false)
				)
				.addRoleOption((opt: any) =>
					opt.setName("staff_role").setDescription("Designated staff role with access to tickets").setRequired(false)
				)
				.addIntegerOption((opt: any) =>
					opt.setName("min_withdrawal").setDescription("Minimum allowed withdrawal amount").setRequired(false)
				)
				.addChannelOption((opt: any) =>
					opt
						.setName("transcripts_channel")
						.setDescription("Text channel for automated transcripts & receipts")
						.addChannelTypes(ChannelType.GuildText)
						.setRequired(false)
				)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[]) => {
		const isSlash = commandType === CommandType.SLASH;
		const guild = messageOrInteraction.guild;

		if (!guild) {
			const text = "❌ This command can only be used inside a server.";
			return isSlash
				? messageOrInteraction.editReply({ content: text })
				: messageOrInteraction.reply(text);
		}

		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const member = messageOrInteraction.member;
		const currentChannel = messageOrInteraction.channel;
		const E = config.Emojis || {};
		const C = config.Colors || {};
		const botPrefix = config.settings?.bot?.prefix || ".";

		const replyMsg = async (container: any, ephemeral: boolean = false) => {
			const payload = { components: [container], flags: MessageFlags.IsComponentsV2, ephemeral };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		};

		const hasAdmin =
			member?.permissions?.has(PermissionFlagsBits.Administrator) ||
			member?.permissions?.has(PermissionFlagsBits.ManageGuild);

		// Determine subcommand
		let subcommand = "create";
		let topicArg = "";
		let reasonArg = "";
		let categoryArg: any = null;
		let staffRoleArg: any = null;
		let minWithdrawalArg: number | null = null;
		let transcriptsChannelArg: any = null;

		if (isSlash) {
			subcommand = messageOrInteraction.options.getSubcommand(false) || "create";
			if (subcommand === "create") {
				topicArg = messageOrInteraction.options.getString("topic") || "";
			} else if (subcommand === "close") {
				reasonArg = messageOrInteraction.options.getString("reason") || "";
			} else if (subcommand === "list") {
				subcommand = "list";
			} else if (subcommand === "settings") {
				categoryArg = messageOrInteraction.options.getChannel("category");
				staffRoleArg = messageOrInteraction.options.getRole("staff_role");
				minWithdrawalArg = messageOrInteraction.options.getInteger("min_withdrawal");
				transcriptsChannelArg = messageOrInteraction.options.getChannel("transcripts_channel");
			}
		} else {
			const firstArg = args?.[0]?.toLowerCase();
			if (firstArg === "close") {
				subcommand = "close";
				reasonArg = args?.slice(1).join(" ");
			} else if (firstArg === "list") {
				subcommand = "list";
			} else if (firstArg === "settings" || firstArg === "config") {
				subcommand = "settings";
				if (args?.[1]) {
					const cleanCat = args[1].replace(/[<#>]/g, "").trim();
					categoryArg = guild.channels.cache.get(cleanCat);
				}
				if (args?.[2]) {
					const cleanRole = args[2].replace(/[<@&>]/g, "").trim();
					staffRoleArg = guild.roles.cache.get(cleanRole);
				}
				if (args?.[3]) {
					const parsed = parseInt(args[3], 10);
					if (!isNaN(parsed)) minWithdrawalArg = parsed;
				}
				if (args?.[4]) {
					const cleanTr = args[4].replace(/[<#>]/g, "").trim();
					transcriptsChannelArg = guild.channels.cache.get(cleanTr);
				}
			} else if (firstArg === "create") {
				subcommand = "create";
				topicArg = args?.slice(1).join(" ");
			} else {
				subcommand = "create";
				topicArg = args?.join(" ") || "";
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: SETTINGS (ADMIN ONLY)
		 * --------------------------------------------------------- */
		if (subcommand === "settings") {
			if (!hasAdmin) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Administrator` or `Manage Server` permission to configure tickets.")
					.build();
				return replyMsg(denied, true);
			}

			const currentConfig = await TicketManager.getGuildConfig(guild.id);
			const updates: any = {};

			if (categoryArg) updates.categoryId = categoryArg.id;
			if (staffRoleArg) {
				const existingRoles = new Set(currentConfig.staffRoleIds || []);
				existingRoles.add(staffRoleArg.id);
				updates.staffRoleIds = Array.from(existingRoles);
			}
			if (minWithdrawalArg !== null && Number.isInteger(minWithdrawalArg) && minWithdrawalArg > 0) {
				updates.minWithdrawalAmount = minWithdrawalArg;
			}
			if (transcriptsChannelArg) {
				updates.transcriptChannelId = transcriptsChannelArg.id;
				updates.transcriptsEnabled = true;
			}

			let updatedConfig = currentConfig;
			if (Object.keys(updates).length > 0) {
				updatedConfig = await TicketManager.updateGuildConfig(guild.id, updates, user.id);
			}

			const categoryDisplay = updatedConfig.categoryId
				? `<#${updatedConfig.categoryId}> (\`${updatedConfig.categoryId}\`)`
				: "None (Tickets created at top level)";
			const staffRolesDisplay = updatedConfig.staffRoleIds.length > 0
				? updatedConfig.staffRoleIds.map((r) => `<@&${r}>`).join(", ")
				: "None configured";
			const transcriptsDisplay = updatedConfig.transcriptChannelId
				? `<#${updatedConfig.transcriptChannelId}> (\`${updatedConfig.transcriptChannelId}\`)`
				: "*None configured*";

			const container = new ContainerBuilder()
				.setAccentColor(C.default || "#3b82f6")
				.addTextDisplay(`### 🎫 Ticket Settings: ${guild.name}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`• **Ticket Category:** ${categoryDisplay}\n` +
					`• **Staff Roles:** ${staffRolesDisplay}\n` +
					`• **Transcripts Channel:** ${transcriptsDisplay}\n` +
					`• **Transcripts Logging:** \`${updatedConfig.transcriptsEnabled !== false ? "Yes" : "No"}\`\n` +
					`• **Min Withdrawal Limit:** \`${updatedConfig.minWithdrawalAmount}\`\n` +
					`• **Ticketing Enabled:** \`${updatedConfig.enabled ? "Yes" : "No"}\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`-# Use \`${botPrefix}ticket settings [category] [staff_role] [min_withdrawal] [transcripts_channel]\` to update.`);

			if (!updatedConfig.transcriptChannelId) {
				container.addActionRow((row: any) => {
					row.addButton({
						custom_id: "ticket:autocreate_transcripts:cfg",
						label: "Auto-Create Transcripts Channel",
						emoji: E.add || "➕",
						style: ButtonStyle.Primary,
					});
					return row;
				});
			}

			return replyMsg(container.build());
		}

		/* ---------------------------------------------------------
		 * ACTION: CREATE TICKET
		 * --------------------------------------------------------- */
		if (subcommand === "create") {
			const ticketTitle = topicArg.trim() || `General Support by ${user.username}`;
			const result = await TicketManager.createTicket({
				guild,
				requester: user,
				type: "general",
				title: ticketTitle,
				details: { description: topicArg || "General support ticket" },
			});

			if (!result.success) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Ticket Creation Failed`)
					.addTextDisplay(result.error || "Could not open a ticket.")
					.build();
				return replyMsg(errorC, true);
			}

			const channelMention = result.channel ? `<#${result.channel.id}>` : `#${result.ticket?.ticketId}`;
			const container = new ContainerBuilder()
				.setAccentColor(C.success || "#22c55e")
				.addTextDisplay(`### 🎫 Ticket Opened`)
				.addTextDisplay(`Your support ticket has been created in ${channelMention}.`)
				.build();

			return replyMsg(container, true);
		}

		/* ---------------------------------------------------------
		 * ACTION: CLOSE TICKET
		 * --------------------------------------------------------- */
		if (subcommand === "close") {
			// Find ticket by channelId or check if ticketId is given in topicArg
			const col = await DatabaseManager.collection("economy_tickets");
			const ticket = (await col.findOne({ channelId: currentChannel.id })) as any;

			if (!ticket) {
				const notInTicket = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Not a Ticket Channel`)
					.addTextDisplay("This channel is not an active ticket. Please use this command inside a ticket channel.")
					.build();
				return replyMsg(notInTicket, true);
			}

			const config = await TicketManager.getGuildConfig(guild.id);
			const isStaff =
				hasAdmin ||
				(member?.roles?.cache &&
					config.staffRoleIds.some((rId) => member.roles.cache.has(rId)));
			const isRequester = ticket.requesterId === user.id;

			if (!isStaff && !isRequester) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("Only the ticket creator or authorized staff can close this ticket.")
					.build();
				return replyMsg(denied, true);
			}

			const closeResult = await TicketManager.closeTicket(
				guild.id,
				ticket.ticketId,
				user.id,
				reasonArg || "Resolved by user/staff",
				messageOrInteraction.client
			);

			if (!closeResult.success) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Failed to Close Ticket`)
					.addTextDisplay(closeResult.error || "Could not close ticket.")
					.build();
				return replyMsg(errorC, true);
			}

			const container = new ContainerBuilder()
				.setAccentColor(C.warning || "#f59e0b")
				.addTextDisplay(`### 🔒 Ticket Closed`)
				.addTextDisplay(`Ticket #${ticket.ticketId} has been closed by <@${user.id}>.\nReason: ${reasonArg || "None provided"}`)
				.build();

			return replyMsg(container);
		}

		/* ---------------------------------------------------------
		 * ACTION: LIST TICKETS
		 * --------------------------------------------------------- */
		if (subcommand === "list") {
			const config = await TicketManager.getGuildConfig(guild.id);
			const isStaff =
				hasAdmin ||
				(member?.roles?.cache &&
					config.staffRoleIds.some((rId) => member.roles.cache.has(rId)));

			const col = await DatabaseManager.collection("economy_tickets");
			const query: any = { guildId: guild.id };
			if (!isStaff) {
				query.requesterId = user.id;
			}
			query.status = { $in: ["open", "processing"] };

			const activeTickets = (await col.find(query).sort({ createdAt: -1 }).toArray()) as any[];

			if (!activeTickets || activeTickets.length === 0) {
				const noTickets = new ContainerBuilder()
					.setAccentColor(C.default || "#3b82f6")
					.addTextDisplay(`### 🎫 Active Tickets: ${guild.name}`)
					.addTextDisplay(isStaff ? "No active open tickets found on the server." : "You do not have any open active tickets.")
					.build();
				return replyMsg(noTickets, true);
			}

			const rows = activeTickets.slice(0, 10).map((t) => {
				const ch = t.channelId ? `<#${t.channelId}>` : `\`#${t.ticketId}\``;
				const typeTag = t.type.toUpperCase();
				const amount = t.details?.amount !== undefined ? ` • Amount: __${t.details.amount}__` : "";
				return `• **[#${t.ticketId}]** ${ch} (${typeTag}${amount}) — <@${t.requesterId}>`;
			}).join("\n");

			const listContainer = new ContainerBuilder()
				.setAccentColor(C.default || "#3b82f6")
				.addTextDisplay(`### 🎫 Active Tickets (${activeTickets.length})`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(rows)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`-# Use \`${botPrefix}ticket close\` inside a ticket channel to resolve.`)
				.build();

			return replyMsg(listContainer);
		}
	},
};

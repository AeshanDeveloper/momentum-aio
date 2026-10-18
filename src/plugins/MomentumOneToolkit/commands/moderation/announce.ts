const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
	PermissionFlagsBits,
	ChannelType,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { AuditService } from "../../economy/AuditService";

export interface AnnouncementRecord {
	id: string;
	guildId: string;
	authorId: string;
	channelId: string;
	messageId?: string;
	title: string;
	content: string;
	accentColor?: string;
	roleMentionId?: string;
	timestamp: Date;
}

export default {
	name: "announce",
	aliases: ["announcement", "broadcast"],
	description: "Create, preview, and publish announcements to server channels.",
	category: "Moderation",
	usage: "announce [send <#channel> <title> | <message> | preview <title> | <message> | settings]",
	userPermissions: [PermissionFlagsBits.ManageGuild],
	botPermissions: [PermissionFlagsBits.SendMessages, PermissionFlagsBits.ViewChannel],
	cooldown: 20*1000,

	sub_commands: [
		{ name: "send <#channel> <title> | <message>", description: "Create and publish an announcement to a channel (Admin)." },
		{ name: "preview <title> | <message>", description: "Preview how an announcement will look without sending it." },
		{ name: "settings", description: "View announcement configuration and default preferences." },
	],

	builder: new SlashCommandBuilder()
		.setName("announce")
		.setDescription("Create, preview, and publish server announcements.")
		.addSubcommand((sub: any) =>
			sub
				.setName("send")
				.setDescription("Send an announcement to a designated channel (Admin)")
				.addChannelOption((opt: any) =>
					opt
						.setName("channel")
						.setDescription("Destination channel for the announcement")
						.addChannelTypes(ChannelType.GuildText, ChannelType.GuildAnnouncement)
						.setRequired(true)
				)
				.addStringOption((opt: any) =>
					opt.setName("title").setDescription("Headline or title for the announcement").setRequired(true)
				)
				.addStringOption((opt: any) =>
					opt.setName("message").setDescription("Body text of the announcement").setRequired(true)
				)
				.addRoleOption((opt: any) =>
					opt.setName("role").setDescription("Optional role to mention with the announcement").setRequired(false)
				)
				.addStringOption((opt: any) =>
					opt
						.setName("color")
						.setDescription("Hex color code or theme (e.g. #3b82f6)")
						.setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("preview")
				.setDescription("Preview an announcement before publishing")
				.addStringOption((opt: any) =>
					opt.setName("title").setDescription("Headline or title").setRequired(true)
				)
				.addStringOption((opt: any) =>
					opt.setName("message").setDescription("Body text of the announcement").setRequired(true)
				)
				.addStringOption((opt: any) =>
					opt.setName("color").setDescription("Optional hex accent color").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("settings")
				.setDescription("View announcement policies and channel requirements")
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

		const invokingUser = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const invokingMember = messageOrInteraction.member;
		const E = config.Emojis || {};
		const C = config.Colors || {};
		const botPrefix = config.settings?.bot?.prefix || ".";

		const replyMsg = async (container: any, ephemeral: boolean = false) => {
			const payload = { components: [container], flags: MessageFlags.IsComponentsV2, ephemeral };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		};

		// 1. Permission checks: Author must have ManageGuild or Administrator
		const hasAdmin = invokingMember?.permissions?.has?.(PermissionFlagsBits.Administrator);
		const hasManageGuild = invokingMember?.permissions?.has?.(PermissionFlagsBits.ManageGuild);
		if (!hasAdmin && !hasManageGuild) {
			const deniedContainer = new ContainerBuilder()
				.setAccentColor(C.error || "#ef4444")
				.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
				.addTextDisplay("You need the `Manage Server` or `Administrator` permission to create announcements.")
				.build();
			return replyMsg(deniedContainer, true);
		}

		// 2. Parse invocation arguments
		let subcommand = "overview";
		let targetChannel: any = null;
		let title = "";
		let content = "";
		let roleMention: any = null;
		let colorHex = C.cmd_announce || C.default || "#3b82f6";

		if (isSlash) {
			subcommand = messageOrInteraction.options.getSubcommand(false) || "overview";
			if (subcommand === "send") {
				targetChannel = messageOrInteraction.options.getChannel("channel");
				title = messageOrInteraction.options.getString("title")?.trim() || "";
				content = messageOrInteraction.options.getString("message")?.trim() || "";
				roleMention = messageOrInteraction.options.getRole("role");
				const optColor = messageOrInteraction.options.getString("color")?.trim();
				if (optColor) colorHex = optColor;
			} else if (subcommand === "preview") {
				title = messageOrInteraction.options.getString("title")?.trim() || "";
				content = messageOrInteraction.options.getString("message")?.trim() || "";
				const optColor = messageOrInteraction.options.getString("color")?.trim();
				if (optColor) colorHex = optColor;
			}
		} else {
			const firstArg = args?.[0]?.toLowerCase();
			if (firstArg === "send") {
				subcommand = "send";
				// Channel parse: args[1]
				const rawCh = args?.[1];
				if (rawCh) {
					const cleanChId = rawCh.replace(/[<#>]/g, "").trim();
					targetChannel = guild.channels.cache.get(cleanChId);
				}
				// Remaining text after channel: split by '|'
				const rawRest = args.slice(2).join(" ");
				if (rawRest.includes("|")) {
					const splitParts = rawRest.split("|");
					title = splitParts[0].trim();
					content = splitParts.slice(1).join("|").trim();
				} else {
					title = args[2] || "Server Announcement";
					content = args.slice(3).join(" ").trim();
				}
			} else if (firstArg === "preview") {
				subcommand = "preview";
				const rawRest = args.slice(1).join(" ");
				if (rawRest.includes("|")) {
					const splitParts = rawRest.split("|");
					title = splitParts[0].trim();
					content = splitParts.slice(1).join("|").trim();
				} else {
					title = "Announcement Preview";
					content = rawRest.trim();
				}
			} else if (firstArg === "settings") {
				subcommand = "settings";
			} else {
				subcommand = "overview";
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: OVERVIEW / USAGE
		 * --------------------------------------------------------- */
		if (subcommand === "overview") {
			const container = new ContainerBuilder()
				.setAccentColor(colorHex)
				.addTextDisplay(`### ${E.broadcast || "📢"} Server Announcement System`)
				.addTextDisplay(
					`Broadcast styled, interactive announcements to your community with built-in preview and confirmation safeguards.`
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`**Command Usage:**\n` +
					`• \`${botPrefix}announce send <#channel> <Title> | <Message>\` — Draft and publish an announcement.\n` +
					`• \`${botPrefix}announce preview <Title> | <Message>\` — Test formatting before broadcasting.\n` +
					`• \`${botPrefix}announce settings\` — Inspect channel access and safeguards.\n\n` +
					`**Slash Command:**\n` +
					`• \`/announce send channel:#announcements title:... message:... [role:...]\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`-# ${E.info || "💡"} Mentions of @everyone and @here are strictly restricted to authorized server managers.`
				)
				.build();
			return replyMsg(container);
		}

		/* ---------------------------------------------------------
		 * ACTION: SETTINGS
		 * --------------------------------------------------------- */
		if (subcommand === "settings") {
			const textChannels = guild.channels.cache.filter((c: any) =>
				c.type === ChannelType.GuildText || c.type === ChannelType.GuildAnnouncement
			);

			const container = new ContainerBuilder()
				.setAccentColor(colorHex)
				.addTextDisplay(`### ${E.settings || "⚙️"} Announcement Configuration: ${guild.name}`)
				.addTextDisplay(`Current permissions and publishing parameters for this server.`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`• **Eligible Broadcast Channels:** \`${textChannels.size} channels\`\n` +
					`• **Broadcast Safety Safeguards:** \`Active (Interactive Confirmation)\`\n` +
					`• **Allowed Mentions Policy:** \`Safe (Unauthorized @everyone blocked)\`\n` +
					`• **Default Theme Accent:** \`${colorHex}\`\n` +
					`• **Required Permission:** \`Manage Server (ManageGuild)\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`-# Use \`/announce send\` to draft an announcement with live preview.`)
				.build();
			return replyMsg(container);
		}

		/* ---------------------------------------------------------
		 * ACTION: PREVIEW
		 * --------------------------------------------------------- */
		if (subcommand === "preview") {
			if (!title || !content) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Missing Announcement Content`)
					.addTextDisplay("Please provide both a title and body text: `announce preview <Title> | <Message>`.")
					.build();
				return replyMsg(errorC, true);
			}

			const previewContainer = new ContainerBuilder()
				.setAccentColor(colorHex)
				.addTextDisplay(`### 📢 ${title}`)
				.addTextDisplay(content)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`-# 👁️ Preview Mode • Drafted by <@${invokingUser.id}>`)
				.build();

			return replyMsg(previewContainer);
		}

		/* ---------------------------------------------------------
		 * ACTION: SEND WITH PREVIEW & CONFIRMATION
		 * --------------------------------------------------------- */
		if (subcommand === "send") {
			if (!targetChannel) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Missing Target Channel`)
					.addTextDisplay("Please specify a valid text channel: `announce send <#channel> <Title> | <Message>`.")
					.build();
				return replyMsg(errorC, true);
			}

			if (!title || !content) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Missing Announcement Content`)
					.addTextDisplay("Please provide both a title and body text: `announce send <#channel> <Title> | <Message>`.")
					.build();
				return replyMsg(errorC, true);
			}

			// Validate bot permissions in destination channel
			const botMember = guild.members?.me;
			if (botMember && !targetChannel.permissionsFor(botMember)?.has(PermissionFlagsBits.SendMessages)) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Bot Permission Denied`)
					.addTextDisplay(`The bot does not have permission to send messages in <#${targetChannel.id}>.`)
					.build();
				return replyMsg(errorC, true);
			}

			// Unauthorized mention protection
			const hasMentionEveryone = invokingMember?.permissions?.has(PermissionFlagsBits.MentionEveryone);
			const containsMassMention = content.includes("@everyone") || content.includes("@here") || title.includes("@everyone") || title.includes("@here");

			if (containsMassMention && !hasMentionEveryone) {
				// Strip or escape unauthorized mass mentions
				content = content.replace(/@everyone/g, "@\u200beveryone").replace(/@here/g, "@\u200bhere");
				title = title.replace(/@everyone/g, "@\u200beveryone").replace(/@here/g, "@\u200bhere");
			}

			// Interactive Confirmation workflow
			const sessionId = `${invokingUser.id}_${Date.now()}`;
			const confirmId = `announce_confirm_${sessionId}`;
			const cancelId = `announce_cancel_${sessionId}`;

			const confirmContainer = new ContainerBuilder()
				.setAccentColor(C.warning || "#f59e0b")
				.addTextDisplay(`### ⚠️ Confirm Announcement Broadcast`)
				.addTextDisplay(
					`Please review your proposed announcement below before publishing to <#${targetChannel.id}>.\n\n` +
					(containsMassMention ? "⚠️ **Contains broad @everyone/@here mention!**\n" : "") +
					(roleMention ? `• **Mentioned Role:** <@&${roleMention.id}>\n` : "") +
					`• **Destination:** <#${targetChannel.id}>`
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`### 📢 ${title}\n\n${content}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addActionRow((row: any) => {
					row.addButton({
						custom_id: confirmId,
						label: "Publish Announcement",
						style: ButtonStyle.Success,
					});
					row.addButton({
						custom_id: cancelId,
						label: "Cancel",
						style: ButtonStyle.Secondary,
					});
					return row;
				})
				.build();

			const sent = await replyMsg(confirmContainer);
			if (!sent?.createMessageComponentCollector) return;

			const collector = sent.createMessageComponentCollector({
				time: 120_000,
				filter: (i: any) => i.user.id === invokingUser.id,
			});

			collector.on("collect", async (interaction: any) => {
				try {
					if (interaction.customId === cancelId) {
						collector.stop("cancelled");
						const cancelledC = new ContainerBuilder()
							.setAccentColor(C.default || "#6b7280")
							.addTextDisplay(`### ❌ Announcement Cancelled`)
							.addTextDisplay("The announcement was discarded and not sent.")
							.build();
						await interaction.update({ components: [cancelledC], flags: MessageFlags.IsComponentsV2 });
						return;
					}

					if (interaction.customId === confirmId) {
						collector.stop("confirmed");

						// Build the public broadcast container
						const broadcastContainer = new ContainerBuilder()
							.setAccentColor(colorHex)
							.addTextDisplay(`### 📢 ${title}`)
							.addTextDisplay(content)
							.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
							.addTextDisplay(`-# Published by <@${invokingUser.id}> in **${guild.name}**`)
							.build();

						// Mentions configuration to prevent abuse
						const allowedMentions: any = {
							parse: hasMentionEveryone ? ["users"] : [],
						};
						if (roleMention) {
							allowedMentions.roles = [roleMention.id];
						}

						const rolePrefix = roleMention ? `<@&${roleMention.id}> ` : "";

						// Send to target channel
						const publishedMsg = await targetChannel.send({
							content: rolePrefix || undefined,
							components: [broadcastContainer],
							flags: MessageFlags.IsComponentsV2,
							allowedMentions,
						});

						// Record audit trail
						void AuditService.record({
							guildId: guild.id,
							actorId: invokingUser.id,
							action: "settings_update",
							reason: `Published announcement to #${targetChannel.name} (Msg ID: ${publishedMsg.id})`,
						});

						const successC = new ContainerBuilder()
							.setAccentColor(C.success || "#22c55e")
							.addTextDisplay(`### ${E.success || E.confirmed  || "✅"} Announcement Published`)
							.addTextDisplay(
								`Successfully sent announcement to <#${targetChannel.id}>!\n\n` +
								`• **Title:** \`${title}\`\n` +
								`• **Message ID:** \`${publishedMsg.id}\`\n` +
								`• **Timestamp:** <t:${Math.floor(Date.now() / 1000)}:f>`
							)
							.build();

						await interaction.update({ components: [successC], flags: MessageFlags.IsComponentsV2 });
					}
				} catch (err: any) {
					logger.error("[AnnounceCommand] Collector error:", err);
				}
			});
		}
	},
};

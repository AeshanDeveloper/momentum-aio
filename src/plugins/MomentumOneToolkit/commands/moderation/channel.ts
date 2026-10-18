const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	PermissionFlagsBits,
	ChannelType,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";

export default {
	name: "channel",
	aliases: ["ch"],
	description: "Manage channel settings, inspect channel information, slowmode, and lock channels.",
	category: "Channels",
	usage: "channel [info [#ch] | slowmode <sec> [#ch] | lock [#ch] | unlock [#ch]]",
	userPermissions: [PermissionFlagsBits.ManageChannels],
	botPermissions: [PermissionFlagsBits.ManageChannels],
	cooldown: 5000,

	sub_commands: [
		{ name: "info [#channel]", description: "View details, slowmode, and metadata for a channel." },
		{ name: "slowmode <seconds> [#channel]", description: "Configure slowmode rate limit on a channel (Admin/Mod)." },
		{ name: "lock [#channel]", description: "Lock a channel to prevent regular members from sending messages." },
		{ name: "unlock [#channel]", description: "Unlock a locked channel to restore chat permissions." },
		{ name: "hide [#channel]", description: "Hide a channel from @everyone by denying ViewChannel (Admin/Mod)." },
		{ name: "unhide [#channel]", description: "Unhide a channel to restore default ViewChannel visibility (Admin/Mod)." },
	],

	builder: new SlashCommandBuilder()
		.setName("channel")
		.setDescription("Manage channel settings, slowmode, and locking.")
		.addSubcommand((sub: any) =>
			sub
				.setName("info")
				.setDescription("Inspect details and configuration of a channel")
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel (defaults to current)").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("slowmode")
				.setDescription("Set slowmode cooldown in seconds for a channel (Admin/Mod)")
				.addIntegerOption((opt: any) =>
					opt.setName("seconds").setDescription("Slowmode in seconds (0 to disable)").setRequired(true)
				)
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("lock")
				.setDescription("Lock a channel to prevent regular members from chatting")
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("unlock")
				.setDescription("Unlock a previously locked channel")
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("hide")
				.setDescription("Hide a channel by denying ViewChannel to @everyone")
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel to hide").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("unhide")
				.setDescription("Unhide a channel by restoring default ViewChannel to @everyone")
				.addChannelOption((opt: any) =>
					opt.setName("channel").setDescription("Target channel to unhide").setRequired(false)
				)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[]) => {
		const isSlash = commandType === CommandType.SLASH;
		const guild = messageOrInteraction.guild;

		if (!guild) {
			const text = (config.Emojis.no_access || config.Emojis.disabled || config.Emojis.disable || config.Emojis.error || "❌") + " This command can only be used inside a server.";
			return isSlash
				? messageOrInteraction.editReply({ content: text })
				: messageOrInteraction.reply(text);
		}

		const invokingUser = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const invokingMember = messageOrInteraction.member;
		const currentChannel = messageOrInteraction.channel;
		const E = config.Emojis || {};
		const C = config.Colors || {};
		const botPrefix = config.settings?.bot?.prefix || ".";

		const replyMsg = async (container: any, ephemeral: boolean = false) => {
			const payload = { components: [container], flags: MessageFlags.IsComponentsV2, ephemeral };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		};

		const hasManageChannels = invokingMember?.permissions?.has(PermissionFlagsBits.ManageChannels) ||
			invokingMember?.permissions?.has(PermissionFlagsBits.Administrator);

		let subcommand = "info";
		let targetChannel = currentChannel;
		let slowmodeSec = 0;

		if (isSlash) {
			subcommand = messageOrInteraction.options.getSubcommand(false) || "info";
			const ch = messageOrInteraction.options.getChannel("channel");
			if (ch) targetChannel = ch;
			if (subcommand === "slowmode") {
				slowmodeSec = messageOrInteraction.options.getInteger("seconds") ?? 0;
			}
		} else {
			const firstArg = args?.[0]?.toLowerCase();
			if (["lock", "unlock", "slowmode", "info", "hide", "unhide"].includes(firstArg)) {
				subcommand = firstArg;
				if (subcommand === "slowmode") {
					slowmodeSec = parseInt(args?.[1], 10) || 0;
					if (args?.[2]) {
						const cleanId = args[2].replace(/[<#>]/g, "").trim();
						const ch = guild.channels.cache.get(cleanId);
						if (ch) targetChannel = ch;
					}
				} else {
					if (args?.[1]) {
						const cleanId = args[1].replace(/[<#>]/g, "").trim();
						const ch = guild.channels.cache.get(cleanId);
						if (ch) targetChannel = ch;
					}
				}
			} else if (args && args.length > 0) {
				const cleanId = args[0].replace(/[<#>]/g, "").trim();
				const ch = guild.channels.cache.get(cleanId);
				if (ch) {
					targetChannel = ch;
					subcommand = "info";
				}
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: SLOWMODE
		 * --------------------------------------------------------- */
		if (subcommand === "slowmode") {
			if (!hasManageChannels) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Channels` permission to modify channel slowmode.")
					.build();
				return replyMsg(denied, true);
			}

			if (slowmodeSec < 0 || slowmodeSec > 21600) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Invalid Duration`)
					.addTextDisplay("Slowmode must be between 0 seconds (disabled) and 21,600 seconds (6 hours).")
					.build();
				return replyMsg(errorC, true);
			}

			try {
				await targetChannel.setRateLimitPerUser(slowmodeSec);
				const container = new ContainerBuilder()
					.setAccentColor(C.success || "#22c55e")
					.addTextDisplay(`### ${E.success || E.confirmed  || "✅"} Slowmode Updated`)
					.addTextDisplay(
						slowmodeSec === 0
							? `Slowmode has been **disabled** in <#${targetChannel.id}>.`
							: `Slowmode in <#${targetChannel.id}> set to **${slowmodeSec} seconds** per member.`
					)
					.build();
				return replyMsg(container);
			} catch (err: any) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Failed to Set Slowmode`)
					.addTextDisplay(err?.message || "Missing bot permissions.")
					.build();
				return replyMsg(errorC, true);
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: LOCK CHANNEL
		 * --------------------------------------------------------- */
		if (subcommand === "lock") {
			if (!hasManageChannels) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Channels` permission to lock channels.")
					.build();
				return replyMsg(denied, true);
			}

			try {
				await targetChannel.permissionOverwrites.edit(guild.roles.everyone, {
					SendMessages: false,
				});

				const container = new ContainerBuilder()
					.setAccentColor(C.warning || "#f59e0b")
					.addTextDisplay(`### 🔒 Channel Locked`)
					.addTextDisplay(`Successfully locked <#${targetChannel.id}>. Regular members cannot send messages.`)
					.build();
				return replyMsg(container);
			} catch (err: any) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Lock Failed`)
					.addTextDisplay(err?.message || "Failed to update channel permissions.")
					.build();
				return replyMsg(errorC, true);
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: UNLOCK CHANNEL
		 * --------------------------------------------------------- */
		if (subcommand === "unlock") {
			if (!hasManageChannels) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Channels` permission to unlock channels.")
					.build();
				return replyMsg(denied, true);
			}

			try {
				await targetChannel.permissionOverwrites.edit(guild.roles.everyone, {
					SendMessages: null,
				});

				const container = new ContainerBuilder()
					.setAccentColor(C.success || "#22c55e")
					.addTextDisplay(`### 🔓 Channel Unlocked`)
					.addTextDisplay(`Successfully unlocked <#${targetChannel.id}>. Regular members can chat again.`)
					.build();
				return replyMsg(container);
			} catch (err: any) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Unlock Failed`)
					.addTextDisplay(err?.message || "Failed to update channel permissions.")
					.build();
				return replyMsg(errorC, true);
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: HIDE CHANNEL
		 * --------------------------------------------------------- */
		if (subcommand === "hide") {
			if (!hasManageChannels) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Channels` permission to hide channels.")
					.build();
				return replyMsg(denied, true);
			}

			const botMember = guild.members?.me || (messageOrInteraction.client?.user ? await guild.members.fetch(messageOrInteraction.client.user.id).catch(() => null) : null);
			if (botMember && !botMember.permissions?.has(PermissionFlagsBits.ManageChannels) && !botMember.permissions?.has(PermissionFlagsBits.Administrator)) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Bot Permission Missing`)
					.addTextDisplay("I need the `Manage Channels` permission to hide channels.")
					.build();
				return replyMsg(denied, true);
			}

			try {
				const everyoneRole = guild.roles?.everyone || { id: guild.id };
				await targetChannel.permissionOverwrites.edit(everyoneRole, {
					ViewChannel: false,
				}, { reason: `Channel hidden by ${invokingUser.tag || invokingUser.username}` });

				// Audit existing overwrites that still explicitly allow ViewChannel
				const explicitlyAllowed: string[] = [];
				if (targetChannel.permissionOverwrites?.cache) {
					for (const [id, overwrite] of targetChannel.permissionOverwrites.cache) {
						if (id === everyoneRole.id) continue;
						if (overwrite.allow?.has?.(PermissionFlagsBits.ViewChannel)) {
							const role = guild.roles?.cache?.get(id);
							if (role) {
								explicitlyAllowed.push(`Role **@${role.name}**`);
							} else {
								explicitlyAllowed.push(`Target <@${id}>`);
							}
						}
					}
				}

				const container = new ContainerBuilder()
					.setAccentColor(C.warning || "#f59e0b")
					.addTextDisplay(`### 🙈 Channel Hidden`)
					.addTextDisplay(`Successfully hidden <#${targetChannel.id}>. \`ViewChannel\` denied for \`@everyone\`.`);

				if (explicitlyAllowed.length > 0) {
					container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
					container.addTextDisplay(`⚠️ **Explicit Access Overwrites:**\nThe following roles/members still have explicit \`ViewChannel\` allow overwrites:\n• ${explicitlyAllowed.join("\n• ")}`);
				}

				return replyMsg(container.build());
			} catch (err: any) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Hide Failed`)
					.addTextDisplay(err?.message || "Failed to update channel visibility permissions.")
					.build();
				return replyMsg(errorC, true);
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: UNHIDE CHANNEL
		 * --------------------------------------------------------- */
		if (subcommand === "unhide") {
			if (!hasManageChannels) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Channels` permission to unhide channels.")
					.build();
				return replyMsg(denied, true);
			}

			const botMember = guild.members?.me || (messageOrInteraction.client?.user ? await guild.members.fetch(messageOrInteraction.client.user.id).catch(() => null) : null);
			if (botMember && !botMember.permissions?.has(PermissionFlagsBits.ManageChannels) && !botMember.permissions?.has(PermissionFlagsBits.Administrator)) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Bot Permission Missing`)
					.addTextDisplay("I need the `Manage Channels` permission to unhide channels.")
					.build();
				return replyMsg(denied, true);
			}

			try {
				const everyoneRole = guild.roles?.everyone || { id: guild.id };
				await targetChannel.permissionOverwrites.edit(everyoneRole, {
					ViewChannel: null,
				}, { reason: `Channel unhidden by ${invokingUser.tag || invokingUser.username}` });

				const container = new ContainerBuilder()
					.setAccentColor(C.success || "#22c55e")
					.addTextDisplay(`### 👁️ Channel Unhidden`)
					.addTextDisplay(`Successfully unhidden <#${targetChannel.id}>. Default visibility restored without affecting unrelated permissions.`)
					.build();
				return replyMsg(container);
			} catch (err: any) {
				const errorC = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Unhide Failed`)
					.addTextDisplay(err?.message || "Failed to restore channel visibility permissions.")
					.build();
				return replyMsg(errorC, true);
			}
		}

		/* ---------------------------------------------------------
		 * ACTION: INFO (DEFAULT)
		 * --------------------------------------------------------- */
		const ch = targetChannel || currentChannel;
		const chCreated = ch?.createdAt instanceof Date ? Math.floor(ch.createdAt.getTime() / 1000) : null;
		const chName = ch?.name || "current-channel";
		const chTopic = ch?.topic || "No topic set for this channel.";
		const chId = ch?.id || "N/A";
		const rateLimit = ch?.rateLimitPerUser || 0;

		const container = new ContainerBuilder()
			.setAccentColor(C.default || "#3b82f6")
			.addTextDisplay(`### 📺 Channel Info: #${chName}`)
			.addTextDisplay(chTopic)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`• **Channel ID:** \`${chId}\`\n` +
				`• **Mention:** <#${chId}>\n` +
				`• **Slowmode:** \`${rateLimit > 0 ? `${rateLimit}s` : "Disabled"}\`\n` +
				(chCreated ? `• **Created:** <t:${chCreated}:f> (<t:${chCreated}:R>)\n` : "") +
				`• **NSFW:** \`${ch?.nsfw ? "Yes" : "No"}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`-# Use \`${botPrefix}channel slowmode <sec>\`, \`${botPrefix}channel lock\`, or \`${botPrefix}channel unlock\`.`)
			.build();

		return replyMsg(container);
	},
};

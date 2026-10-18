const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
	PermissionFlagsBits,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import DatabaseManager from "@database/Database";

async function resolveUser(client: any, raw: string | undefined): Promise<any> {
	if (!raw) return null;
	const cleanId = raw.replace(/[<@!>]/g, "").trim();
	if (!cleanId) return null;
	try {
		return await client.users.fetch(cleanId).catch(() => null);
	} catch {
		return null;
	}
}

export default {
	name: "invites",
	aliases: ["invite", "inv"],
	description: "Track server invites, view invite statistics, and manage member invite counts.",
	category: "Invites",
	usage: "invites [view [@user] | top | reset <@user|all>]",
	cooldown: 5000,

	sub_commands: [
		{ name: "view [@user]", description: "View your own or another member's total invites and breakdown." },
		{ name: "top", description: "Display the server invite leaderboard." },
		{ name: "reset <@user|all>", description: "Reset invite counts for a member or everyone (Admin)." },
	],

	builder: new SlashCommandBuilder()
		.setName("invites")
		.setDescription("Track server invites and view invite statistics.")
		.addSubcommand((sub: any) =>
			sub
				.setName("view")
				.setDescription("View invite counts for yourself or a target member")
				.addUserOption((opt: any) =>
					opt.setName("user").setDescription("Target member (defaults to you)").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("top")
				.setDescription("Display the server invite leaderboard")
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("reset")
				.setDescription("Reset invite counts for a member or the entire server (Admin)")
				.addUserOption((opt: any) =>
					opt.setName("user").setDescription("Member to reset (leave blank for all)").setRequired(false)
				)
				.addBooleanOption((opt: any) =>
					opt.setName("all").setDescription("Reset all invites across the server").setRequired(false)
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

		const invokingUser = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const invokingMember = messageOrInteraction.member;
		const E = config.Emojis || {};
		const C = config.Colors || {};
		const botPrefix = config.settings?.bot?.prefix || ".";

		const replyMsg = async (container: any, ephemeral: boolean = false) => {
			const payload = { components: [container], flags: MessageFlags.IsComponentsV2, ephemeral };
			return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
		};

		let subcommand = "view";
		let targetUser = invokingUser;
		let resetAll = false;

		if (isSlash) {
			subcommand = messageOrInteraction.options.getSubcommand(false) || "view";
			if (subcommand === "view") {
				const u = messageOrInteraction.options.getUser("user");
				if (u) targetUser = u;
			} else if (subcommand === "reset") {
				const u = messageOrInteraction.options.getUser("user");
				if (u) targetUser = u;
				resetAll = Boolean(messageOrInteraction.options.getBoolean("all"));
			}
		} else {
			const firstArg = args?.[0]?.toLowerCase();
			if (firstArg === "top" || firstArg === "leaderboard") {
				subcommand = "top";
			} else if (firstArg === "reset") {
				subcommand = "reset";
				if (args?.[1]?.toLowerCase() === "all") {
					resetAll = true;
				} else if (args?.[1]) {
					const fetched = await resolveUser(messageOrInteraction.client, args[1]);
					if (fetched) targetUser = fetched;
				}
			} else if (firstArg === "view") {
				subcommand = "view";
				if (args?.[1]) {
					const fetched = await resolveUser(messageOrInteraction.client, args[1]);
					if (fetched) targetUser = fetched;
				}
			} else if (args?.[0]) {
				const fetched = await resolveUser(messageOrInteraction.client, args[0]);
				if (fetched) {
					targetUser = fetched;
					subcommand = "view";
				}
			}
		}

		const collection = await DatabaseManager.collection("server_invites");

		/* ---------------------------------------------------------
		 * ACTION: RESET INVITES (ADMIN ONLY)
		 * --------------------------------------------------------- */
		if (subcommand === "reset") {
			const hasAdmin = invokingMember?.permissions?.has(PermissionFlagsBits.Administrator) ||
				invokingMember?.permissions?.has(PermissionFlagsBits.ManageGuild);

			if (!hasAdmin) {
				const denied = new ContainerBuilder()
					.setAccentColor(C.error || "#ef4444")
					.addTextDisplay(`### ${E.no_access || E.error  || "❌"} Permission Denied`)
					.addTextDisplay("You need the `Manage Server` permission to reset invite tracking data.")
					.build();
				return replyMsg(denied, true);
			}

			if (resetAll) {
				await collection.deleteMany({ guildId: guild.id });
				const container = new ContainerBuilder()
					.setAccentColor(C.warning || "#f59e0b")
					.addTextDisplay(`### ⚠️ Server Invites Reset`)
					.addTextDisplay(`Successfully reset all tracked invite records for **${guild.name}**.`)
					.build();
				return replyMsg(container);
			}

			await collection.deleteOne({ guildId: guild.id, userId: targetUser.id });
			const container = new ContainerBuilder()
				.setAccentColor(C.success || "#22c55e")
				.addTextDisplay(`### ${E.success || E.confirmed  || "✅"} Member Invites Reset`)
				.addTextDisplay(`Successfully reset all invite statistics for <@${targetUser.id}>.`)
				.build();
			return replyMsg(container);
		}

		/* ---------------------------------------------------------
		 * ACTION: INVITES TOP / LEADERBOARD
		 * --------------------------------------------------------- */
		if (subcommand === "top") {
			let topUsers: any[] = [];
			try {
				topUsers = await collection
					.find({ guildId: guild.id })
					.sort({ total: -1 })
					.limit(10)
					.toArray();
			} catch (err) {
				logger.debug("[InvitesCommand] Query fallback:", err);
			}

			const container = new ContainerBuilder()
				.setAccentColor(C.default || "#3b82f6")
				.addTextDisplay(`### 🏆 Top Inviters: ${guild.name}`)
				.addTextDisplay(`Members who have invited the most people to the server.`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

			if (topUsers.length === 0) {
				container.addTextDisplay("No tracked invites recorded yet for this server.");
			} else {
				const lines = topUsers.map((item, idx) => {
					const medal = idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : `**#${idx + 1}**`;
					return `${medal} <@${item.userId}> — **${item.total || 0}** invites (Net: \`${(item.regular || 0) - (item.leaves || 0)}\`)`;
				}).join("\n");
				container.addTextDisplay(lines);
			}

			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addTextDisplay(`-# Use \`${botPrefix}invites view [@user]\` to check individual member details.`);
			return replyMsg(container.build());
		}

		/* ---------------------------------------------------------
		 * ACTION: VIEW (DEFAULT)
		 * --------------------------------------------------------- */
		let userRecord: any = null;
		try {
			userRecord = await collection.findOne({ guildId: guild.id, userId: targetUser.id });
		} catch (err) {
			logger.debug("[InvitesCommand] Fetch error:", err);
		}

		// Also try to read real guild invites if bot has ManageGuild
		let liveCount = 0;
		try {
			if (guild.members?.me?.permissions?.has(PermissionFlagsBits.ManageGuild)) {
				const guildInvites = await guild.invites.fetch().catch(() => new Map());
				for (const inv of guildInvites.values()) {
					if (inv.inviter?.id === targetUser.id) {
						liveCount += inv.uses || 0;
					}
				}
			}
		} catch {}

		const regular = userRecord?.regular ?? liveCount;
		const fake = userRecord?.fake ?? 0;
		const leaves = userRecord?.leaves ?? 0;
		const bonus = userRecord?.bonus ?? 0;
		const net = Math.max(0, regular + bonus - leaves - fake);
		const isSelf = targetUser.id === invokingUser.id;

		const container = new ContainerBuilder()
			.setAccentColor(C.default || "#3b82f6")
			.addTextDisplay(`### ✉️ ${isSelf ? "Your Invites" : `${targetUser.username}'s Invites`}`)
			.addTextDisplay(`Invite statistics for <@${targetUser.id}> in **${guild.name}**.`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`• **Net Invites:** \`${net}\`\n` +
				`• **Total Joins:** \`${regular}\`\n` +
				`• **Left / Left Server:** \`${leaves}\`\n` +
				`• **Fake / Invalid:** \`${fake}\`\n` +
				`• **Bonus Invites:** \`${bonus}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`-# Tracked automatically • Use \`${botPrefix}invites top\` for server ranking.`)
			.build();

		return replyMsg(container);
	},
};

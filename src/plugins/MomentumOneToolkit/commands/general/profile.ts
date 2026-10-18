const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	PermissionFlagsBits,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import { isBotOwner } from "@core/security/SecurityHelpers";
import { BlacklistManager } from "@core/security/BlacklistManager";

export default {
	name: "profile",
	aliases: ["userprofile", "userinfo", "whois"],
	description: "View your user profile, economy balances, badges, and payout configurations.",
	category: "General",
	usage: "profile [@user|userId]",
	cooldown: 3000,

	builder: new SlashCommandBuilder()
		.setName("profile")
		.setDescription("View user profile, economy stats, and registered payout details.")
		.addUserOption((opt: any) =>
			opt
				.setName("user")
				.setDescription("The user whose profile to inspect")
				.setRequired(false)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const author = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const guild = messageOrInteraction.guild;
		const guildId = guild?.id || "global";

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			profile: E.profile || E.user || "👤",
			wallet: E.wallet || E.balance || "🪙",
			safe: E.safe || "🏦",
			currency: E.currency || "₹",
			payout: E.payout || "💳",
			shield: E.shield || emojis.privacy || "🛡️",
			ban: E.ban || E.blacklist || "🚫",
			owner: E.owner || "👑",
			check: E.check || E.success || "✅",
		};

		const colors = {
			default: C.default || "#FF7B00",
			error: C.error || "#EF4444",
		};

		let targetUser = author;

		if (isSlash) {
			const slashTarget = messageOrInteraction.options.getUser("user");
			if (slashTarget) targetUser = slashTarget;
		} else {
			const firstArg = args[0];
			if (firstArg) {
				const cleaned = firstArg.replace(/[<@!>]/g, "").trim();
				if (/^\d{17,20}$/.test(cleaned)) {
					const client = messageOrInteraction.client;
					const fetched = await client.users.fetch(cleaned).catch(() => null);
					if (fetched) targetUser = fetched;
				}
			}
		}

		// Check member permissions / badges
		const isOwner = isBotOwner(targetUser.id);
		const blStatus = await BlacklistManager.isUserBlacklisted(targetUser.id);

		let memberRoleStr = "Member";
		if (guild) {
			const member = await guild.members.fetch(targetUser.id).catch(() => null);
			if (guild.ownerId === targetUser.id) {
				memberRoleStr = "Server Owner";
			} else if (member?.permissions?.has(PermissionFlagsBits.Administrator)) {
				memberRoleStr = "Server Administrator";
			} else if (member?.permissions?.has(PermissionFlagsBits.ManageGuild)) {
				memberRoleStr = "Server Moderator";
			}
		}

		const badges: string[] = [];
		if (isOwner) badges.push(`${emojis.owner} **Bot Developer / Owner**`);
		badges.push(`${emojis.shield} **${memberRoleStr}**`);
		if (blStatus.blacklisted) badges.push(`${emojis.ban} **System Blacklisted**`);

		const container = new ContainerBuilder()
			.setAccentColor(colors.default)
			.addTextDisplay(`### ${emojis.profile} User Profile: ${targetUser.username}`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`• **Discord ID:** \`${targetUser.id}\`\n` +
				`• **Account Created:** <t:${Math.floor(targetUser.createdTimestamp / 1000)}:R>\n` +
				`• **Roles & Badges:**\n  > ${badges.join("\n  > ")}`
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay("-# MomentumOne Platform Profile")
			.build();

		const payload = {
			components: [container],
			flags: MessageFlags.IsComponentsV2,
		};

		if (isSlash) {
			if (messageOrInteraction.deferred || messageOrInteraction.replied) {
				return messageOrInteraction.editReply(payload);
			}
			return messageOrInteraction.reply(payload);
		}

		return messageOrInteraction.reply(payload);
	},
};

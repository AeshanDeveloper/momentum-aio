const {
	MessageFlags,
	SeparatorSpacingSize,
} = require("discord.js");

const {
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import { BlacklistManager } from "@core/security/BlacklistManager";

function resolveTargetId(raw?: string): string | null {
	if (!raw) return null;
	const cleaned = raw.replace(/[<@!>]/g, "").trim();
	if (/^\d{17,20}$/.test(cleaned)) {
		return cleaned;
	}
	return null;
}

export default {
	name: "unblacklist",
	aliases: ["unbl"],
	description: "Remove a user or server from the global blacklist (Bot Owner Only).",
	category: "Owner",
	usage: "unblacklist <user|server> <targetId>",
	ownerOnly: true,

	execute: async (ctx: any, commandType: number, message: any, args: string[] = []) => {
		const ownerIds: string[] = config.settings?.bot?.owner_ids || [];
		const authorId = message.author?.id;

		if (!ownerIds.includes(authorId)) {
			return message.reply({
				content: "❌ **Access Denied**: This command is restricted to the bot owner.",
			});
		}

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			check: E.success || "✅",
			ban: E.ban || E.error || "🚫",
		};

		const colors = {
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
		};

		const reply = async (title: string, description: string, color = colors.success) => {
			const container = new ContainerBuilder()
				.setAccentColor(color)
				.addTextDisplay(`### ${title}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(description);

			return message.reply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			});
		};

		let type = args[0]?.toLowerCase();
		let targetRaw = args[1];

		// If user only passed target ID (or mention): `$unblacklist @user`
		if (type && !["user", "server", "guild"].includes(type)) {
			targetRaw = args[0];
			type = "user";
		}

		const targetId = resolveTargetId(targetRaw);
		if (!targetId) {
			return reply(
				`${emojis.ban} Invalid Target`,
				"Usage: `$unblacklist <user|server> <targetId>`\nExample: `$unblacklist user @john` or `$unblacklist server 123456789`",
				colors.error
			);
		}

		if (type === "server" || type === "guild") {
			const res = await BlacklistManager.unblacklistGuild(targetId, authorId);
			if (!res.success) {
				return reply(`${emojis.ban} Unblacklist Failed`, res.error || "Database error.", colors.error);
			}
			return reply(
				`${emojis.check} Server Unblacklisted`,
				`Successfully removed server \`${targetId}\` from the global blacklist.`,
				colors.success
			);
		} else {
			const res = await BlacklistManager.unblacklistUser(targetId, authorId);
			if (!res.success) {
				return reply(`${emojis.ban} Unblacklist Failed`, res.error || "Database error.", colors.error);
			}
			return reply(
				`${emojis.check} User Unblacklisted`,
				`Successfully removed user <@${targetId}> (\`${targetId}\`) from the global blacklist.`,
				colors.success
			);
		}
	},
};

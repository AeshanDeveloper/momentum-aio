const {
	MessageFlags,
	SeparatorSpacingSize,
} = require("discord.js");

const {
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { NoPrefixManager } from "@core/security/NoPrefixManager";
import { parseDuration } from "@core/security/BlacklistManager";

function resolveTargetId(raw?: string): string | null {
	if (!raw) return null;
	const cleaned = raw.replace(/[<@!>]/g, "").trim();
	if (/^\d{17,20}$/.test(cleaned)) {
		return cleaned;
	}
	return null;
}

export default {
	name: "noprefix",
	aliases: ["np", "noprefixuser"],
	description: "Grant or revoke persistent no-prefix command access for users (Bot Owner Only).",
	category: "Owner",
	usage: "noprefix <add|remove|list> <@user/id> [duration]",
	ownerOnly: true,

	sub_commands: [
		{ name: "add <@user> [duration]", description: "Grant no-prefix command privileges to a user." },
		{ name: "remove <@user>", description: "Revoke no-prefix command privileges from a user." },
		{ name: "list", description: "List all users with active no-prefix access." },
	],

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
			key: E.key || E.mod || "🔑",
			check: E.success || "✅",
			cross: E.error || "❌",
			info: E.info || "ℹ️",
			time: E.time || "⏱️",
			user: E.user || "👤",
		};

		const colors = {
			default: C.default || "#3B82F6",
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
		};

		const reply = async (title: string, description: string, color = colors.default) => {
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

		const action = args[0]?.toLowerCase();

		// Interactive Overview / List if no arguments provided or action === "list"
		if (!action || action === "list") {
			const entries = await NoPrefixManager.list();
			if (entries.length === 0) {
				return reply(
					`${emojis.info} No-Prefix System`,
					"No users currently have no-prefix privileges.\n\n" +
					"**Usage:**\n" +
					"> `$noprefix add <@user|id> [duration]` (e.g. `1h`, `7d`, `permanent`)\n" +
					"> `$noprefix remove <@user|id>`\n" +
					"> `$noprefix list [page]`",
					colors.default
				);
			}

			const pageArg = parseInt(args[1], 10) || 1;
			const pageSize = 10;
			const totalPages = Math.max(1, Math.ceil(entries.length / pageSize));
			const safePage = Math.max(1, Math.min(pageArg, totalPages));
			const pageItems = entries.slice((safePage - 1) * pageSize, safePage * pageSize);

			const desc = pageItems.map((e, idx) => {
				const exp = e.expiresAt
					? `<t:${Math.floor(new Date(e.expiresAt).getTime() / 1000)}:F> (<t:${Math.floor(new Date(e.expiresAt).getTime() / 1000)}:R>)`
					: "`Permanent`";
				const status = e.expiresAt ? "Temporary" : "Permanent";
				return `${(safePage - 1) * pageSize + idx + 1}. <@${e.userId}> (\`${e.userId}\`)\n   > **Status:** Active (${status})\n   > **Expires:** ${exp}\n   > **Granted by:** <@${e.addedBy}>`;
			}).join("\n\n");

			const container = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.key} Authorized No-Prefix Users (${entries.length}) — Page ${safePage}/${totalPages}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`${desc}\n\n` +
					`**Usage:**\n` +
					`> \`$noprefix add <@user|id> [duration]\` (e.g. \`1h\`, \`7d\`, \`permanent\`)\n` +
					`> \`$noprefix remove <@user|id>\`\n` +
					`> \`$noprefix list [page]\`` +
					(totalPages > 1 ? `\n\n-# View other pages with \`$noprefix list <page>\`` : "")
				)
				.build();

			return message.reply({
				components: [container],
				flags: MessageFlags.IsComponentsV2,
			});
		}

		if (action === "add") {
			const targetId = resolveTargetId(args[1]);
			if (!targetId) {
				return reply(
					`${emojis.cross} Missing User`,
					"Please mention a user or provide their Discord ID.\nExample: `$noprefix add @user 7d`",
					colors.error
				);
			}

			const durationStr = args[2] || "permanent";
			const res = await NoPrefixManager.add(targetId, durationStr, authorId);

			if (!res.success) {
				return reply(`${emojis.cross} Failed to Add`, res.error || "Database error.", colors.error);
			}

			const expiryText = res.entry?.expiresAt
				? `<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:F> (<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:R>)`
				: "`Permanent`";

			return reply(
				`${emojis.check} No-Prefix Access Granted`,
				`• **User:** <@${targetId}> (\`${targetId}\`)\n` +
				`• **Duration:** ${expiryText}\n` +
				`• **Status:** Active (can execute bot prefix commands without \`${config.settings.bot.prefix}\`)`,
				colors.success
			);
		}

		if (action === "remove" || action === "delete" || action === "revoke") {
			const targetId = resolveTargetId(args[1]);
			if (!targetId) {
				return reply(
					`${emojis.cross} Missing User`,
					"Please mention a user or provide their Discord ID.\nExample: `$noprefix remove @user`",
					colors.error
				);
			}

			const res = await NoPrefixManager.remove(targetId, authorId);
			if (!res.success) {
				return reply(`${emojis.cross} Failed to Remove`, res.error || "Database error.", colors.error);
			}

			return reply(
				`${emojis.check} No-Prefix Access Revoked`,
				`Successfully removed no-prefix privileges from <@${targetId}> (\`${targetId}\`).`,
				colors.success
			);
		}

		return reply(
			`${emojis.cross} Unknown Action`,
			"Available actions: `add`, `remove`, `list`.\nExample: `$noprefix add @user 3d`",
			colors.error
		);
	},
};

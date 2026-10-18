const {
	MessageFlags,
	ButtonStyle,
	StringSelectMenuOptionBuilder,
	SeparatorSpacingSize,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { BlacklistManager, parseDuration } from "@core/security/BlacklistManager";

function resolveTargetId(raw?: string): string | null {
	if (!raw) return null;
	const cleaned = raw.replace(/[<@!>]/g, "").trim();
	if (/^\d{17,20}$/.test(cleaned)) {
		return cleaned;
	}
	return null;
}

export default {
	name: "blacklist",
	aliases: ["bl", "globalblacklist", "gbl"],
	description: "Manage global persistent user and server blacklists (Bot Owner Only).",
	category: "Owner",
	usage: "blacklist <user|server> <add|remove|list> <targetId> [duration] [reason]",
	ownerOnly: true,

	sub_commands: [
		{ name: "user add <target> [duration] [reason]", description: "Blacklist a user globally." },
		{ name: "user remove <target>", description: "Remove a user from global blacklist." },
		{ name: "user list", description: "List all globally blacklisted users." },
		{ name: "server add <guildId> [duration] [reason]", description: "Blacklist a server globally." },
		{ name: "server remove <guildId>", description: "Remove a server from global blacklist." },
		{ name: "server list", description: "List all globally blacklisted servers." },
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
			shield: E.shield || E.mod || "🛡️",
			ban: E.ban || E.error || "🚫",
			check: E.success || "✅",
			info: E.info || "ℹ️",
			time: E.time || E.history || "⏱️",
			server: E.server || "🌐",
			user: E.user || "👤",
		};

		const colors = {
			default: C.default || "#3B82F6",
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
			warning: C.warning || "#F59E0B",
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

		const sub = args[0]?.toLowerCase();

		// Interactive Overview Panel if no args or invalid target
		if (!sub || !["user", "server", "guild", "list"].includes(sub)) {
			const userCount = (await BlacklistManager.listBlacklists("user")).length;
			const guildCount = (await BlacklistManager.listBlacklists("guild")).length;
			const menuId = `bl_menu_${message.id}`;

			const container = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.shield} Global Blacklist System`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`Manage persistent global restrictions across the entire bot platform.\n\n` +
					`• **Active Blacklisted Users:** \`${userCount}\`\n` +
					`• **Active Blacklisted Servers:** \`${guildCount}\`\n\n` +
					`**Command Usage:**\n` +
					`> \`$blacklist user add <@user|id> [duration] [reason]\`\n` +
					`> \`$blacklist user remove <@user|id>\`\n` +
					`> \`$blacklist server add <guildId> [duration] [reason]\`\n` +
					`> \`$blacklist server remove <guildId>\`\n` +
					`> \`$blacklist list\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`-# Durations: 10m, 1h, 1d, 7d, permanent, or ISO date`);

			container.addActionRow((row: any) =>
				row.addStringSelectMenu({
					custom_id: menuId,
					placeholder: "Select Blacklist View...",
					minValues: 1,
					maxValues: 1,
					options: [
						{
							label: "View Blacklisted Users",
							value: "view_users",
							description: `View currently blacklisted users (${userCount} active)`.slice(0, 100),
							emoji: emojis.user,
						},
						{
							label: "View Blacklisted Servers",
							value: "view_servers",
							description: `View currently blacklisted servers (${guildCount} active)`.slice(0, 100),
							emoji: emojis.server,
						},
					],
				})
			);

			const replyMsg = await message.reply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			});

			let currentView = "overview";
			let viewPage = 0;
			const VIEW_PAGE_SIZE = 10;

			const renderViewContainer = async (type: "user" | "guild", page: number) => {
				const entries = await BlacklistManager.listBlacklists(type);
				const totalPages = Math.max(1, Math.ceil(entries.length / VIEW_PAGE_SIZE));
				const safePage = Math.max(0, Math.min(page, totalPages - 1));
				viewPage = safePage;
				const pageEntries = entries.slice(safePage * VIEW_PAGE_SIZE, (safePage + 1) * VIEW_PAGE_SIZE);

				let desc = "";
				if (entries.length === 0) {
					desc = `${emojis.check} No ${type}s are currently blacklisted.`;
				} else {
					desc = pageEntries.map((e, idx) => {
						const num = safePage * VIEW_PAGE_SIZE + idx + 1;
						const exp = e.expiresAt ? `<t:${Math.floor(new Date(e.expiresAt).getTime() / 1000)}:R>` : "`Permanent`";
						const target = type === "user" ? `<@${e.targetId}> (\`${e.targetId}\`)` : `Guild \`${e.targetId}\``;
						return `**${num}.** ${target}\n  > **Reason:** ${e.reason}\n  > **Expires:** ${exp}`;
					}).join("\n\n");
				}

				const title = type === "user"
					? `${emojis.ban} Globally Blacklisted Users (${entries.length}) — Page ${safePage + 1}/${totalPages}`
					: `${emojis.server} Globally Blacklisted Servers (${entries.length}) — Page ${safePage + 1}/${totalPages}`;

				const box = new ContainerBuilder()
					.setAccentColor(colors.default)
					.addTextDisplay(`### ${title}`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(desc)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

				box.addActionRow((row: any) => {
					row.addButton({
						custom_id: `${menuId}:prev:${type}`,
						label: "◀ Previous",
						style: ButtonStyle.Secondary,
						disabled: safePage <= 0,
					});
					row.addButton({
						custom_id: `${menuId}:next:${type}`,
						label: "Next ▶",
						style: ButtonStyle.Secondary,
						disabled: safePage >= totalPages - 1,
					});
					row.addButton({
						custom_id: `${menuId}:back`,
						label: "Back to Menu",
						style: ButtonStyle.Secondary,
					});
					return row;
				});

				return box.build();
			};

			const filter = (i: any) => i.customId.startsWith(menuId) && i.user.id === authorId;
			const collector = replyMsg.createMessageComponentCollector?.({ filter, time: 120_000 });

			collector?.on("collect", async (interaction: any) => {
				const cid = interaction.customId;
				if (cid === menuId) {
					const val = interaction.values?.[0];
					if (val === "view_users") {
						currentView = "user";
						viewPage = 0;
						const box = await renderViewContainer("user", 0);
						await interaction.update({ components: [box], flags: MessageFlags.IsComponentsV2 });
					} else if (val === "view_servers") {
						currentView = "guild";
						viewPage = 0;
						const box = await renderViewContainer("guild", 0);
						await interaction.update({ components: [box], flags: MessageFlags.IsComponentsV2 });
					}
				} else if (cid === `${menuId}:back`) {
					await interaction.update({ components: [container.build()], flags: MessageFlags.IsComponentsV2 });
				} else if (cid.startsWith(`${menuId}:prev:`)) {
					const type = cid.split(":")[2] as "user" | "guild";
					viewPage = Math.max(0, viewPage - 1);
					const box = await renderViewContainer(type, viewPage);
					await interaction.update({ components: [box], flags: MessageFlags.IsComponentsV2 });
				} else if (cid.startsWith(`${menuId}:next:`)) {
					const type = cid.split(":")[2] as "user" | "guild";
					viewPage++;
					const box = await renderViewContainer(type, viewPage);
					await interaction.update({ components: [box], flags: MessageFlags.IsComponentsV2 });
				}
			});

			return;
		}

		if (sub === "list") {
			const users = await BlacklistManager.listBlacklists("user");
			const guilds = await BlacklistManager.listBlacklists("guild");

			if (users.length === 0 && guilds.length === 0) {
				return reply(`${emojis.check} Empty Blacklist`, "There are currently no users or servers blacklisted.", colors.success);
			}

			const userLines = users.length === 0
				? "None"
				: users.slice(0, 10).map((u, i) => {
					const exp = u.expiresAt ? `<t:${Math.floor(new Date(u.expiresAt).getTime() / 1000)}:R>` : "`Permanent`";
					return `• <@${u.targetId}> (\`${u.targetId}\`)\n  > **Reason:** ${u.reason}\n  > **Status:** Active (${exp}) | Added by <@${u.adminId}>`;
				}).join("\n\n");

			const guildLines = guilds.length === 0
				? "None"
				: guilds.slice(0, 10).map((g, i) => {
					const exp = g.expiresAt ? `<t:${Math.floor(new Date(g.expiresAt).getTime() / 1000)}:R>` : "`Permanent`";
					return `• Server \`${g.targetId}\`\n  > **Reason:** ${g.reason}\n  > **Status:** Active (${exp}) | Added by <@${g.adminId}>`;
				}).join("\n\n");

			return reply(
				`${emojis.shield} Active Global Blacklists`,
				`**Blacklisted Users (${users.length}):**\n${userLines}\n\n**Blacklisted Servers (${guilds.length}):**\n${guildLines}` +
				(users.length > 10 || guilds.length > 10 ? `\n\n-# Showing top 10. Use \`$blacklist user list [page]\` or \`$blacklist server list [page]\` for more.` : "")
			);
		}

		const isUserTarget = sub === "user";
		const isGuildTarget = sub === "server" || sub === "guild";

		let action = args[1]?.toLowerCase();
		let targetRaw = args[2];
		let durationArg = args[3];
		let reasonStartIndex = 4;

		// Handle shorthand: `$blacklist user <@target> [duration] [reason]`
		if (action && !["add", "remove", "unblacklist", "list"].includes(action)) {
			targetRaw = args[1];
			action = "add";
			durationArg = args[2];
			reasonStartIndex = 3;
		}

		if (action === "list") {
			const type = isUserTarget ? "user" : "guild";
			const entries = await BlacklistManager.listBlacklists(type);
			if (entries.length === 0) {
				return reply(`${emojis.check} Empty Blacklist`, `No ${type}s are currently blacklisted in database.`, colors.success);
			}

			let safePage = parseInt(args[2], 10) || 1;
			const pageSize = 10;
			const totalPages = Math.max(1, Math.ceil(entries.length / pageSize));
			safePage = Math.max(1, Math.min(safePage, totalPages));

			const buildListPage = (page: number) => {
				const pageItems = entries.slice((page - 1) * pageSize, page * pageSize);
				const text = pageItems.map((e, idx) => {
					const exp = e.expiresAt ? `<t:${Math.floor(new Date(e.expiresAt).getTime() / 1000)}:F> (<t:${Math.floor(new Date(e.expiresAt).getTime() / 1000)}:R>)` : "`Permanent`";
					const target = type === "user" ? `<@${e.targetId}> (\`${e.targetId}\`)` : `Server \`${e.targetId}\``;
					const status = e.expiresAt ? "Temporary" : "Permanent";
					return `**${(page - 1) * pageSize + idx + 1}.** ${target}\n   > **Reason:** ${e.reason}\n   > **Status:** Active (${status})\n   > **Admin:** <@${e.adminId}>\n   > **Expires:** ${exp}`;
				}).join("\n\n");

				const container = new ContainerBuilder()
					.setAccentColor(colors.default)
					.addTextDisplay(`### ${emojis.ban} Blacklisted ${type === "user" ? "Users" : "Servers"} (${entries.length}) — Page ${page}/${totalPages}`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(text);

				if (totalPages > 1) {
					container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
					container.addActionRow((row: any) => {
						row.addButton({
							custom_id: `bl_sub_prev_${message.id}`,
							label: "◀ Previous",
							style: ButtonStyle.Secondary,
							disabled: page <= 1,
						});
						row.addButton({
							custom_id: `bl_sub_next_${message.id}`,
							label: "Next ▶",
							style: ButtonStyle.Secondary,
							disabled: page >= totalPages,
						});
						return row;
					});
				}

				return container.build();
			};

			const listMsg = await message.reply({
				components: [buildListPage(safePage)],
				flags: MessageFlags.IsComponentsV2,
			});

			if (totalPages > 1) {
				const filter = (i: any) => i.customId.startsWith(`bl_sub_`) && i.user.id === authorId;
				const collector = listMsg.createMessageComponentCollector?.({ filter, time: 120_000 });
				collector?.on("collect", async (interaction: any) => {
					if (interaction.customId === `bl_sub_prev_${message.id}`) {
						safePage = Math.max(1, safePage - 1);
					} else if (interaction.customId === `bl_sub_next_${message.id}`) {
						safePage = Math.min(totalPages, safePage + 1);
					}
					await interaction.update({ components: [buildListPage(safePage)], flags: MessageFlags.IsComponentsV2 });
				});
			}

			return;
		}

		const targetId = resolveTargetId(targetRaw);
		if (!targetId) {
			return reply(
				`${emojis.ban} Invalid Target`,
				`Please provide a valid Discord ${isUserTarget ? "user mention or ID" : "guild ID"}.\nExample: \`$blacklist ${sub} add 123456789012345678 1d Spamming\``,
				colors.error
			);
		}

		if (isUserTarget && ownerIds.includes(targetId)) {
			return reply(`${emojis.ban} Action Disallowed`, "You cannot blacklist a bot owner.", colors.error);
		}

		// REMOVE / UNBLACKLIST
		if (action === "remove" || action === "unblacklist") {
			if (isUserTarget) {
				const res = await BlacklistManager.unblacklistUser(targetId, authorId);
				if (!res.success) {
					return reply(`${emojis.ban} Unblacklist Failed`, res.error || "Failed to unblacklist user.", colors.error);
				}
				return reply(
					`${emojis.check} User Unblacklisted`,
					`Successfully removed <@${targetId}> (\`${targetId}\`) from the global blacklist.`,
					colors.success
				);
			} else {
				const res = await BlacklistManager.unblacklistGuild(targetId, authorId);
				if (!res.success) {
					return reply(`${emojis.ban} Unblacklist Failed`, res.error || "Failed to unblacklist server.", colors.error);
				}
				return reply(
					`${emojis.check} Server Unblacklisted`,
					`Successfully removed server \`${targetId}\` from the global blacklist.`,
					colors.success
				);
			}
		}

		// ADD BLACKLIST
		let durationStr: string | null = null;
		let reason = "Violation of bot rules / terms of service";

		// Test if durationArg looks like duration
		const parsedExpiry = parseDuration(durationArg);
		if (parsedExpiry || ["perm", "permanent", "never", "forever", "0"].includes(durationArg?.toLowerCase() || "")) {
			durationStr = durationArg;
			reason = args.slice(reasonStartIndex).join(" ") || reason;
		} else {
			// Duration argument omitted, everything is reason
			reason = args.slice(reasonStartIndex - 1).join(" ") || reason;
		}

		if (isUserTarget) {
			const res = await BlacklistManager.blacklistUser(
				targetId,
				durationStr,
				reason,
				authorId,
				message.client
			);

			if (!res.success) {
				return reply(`${emojis.ban} Blacklist Failed`, res.error || "Database error.", colors.error);
			}

			const expiryText = res.entry?.expiresAt
				? `<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:F> (<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:R>)`
				: "`Permanent`";

			return reply(
				`${emojis.ban} User Blacklisted Globally`,
				`• **Target User:** <@${targetId}> (\`${targetId}\`)\n` +
				`• **Reason:** ${res.entry?.reason}\n` +
				`• **Expires:** ${expiryText}\n` +
				`• **DM Notice:** Sent explanation message to the user.`,
				colors.success
			);
		} else {
			const res = await BlacklistManager.blacklistGuild(
				targetId,
				durationStr,
				reason,
				authorId,
				message.client
			);

			if (!res.success) {
				return reply(`${emojis.ban} Blacklist Failed`, res.error || "Database error.", colors.error);
			}

			const expiryText = res.entry?.expiresAt
				? `<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:F> (<t:${Math.floor(new Date(res.entry.expiresAt).getTime() / 1000)}:R>)`
				: "`Permanent`";

			return reply(
				`${emojis.ban} Server Blacklisted Globally`,
				`• **Server ID:** \`${targetId}\`\n` +
				`• **Reason:** ${res.entry?.reason}\n` +
				`• **Expires:** ${expiryText}\n` +
				`• **DM Notice:** Sent explanation message to the server owner.`,
				colors.success
			);
		}
	},
};

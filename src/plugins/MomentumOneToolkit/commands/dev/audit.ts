const {
	MessageFlags,
	ButtonStyle,
	SeparatorSpacingSize,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import AuditLog, { type AuditLogEntry } from "@core/audit/AuditLog";
import { ErrorTracker, type CommandErrorRecord } from "@core/logging/ErrorTracker";
import { isBotOwner } from "@core/security/SecurityHelpers";

const PAGE_SIZE = 5;

export default {
	name: "audit",
	aliases: ["auditlog", "auditlogs", "logs"],
	description: "Scroll through system audit logs and inspect recorded command errors (Bot Owner Only).",
	category: "Owner",
	usage: "audit [page|filter <action>|view <auditId>|errors [page]|error <errorId>]",
	ownerOnly: true,

	sub_commands: [
		{ name: "list [page]", description: "Scroll through system audit logs." },
		{ name: "filter <action>", description: "Filter audit logs by specific action name." },
		{ name: "view <auditId>", description: "Inspect full details of an audit log entry." },
		{ name: "errors [page]", description: "Scroll through recorded command errors." },
		{ name: "error <errorId>", description: "Inspect detailed error trace and metadata by Error ID." },
	],

	execute: async (ctx: any, commandType: number, message: any, args: string[] = []) => {
		const authorId = message.author?.id || message.user?.id;
		if (!isBotOwner(authorId)) {
			return message.reply({
				content: "❌ **Access Denied**: This command is restricted to bot owners.",
			});
		}

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			audit: E.history || E.info || "📜",
			error: E.error || "❌",
			success: E.success || "✅",
			warning: E.warning || "⚠️",
			time: E.time || "⏱️",
			cmd: E.cmd || "⚡",
			user: E.user || "👤",
			server: E.server || "🌐",
		};

		const colors = {
			default: C.default || "#3B82F6",
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
			warning: C.warning || "#F59E0B",
		};

		const sub = args[0]?.toLowerCase();

		// Subcommand: error <id>
		if (sub === "error") {
			const errorId = args[1]?.trim();
			if (!errorId) {
				return message.reply({ content: "⚠️ Please specify an Error ID (e.g. `ERR-A1B2C3D4`)." });
			}
			const record = await ErrorTracker.get(errorId);
			if (!record) {
				return message.reply({ content: `❌ Error with ID \`${errorId}\` was not found in the database.` });
			}
			const container = buildErrorDetailContainer(record, emojis, colors);
			return message.reply({ components: [container], flags: MessageFlags.IsComponentsV2 });
		}

		// Subcommand: view <auditId>
		if (sub === "view") {
			const auditId = args[1]?.trim();
			if (!auditId) {
				return message.reply({ content: "⚠️ Please specify an Audit ID." });
			}
			const entry = await AuditLog.get(auditId);
			if (!entry) {
				return message.reply({ content: `❌ Audit record \`${auditId}\` was not found.` });
			}
			const container = buildAuditDetailContainer(entry, emojis, colors);
			return message.reply({ components: [container], flags: MessageFlags.IsComponentsV2 });
		}

		// Subcommand: errors [page]
		if (sub === "errors") {
			let page = Number.parseInt(args[1], 10);
			if (Number.isNaN(page) || page < 1) page = 1;
			return handleErrorsPagination(message, authorId, page, emojis, colors);
		}

		// Subcommand: filter <action>
		let filterAction: string | undefined;
		let initialPage = 1;

		if (sub === "filter") {
			filterAction = args[1]?.trim();
			const parsedPage = Number.parseInt(args[2], 10);
			if (!Number.isNaN(parsedPage) && parsedPage >= 1) initialPage = parsedPage;
		} else {
			const parsedPage = Number.parseInt(sub, 10);
			if (!Number.isNaN(parsedPage) && parsedPage >= 1) initialPage = parsedPage;
		}

		return handleAuditPagination(message, authorId, initialPage, filterAction, emojis, colors);
	},
};

function formatUnix(date: Date | string | number): number {
	const ms = new Date(date).getTime();
	return Math.floor(ms / 1000);
}

function buildAuditDetailContainer(entry: AuditLogEntry, emojis: any, colors: any): any {
	const unix = formatUnix(entry.timestamp);
	const statusEmoji = entry.success ? emojis.success : emojis.error;

	let details =
		`• **Audit ID:** \`${entry.auditId}\`\n` +
		`• **Action:** \`${entry.action}\`\n` +
		`• **Status:** ${statusEmoji} ${entry.success ? "Success" : "Failed"}\n` +
		`• **Timestamp:** <t:${unix}:F> (<t:${unix}:R>)\n` +
		`• **Actor:** \`${entry.actorType}\` (${entry.actorId ? `<@${entry.actorId}> (\`${entry.actorId}\`)` : "System"})\n` +
		`• **Resource:** \`${entry.resourceType}\` (${entry.resourceId || "N/A"})\n` +
		`• **Guild ID:** ${entry.guildId ? `\`${entry.guildId}\`` : "N/A"}\n`;

	if (entry.error) {
		details += `• **Error Message:** \`${entry.error}\`\n`;
	}

	if (entry.changedFields && entry.changedFields.length > 0) {
		details += `• **Changed Fields:** \`${entry.changedFields.join("`, `")}\`\n`;
	}

	let stateBlock = "";
	if (entry.newState) {
		const str = JSON.stringify(entry.newState, null, 2);
		stateBlock = `\n**State Payload:**\n\`\`\`json\n${str.slice(0, 800)}\n\`\`\``;
	}

	return new ContainerBuilder()
		.setAccentColor(entry.success ? colors.default : colors.error)
		.addTextDisplay(`### ${emojis.audit} Audit Log Inspector`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
		.addTextDisplay(details + stateBlock)
		.build();
}

function buildErrorDetailContainer(record: CommandErrorRecord, emojis: any, colors: any): any {
	const unix = formatUnix(record.timestamp);
	const userDisplay = record.userId ? `<@${record.userId}> (\`${record.userId}\`)` : "N/A";
	const guildDisplay = record.guildId ? `\`${record.guildId}\`` : "Direct Message / Global";
	const typeDisplay = record.commandType || "UNKNOWN";
	const argsDisplay = record.args && record.args.length > 0 ? `\`${record.args.join(" ")}\`` : "_None_";

	const stackText = record.stack
		? record.stack.slice(0, 1200)
		: record.message || "No stack trace recorded.";

	const desc =
		`• **Error ID:** \`${record.errorId}\`\n` +
		`• **Command:** \`${record.commandName}\` (${typeDisplay})\n` +
		`• **Timestamp:** <t:${unix}:F> (<t:${unix}:R>)\n` +
		`• **Invoker:** ${userDisplay}\n` +
		`• **Guild:** ${guildDisplay}\n` +
		`• **Arguments:** ${argsDisplay}\n` +
		`• **Error Summary:** \`${record.message}\`\n\n` +
		`**Stack Trace:**\n\`\`\`ts\n${stackText}\n\`\`\``;

	return new ContainerBuilder()
		.setAccentColor(colors.error)
		.addTextDisplay(`### ${emojis.error} Command Execution Error`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
		.addTextDisplay(desc)
		.build();
}

async function handleAuditPagination(
	message: any,
	authorId: string,
	initialPage: number,
	filterAction: string | undefined,
	emojis: any,
	colors: any
) {
	let currentPage = initialPage;
	const filter: Record<string, any> = {};
	if (filterAction) {
		filter.action = { $regex: filterAction, $options: "i" };
	}

	async function renderPage(page: number) {
		const totalCount = await AuditLog.count(filter);
		const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
		const safePage = Math.min(Math.max(1, page), totalPages);
		currentPage = safePage;

		const skip = (safePage - 1) * PAGE_SIZE;
		const entries = await AuditLog.list(filter, skip, PAGE_SIZE);

		let contentText = "";
		if (entries.length === 0) {
			contentText = `${emojis.audit} *No audit log records found matching criteria.*`;
		} else {
			contentText = entries
				.map((e, idx) => {
					const num = skip + idx + 1;
					const unix = formatUnix(e.timestamp);
					const icon = e.success ? emojis.success : emojis.error;
					const actorStr = e.actorId ? `<@${e.actorId}>` : `\`${e.actorType}\``;
					const errStr = e.error ? `\n    └ ⚠️ \`${e.error.slice(0, 80)}\`` : "";

					return (
						`**${num}.** ${icon} \`${e.action}\` by ${actorStr} • <t:${unix}:R>\n` +
						`  > **Resource:** \`${e.resourceType}:${e.resourceId || "N/A"}\` | **ID:** \`${e.auditId.slice(0, 8)}...\`${errStr}`
					);
				})
				.join("\n\n");
		}

		const headerText = filterAction
			? `### ${emojis.audit} Audit Log (Filter: \`${filterAction}\`) — Page ${safePage}/${totalPages}`
			: `### ${emojis.audit} System Audit Log — Page ${safePage}/${totalPages}`;

		const container = new ContainerBuilder()
			.setAccentColor(colors.default)
			.addTextDisplay(headerText)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`${contentText}\n\n` +
				`-# Total Events: ${totalCount} • Use select menu below to inspect an entry`
			);

		// Select menu for current page entries
		if (entries.length > 0) {
			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addActionRow((row: any) =>
				row.addStringSelectMenu({
					custom_id: `audit_inspect_${message.id}`,
					placeholder: "Select an audit entry to inspect...",
					minValues: 1,
					maxValues: 1,
					options: entries.slice(0, 25).map((e, idx) => {
						const dateStr = e.timestamp ? new Date(e.timestamp).toISOString().slice(0, 19) : "Unknown date";
						const descStr = `${e.success ? "Success" : "Failed"} | ${dateStr}`.slice(0, 100);
						return {
							label: `${skip + idx + 1}. ${e.action || "Action"}`.slice(0, 100),
							value: `inspect:${e.auditId}`.slice(0, 100),
							description: descStr,
							emoji: e.success ? emojis.success : emojis.error,
						};
					}),
				})
			);
		}

		// Navigation buttons
		container.addActionRow((row: any) => {
			row.addButton({
				custom_id: `audit_prev_${message.id}`,
				label: "◀ Previous",
				style: ButtonStyle.Secondary,
				isDisabled: safePage <= 1,
			});
			row.addButton({
				custom_id: `audit_next_${message.id}`,
				label: "Next ▶",
				style: ButtonStyle.Secondary,
				isDisabled: safePage >= totalPages,
			});
			row.addButton({
				custom_id: `audit_errors_${message.id}`,
				label: "Check Errors",
				style: ButtonStyle.Primary,
				emoji: emojis.error,
			});
			row.addButton({
				custom_id: `audit_refresh_${message.id}`,
				label: "Refresh",
				style: ButtonStyle.Secondary,
			});
			return row;
		});

		return { container: container.build(), totalPages };
	}

	const initial = await renderPage(currentPage);
	const replyMsg = await message.reply({
		components: [initial.container],
		flags: MessageFlags.IsComponentsV2,
	});

	const filterComp = (i: any) =>
		[
			`audit_prev_${message.id}`,
			`audit_next_${message.id}`,
			`audit_errors_${message.id}`,
			`audit_refresh_${message.id}`,
			`audit_inspect_${message.id}`,
		].includes(i.customId) && isBotOwner(i.user.id);

	const collector = replyMsg.createMessageComponentCollector?.({ filter: filterComp, time: 180_000 });

	collector?.on("collect", async (interaction: any) => {
		try {
			if (interaction.customId === `audit_prev_${message.id}`) {
				currentPage = Math.max(1, currentPage - 1);
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `audit_next_${message.id}`) {
				currentPage++;
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `audit_refresh_${message.id}`) {
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `audit_errors_${message.id}`) {
				collector.stop("switched_to_errors");
				await handleErrorsPagination(interaction, authorId, 1, emojis, colors, true);
			} else if (interaction.customId === `audit_inspect_${message.id}`) {
				const val = interaction.values?.[0];
				if (val?.startsWith("inspect:")) {
					const auditId = val.slice("inspect:".length);
					const entry = await AuditLog.get(auditId);
					if (entry) {
						const detailBox = buildAuditDetailContainer(entry, emojis, colors);
						await interaction.reply({
							components: [detailBox],
							flags: MessageFlags.IsComponentsV2,
							ephemeral: true,
						});
					} else {
						await interaction.reply({ content: "Audit entry not found.", ephemeral: true });
					}
				}
			}
		} catch (collectErr) {
			logger.warn("[AuditCommand] Collector error:", collectErr);
		}
	});
}

async function handleErrorsPagination(
	source: any,
	authorId: string,
	initialPage: number,
	emojis: any,
	colors: any,
	isInteraction = false
) {
	let currentPage = initialPage;

	async function renderErrorPage(page: number) {
		const totalCount = await ErrorTracker.count();
		const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
		const safePage = Math.min(Math.max(1, page), totalPages);
		currentPage = safePage;

		const skip = (safePage - 1) * PAGE_SIZE;
		const records = await ErrorTracker.list(skip, PAGE_SIZE);

		let contentText = "";
		if (records.length === 0) {
			contentText = `${emojis.success} **No command errors currently recorded!**`;
		} else {
			contentText = records
				.map((r, idx) => {
					const num = skip + idx + 1;
					const unix = formatUnix(r.timestamp);
					const userStr = r.userId ? `<@${r.userId}>` : "N/A";
					const typeStr = r.commandType ? `[${r.commandType}]` : "";

					return (
						`**${num}.** ${emojis.error} \`${r.errorId}\` — Command: \`${r.commandName}\` ${typeStr} • <t:${unix}:R>\n` +
						`  > **User:** ${userStr} | **Summary:** \`${r.message.slice(0, 90)}\``
					);
				})
				.join("\n\n");
		}

		const container = new ContainerBuilder()
			.setAccentColor(colors.error)
			.addTextDisplay(`### ${emojis.error} Command Error Tracker — Page ${safePage}/${totalPages}`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`${contentText}\n\n` +
				`-# Total Errors: ${totalCount} • Select an error below to inspect full stack trace`
			);

		if (records.length > 0) {
			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addActionRow((row: any) =>
				row.addStringSelectMenu({
					custom_id: `err_inspect_${source.id}`,
					placeholder: "Select an error to inspect stack trace...",
					minValues: 1,
					maxValues: 1,
					options: records.slice(0, 25).map((r, idx) => {
						const desc = (r.message && r.message.trim()) ? r.message.trim().slice(0, 100) : "Execution error";
						return {
							label: `${skip + idx + 1}. ${r.errorId} (${r.commandName})`.slice(0, 100),
							value: `err_inspect:${r.errorId}`.slice(0, 100),
							description: desc,
							emoji: emojis.error,
						};
					}),
				})
			);
		}

		container.addActionRow((row: any) => {
			row.addButton({
				custom_id: `err_prev_${source.id}`,
				label: "◀ Previous",
				style: ButtonStyle.Secondary,
				isDisabled: safePage <= 1,
			});
			row.addButton({
				custom_id: `err_next_${source.id}`,
				label: "Next ▶",
				style: ButtonStyle.Secondary,
				isDisabled: safePage >= totalPages,
			});
			row.addButton({
				custom_id: `err_refresh_${source.id}`,
				label: "Refresh",
				style: ButtonStyle.Secondary,
			});
			return row;
		});

		return { container: container.build(), totalPages };
	}

	const initial = await renderErrorPage(currentPage);
	let replyMsg: any;

	if (isInteraction) {
		replyMsg = await source.update({
			components: [initial.container],
			flags: MessageFlags.IsComponentsV2,
		});
	} else {
		replyMsg = await source.reply({
			components: [initial.container],
			flags: MessageFlags.IsComponentsV2,
		});
	}

	const filterComp = (i: any) =>
		[
			`err_prev_${source.id}`,
			`err_next_${source.id}`,
			`err_refresh_${source.id}`,
			`err_inspect_${source.id}`,
		].includes(i.customId) && isBotOwner(i.user.id);

	const collector = replyMsg?.createMessageComponentCollector?.({ filter: filterComp, time: 180_000 });

	collector?.on("collect", async (interaction: any) => {
		try {
			if (interaction.customId === `err_prev_${source.id}`) {
				currentPage = Math.max(1, currentPage - 1);
				const { container } = await renderErrorPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `err_next_${source.id}`) {
				currentPage++;
				const { container } = await renderErrorPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `err_refresh_${source.id}`) {
				const { container } = await renderErrorPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (interaction.customId === `err_inspect_${source.id}`) {
				const val = interaction.values?.[0];
				if (val?.startsWith("err_inspect:")) {
					const errorId = val.slice("err_inspect:".length);
					const record = await ErrorTracker.get(errorId);
					if (record) {
						const detailBox = buildErrorDetailContainer(record, emojis, colors);
						await interaction.reply({
							components: [detailBox],
							flags: MessageFlags.IsComponentsV2,
							ephemeral: true,
						});
					} else {
						await interaction.reply({ content: "Error record not found.", ephemeral: true });
					}
				}
			}
		} catch (collectErr) {
			logger.warn("[AuditCommand:Errors] Collector error:", collectErr);
		}
	});
}

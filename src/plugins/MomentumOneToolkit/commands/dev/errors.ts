const {
	MessageFlags,
	ButtonStyle,
	SeparatorSpacingSize,
	SlashCommandBuilder,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { ErrorTracker, type CommandErrorRecord } from "@core/logging/ErrorTracker";
import { isBotOwner } from "@core/security/SecurityHelpers";

const PAGE_SIZE = 5;

export default {
	name: "errors",
	aliases: ["error", "err", "errorlogs", "errlog"],
	description: "Check and scroll through command execution errors and stack traces (Bot Owner Only).",
	category: "Owner",
	usage: "errors [page|view <id>|clear]",
	ownerOnly: true,

	sub_commands: [
		{ name: "list [page]", description: "Scroll through command error logs." },
		{ name: "view <errorId>", description: "Inspect full stack trace and metadata for an Error ID." },
		{ name: "clear", description: "Clear stored error logs from the database." },
	],

	builder: new SlashCommandBuilder()
		.setName("errors")
		.setDescription("Inspect command execution errors and stack traces (Bot Owner Only).")
		.addSubcommand((sub: any) =>
			sub
				.setName("list")
				.setDescription("Scroll through recent command error logs")
				.addIntegerOption((opt: any) =>
					opt.setName("page").setDescription("Page number").setRequired(false)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("view")
				.setDescription("Inspect full stack trace and details for an Error ID")
				.addStringOption((opt: any) =>
					opt.setName("id").setDescription("The Error ID (e.g. ERR-12345678)").setRequired(true)
				)
		)
		.addSubcommand((sub: any) =>
			sub
				.setName("clear")
				.setDescription("Clear stored error logs from database")
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const authorId = user?.id;

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			error: E.error || "❌",
			success: E.success || "✅",
			warning: E.warning || "⚠️",
			time: E.pending || E.loading || "⏱️",
			cmd: E.commands || "⚡",
			search: E.search || "🔍",
			user: E.user || "👤",
			reset: E.reset || "🔄",
		};

		const colors = {
			default: C.default || "#0844C5",
			success: C.success || "#3FD438",
			error: C.error || "#B21F1F",
			warning: C.warning || "#B21F1F",
		};

		const sendReply = async (payload: any) => {
			if (isSlash) {
				if (messageOrInteraction.deferred || messageOrInteraction.replied) {
					return messageOrInteraction.editReply(payload);
				}
				return messageOrInteraction.reply({ ...payload, fetchReply: true });
			}
			return messageOrInteraction.reply(payload);
		};

		if (!isBotOwner(authorId)) {
			const denyBox = new ContainerBuilder()
				.setAccentColor(colors.error)
				.addTextDisplay(`### ${emojis.error} Access Restricted`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay("This command is strictly restricted to bot owners.")
				.build();
			return sendReply({ components: [denyBox], flags: MessageFlags.IsComponentsV2, ephemeral: true });
		}

		let sub = args[0]?.toLowerCase();
		let targetErrorId: string | undefined;

		if (isSlash) {
			sub = messageOrInteraction.options.getSubcommand(false) || "list";
			if (sub === "view") {
				targetErrorId = messageOrInteraction.options.getString("id")?.trim();
			} else if (sub === "list") {
				const p = messageOrInteraction.options.getInteger("page");
				if (p && p >= 1) args = ["list", String(p)];
			}
		}

		// Subcommand: clear
		if (sub === "clear") {
			const count = await ErrorTracker.clear();
			const container = new ContainerBuilder()
				.setAccentColor(colors.success)
				.addTextDisplay(`### ${emojis.success} Error Logs Cleared`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(`Successfully cleared **${count}** error log record(s) from the database.`)
				.build();

			return sendReply({ components: [container], flags: MessageFlags.IsComponentsV2 });
		}

		// Subcommand: view <errorId>
		if (!targetErrorId) {
			if (sub === "view" || sub === "get") {
				targetErrorId = args[1]?.trim();
			} else if (sub && (sub.startsWith("err-") || sub.length >= 6) && Number.isNaN(Number(sub))) {
				targetErrorId = sub.trim();
			}
		}

		if (targetErrorId) {
			const record = await ErrorTracker.get(targetErrorId);
			if (!record) {
				const notFoundBox = new ContainerBuilder()
					.setAccentColor(colors.error)
					.addTextDisplay(`### ${emojis.error} Error Record Not Found`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`Error ID \`${targetErrorId}\` was not found in the database.`)
					.build();
				return sendReply({ components: [notFoundBox], flags: MessageFlags.IsComponentsV2, ephemeral: true });
			}

			const detailBox = buildErrorDetailContainer(record, emojis, colors);
			return sendReply({ components: [detailBox], flags: MessageFlags.IsComponentsV2 });
		}

		// Subcommand: list [page]
		let initialPage = 1;
		const parsedPage = Number.parseInt(sub === "list" ? args[1] : sub, 10);
		if (!Number.isNaN(parsedPage) && parsedPage >= 1) {
			initialPage = parsedPage;
		}

		return handleErrorsPagination(messageOrInteraction, isSlash, authorId, initialPage, emojis, colors, sendReply);
	},
};

function formatUnix(date: Date | string | number): number {
	const ms = new Date(date).getTime();
	return Math.floor(ms / 1000);
}

function buildErrorDetailContainer(record: CommandErrorRecord, emojis: any, colors: any): any {
	const unix = formatUnix(record.timestamp);
	const userDisplay = record.userId
		? `${record.username ? `**${record.username}** ` : ""}<@${record.userId}> (\`${record.userId}\`)`
		: "N/A";
	const guildDisplay = record.guildId ? `\`${record.guildId}\`` : "Direct Message / Global";
	const typeDisplay = record.commandType || "UNKNOWN";
	const argsDisplay = record.args && record.args.length > 0 ? `\`${record.args.join(" ")}\`` : "_None_";

	const stackText = record.stack
		? record.stack.slice(0, 1300)
		: record.message || "No stack trace available.";

	const desc =
		`• **Error ID:** \`${record.errorId}\`\n` +
		`• **Command:** \`${record.commandName}\` (${typeDisplay})\n` +
		`• **Timestamp:** <t:${unix}:F> (<t:${unix}:R>)\n` +
		`• **Invoker:** ${userDisplay}\n` +
		`• **Guild ID:** ${guildDisplay}\n` +
		`• **Arguments:** ${argsDisplay}\n` +
		`• **Error Summary:** \`${(record.message || "Execution exception").slice(0, 200)}\`\n\n` +
		`**Stack Trace:**\n\`\`\`ts\n${stackText}\n\`\`\``;

	return new ContainerBuilder()
		.setAccentColor(colors.error)
		.addTextDisplay(`### ${emojis.error} Command Execution Error Inspector`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
		.addTextDisplay(desc)
		.build();
}

async function handleErrorsPagination(
	messageOrInteraction: any,
	isSlash: boolean,
	authorId: string,
	initialPage: number,
	emojis: any,
	colors: any,
	sendReply: (payload: any) => Promise<any>
) {
	let currentPage = initialPage;
	const sessionId = `errs_${authorId}_${Date.now()}`;

	async function renderPage(page: number) {
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
					const summary = (r.message && r.message.trim()) ? r.message.trim().slice(0, 90) : "Execution error";

					return (
						`**${num}.** ${emojis.error} \`${r.errorId}\` — Command: \`${r.commandName}\` ${typeStr} • <t:${unix}:R>\n` +
						`  > **User:** ${userStr} | **Summary:** \`${summary}\``
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
				`-# Total Errors: ${totalCount} • Select an error below or run \`.errors view <id>\` to inspect`
			);

		if (records.length > 0) {
			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			container.addActionRow((row: any) =>
				row.addStringSelectMenu({
					custom_id: `${sessionId}:inspect`,
					placeholder: "Select an error to inspect stack trace...",
					minValues: 1,
					maxValues: 1,
					options: records.slice(0, 25).map((r, idx) => {
						const desc = (r.message && r.message.trim()) ? r.message.trim().slice(0, 100) : "Execution exception";
						return {
							label: `${skip + idx + 1}. ${r.errorId} (${r.commandName})`.slice(0, 100),
							value: `errs_inspect:${r.errorId}`.slice(0, 100),
							description: desc,
							emoji: emojis.error,
						};
					}),
				})
			);
		}

		container.addActionRow((row: any) => {
			row.addButton({
				custom_id: `${sessionId}:prev`,
				label: "◀ Previous",
				style: ButtonStyle.Secondary,
				isDisabled: safePage <= 1,
			});
			row.addButton({
				custom_id: `${sessionId}:next`,
				label: "Next ▶",
				style: ButtonStyle.Secondary,
				isDisabled: safePage >= totalPages,
			});
			row.addButton({
				custom_id: `${sessionId}:refresh`,
				label: "Refresh",
				emoji: emojis.reset,
				style: ButtonStyle.Secondary,
			});
			return row;
		});

		return { container: container.build(), totalPages };
	}

	const initial = await renderPage(currentPage);
	const replyMsg = await sendReply({
		components: [initial.container],
		flags: MessageFlags.IsComponentsV2,
	});

	if (!replyMsg?.createMessageComponentCollector) return;

	const collector = replyMsg.createMessageComponentCollector({
		time: 180_000,
		filter: (i: any) => i.customId.startsWith(`${sessionId}:`) && isBotOwner(i.user.id),
	});

	collector.on("collect", async (interaction: any) => {
		try {
			if (!isBotOwner(interaction.user.id)) {
				return interaction.reply({ content: "❌ Unauthorized.", ephemeral: true });
			}

			const parts = interaction.customId.split(":");
			const action = parts[parts.length - 1];

			if (action === "prev") {
				currentPage = Math.max(1, currentPage - 1);
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (action === "next") {
				currentPage++;
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (action === "refresh") {
				const { container } = await renderPage(currentPage);
				await interaction.update({ components: [container], flags: MessageFlags.IsComponentsV2 });
			} else if (action === "inspect") {
				const val = interaction.values?.[0];
				if (val?.startsWith("errs_inspect:")) {
					const errorId = val.slice("errs_inspect:".length);
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
			logger.warn("[ErrorsCommand] Collector error:", collectErr);
		}
	});
}

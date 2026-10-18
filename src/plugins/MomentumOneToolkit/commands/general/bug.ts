const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ModalBuilder,
	TextInputBuilder,
	TextInputStyle,
	ActionRowBuilder: DiscordActionRowBuilder,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import DatabaseManager from "@database/Database";
import { isBotOwner } from "@core/security/SecurityHelpers";
import { randomBytes } from "node:crypto";

export interface BugReportRecord {
	bugId: string;
	userId: string;
	username: string;
	guildId?: string;
	guildName?: string;
	title: string;
	description: string;
	status: "open" | "investigating" | "resolved" | "closed";
	createdAt: Date;
}

export default {
	name: "bug",
	aliases: ["report", "bugreport"],
	description: "Report a bug or unexpected issue directly to the bot development team.",
	category: "Utility",
	usage: "bug [summary | list | view <id>]",
	cooldown: 5000,

	builder: new SlashCommandBuilder()
		.setName("bug")
		.setDescription("Report a bug or unexpected issue to the development team.")
		.addStringOption((opt: any) =>
			opt
				.setName("summary")
				.setDescription("Brief summary of the bug or issue")
				.setRequired(false)
		)
		.addStringOption((opt: any) =>
			opt
				.setName("details")
				.setDescription("Detailed steps to reproduce or behavior observed")
				.setRequired(false)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const guild = messageOrInteraction.guild;
		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			bug: E.bug || "🐛",
			success: E.success || "✅",
			error: E.error || "❌",
			info: E.info || "ℹ️",
			time: E.clock || "⏱️",
		};

		const colors = {
			default: C.default || "#FF7B00",
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
		};

		const reply = async (container: any, ephemeral = false) => {
			const payload = {
				components: [container],
				flags: MessageFlags.IsComponentsV2,
				ephemeral,
			};
			if (isSlash) {
				if (messageOrInteraction.deferred || messageOrInteraction.replied) {
					return messageOrInteraction.editReply(payload);
				}
				return messageOrInteraction.reply(payload);
			}
			return messageOrInteraction.reply(payload);
		};

		const sub = args[0]?.toLowerCase();

		// Owner inspection subcommands: $bug list & $bug view <id>
		if (sub === "list" && isBotOwner(user.id)) {
			const col = await DatabaseManager.collection("bug_reports");
			const reports: BugReportRecord[] = await col.find({}).sort({ createdAt: -1 }).limit(10).toArray();

			let listText = "*No bug reports recorded yet.*";
			if (reports.length > 0) {
				listText = reports
					.map(
						(r, i) =>
							`**${i + 1}.** \`${r.bugId}\` — **${r.title.slice(0, 50)}**\n` +
							`  > By: <@${r.userId}> | Status: \`${r.status}\` | <t:${Math.floor(new Date(r.createdAt).getTime() / 1000)}:R>`
					)
					.join("\n\n");
			}

			const box = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.bug} Recent Bug Reports`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(listText)
				.build();

			return reply(box, true);
		}

		if (sub === "view" && isBotOwner(user.id)) {
			const targetId = args[1]?.trim()?.toUpperCase();
			if (!targetId) {
				const box = new ContainerBuilder()
					.setAccentColor(colors.error)
					.addTextDisplay(`### ${emojis.error} Missing Bug ID`)
					.addTextDisplay("Usage: `$bug view <BUG-ID>`")
					.build();
				return reply(box, true);
			}

			const col = await DatabaseManager.collection("bug_reports");
			const r: BugReportRecord | null = await col.findOne({ bugId: targetId });
			if (!r) {
				const box = new ContainerBuilder()
					.setAccentColor(colors.error)
					.addTextDisplay(`### ${emojis.error} Bug Report Not Found`)
					.addTextDisplay(`Could not find bug report \`${targetId}\`.`)
					.build();
				return reply(box, true);
			}

			const box = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.bug} Bug Report: \`${r.bugId}\``)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`• **Title:** ${r.title}\n` +
					`• **Reporter:** <@${r.userId}> (\`${r.username}\`)\n` +
					`• **Guild:** ${r.guildName || "Direct Message"} (\`${r.guildId || "N/A"}\`)\n` +
					`• **Status:** \`${r.status}\`\n` +
					`• **Submitted:** <t:${Math.floor(new Date(r.createdAt).getTime() / 1000)}:F>\n\n` +
					`**Details:**\n> ${r.description.replace(/\n/g, "\n> ")}`
				)
				.build();

			return reply(box, true);
		}

		// User submission via slash options or text args
		let summary = "";
		let details = "";

		if (isSlash) {
			summary = messageOrInteraction.options.getString("summary")?.trim() || "";
			details = messageOrInteraction.options.getString("details")?.trim() || "";
		} else {
			if (args.length > 0) {
				summary = args.join(" ").trim();
				details = "Provided via command arguments.";
			}
		}

		// If no summary was provided, show modal or helpful prompt
		if (!summary) {
			if (isSlash && typeof messageOrInteraction.showModal === "function") {
				const modalId = `bug_modal_${user.id}_${Date.now()}`;
				const modal = new ModalBuilder()
					.setCustomId(modalId)
					.setTitle("Submit a Bug Report");

				const titleInput = new TextInputBuilder()
					.setCustomId("title")
					.setLabel("Bug Summary")
					.setPlaceholder("What is the issue you encountered?")
					.setStyle(TextInputStyle.Short)
					.setRequired(true)
					.setMaxLength(100);

				const detailsInput = new TextInputBuilder()
					.setCustomId("details")
					.setLabel("Steps to Reproduce / Details")
					.setPlaceholder("Explain what happened and what command you were using...")
					.setStyle(TextInputStyle.Paragraph)
					.setRequired(true)
					.setMaxLength(1000);

				modal.addComponents(
					new DiscordActionRowBuilder().addComponents(titleInput),
					new DiscordActionRowBuilder().addComponents(detailsInput)
				);

				await messageOrInteraction.showModal(modal);

				// Await modal submission
				try {
					const submission = await messageOrInteraction.awaitModalSubmit({
						filter: (i: any) => i.customId === modalId && i.user.id === user.id,
						time: 180_000,
					});

					const modalSummary = submission.fields.getTextInputValue("title").trim();
					const modalDetails = submission.fields.getTextInputValue("details").trim();

					const bugId = `BUG-${randomBytes(4).toString("hex").toUpperCase()}`;
					const record: BugReportRecord = {
						bugId,
						userId: user.id,
						username: user.tag || user.username,
						guildId: guild?.id,
						guildName: guild?.name,
						title: modalSummary,
						description: modalDetails,
						status: "open",
						createdAt: new Date(),
					};

					const col = await DatabaseManager.collection("bug_reports");
					await col.insertOne(record);

					const conf = new ContainerBuilder()
						.setAccentColor(colors.success)
						.addTextDisplay(`### ${emojis.success} Bug Report Submitted`)
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(
							`Thank you for reporting this issue!\n\n` +
							`• **Bug ID:** \`${bugId}\`\n` +
							`• **Summary:** ${modalSummary}\n` +
							`• **Status:** \`Under Review\`\n\n` +
							`Our development team has been alerted.`
						)
						.build();

					return submission.reply({
						components: [conf],
						flags: MessageFlags.IsComponentsV2,
						ephemeral: true,
					});
				} catch {
					return;
				}
			}

			// Prefix usage instructions
			const guideBox = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.bug} Report a Bug`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`Please describe the problem you experienced.\n\n` +
					`**Usage:**\n` +
					`> \`$bug <describe what went wrong>\`\n` +
					`> \`/bug summary:... details:...\`\n\n` +
					`Example: \`$bug Withdrawal button returned session expired on second page\``
				)
				.build();

			return reply(guideBox);
		}

		// Save direct bug report
		const bugId = `BUG-${randomBytes(4).toString("hex").toUpperCase()}`;
		const record: BugReportRecord = {
			bugId,
			userId: user.id,
			username: user.tag || user.username,
			guildId: guild?.id,
			guildName: guild?.name,
			title: summary.slice(0, 100),
			description: details || summary,
			status: "open",
			createdAt: new Date(),
		};

		const col = await DatabaseManager.collection("bug_reports");
		await col.insertOne(record);

		logger.info(`[BugReport] Recorded bug ${bugId} by user ${user.id} (${record.title})`);

		const conf = new ContainerBuilder()
			.setAccentColor(colors.success)
			.addTextDisplay(`### ${emojis.success} Bug Report Submitted`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`Thank you for your report! Our team will look into this issue.\n\n` +
				`• **Bug ID:** \`${bugId}\`\n` +
				`• **Summary:** ${record.title}\n` +
				`• **Status:** \`Under Review\`\n\n` +
				`-# Keep this Bug ID for reference.`
			)
			.build();

		return reply(conf);
	},
};

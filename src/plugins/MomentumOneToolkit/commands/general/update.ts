const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import {
	CHANGELOG_RELEASES,
	type ChangelogRelease,
	getLatestRelease,
	getPreviousRelease,
} from "@config/Changelog";

function buildReleaseContainer(
	release: ChangelogRelease,
	colors: any,
	emojis: any,
	isLatest: boolean
): ContainerBuilder {
	const container = new ContainerBuilder()
		.setAccentColor(colors.default || "#3b82f6")
		.addTextDisplay(`### ${"🚀"} Release Notes — v${release.version}: ${release.title}`)
		.addTextDisplay(
			`**Published Version:** \`v${release.version}\` ${isLatest ? "⭐ *(Latest Release)*" : "*(Historical Release)*"}\n` +
			`**Release Date:** \`${release.releaseDate}\`\n\n` +
			`${release.summary}`
		)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	if (release.features?.length) {
		const featureLines = release.features.map((f) => `- ${f}`).join("\n");
		container.addTextDisplay(`✨ **New Features & Capabilities:**\n${featureLines}`);
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	}

	if (release.improvements?.length) {
		const impLines = release.improvements.map((imp) => `- ${imp}`).join("\n");
		container.addTextDisplay(`📈 **Improvements & Performance:**\n${impLines}`);
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	}

	if (release.bugFixes?.length) {
		const bugLines = release.bugFixes.map((b) => `- ${b}`).join("\n");
		container.addTextDisplay(`🛠️ **Bug Fixes & Stability:**\n${bugLines}`);
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	}

	if (release.notices?.length) {
		const noticeLines = release.notices.map((n) => `- ${n}`).join("\n");
		container.addTextDisplay(`📢 **Important Notices:**\n${noticeLines}`);
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	}

	if (isLatest) {
		container.addTextDisplay(
			"-# ℹ️ You are viewing the latest release notes. No newer updates are currently published."
		);
	} else {
		container.addTextDisplay(
			"-# ℹ️ You are viewing an archived release. Use the buttons below to switch versions."
		);
	}

	return container;
}

function buildReleaseButtons(
	prefix: string,
	currentIndex: number,
	totalCount: number
): ActionRowBuilder[] {
	const row = new ActionRowBuilder();

	row.addButton({
		custom_id: `${prefix}:ver:0`,
		label: "Latest (v26.7.20)",
		style: currentIndex === 0 ? ButtonStyle.Primary : ButtonStyle.Secondary,
		disabled: currentIndex === 0,
	});

	if (totalCount > 1) {
		row.addButton({
			custom_id: `${prefix}:ver:1`,
			label: "Previous (v26.6.0)",
			style: currentIndex === 1 ? ButtonStyle.Primary : ButtonStyle.Secondary,
			disabled: currentIndex === 1,
		});
	}

	return [row];
}

export default {
	name: "update",
	aliases: ["updates", "changelog", "whatsnew", "release", "patchnotes"],
	description: "View what has changed in the latest bot release and update notes.",
	category: "General",
	usage: "update [version]",
	cooldown: 20*1000,

	builder: new SlashCommandBuilder()
		.setName("update")
		.setDescription("View what has changed in the latest bot release.")
		.addStringOption((opt: any) =>
			opt
				.setName("version")
				.setDescription("Optional specific version to inspect (e.g. 26.7.20 or 26.6.0)")
				.setRequired(false)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const C = config.Colors || {};
		const E = config.Emojis || {};

		const requestedVersion = isSlash
			? messageOrInteraction.options.getString("version")?.trim()
			: args[0]?.trim();

		let currentIndex = 0;
		if (requestedVersion) {
			const foundIdx = CHANGELOG_RELEASES.findIndex(
				(r) => r.version.toLowerCase() === requestedVersion.toLowerCase().replace(/^v/, "")
			);
			if (foundIdx !== -1) {
				currentIndex = foundIdx;
			}
		}

		const totalReleases = CHANGELOG_RELEASES.length;
		const actionPrefix = `upd_${user.id}_${Date.now()}`;

		const currentRelease = CHANGELOG_RELEASES[currentIndex] || getLatestRelease();
		const container = buildReleaseContainer(currentRelease, C, E, currentIndex === 0);
		const buttons = buildReleaseButtons(actionPrefix, currentIndex, totalReleases);

		const payload = {
			components: [container, ...buttons],
			flags: MessageFlags.IsComponentsV2,
		};

		const sent = isSlash
			? await messageOrInteraction.editReply({ ...payload, fetchReply: true })
			: await messageOrInteraction.reply(payload);

		if (!sent?.createMessageComponentCollector) return;

		const collector = sent.createMessageComponentCollector({
			time: 120_000,
			filter: (i: any) => i.customId.startsWith(`${actionPrefix}:`),
		});

		collector.on("collect", async (interaction: any) => {
			try {
				if (interaction.user.id !== user.id) {
					return interaction.reply({
						content: "Open your own release notes using `.update`.",
						ephemeral: true,
					});
				}

				const parts = interaction.customId.split(":");
				if (parts[1] === "ver") {
					const targetIdx = parseInt(parts[2], 10);
					if (!isNaN(targetIdx) && targetIdx >= 0 && targetIdx < totalReleases) {
						currentIndex = targetIdx;
						const release = CHANGELOG_RELEASES[currentIndex];
						const newContainer = buildReleaseContainer(release, C, E, currentIndex === 0);
						const newButtons = buildReleaseButtons(actionPrefix, currentIndex, totalReleases);

						await interaction.update({
							components: [newContainer, ...newButtons],
							flags: MessageFlags.IsComponentsV2,
						});
					}
				}
			} catch (err) {
				logger.error("[UpdateCommand] Collector error:", err);
			}
		});

		collector.on("end", async () => {
			try {
				const release = CHANGELOG_RELEASES[currentIndex];
				const disabledContainer = buildReleaseContainer(release, C, E, currentIndex === 0);
				const disabledRow = new ActionRowBuilder();
				disabledRow.addButton({
					custom_id: `${actionPrefix}:disabled_latest`,
					label: "Latest (v26.7.20)",
					style: ButtonStyle.Secondary,
					disabled: true,
				});
				if (totalReleases > 1) {
					disabledRow.addButton({
						custom_id: `${actionPrefix}:disabled_prev`,
						label: "Previous (v26.6.0)",
						style: ButtonStyle.Secondary,
						disabled: true,
					});
				}

				await sent.edit({
					components: [disabledContainer, disabledRow],
					flags: MessageFlags.IsComponentsV2,
				}).catch(() => null);
			} catch {}
		});
	},
};

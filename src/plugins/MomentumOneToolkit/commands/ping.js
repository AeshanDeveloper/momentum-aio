const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
} = require("discord.js");

const { CommandType, ContainerBuilder } = require("@sdk/discord");

import config from "@config";
import db from "@database/Database";

export default {
	name: "ping",
	aliases: ["latency", "pong"],
	description: "Check bot connectivity, gateway latency, and database responsiveness.",
	category: "Utility",
	usage: "ping",
	cooldown: 3000,

	builder: new SlashCommandBuilder()
		.setName("ping")
		.setDescription("Check bot connectivity, gateway latency, and database responsiveness."),

	execute: async (ctx, commandType, message, args) => {
		const isSlash = commandType === CommandType.SLASH;
		const E = config.Emojis || config.emojis || {};
		const colors = config.Colors || config.colors || {};

		const onlineIcon = E.online || E.success || "🟢";
		const pingIcon = E.ping || E.latency || "📡";
		const wsIcon = E.latency || "⚡";
		const dbIcon = E.database || "💾";

		const client = isSlash ? message.client : (ctx?.client || message.client);
		const start = Date.now();

		// Measure real database ping
		let dbLatencyMs = null;
		try {
			const dbStart = Date.now();
			await db.ping();
			dbLatencyMs = Date.now() - dbStart;
		} catch {
			dbLatencyMs = null;
		}

		// Initial response measurement
		if (isSlash) {
			const roundtrip = Date.now() - start;
			const wsPing = typeof client?.ws?.ping === "number" && client.ws.ping >= 0 ? `${client.ws.ping}ms` : "Connecting...";
			const dbPingStr = dbLatencyMs !== null ? `${dbLatencyMs}ms` : "Unavailable";

			const container = new ContainerBuilder()
				.setAccentColor(colors.default || "#FF7B00")
				.addTextDisplay(`### ${pingIcon} Bot Connectivity Status`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`• **Status:** ${onlineIcon} \`Online\`\n` +
					`• **Interaction Roundtrip:** \`${roundtrip}ms\`\n` +
					`• **Gateway Heartbeat:** ${wsIcon} \`${wsPing}\`\n` +
					`• **Database Response:** ${dbIcon} \`${dbPingStr}\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay("-# Metrics represent live cluster & socket health.")
				.build();

			if (message.deferred || message.replied) {
				return message.editReply({
					flags: MessageFlags.IsComponentsV2,
					components: [container],
				});
			}

			return message.reply({
				flags: MessageFlags.IsComponentsV2,
				components: [container],
			});
		}

		// Prefix execution flow
		const sent = await message.reply({
			flags: MessageFlags.IsComponentsV2,
			components: [
				new ContainerBuilder()
					.setAccentColor(colors.default || "#FF7B00")
					.addTextDisplay(`### ${pingIcon} Measuring Latency...`)
					.build(),
			],
		});

		const roundtrip = Date.now() - start;
		const wsPing = typeof client?.ws?.ping === "number" && client.ws.ping >= 0 ? `${client.ws.ping}ms` : "Connecting...";
		const dbPingStr = dbLatencyMs !== null ? `${dbLatencyMs}ms` : "Unavailable";

		const finalContainer = new ContainerBuilder()
			.setAccentColor(colors.default || "#FF7B00")
			.addTextDisplay(`### ${pingIcon} Bot Connectivity Status`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`• **Status:** ${onlineIcon} \`Online\`\n` +
				`• **Message Roundtrip:** \`${roundtrip}ms\`\n` +
				`• **Gateway Heartbeat:** ${wsIcon} \`${wsPing}\`\n` +
				`• **Database Response:** ${dbIcon} \`${dbPingStr}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay("-# Metrics represent live cluster & socket health.")
			.build();

		return sent.edit({
			flags: MessageFlags.IsComponentsV2,
			components: [finalContainer],
		});
	},
};
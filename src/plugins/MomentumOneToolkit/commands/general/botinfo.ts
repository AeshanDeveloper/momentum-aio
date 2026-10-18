const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";

export default {
	name: "botinfo",
	aliases: ["info", "about", "stats"],
	description: "View statistics, technical specifications, and system status of the bot.",
	category: "General",
	usage: "botinfo",
	cooldown: 8*1000,

	builder: new SlashCommandBuilder()
		.setName("botinfo")
		.setDescription("View technical specifications and status of the bot."),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[]) => {
		const isSlash = commandType === CommandType.SLASH;
		const client = messageOrInteraction.client;
		const E = config.Emojis || {};
		const C = config.Colors || {};

		const botName = config.settings?.bot?.name || client?.user?.username || "Bot";
		const botPrefix = config.settings?.bot?.prefix || ".";
		const wsPing = client?.ws?.ping ?? -1;
		const uptimeSec = Math.floor(process.uptime());
		const days = Math.floor(uptimeSec / 86400);
		const hours = Math.floor((uptimeSec % 86400) / 3600);
		const minutes = Math.floor((uptimeSec % 3600) / 60);
		const seconds = uptimeSec % 60;
		const uptimeFormatted = `${days}d ${hours}h ${minutes}m ${seconds}s`;

		const memoryUsage = process.memoryUsage();
		const heapUsedMB = (memoryUsage.heapUsed / 1024 / 1024).toFixed(1);
		const heapTotalMB = (memoryUsage.heapTotal / 1024 / 1024).toFixed(1);
		const rssMB = (memoryUsage.rss / 1024 / 1024).toFixed(1);

		const guildCount = client?.guilds?.cache?.size ?? 1;
		const userCount = client?.users?.cache?.size ?? 0;

		const container = new ContainerBuilder()
			.setAccentColor(C.default || "#3b82f6")
			.addTextDisplay(`### ${config.Emojis.bot || config.Emojis.info} ${botName} — System Information`)
			.addTextDisplay(
				config.settings?.bot?.description ||
				`Enterprise-grade Discord automation and modular platform.`
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`**Bot & Host Status**\n` +
				`• **Prefix:** \`${botPrefix}\` • **Slash Invocation:** \`Supported\`\n` +
				`• **WebSocket Latency:** \`${wsPing}ms\`\n` +
				`• **Process Uptime:** \`${uptimeFormatted}\`\n` +
				`• **Node Version:** \`${process.version}\`\n` +
				`• **Platform:** \`${process.platform} (${process.arch})\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`**Memory & Cache**\n` +
				`• **Heap Used:** \`${heapUsedMB} MB / ${heapTotalMB} MB\`\n` +
				`• **RSS Allocated:** \`${rssMB} MB\`\n` +
				`• **Connected Guilds:** \`${guildCount}\`\n` +
				`• **Cached Users:** \`${userCount}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`-# ${botName} | Maintained by ${config.settings.bot.team.name || "@4ever.io"}`)
			.build();

		const payload = { components: [container], flags: MessageFlags.IsComponentsV2 };
		return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
	},
};

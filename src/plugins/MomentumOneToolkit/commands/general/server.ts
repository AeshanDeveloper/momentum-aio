const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ChannelType,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";

export default {
	name: "server",
	aliases: ["serverinfo", "guild"],
	description: "View detailed statistics and information about the server.",
	category: "General",
	usage: "server",
	cooldown: 8*1000,

	builder: new SlashCommandBuilder()
		.setName("server")
		.setDescription("View statistics and information about this Discord server."),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[]) => {
		const isSlash = commandType === CommandType.SLASH;
		const guild = messageOrInteraction.guild;

		if (!guild) {
			const text = `${config.Emojis.no_access || config.Emojis.disabled || config.Emojis.error || ""} This command can only be used inside a server.`;
			return isSlash
				? messageOrInteraction.editReply({ content: text })
				: messageOrInteraction.reply(text);
		}

		const E = config.Emojis || {};
		const C = config.Colors || {};

		const createdSec = guild.createdAt instanceof Date ? Math.floor(guild.createdAt.getTime() / 1000) : Math.floor(Date.now() / 1000);
		const members = guild.memberCount || 1;
		const rolesCount = guild.roles?.cache?.size || 1;
		let textChannels = 0;
		let voiceChannels = 0;
		if (guild.channels?.cache) {
			for (const ch of guild.channels.cache.values()) {
				if (ch?.type === ChannelType.GuildText) textChannels++;
				if (ch?.type === ChannelType.GuildVoice) voiceChannels++;
			}
		}
		const boostLevel = guild.premiumTier || 0;
		const boostCount = guild.premiumSubscriptionCount || 0;

		const container = new ContainerBuilder()
			.setAccentColor(C.default || "#3b82f6")
			.addTextDisplay(`### ${config.Emojis.server || ""} Server Information: ${guild.name}`)
			.addTextDisplay(guild.description || `Welcome to **${guild.name}**!`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`**General**\n` +
				`• **Server ID:** \`${guild.id}\`\n` +
				`• **Owner:** <@${guild.ownerId}>\n` +
				`• **Created:** <t:${createdSec}:f> (<t:${createdSec}:R>)\n` +
				`• **Verification Level:** \`${guild.verificationLevel}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`**Members & Channels**\n` +
				`• **Total Members:** \`${members.toLocaleString()}\`\n` +
				`• **Roles:** \`${rolesCount}\`\n` +
				`• **Text Channels:** \`${textChannels}\` • **Voice Channels:** \`${voiceChannels}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`**Server Boost Status**\n` +
				`• **Boost Level:** \`Tier ${boostLevel}\`\n` +
				`• **Total Boosts:** \`${boostCount}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`-# ${guild.name} • Server Overview`)
			.build();

		const payload = { components: [container], flags: MessageFlags.IsComponentsV2 };
		return isSlash ? messageOrInteraction.editReply(payload) : messageOrInteraction.reply(payload);
	},
};

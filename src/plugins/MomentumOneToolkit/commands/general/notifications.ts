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
import DatabaseManager from "@database/Database";

export default {
	name: "notifications",
	aliases: ["notifs", "dmnotifs", "notify"],
	description: "Configure your DM delivery preferences for transactions and payouts.",
	category: "Utility",
	usage: "notifications [enable|disable|toggle]",
	cooldown: 3000,

	builder: new SlashCommandBuilder()
		.setName("notifications")
		.setDescription("Configure direct message notifications for transactions and payouts.")
		.addStringOption((opt: any) =>
			opt
				.setName("status")
				.setDescription("Enable or disable transaction DM alerts")
				.setRequired(false)
				.addChoices(
					{ name: "Enable Alerts", value: "enable" },
					{ name: "Disable Alerts", value: "disable" },
					{ name: "Toggle", value: "toggle" }
				)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			notif: E.notification || "🔔",
			success: E.success || "✅",
			enabled: E.enabled || "🟢",
			disabled: E.disabled || "🔴",
		};

		const colors = {
			default: C.default || "#FF7B00",
			success: C.success || "#10B981",
		};

		const col = await DatabaseManager.collection("user_notification_prefs");
		let pref = await col.findOne({ userId: user.id });

		let currentStatus = pref?.dmsEnabled !== false;

		const sub = isSlash
			? messageOrInteraction.options.getString("status")?.toLowerCase()
			: args[0]?.toLowerCase();

		let updated = false;
		if (sub === "enable" || sub === "on" || sub === "true") {
			currentStatus = true;
			updated = true;
		} else if (sub === "disable" || sub === "off" || sub === "false") {
			currentStatus = false;
			updated = true;
		} else if (sub === "toggle") {
			currentStatus = !currentStatus;
			updated = true;
		}

		if (updated) {
			await col.updateOne(
				{ userId: user.id },
				{ $set: { userId: user.id, dmsEnabled: currentStatus, updatedAt: new Date() } },
				{ upsert: true }
			);
		}

		const statusIcon = currentStatus ? emojis.enabled : emojis.disabled;
		const statusText = currentStatus ? "Enabled" : "Disabled";

		const container = new ContainerBuilder()
			.setAccentColor(currentStatus ? colors.success : colors.default)
			.addTextDisplay(`### ${emojis.notif} Transaction Notifications`)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(
				`• **DM Delivery Status:** ${statusIcon} \`${statusText}\`\n\n` +
				(currentStatus
					? "You will receive direct messages when withdrawal payouts and staff distributions are processed."
					: "Transaction DM alerts are muted. You will not receive private messages from the bot.")
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay("-# Use `$notifications toggle` or `/notifications status:Toggle` to change preferences.")
			.build();

		const payload = {
			components: [container],
			flags: MessageFlags.IsComponentsV2,
		};

		if (isSlash) {
			if (messageOrInteraction.deferred || messageOrInteraction.replied) {
				return messageOrInteraction.editReply(payload);
			}
			return messageOrInteraction.reply(payload);
		}

		return messageOrInteraction.reply(payload);
	},
};

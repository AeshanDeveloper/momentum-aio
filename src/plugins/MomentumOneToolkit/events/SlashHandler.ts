import logger from "@logger";
import { checkPermissions } from "@shared/helpers/index.ts";
import { CommandStatus, RegisteredBy, CommandType } from "../../../shared/types/CommandRecord";
import { MessageFlags, SeparatorSpacingSize } from "discord.js";
import { ContainerBuilder } from "@sdk/discord";
import config from "@config";
import { BlacklistManager } from "@core/security/BlacklistManager";
import { AntiSpamService } from "@core/security/AntiSpamService";
import { CooldownManager } from "@core/security/CooldownManager";
import { ErrorTracker } from "@core/logging/ErrorTracker";
import { ServerCommandManager } from "@core/security/ServerCommandManager";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

module.exports = {
	name: "interactionCreate",
	description: "Official Slash command handler",
	execute: async (ctx, interaction) => {
		try {
			if (interaction.isStringSelectMenu()) return;
			if (!interaction.isChatInputCommand()) return;

			// Central Global Blacklist check: User
			const userBl = await BlacklistManager.isUserBlacklisted(interaction.user.id);
			if (userBl.blacklisted) {
				const container = new ContainerBuilder()
					.setAccentColor(config.Colors?.error || "#EF4444")
					.addTextDisplay("### 🚫 Access Restricted")
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`**You are globally blacklisted from using the bot.**\n• **Reason:** ${userBl.entry?.reason || "Violation of rules"}`)
					.build();
				return interaction.reply({ components: [container], flags: MessageFlags.IsComponentsV2, ephemeral: true });
			}

			// Central Global Blacklist check: Guild
			if (interaction.guildId) {
				const guildBl = await BlacklistManager.isGuildBlacklisted(interaction.guildId);
				if (guildBl.blacklisted) {
					const container = new ContainerBuilder()
						.setAccentColor(config.Colors?.error || "#EF4444")
						.addTextDisplay("### 🚫 Server Restricted")
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(`**This server is blacklisted from using the bot.**\n• **Reason:** ${guildBl.entry?.reason || "Server blacklisted"}`)
						.build();
					return interaction.reply({ components: [container], flags: MessageFlags.IsComponentsV2, ephemeral: true });
				}
			}

			// Anti-Spam Check: rolling 30s window
			const spamResult = await AntiSpamService.check(interaction.user.id, interaction.client);
			if (!spamResult.allowed) {
				const container = new ContainerBuilder()
					.setAccentColor(config.Colors?.error || "#EF4444")
					.addTextDisplay("### 🚫 Command Rejected")
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`**You have been temporarily blacklisted for excessive command spam.**\n${spamResult.reason || ""}`)
					.build();
				return interaction.reply({ components: [container], flags: MessageFlags.IsComponentsV2, ephemeral: true });
			}
				
			const commandName = interaction.commandName;
			let foundCommand: any = null;
			for (const [, command] of global.commands) {
				const isEnabled =
					typeof command.enabled === "boolean"
						? command.enabled
						: String(command.enabled).toLowerCase() === "true";

				if (
					command.status !== CommandStatus.ACTIVE ||
					!isEnabled
				) {
					continue;
				}
	
				if (
					command.type !== CommandType.SLASH &&
					command.type !== CommandType.HYBRID
				) {
					continue;
				}
	
				if (
					command.name?.toLowerCase() ===
					commandName.toLowerCase()
				) {
					foundCommand = command;
					break;
				}
			}
                
			if (!foundCommand) return;

			const isOwnerOnly =
				Boolean(foundCommand.command?.ownerOnly) ||
				Boolean(foundCommand.command?.ownersOnly) ||
				["dev", "owner"].includes(foundCommand.command?.category?.toLowerCase());

			const sendReply = interaction.reply?.bind(interaction) || interaction.editReply?.bind(interaction) || (() => Promise.resolve());

			if (isOwnerOnly && !config.settings?.bot?.owner_ids?.includes(interaction.user.id)) {
				return sendReply({ content: "❌ This command is restricted to bot owners.", ephemeral: true });
			}

			// Cooldown Check
			const cdCheck = CooldownManager.check(foundCommand, interaction.user.id, interaction.guildId);
			if (cdCheck.onCooldown) {
				const E = config.Emojis || {};
				const C = config.Colors || {};
				const cdContainer = new ContainerBuilder()
					.setAccentColor(C.warning || "#F59E0B")
					.addTextDisplay(`### ${E.time || E.cooldown || "⏱️"} Command on Cooldown`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`Please wait **${cdCheck.remainingSeconds}s** before using \`/${commandName}\` again.`)
					.build();
				return sendReply({ components: [cdContainer], flags: MessageFlags.IsComponentsV2, ephemeral: true });
			}

			await interaction.deferReply();

			if (spamResult.warning) {
				await interaction.followUp({ content: spamResult.warning, ephemeral: true }).catch(() => null);
			}

			if (interaction.guild) {
				const isServerDisabled = await ServerCommandManager.isCommandDisabled(
					interaction.guild.id,
					foundCommand.name,
					foundCommand.command?.category
				);
				if (isServerDisabled) {
					const disabledBox = new ContainerBuilder()
						.setAccentColor(config.Colors?.warning || "#F59E0B")
						.addTextDisplay("### ⚠️ Command Disabled in Server")
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(`The command \`/${foundCommand.name}\` has been disabled by server administrators.`)
						.build();
					return interaction.editReply({ components: [disabledBox], flags: MessageFlags.IsComponentsV2 });
				}

				const perms = checkPermissions(
					interaction.member,
					interaction.guild.members.me,
					foundCommand.command.userPermissions,
					foundCommand.command.botPermissions
				);
				
				if (!perms.allowed) {
					if (perms.missingUserNames.length) {
						let container = new ContainerBuilder()
							.addTextDisplay("### Access Denied")
							.addSeparator({
								divider: true,
								spacing: SeparatorSpacingSize.Small
							})
							.addTextDisplay(`<@${interaction.user.id}>, You don't have the required __permissions__ to run the command!
								> **Missing permissions:** \`${perms.missingUserNames.join("`, `")}\``)
							.build();
						return interaction.editReply({
							components: [container],
							flags: MessageFlags.IsComponentsV2
						});
					}
				
					if (perms.missingBotNames.length) {
						let container = new ContainerBuilder()
							.addTextDisplay("### Access Denied")
							.addSeparator({
								divider: true,
								spacing: SeparatorSpacingSize.Small
							})
							.addTextDisplay(`<@${interaction.user.id}>, I don't have the required __permissions__ to run the command!
								> **Missing permissions:** \`${perms.missingBotNames.join("`, `")}\``)
							.build();
						return interaction.editReply({
							components: [container],
							flags: MessageFlags.IsComponentsV2
						});
					}
				
					return;
				}
			}
		
			CooldownManager.apply(foundCommand, interaction.user.id, interaction.guildId);

			let ctxPlugin = global.cache.plugins.get(foundCommand.pluginId)?.pluginContext;
			const startTime = Date.now();
			try {
				await foundCommand.command.execute(ctxPlugin, CommandType.SLASH, interaction);
				ObservabilityManager.recordCommand(foundCommand.name || commandName, "slash", true, Date.now() - startTime);
			} catch (execErr: any) {
				ObservabilityManager.recordCommand(foundCommand.name || commandName, "slash", false, Date.now() - startTime, "command_error");
				const errorRecord = await ErrorTracker.record(interaction.commandName, execErr, {
					userId: interaction.user?.id,
					username: interaction.user?.tag || interaction.user?.username,
					guildId: interaction.guildId || undefined,
					commandType: "SLASH",
				});

				const errContainer = new ContainerBuilder()
					.setAccentColor(config.Colors?.error || "#EF4444")
					.addTextDisplay("### ❌ Command Execution Error")
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(
						`An error occurred while executing \`/${interaction.commandName}\`.\n\n` +
						`• **Error ID:** \`${errorRecord.errorId}\`\n` +
						`• **Summary:** \`${(execErr?.message || "Internal error").slice(0, 180)}\`\n\n` +
						`-# Please provide this Error ID to the bot administrator.`
					)
					.build();

				const errPayload = { components: [errContainer], flags: MessageFlags.IsComponentsV2, ephemeral: true };
				if (interaction.deferred || interaction.replied) {
					await interaction.editReply(errPayload).catch(() => null);
				} else {
					await interaction.reply(errPayload).catch(() => null);
				}
			}

		} catch (err: any) {
			logger.error(
				"[SlashCommandHandler] Error while executing slash command.",
				err
			);
			await ErrorTracker.record("slash_dispatcher", err, {
				userId: interaction?.user?.id,
				guildId: interaction?.guildId || undefined,
				commandType: "SLASH",
			}).catch(() => null);
		}
	}
};
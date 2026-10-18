import logger from `@logger`;
import { MessageFlags, SeparatorSpacingSize } from `discord.js`;
import config from `@config`;
import { CommandStatus, RegisteredBy, CommandType } from `../../../shared/types/CommandRecord`;
import { checkPermissions } from `@shared/helpers/index.ts`;
import { ContainerBuilder } from `@sdk/discord`;
import { BlacklistManager } from `@core/security/BlacklistManager`;
import { AntiSpamService } from `@core/security/AntiSpamService`;
import { NoPrefixManager } from `@core/security/NoPrefixManager`;
import { CooldownManager } from `@core/security/CooldownManager`;
import { ErrorTracker } from `@core/logging/ErrorTracker`;
import { ServerCommandManager } from `@core/security/ServerCommandManager`;
import { ObservabilityManager } from `@core/telemetry/ObservabilityManager`;

module.exports = {
	name: `messageCreate`,
	description: `Official prefix command handler \n~ By MomentumOne`,
	execute: async (ctx, message) => {
		try {
			if (message.author.bot) return;

			// Central Global Blacklist check: User
			const userBl = await BlacklistManager.isUserBlacklisted(message.author.id);
			if (userBl.blacklisted) return;

			// Central Global Blacklist check: Guild
			if (message.guild) {
				const guildBl = await BlacklistManager.isGuildBlacklisted(message.guild.id);
				if (guildBl.blacklisted) return;
			}

			const configuredPrefix = process.env.BOT_PREFIX || config.settings?.bot?.prefix || `$`;
			const validPrefixes = Array.from(new Set([configuredPrefix, `.`]));
			const matchedPrefix = validPrefixes.find(p => message.content.startsWith(p));
			let content = ``;
			let isNoPrefix = false;

			if (matchedPrefix) {
				content = message.content.slice(matchedPrefix.length).trim();
			} else {
				// Check if user has active No-Prefix authorization
				const hasNoPrefix = await NoPrefixManager.hasNoPrefix(message.author.id);
				if (hasNoPrefix) {
					content = message.content.trim();
					isNoPrefix = true;
				} else {
					return;
				}
			}

			if (!content) return;

			const args = content.split(/\s+/);
			const commandName = args.shift()?.toLowerCase();
			if (!commandName) return;

			let foundCommand: any = null;

			for (const [, command] of global.commands) {
				const isEnabled =
					typeof command.enabled === `boolean`
						? command.enabled
						: String(command.enabled).toLowerCase() === `true`;

				if (command.status !== CommandStatus.ACTIVE || !isEnabled) {
					continue;
				}

				if (
					command.type !== CommandType.PREFIX &&
					command.type !== CommandType.HYBRID
				) {
					continue;
				}

				const aliases = command.command?.aliases ?? [];

				if (
					command.name?.toLowerCase() === commandName ||
					aliases.some((alias: string) => alias.toLowerCase() === commandName)
				) {
					foundCommand = command;
					break;
				}
			}

			if (!foundCommand) {
				// If message was without prefix and didn't match a valid command, ignore silently
				return;
			}

			// Anti-Spam Check: rolling 30s window
			const spamResult = await AntiSpamService.check(message.author.id, message.client);
			if (!spamResult.allowed) {
				const container = new ContainerBuilder()
					.setAccentColor(config.Colors?.error || `#EF4444`)
					.addTextDisplay(`### ${config.Emojis.danger || config.Emojis.blacklist || config.Emojis.error ||  ``} Command Rejected`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`**You have been blacklisted for excessive rate of commands.**\n${spamResult.reason || ``}`)
					.build();
				return message.reply({ components: [container], flags: MessageFlags.IsComponentsV2 }).catch(() => null);
			}

			if (spamResult.warning) {
				await message.reply({ content: spamResult.warning }).catch(() => null);
			}

			const isOwnerOnly =
				Boolean(foundCommand.command?.ownerOnly) ||
				Boolean(foundCommand.command?.ownersOnly) ||
				[`dev`, `owner`].includes(foundCommand.command?.category?.toLowerCase());

			if (isOwnerOnly && !config.settings.bot.owner_ids.includes(message.author.id)) {
				return;
			}

			if (message.guild) {
				const isServerDisabled = await ServerCommandManager.isCommandDisabled(
					message.guild.id,
					foundCommand.name,
					foundCommand.command?.category
				);
				if (isServerDisabled) {
					const disabledBox = new ContainerBuilder()
						.setAccentColor(config.Colors?.warning || `#F59E0B`)
						.addTextDisplay(`### ⚠️ Command Disabled in Server`)
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(`The command \`${foundCommand.name}\` has been disabled by server administrators.`)
						.build();
					return message.reply({ components: [disabledBox], flags: MessageFlags.IsComponentsV2 }).catch(() => null);
				}

				const perms = checkPermissions(
					message.member,
					message.guild.members.me,
					foundCommand.command.userPermissions,
					foundCommand.command.botPermissions
				);

				if (!perms.allowed) {
					if (perms.missingUserNames.length) {
						let container = new ContainerBuilder()
							.addTextDisplay(`### ${config.Emojis.no_access || config.Emojis.blacklist || config.Emojis.error || ``} Access Denied`)
							.addSeparator({
								divider: true,
								spacing: SeparatorSpacingSize.Small
							})
							.addTextDisplay(`<@${message.author.id}>, You don't have the required __permissions__ to run the command!
								> **Missing permissions:** \`${perms.missingUserNames.join(``, ``)}\``)
							.build();
						return message.reply({
							components: [container],
							flags: MessageFlags.IsComponentsV2
						});
					}

					if (perms.missingBotNames.length) {
						let container = new ContainerBuilder()
							.addTextDisplay(`### ${config.Emojis.no_access || config.Emojis.blacklist || config.Emojis.error || ``} Access Denied`)
							.addSeparator({
								divider: true,
								spacing: SeparatorSpacingSize.Small
							})
							.addTextDisplay(`<@${message.author.id}>, I don't have the required __permissions__ to run the command!
								> **Missing permissions:** \`${perms.missingBotNames.join(``, ``)}\``)
							.build();
						return message.reply({
							components: [container],
							flags: MessageFlags.IsComponentsV2
						});
					}

					return;
				}
			}

			// Cooldown Check
			const cdCheck = CooldownManager.check(foundCommand, message.author.id, message.guild?.id);
			if (cdCheck.onCooldown) {
				const E = config.Emojis || {};
				const C = config.Colors || {};
				const cdContainer = new ContainerBuilder()
					.setAccentColor(C.warning || `#F59E0B`)
					.addTextDisplay(`### ${config.Emojis.time || config.Emojis.cooldown || `⏱️`} Command on Cooldown`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(`Please wait **${cdCheck.remainingSeconds}s** before using \`${commandName}\` again.`)
					.build();
				return message.reply({ components: [cdContainer], flags: MessageFlags.IsComponentsV2 }).catch(() => null);
			}

			CooldownManager.apply(foundCommand, message.author.id, message.guild?.id);

			let pluginCtx = global.cache.plugins.get(foundCommand.pluginId)?.pluginContext;
			const startTime = Date.now();
			try {
				await foundCommand.command.execute(pluginCtx, CommandType.PREFIX, message, args);
				ObservabilityManager.recordCommand(foundCommand.name || commandName, "prefix", true, Date.now() - startTime);
			} catch (execErr: any) {
				ObservabilityManager.recordCommand(foundCommand.name || commandName, "prefix", false, Date.now() - startTime, "command_error");
				const errorRecord = await ErrorTracker.record(commandName, execErr, {
					userId: message.author.id,
					username: message.author.tag || message.author.username,
					guildId: message.guild?.id,
					commandType: `PREFIX`,
					args,
				});

				const errContainer = new ContainerBuilder()
					.setAccentColor(config.Colors?.error || `#EF4444`)
					.addTextDisplay(`### ${config.Emojis.error || ``} Command Execution Error`)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
					.addTextDisplay(
						`An error occurred while executing \`${commandName}\`.\n\n` +
						`• **Error ID:** \`${errorRecord.errorId}\`\n` +
						`• **Summary:** \`${(execErr?.message || `Internal error`).slice(0, 180)}\`\n\n` +
						`-# Please provide this Error ID to the bot administrator.`
					)
					.build();

				await message.reply({ components: [errContainer], flags: MessageFlags.IsComponentsV2 }).catch(() => null);
			}

		} catch (err: any) {
			logger.error(
				`[PrefixCommandHandler] Error while executing prefix command.`,
				err
			);
			await ErrorTracker.record(`prefix_dispatcher`, err, {
				userId: message?.author?.id,
				guildId: message?.guild?.id,
				commandType: `PREFIX`,
			}).catch(() => null);
		}
	}
};
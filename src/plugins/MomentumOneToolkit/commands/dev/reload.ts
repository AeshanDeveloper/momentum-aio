const {
	MessageFlags,
	SeparatorSpacingSize,
	ButtonStyle,
} = require("discord.js");

const {
	ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { ReloadService } from "@core/plugins/ReloadService";

export default {
	name: "reload",
	aliases: ["rel", "rld"],
	description: "Hot reload a specific command, all commands in a plugin, or an entire plugin (Bot Owner Only).",
	category: "Owner",
	usage: "reload <command|commands|plugin> [target]",
	ownerOnly: true,

	sub_commands: [
		{ name: "command <name>", description: "Reload a specific command by name or alias." },
		{ name: "commands [plugin]", description: "Reload all commands in a plugin." },
		{ name: "events [plugin]", description: "Reload all event listeners in a plugin." },
		{ name: "plugin [plugin]", description: "Reload an entire plugin and lifecycle listeners." },
	],

	execute: async (ctx: any, commandType: number, message: any, args: string[] = []) => {
		const ownerIds: string[] = config.settings?.bot?.owner_ids || [];
		const authorId = message.author?.id;

		if (!ownerIds.includes(authorId)) {
			return message.reply({
				content: "❌ **Access Denied**: This command is restricted to the bot owner.",
			});
		}

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			reload: E.reload || E.loading || "🔄",
			check: E.success || "✅",
			cross: E.error || "❌",
			plugin: E.plugin || "🧩",
			command: E.cmd || "⚡",
		};

		const colors = {
			default: C.default || "#3B82F6",
			success: C.success || "#10B981",
			error: C.error || "#EF4444",
		};

		const reply = async (title: string, description: string, color = colors.default) => {
			const container = new ContainerBuilder()
				.setAccentColor(color)
				.addTextDisplay(`### ${title}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(description);

			return message.reply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			});
		};

		const sub = args[0]?.toLowerCase();

		// Interactive Select Menu if called with no arguments
		if (!sub) {
			const menuId = `reload_select_${message.id}`;
			const plugins = Array.from(global.cache?.plugins?.keys() || []);
			const defaultPlugin = plugins[0] || "MomentumOneToolkit";

			const container = new ContainerBuilder()
				.setAccentColor(colors.default)
				.addTextDisplay(`### ${emojis.reload} System Hot Reload Center`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`Hot-reload bot systems without taking the bot process offline.\n\n` +
					`**Select an action below or run commands directly:**\n` +
					`• \`$reload command <name>\` — Reload a single command file\n` +
					`• \`$reload commands [plugin]\` — Reload all commands in a plugin\n` +
					`• \`$reload plugin [plugin]\` — Reload full plugin and listeners\n\n` +
					`-# Active Plugins: \`${plugins.join(", ") || "None"}\``
				)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addActionRow((row: any) =>
					row.addStringSelectMenu({
						custom_id: menuId,
						placeholder: "Choose a component to reload...",
						options: [
							{
								label: `Reload Entire Plugin (${defaultPlugin})`,
								value: `plugin:${defaultPlugin}`,
								description: "Re-executes lifecycle, clears cache, reloads events & commands",
								emoji: emojis.plugin,
							},
							{
								label: `Reload All Commands (${defaultPlugin})`,
								value: `commands:${defaultPlugin}`,
								description: "Re-maps and refreshes all command definitions",
								emoji: emojis.command,
							},
							{
								label: "Reload Command: balance",
								value: "cmd:balance",
								description: "Reloads balance & economy admin command",
								emoji: emojis.command,
							},
							{
								label: "Reload Command: leaderboard",
								value: "cmd:leaderboard",
								description: "Reloads leaderboard command & pagination",
								emoji: emojis.command,
							},
							{
								label: "Reload Command: blacklist",
								value: "cmd:blacklist",
								description: "Reloads global blacklist command",
								emoji: emojis.command,
							},
							{
								label: "Reload Command: noprefix",
								value: "cmd:noprefix",
								description: "Reloads no-prefix privilege manager command",
								emoji: emojis.command,
							},
						],
					})
				);

			const replyMsg = await message.reply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			});

			const filter = (i: any) => i.customId === menuId && i.user.id === authorId;
			const collector = replyMsg.createMessageComponentCollector?.({ filter, time: 60_000 });

			collector?.on("collect", async (interaction: any) => {
				const selected = interaction.values?.[0];
				if (!selected) return;

				await interaction.deferUpdate();

				const [type, target] = selected.split(":");

				if (type === "cmd") {
					const res = await ReloadService.reloadCommand(target);
					const statusBox = new ContainerBuilder()
						.setAccentColor(res.success ? colors.success : colors.error)
						.addTextDisplay(`### ${res.success ? emojis.check : emojis.cross} Reload: \`${target}\``)
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(
							res.success
								? `Successfully reloaded command \`${res.commandName}\` from plugin **${res.pluginName}** without restart.`
								: `Failed to reload command: ${res.error}`
						)
						.build();
					await interaction.editReply({ components: [statusBox] });
				} else if (type === "commands") {
					const res = await ReloadService.reloadPluginCommands(target);
					const statusBox = new ContainerBuilder()
						.setAccentColor(res.success ? colors.success : colors.error)
						.addTextDisplay(`### ${res.success ? emojis.check : emojis.cross} Reload Commands: \`${target}\``)
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(
							res.success
								? `Successfully refreshed **${res.count}** commands in plugin **${res.pluginName}**.`
								: `Failed to reload commands: ${res.error}`
						)
						.build();
					await interaction.editReply({ components: [statusBox] });
				} else if (type === "plugin") {
					const res = await ReloadService.reloadPlugin(target, message.client);
					const statusBox = new ContainerBuilder()
						.setAccentColor(res.success ? colors.success : colors.error)
						.addTextDisplay(`### ${res.success ? emojis.check : emojis.cross} Reload Plugin: \`${target}\``)
						.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
						.addTextDisplay(
							res.success
								? `Successfully reloaded entire plugin **${res.pluginName}** (listeners, lifecycle, and commands updated).`
								: `Failed to reload plugin: ${res.error}`
						)
						.build();
					await interaction.editReply({ components: [statusBox] });
				}
			});

			return;
		}

		// Direct Subcommand execution:
		if (sub === "command" || sub === "cmd") {
			const targetCmd = args[1];
			if (!targetCmd) {
				return reply(
					`${emojis.cross} Missing Command Name`,
					"Usage: `$reload command <name>`\nExample: `$reload command balance`",
					colors.error
				);
			}

			const res = await ReloadService.reloadCommand(targetCmd);
			if (!res.success) {
				return reply(`${emojis.cross} Reload Failed`, res.error || "Could not reload command.", colors.error);
			}

			return reply(
				`${emojis.check} Command Reloaded`,
				`Successfully reloaded command \`${res.commandName}\` from plugin **${res.pluginName}**.\nMemory and registry updated safely.`,
				colors.success
			);
		}

		if (sub === "commands") {
			const targetPlugin = args[1] || Array.from(global.cache?.plugins?.keys() || [])[0] || "MomentumOneToolkit";
			const res = await ReloadService.reloadPluginCommands(targetPlugin);

			if (!res.success) {
				return reply(`${emojis.cross} Reload Failed`, res.error || "Could not reload commands.", colors.error);
			}

			return reply(
				`${emojis.check} Plugin Commands Reloaded`,
				`Successfully refreshed **${res.count}** commands in plugin **${res.pluginName}**.\nAll command definitions and mappings are updated.`,
				colors.success
			);
		}

		if (sub === "events") {
			const targetPlugin = args[1] || Array.from(global.cache?.plugins?.keys() || [])[0] || "MomentumOneToolkit";
			const res = await ReloadService.reloadPluginEvents(targetPlugin, message.client);

			if (!res.success) {
				return reply(`${emojis.cross} Reload Failed`, res.error || "Could not reload events.", colors.error);
			}

			return reply(
				`${emojis.check} Plugin Events Reloaded`,
				`Successfully reloaded event listeners in plugin **${res.pluginName}**.\nAll event handlers and mappings refreshed without duplication.`,
				colors.success
			);
		}

		if (sub === "plugin") {
			const targetPlugin = args[1] || Array.from(global.cache?.plugins?.keys() || [])[0] || "MomentumOneToolkit";
			const res = await ReloadService.reloadPlugin(targetPlugin, message.client);

			if (!res.success) {
				return reply(`${emojis.cross} Reload Failed`, res.error || "Could not reload plugin.", colors.error);
			}

			return reply(
				`${emojis.check} Plugin Reloaded`,
				`Successfully reloaded entire plugin **${res.pluginName}**.\nListeners, cache, commands, and lifecycle re-initialized.`,
				colors.success
			);
		}

		// Shorthand: `$reload <commandName>`
		const res = await ReloadService.reloadCommand(sub);
		if (res.success) {
			return reply(
				`${emojis.check} Command Reloaded`,
				`Successfully reloaded command \`${res.commandName}\` from plugin **${res.pluginName}**.`,
				colors.success
			);
		}

		return reply(
			`${emojis.cross} Unknown Target`,
			`Could not find command or action matching \`${sub}\`.\nUsage: \`$reload [command <name> | commands [plugin] | plugin [plugin]]\``,
			colors.error
		);
	},
};

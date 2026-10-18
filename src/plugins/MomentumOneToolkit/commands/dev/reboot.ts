const { writeFileSync, unlinkSync } = require("fs");
const { spawn } = require("child_process");
const path = require("path");

const {
	ButtonStyle,
	MessageFlags
} = require("discord.js");

import {
	ContainerBuilder
} from "@sdk/discord";

import config from "@config";

export default {
	name: "reboot",

	aliases: [
		"shutdown",
		"restart",
		"reloadbot"
	],

	category: "Owner",

	description: "Restarts the bot process.",

	ownerOnly: true,

	async execute(ctx, commandType, message, args) {
		const client = message.client;

		const confirmId = `reboot_confirm_${message.id}`;
		const cancelId = `reboot_cancel_${message.id}`;

		let timeout;

		/*
		 * ---------------------------------------------------------
		 * BUILD INITIAL CONFIRMATION CONTAINER
		 * ---------------------------------------------------------
		 */

		const container = new ContainerBuilder()
			.addTextDisplay(
				`### ${
					config.Emojis?.reload ||
					config.Emojis?.reboot ||
					config.Emojis?.loading || ""
				} Restart ${config.settings.bot.name}?`
			)

			.addSeparator({
				divider: true
			})

			.addTextDisplay(
				`${
					config.Emojis.dot ||
					config.Emojis.info ||
					""
				} This will restart the bot process.`
			)

			.addSeparator({
				divider: true
			})

			.addTextDisplay(
				`-# ${config.settings.bot.name} • Reboot`
			)

			.setAccentColor(
				config.Colors.cmd_reboot ||
				config.Colors.default
			)

			.addActionRow(row =>
				row
					.addButton({
						custom_id: confirmId,
						label: "Confirm Reboot",
						style: ButtonStyle.Danger
					})

					.addButton({
						custom_id: cancelId,
						label: "Cancel",
						style: ButtonStyle.Secondary
					})
			)

			.build();

		/*
		 * ---------------------------------------------------------
		 * SEND MESSAGE
		 * ---------------------------------------------------------
		 *
		 * Components V2 expects the built container directly.
		 */

		const reply = await message.reply({
			components: [container],
			flags: MessageFlags.IsComponentsV2
		});

		/*
		 * ---------------------------------------------------------
		 * CLEANUP
		 * ---------------------------------------------------------
		 */

		const cleanup = () => {
			client.removeListener(
				"interactionCreate",
				interactionHandler
			);

			if (timeout) {
				clearTimeout(timeout);
				timeout = null;
			}
		};

		/*
		 * ---------------------------------------------------------
		 * INTERACTION HANDLER
		 * ---------------------------------------------------------
		 */

		const interactionHandler = async interaction => {
			if (!interaction.isButton()) {
				return;
			}

			if (
				interaction.customId !== confirmId &&
				interaction.customId !== cancelId
			) {
				return;
			}

			/*
			 * Only the command author can use these buttons.
			 */

			if (interaction.user.id !== message.author.id) {
				await interaction.reply({
					content: "You cannot use these buttons.",
					flags: MessageFlags.Ephemeral
				}).catch(() => {});

				return;
			}

			/*
			 * -----------------------------------------------------
			 * CANCEL
			 * -----------------------------------------------------
			 */

			if (interaction.customId === cancelId) {
				cleanup();

				await interaction.update({
					content: "Reboot cancelled.",
					components: []
				}).catch(() => {});

				return;
			}

			/*
			 * -----------------------------------------------------
			 * CONFIRM
			 * -----------------------------------------------------
			 */

			cleanup();

			const restartingContainer = new ContainerBuilder()
				.addTextDisplay(
					`### ${
						config.Emojis.reload ||
						config.Emojis.reboot ||
						config.Emojis.loading
					} Restarting ${config.settings.bot.name}...`
				)

				.addSeparator({
					divider: true
				})

				.addTextDisplay(
					`${
						config.Emojis.dot ||
						config.Emojis.info ||
						""
					} Hold on, rebooting the bot...`
				)

				.addSeparator({
					divider: true
				})

				.addTextDisplay(
					`-# ${config.settings.bot.name} • Reboot`
				)

				.setAccentColor(
					config.Colors.cmd_reboot ||
					config.Colors.default
				)

				.build();

			await interaction.update({
				components: [
					restartingContainer
				]
			}).catch(() => {});

			/*
			 * -----------------------------------------------------
			 * START NEW PROCESS
			 * -----------------------------------------------------
			 *
			 * index.js is resolved relative to this command file.
			 */

			const startScript = path.resolve(
				__dirname,
				"../../../../index.ts"
			);

			/*
			 * Create a tiny detached bootstrap process.
			 *
			 * The bootstrap starts the new bot process and then
			 * exits independently from the current process.
			 */

			const rebootScript = `
                const { spawn } = require("child_process");
                
                const child = spawn(
                    "npx",
                    ["tsc", "src/index.ts"],
                    {
                        stdio: "inherit",
                        detached: true,
                        shell: true,
                        cwd: ${JSON.stringify(process.cwd())}
                    }
                );
                
                child.unref();
                `;

			const rebootFile = path.resolve(
				process.cwd(),
				".reboot-temp.js"
			);

			writeFileSync(
				rebootFile,
				rebootScript,
				"utf8"
			);

			/*
			 * Start bootstrap process detached.
			 */

			const rebootProcess = spawn(
				process.execPath,
				[rebootFile],
				{
					detached: true,
					stdio: "ignore"
				}
			);

			rebootProcess.unref();

			/*
			 * Give the child process a moment to spawn before
			 * terminating this process.
			 */

			setTimeout(() => {
				try {
					unlinkSync(rebootFile);
				} catch {}

				process.exit(0);
			}, 1200);
		};

		/*
		 * ---------------------------------------------------------
		 * ATTACH LISTENER
		 * ---------------------------------------------------------
		 */

		client.on(
			"interactionCreate",
			interactionHandler
		);

		/*
		 * ---------------------------------------------------------
		 * AUTO EXPIRY
		 * ---------------------------------------------------------
		 *
		 * Prevents abandoned listeners from remaining forever.
		 */

		timeout = setTimeout(() => {
			cleanup();

			message.delete().catch(() => {});
		}, 600_000);
	}
};


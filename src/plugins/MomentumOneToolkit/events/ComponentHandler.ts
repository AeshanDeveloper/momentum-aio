import logger from "@logger";
import config from "@config";
import { MessageFlags, PermissionFlagsBits } from "discord.js";
import { ContainerBuilder } from "@sdk/discord";
import { TicketManager } from "../tickets/TicketManager";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

const Emojis = config.Emojis || config.emojis || {};
const Colors = config.Colors || config.colors || {};

const getErrorCode = (error: any): number | undefined => {
	const raw = error?.code ?? error?.rawError?.code;
	return raw !== undefined ? Number(raw) : undefined;
};

const logError = (
	action: string,
	ticketId: string,
	guildId: string,
	error: any
) => {
	logger.error(
		`[ComponentHandler] ${action} failed | Guild: ${guildId} | Ticket: ${ticketId} | Code: ${getErrorCode(error) ?? "UNKNOWN"} | ${error?.message ?? String(error)}`
	);
};

export default {
	name: "interactionCreate",
	description: "Handler for interactive buttons and components (Tickets, Leaderboards)",

	execute: async (ctx: any, interaction: any) => {
		const isButton = typeof interaction.isButton === "function" && interaction.isButton();
		const isSelect = typeof interaction.isStringSelectMenu === "function" && interaction.isStringSelectMenu();
		const isModal = typeof interaction.isModalSubmit === "function" && interaction.isModalSubmit();

		if (!isButton && !isSelect && !isModal) return;

		const customId: string = interaction.customId || "";

		// Blacklist check
		const { BlacklistManager } = require("@core/security/BlacklistManager");
		const userBl = await BlacklistManager.isUserBlacklisted(interaction.user.id);
		if (userBl.blacklisted) {
			if (!interaction.replied && !interaction.deferred) {
				await interaction.reply({
					content: "🚫 You are blacklisted from using this bot.",
					flags: MessageFlags.Ephemeral,
				}).catch(() => null);
			}
			return;
		}

		// ================================================================
		// GLOBAL OWNER MANAGEMENT COMPONENTS (Server or DM)
		// ================================================================
		if (customId.startsWith("cmdmanage:")) {
			try {
				const cmdManage = require("../commands/dev/commandmanage");
				await cmdManage.handleInteraction(interaction);
			} catch (err: any) {
				logger.error("[ComponentHandler] Error handling cmdmanage interaction:", err);
			}
			return;
		}

		if (customId.startsWith("listservers:")) {
			try {
				const listServers = require("../commands/dev/listservers");
				await listServers.handleInteraction(interaction);
			} catch (err: any) {
				logger.error("[ComponentHandler] Error handling listservers interaction:", err);
			}
			return;
		}

		const guild = interaction.guild;
		if (!guild) {
			if (!interaction.replied && !interaction.deferred) {
				await interaction.reply({
					content: `${Emojis.error ?? ""} This action can only be used inside a server.`,
					flags: MessageFlags.Ephemeral,
				}).catch((error: any) => {
					logError("Guild validation response", "unknown", "unknown", error);
				});
			}
			return;
		}

		const respondEphemeral = async (content: string) => {
			try {
				if (interaction.deferred && !interaction.replied) {
					await interaction.editReply({ content, components: [] });
				} else if (interaction.replied || interaction.deferred) {
					await interaction.followUp({
						content,
						flags: MessageFlags.Ephemeral,
					});
				} else {
					await interaction.reply({
						content,
						flags: MessageFlags.Ephemeral,
					});
				}
			} catch (error: any) {
				// The interaction may have expired or its response may no longer exist.
				logError("Interaction feedback", "unknown", guild.id, error);
			}
		};

		try {
			// ================================================================
			// TICKET BUTTONS
			// ================================================================
			if (customId.startsWith("ticket:")) {
				await TicketManager.handleButtonInteraction(interaction);
				return;
			}

		} catch (error: any) {
			const code = getErrorCode(error);

			if (code === 10008 || code === 10003 || code === 10062 || code === 40060 || error?.message?.includes("acknowledged")) {
				logger.warn(
					`[ComponentHandler] Ignored stale or acknowledged Discord interaction/message | Guild: ${guild?.id || "unknown"} | Custom ID: ${customId} | Code: ${code}`
				);
				return;
			}

			logger.error(
				`[ComponentHandler] Interaction failed | Guild: ${guild?.id || "unknown"} | Custom ID: ${customId} | Code: ${code ?? "UNKNOWN"} | ${error?.message ?? String(error)}`
			);
			ObservabilityManager.recordError(
				"component_interaction_error",
				`[${customId.slice(0, 40)}] ${error?.message || "Interaction failed"}`.slice(0, 80)
			);
			ObservabilityManager.recordInteractionEvent(
				isButton ? "button" : isSelect ? "select" : "modal",
				customId,
				false
			);

			if (!interaction.replied && !interaction.deferred) {
				await interaction.reply({
					content: `${Emojis.error ?? ""} An error occurred while processing this component.`,
					flags: MessageFlags.Ephemeral,
				}).catch(() => null);
			}
		}
	},
};
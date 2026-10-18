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
import DatabaseManager from "@database/Database";
import { isBotOwner } from "@core/security/SecurityHelpers";
import { ErrorTracker } from "@core/logging/ErrorTracker";
import DiscordTelemetry from "@core/telemetry/DiscordTelemetry";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";
import { EconomyManager } from "../../economy/EconomyManager";
import { LeaderboardManager } from "../../economy/LeaderboardManager";
import { TicketManager } from "../../tickets/TicketManager";
import { PermissionService } from "../../economy/PermissionService";
import { CHANGELOG_RELEASES, getLatestRelease } from "@config/Changelog";

const VERSION = "26.7.20";

type ActiveView = "overview" | "errors" | "actions" | "caches" | "ratelimits";

async function fetchSystemMetrics(client: any) {
	// 1. Bot & Host
	const uptimeSec = Math.floor(process.uptime());
	const days = Math.floor(uptimeSec / 86400);
	const hours = Math.floor((uptimeSec % 86400) / 3600);
	const minutes = Math.floor((uptimeSec % 3600) / 60);
	const seconds = uptimeSec % 60;
	const uptimeFormatted = `${days}d ${hours}h ${minutes}m ${seconds}s`;
	const memory = process.memoryUsage();
	const heapUsedMb = (memory.heapUsed / 1024 / 1024).toFixed(1);
	const heapTotalMb = (memory.heapTotal / 1024 / 1024).toFixed(1);

	// 2. Discord Gateway
	const wsPing = client?.ws?.ping ?? -1;
	const wsStatus = client?.ws?.status === 0 ? "Ready / Connected" : "Connecting/Reconnecting";
	const guildCount = client?.guilds?.cache?.size ?? 0;
	const userCount = client?.users?.cache?.size ?? 0;

	// 3. Database
	const dbConnected = DatabaseManager.isConnected();
	let dbLatency = -1;
	try {
		const pingStart = Date.now();
		await DatabaseManager.ping();
		dbLatency = Date.now() - pingStart;
	} catch {
		dbLatency = -1;
	}

	// 4. Caches
	const ecoCaches = EconomyManager.getCacheStats();
	const lbCaches = LeaderboardManager.getCacheStats();
	const ticketCaches = TicketManager.getCacheStats();
	const permCaches = PermissionService.getCacheStats();
	const pluginCount = (global as any).cache?.plugins?.size ?? 0;

	// 5. Leaderboard scheduler
	const lbStatus = LeaderboardManager.getLastRefreshStatus();

	// 6. Tickets
	let pendingTickets = 0;
	let totalTickets = 0;
	try {
		const ticketCol = await DatabaseManager.collection("economy_tickets");
		pendingTickets = await ticketCol.countDocuments({ status: { $in: ["open", "processing"] } });
		totalTickets = await ticketCol.countDocuments({});
	} catch {}

	// 7. Error tracking
	let totalErrorsCount = 0;
	try {
		const errCol = await DatabaseManager.collection("command_errors");
		totalErrorsCount = await errCol.countDocuments({});
	} catch {}

	// 8. Telemetry & Observability
	const telemetryStats = DiscordTelemetry.getStats();
	const observabilityStats = ObservabilityManager.getStats();

	return {
		uptimeFormatted,
		heapUsedMb,
		heapTotalMb,
		wsPing,
		wsStatus,
		guildCount,
		userCount,
		dbConnected,
		dbLatency,
		ecoCaches,
		lbCaches,
		ticketCaches,
		permCaches,
		pluginCount,
		lbStatus,
		pendingTickets,
		totalTickets,
		totalErrorsCount,
		telemetryStats,
		observabilityStats,
	};
}

function buildOverviewPanel(metrics: any, colors: any, emojis: any): any {
	const container = new ContainerBuilder()
		.setAccentColor(colors.default)
		.addTextDisplay(`### ${emojis.bot} MomentumOne Operational Control Panel`)
		.addTextDisplay(
			`**Platform Version:** \`v${VERSION}\` • **Node:** \`${process.version}\`\n` +
			`**Uptime:** \`${metrics.uptimeFormatted}\` • **Heap:** \`${metrics.heapUsedMb} MB / ${metrics.heapTotalMb} MB\`\n` +
			`**Status:** ${emojis.enabled} Online & Operational`
		)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// Gateway & Database Connectivity
	const pingText = metrics.wsPing >= 0 ? `${metrics.wsPing}ms` : "Unknown";
	const dbPingText = metrics.dbLatency >= 0 ? `${metrics.dbLatency}ms` : "Active";
	container.addTextDisplay(
		`${emojis.server} **Connectivity & Services**\n` +
		`• **Discord Gateway:** \`${metrics.wsStatus}\` (${pingText})\n` +
		`• **Connected Guilds:** \`${metrics.guildCount}\` (${metrics.userCount} cached users)\n` +
		`• **Database:** ${metrics.dbConnected ? `${emojis.enabled} Connected` : `${emojis.disabled} Disconnected`} (${dbPingText})\n` +
		`• **Active Plugins:** \`${metrics.pluginCount}\` loaded in runtime`
	);

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// Scheduler, Economy & Tickets
	const lbRunningText = metrics.lbStatus.isRunning ? `${emojis.enabled} Active (Polling every 60s)` : `${emojis.disabled} Paused`;
	const lbLastRun = metrics.lbStatus.lastRefreshedAt
		? `<t:${Math.floor(metrics.lbStatus.lastRefreshedAt.getTime() / 1000)}:R>`
		: "Never";

	container.addTextDisplay(
		`${emojis.wallet} **Economy & Automation Status**\n` +
		`• **Live Leaderboard Scheduler:** ${lbRunningText}\n` +
		`• **Last Leaderboard Refresh:** ${lbLastRun}\n` +
		`• **Withdrawal Tickets:** \`${metrics.pendingTickets}\` pending (${metrics.totalTickets} lifetime)\n` +
		`• **Cache State:** \`${metrics.ecoCaches.balanceEntries}\` balances, \`${metrics.ecoCaches.settingsEntries}\` guilds, \`${metrics.lbCaches.rankEntries}\` rank caches`
	);

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// Observability, Analytics & AI
	const obs = metrics.observabilityStats;
	const ga4Text = obs.ga4.enabled
		? `${emojis.enabled} Active (${obs.ga4.sent} delivered)`
		: `${emojis.disabled} Inactive (Set GA4_MEASUREMENT_ID & GA4_API_SECRET)`;
	const webhookText = obs.webhook.enabled
		? `${emojis.enabled} Active (${obs.webhook.sent} sent)`
		: `${emojis.disabled} Inactive (Set DISCORD_LOG_WEBHOOK_URL)`;
	const aiText = Boolean(process.env.GEMINI_API_KEY?.trim())
		? `${emojis.enabled} Ready (Google Gemini: \`${process.env.GEMINI_MODEL?.trim() || "gemini-3.8-flash"}\`)`
		: `${emojis.disabled} Inactive (Set GEMINI_API_KEY)`;

	container.addTextDisplay(
		`📊 **Observability & Intelligence**\n` +
		`• **GA4 Analytics:** ${ga4Text}\n` +
		`• **Webhook Logging:** ${webhookText}\n` +
		`• **Gemini AI Engine:** ${aiText}\n` +
		`• **Operational Events Tracked:** \`${obs.eventsTotal}\` session events`
	);

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// Health & Telemetry
	const lastRLText = metrics.telemetryStats.lastRateLimit
		? `<t:${Math.floor(new Date(metrics.telemetryStats.lastRateLimit).getTime() / 1000)}:R>`
		: "None recorded";
	container.addTextDisplay(
		`${emojis.commands} **Diagnostics & Safety**\n` +
		`• **Recorded Command Errors:** \`${metrics.totalErrorsCount}\`\n` +
		`• **Discord Rate Limit Events:** \`${metrics.telemetryStats.rateLimitsTotal}\` (Last: ${lastRLText})\n` +
		`• **Discord API Failures:** \`${metrics.telemetryStats.apiFailuresTotal}\``
	);

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	container.addTextDisplay("-# Authorized bot owners only. Use the controls below to inspect and manage operational subsystems.");

	return container.build();
}

async function buildErrorsPanel(colors: any, emojis: any): Promise<any> {
	const container = new ContainerBuilder()
		.setAccentColor(colors.error)
		.addTextDisplay(`### ${emojis.error} Recent Command & Execution Errors`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	try {
		const col = await DatabaseManager.collection("command_errors");
		const errors = await col.find({}).sort({ timestamp: -1 }).limit(5).toArray();

		if (!errors.length) {
			container.addTextDisplay(`${emojis.success} **Clean System:** No recorded command errors in database.`);
		} else {
			for (const err of errors) {
				const timeStr = err.timestamp ? `<t:${Math.floor(new Date(err.timestamp).getTime() / 1000)}:R>` : "Recently";
				container.addTextDisplay(
					`• **\`${err.errorId || "ERR"}\`** [${err.commandName || "Unknown"}] — ${timeStr}\n` +
					`  **Message:** \`${String(err.message || "Execution exception").slice(0, 120)}\``
				);
			}
		}
	} catch (e: any) {
		container.addTextDisplay(`${emojis.error} Failed to load errors: ${e?.message}`);
	}

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	container.addTextDisplay("-# For full stack traces, run `.errors view <errorId>`.");
	return container.build();
}

async function buildActionsPanel(colors: any, emojis: any): Promise<any> {
	const container = new ContainerBuilder()
		.setAccentColor(colors.default)
		.addTextDisplay(`### ${emojis.history} Recent Administrative Actions`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	try {
		const col = await DatabaseManager.collection("economy_audit_logs");
		const actions = await col.find({}).sort({ timestamp: -1 }).limit(5).toArray();

		if (!actions.length) {
			container.addTextDisplay("No administrative audit entries recorded yet.");
		} else {
			for (const act of actions) {
				const timeStr = act.timestamp ? `<t:${Math.floor(new Date(act.timestamp).getTime() / 1000)}:R>` : "Recently";
				container.addTextDisplay(
					`• **${act.action || "audit"}** by <@${act.actorId || "unknown"}> — ${timeStr}\n` +
					`  **Reason:** ${act.reason || "Administrative update"}`
				);
			}
		}
	} catch (e: any) {
		container.addTextDisplay(`${emojis.error} Failed to load actions: ${e?.message}`);
	}

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	return container.build();
}

function buildCachesPanel(metrics: any, colors: any, emojis: any): any {
	const container = new ContainerBuilder()
		.setAccentColor(colors.default)
		.addTextDisplay(`### ${emojis.server} In-Memory Cache Health & Diagnostic Breakdown`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
		.addTextDisplay(
			`• **Economy Balances Cache:** \`${metrics.ecoCaches.balanceEntries}\` active memory entries\n` +
			`• **Guild Settings Cache:** \`${metrics.ecoCaches.settingsEntries}\` configured guilds\n` +
			`• **Guild Blacklist Cache:** \`${metrics.ecoCaches.blacklistEntries}\` cached records\n` +
			`• **Leaderboard Rankings Cache:** \`${metrics.lbCaches.rankEntries}\` calculated leaderboards\n` +
			`• **Ticket Guild Configs Cache:** \`${metrics.ticketCaches.configEntries}\` cached ticket configs\n` +
			`• **Permissions Cache:** \`${metrics.permCaches.permissionsEntries}\` cached permissions\n` +
			`• **Loaded Plugins Cache:** \`${metrics.pluginCount}\` registered plugins`
		)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
		.addTextDisplay(
			"-# ℹ️ Caches are automatically synchronized with database mutations. Use 'Clear Safe Caches' to purge volatile memory caches without affecting persistent records."
		);

	return container.build();
}

function buildRateLimitsPanel(colors: any, emojis: any): any {
	const events = DiscordTelemetry.getRateLimitEvents();
	const failures = DiscordTelemetry.getApiFailures();

	const container = new ContainerBuilder()
		.setAccentColor(colors.warning)
		.addTextDisplay(`### ${emojis.warning} Discord Rate-Limit & API Telemetry`)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	if (!events.length && !failures.length) {
		container.addTextDisplay(`${emojis.success} **Zero Rate Limits:** Discord REST API connection has encountered no recent rate limits.`);
	} else {
		if (events.length) {
			const rlLines = events.slice(0, 5).map((e) => {
				const timeStr = `<t:${Math.floor(new Date(e.timestamp).getTime() / 1000)}:R>`;
				return `• **[${e.method || "REQ"}]** \`${e.route || e.path || "API"}\` — ${timeStr} (Cooldown: \`${e.timeoutMs}ms\`${e.global ? ", Global: YES" : ""})`;
			}).join("\n");
			container.addTextDisplay(`${emojis.warning} **Recent Rate Limit Events (Bounded):**\n${rlLines}`);
		}
		if (failures.length) {
			container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			const failLines = failures.slice(0, 4).map((f) => {
				const timeStr = `<t:${Math.floor(new Date(f.timestamp).getTime() / 1000)}:R>`;
				return `• **Failure:** \`${f.message}\` — ${timeStr}`;
			}).join("\n");
			container.addTextDisplay(`${emojis.error} **Recent API Failures:**\n${failLines}`);
		}
	}

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
	container.addTextDisplay(
		"-# ℹ️ Rate limits are managed conservatively in accordance with Discord API guidelines. Bypassing or resetting rate limits is strictly avoided to protect application health."
	);

	return container.build();
}

function buildActionButtons(
	prefix: string,
	currentView: ActiveView,
	isSchedulerRunning: boolean,
	emojis: any
): ActionRowBuilder[] {
	const row1 = new ActionRowBuilder();
	row1.addButton({
		custom_id: `${prefix}:view:overview`,
		label: "Overview",
		emoji: emojis.bot,
		style: currentView === "overview" ? ButtonStyle.Primary : ButtonStyle.Secondary,
	});
	row1.addButton({
		custom_id: `${prefix}:view:errors`,
		label: "Errors",
		emoji: emojis.error,
		style: currentView === "errors" ? ButtonStyle.Primary : ButtonStyle.Secondary,
	});
	row1.addButton({
		custom_id: `${prefix}:view:actions`,
		label: "Audit Log",
		emoji: emojis.history,
		style: currentView === "actions" ? ButtonStyle.Primary : ButtonStyle.Secondary,
	});
	row1.addButton({
		custom_id: `${prefix}:view:caches`,
		label: "Caches",
		emoji: emojis.server,
		style: currentView === "caches" ? ButtonStyle.Primary : ButtonStyle.Secondary,
	});
	row1.addButton({
		custom_id: `${prefix}:view:ratelimits`,
		label: "Rate Limits",
		emoji: emojis.warning,
		style: currentView === "ratelimits" ? ButtonStyle.Primary : ButtonStyle.Secondary,
	});

	const row2 = new ActionRowBuilder();
	row2.addButton({
		custom_id: `${prefix}:act:refresh`,
		label: "Refresh Status",
		emoji: emojis.reset,
		style: ButtonStyle.Secondary,
	});
	row2.addButton({
		custom_id: `${prefix}:act:clear_caches`,
		label: "Clear Safe Caches",
		emoji: emojis.reset,
		style: ButtonStyle.Secondary,
	});
	row2.addButton({
		custom_id: `${prefix}:act:toggle_scheduler`,
		label: isSchedulerRunning ? "Pause Scheduler" : "Resume Scheduler",
		style: isSchedulerRunning ? ButtonStyle.Danger : ButtonStyle.Success,
	});
	row2.addButton({
		custom_id: `${prefix}:act:close`,
		label: "Close Panel",
		emoji: emojis.cancel,
		style: ButtonStyle.Danger,
	});

	return [row1, row2];
}

export default {
	name: "status",
	aliases: ["ops", "controlpanel", "botstatus", "systempanel"],
	description: "Comprehensive bot-owner-only operational control panel and live status dashboard.",
	category: "Owner",
	usage: "status",
	ownerOnly: true,

	builder: new SlashCommandBuilder()
		.setName("status")
		.setDescription("Operational control panel and system status dashboard (Bot Owner Only)."),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const client = messageOrInteraction.client;

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const emojis = {
			bot: E.bot || "🤖",
			server: E.server || "🖥️",
			wallet: E.wallet || "💼",
			error: E.error || "❌",
			success: E.success || "✅",
			warning: E.warning || "⚠️",
			loading: E.loading || "⏳",
			history: E.history || "📜",
			commands: E.commands || "⚡",
			reset: E.reset || "🔄",
			search: E.search || "🔍",
			enabled: E.enabled || "🟢",
			disabled: E.disabled || "🔴",
			info: E.info || "ℹ️",
			user: E.user || "👤",
			cancel: E.cancel || "✖️",
		};

		const colors = {
			default: C.default || "#0844C5",
			success: C.success || "#3FD438",
			error: C.error || "#B21F1F",
			warning: C.warning || "#B21F1F",
		};

		const sendReply = async (payload: any) => {
			if (isSlash) {
				if (messageOrInteraction.deferred || messageOrInteraction.replied) {
					return messageOrInteraction.editReply(payload);
				}
				return messageOrInteraction.reply({ ...payload, fetchReply: true });
			}
			return messageOrInteraction.reply(payload);
		};

		// 1. Strict Owner Authorization
		if (!isBotOwner(user.id)) {
			const denyContainer = new ContainerBuilder()
				.setAccentColor(colors.error)
				.addTextDisplay(`### ${emojis.error} Access Restricted`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay("This operational control panel is strictly restricted to authorized bot owners.")
				.build();

			return sendReply({
				components: [denyContainer],
				flags: MessageFlags.IsComponentsV2,
				ephemeral: true,
			});
		}

		let currentView: ActiveView = "overview";
		const actionPrefix = `ops_${user.id}_${Date.now()}`;

		const renderPanel = async (view: ActiveView) => {
			const metrics = await fetchSystemMetrics(client);
			let container: any;

			if (view === "errors") {
				container = await buildErrorsPanel(colors, emojis);
			} else if (view === "actions") {
				container = await buildActionsPanel(colors, emojis);
			} else if (view === "caches") {
				container = buildCachesPanel(metrics, colors, emojis);
			} else if (view === "ratelimits") {
				container = buildRateLimitsPanel(colors, emojis);
			} else {
				container = buildOverviewPanel(metrics, colors, emojis);
			}

			const buttons = buildActionButtons(actionPrefix, view, metrics.lbStatus.isRunning, emojis);
			return { container, buttons };
		};

		const initial = await renderPanel(currentView);
		const initialPayload = {
			components: [initial.container, ...initial.buttons],
			flags: MessageFlags.IsComponentsV2,
			ephemeral: true,
		};

		const sent = await sendReply(initialPayload);

		if (!sent?.createMessageComponentCollector) return;

		const collector = sent.createMessageComponentCollector({
			time: 300_000,
			filter: (i: any) => i.customId.startsWith(`${actionPrefix}:`),
		});

		collector.on("collect", async (interaction: any) => {
			try {
				// Re-verify authorization on every single interaction
				if (!isBotOwner(interaction.user.id)) {
					return interaction.reply({
						content: "❌ Unauthorized: You do not have bot owner authority to perform operational actions.",
						ephemeral: true,
					});
				}

				const parts = interaction.customId.split(":");
				const type = parts[1];
				const target = parts[2];

				if (type === "view") {
					currentView = target as ActiveView;
					const updated = await renderPanel(currentView);
					return interaction.update({
						components: [updated.container, ...updated.buttons],
						flags: MessageFlags.IsComponentsV2,
					});
				}

				if (type === "act") {
					if (target === "refresh") {
						const updated = await renderPanel(currentView);
						return interaction.update({
							components: [updated.container, ...updated.buttons],
							flags: MessageFlags.IsComponentsV2,
						});
					}

					if (target === "clear_caches") {
						// Safe in-memory purge without affecting persistent DB
						EconomyManager.clearMemoryCaches();
						LeaderboardManager.clearMemoryCaches();
						TicketManager.clearMemoryCaches();
						PermissionService.clearCache();

						const updated = await renderPanel("caches");
						currentView = "caches";
						return interaction.update({
							components: [updated.container, ...updated.buttons],
							flags: MessageFlags.IsComponentsV2,
						});
					}

					if (target === "toggle_scheduler") {
						const status = LeaderboardManager.getLastRefreshStatus();
						if (status.isRunning) {
							LeaderboardManager.stopScheduler();
						} else {
							LeaderboardManager.startScheduler(client);
						}
						const updated = await renderPanel(currentView);
						return interaction.update({
							components: [updated.container, ...updated.buttons],
							flags: MessageFlags.IsComponentsV2,
						});
					}

					if (target === "close") {
						collector.stop("closed");
						const closedContainer = new ContainerBuilder()
							.setAccentColor(colors.default)
							.addTextDisplay(`### ${emojis.bot} Operational Control Panel Closed`)
							.addTextDisplay("Dashboard session ended. Run `.status` or `/status` to reopen.")
							.build();
						return interaction.update({
							components: [closedContainer],
							flags: MessageFlags.IsComponentsV2,
						});
					}
				}
			} catch (err) {
				logger.error("[StatusControlPanel] Interaction error:", err);
				if (!interaction.replied && !interaction.deferred) {
					await interaction.reply({ content: "Operation encountered an unexpected error.", ephemeral: true }).catch(() => null);
				}
			}
		});

		collector.on("end", async () => {
			try {
				const finalUpdated = await renderPanel(currentView);
				const disabledButtons = buildActionButtons(actionPrefix, currentView, false, emojis);
				for (const row of disabledButtons) {
					const comps = (row as any).actionRow?.components || (row as any).components || [];
					for (const btn of comps) {
						if (btn.setDisabled) btn.setDisabled(true);
						else btn.disabled = true;
					}
				}
				if (sent?.edit) {
					await sent.edit({
						components: [finalUpdated.container, ...disabledButtons],
						flags: MessageFlags.IsComponentsV2,
					}).catch(() => null);
				}
			} catch {}
		});
	},
};

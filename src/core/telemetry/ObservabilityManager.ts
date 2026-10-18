import logger from "@logger";
import config from "@config";

export interface SafeTelemetryEvent {
	name: string;
	params?: Record<string, string | number>;
	timestamp?: number;
}

export interface WebhookLogPayload {
	severity: "info" | "warn" | "error" | "security";
	title: string;
	description: string;
	fields?: Array<{ name: string; value: string; inline?: boolean }>;
	timestamp?: Date;
}

export class ObservabilityManager {
	private static readonly MAX_QUEUE_SIZE = 1000;
	private static readonly BATCH_SIZE = 25;
	private static readonly FLUSH_INTERVAL_MS = 2000;
	private static readonly MAX_RETRIES = 3;

	// In-memory bounded queues
	private static gaQueue: SafeTelemetryEvent[] = [];
	private static webhookQueue: WebhookLogPayload[] = [];
	private static recentEvents: Array<{ name: string; params: Record<string, any>; timestamp: number }> = [];
	private static readonly MAX_RECENT_EVENTS = 25;

	// Operational counters
	private static totalEventsEnqueued = 0;
	private static totalEventsSent = 0;
	private static totalEventsDropped = 0;
	private static totalWebhooksSent = 0;
	private static totalWebhooksDropped = 0;

	// Deduplication cache for repeated webhook errors
	private static recentWebhookMessages = new Map<string, { count: number; firstSeen: number; lastSent: number }>();

	private static workerTimer: NodeJS.Timeout | null = null;
	private static isFlushing = false;
	private static isShutdown = false;

	// Optional overrides
	private static overrideMeasurementId: string | null = null;
	private static overrideApiSecret: string | null = null;
	private static overrideWebhookUrl: string | null = null;

	public static init(): void {
		const mId = this.getMeasurementId();
		const secret = this.getApiSecret();
		const whUrl = this.getWebhookUrl();

		if (mId && secret) {
			logger.info(`[Observability] GA4 Measurement Protocol active (ID: ${mId.slice(0, 4)}***).`);
		} else {
			logger.info("[Observability] GA4 reporting inactive (set GA4_MEASUREMENT_ID and GA4_API_SECRET in .env to enable).");
		}

		if (whUrl) {
			logger.info("[Observability] Background webhook logging active.");
		} else {
			logger.info("[Observability] Background webhook logging inactive (set DISCORD_LOG_WEBHOOK_URL in .env to enable).");
		}

		if (!this.workerTimer) {
			this.workerTimer = setInterval(() => {
				void this.processQueues();
			}, this.FLUSH_INTERVAL_MS);
			if (this.workerTimer.unref) this.workerTimer.unref();
		}
	}

	public static getMeasurementId(): string | null {
		return this.overrideMeasurementId || process.env.GA4_MEASUREMENT_ID?.trim() || null;
	}

	public static getApiSecret(): string | null {
		return this.overrideApiSecret || process.env.GA4_API_SECRET?.trim() || null;
	}

	public static getWebhookUrl(): string | null {
		return (
			this.overrideWebhookUrl ||
			process.env.DISCORD_LOG_WEBHOOK_URL?.trim() ||
			process.env.LOG_WEBHOOK_URL?.trim() ||
			null
		);
	}

	public static setConfig(options: { measurementId?: string; apiSecret?: string; webhookUrl?: string }): void {
		if (options.measurementId !== undefined) this.overrideMeasurementId = options.measurementId || null;
		if (options.apiSecret !== undefined) this.overrideApiSecret = options.apiSecret || null;
		if (options.webhookUrl !== undefined) this.overrideWebhookUrl = options.webhookUrl || null;
	}

	public static isGa4Enabled(): boolean {
		return Boolean(this.getMeasurementId() && this.getApiSecret());
	}

	public static isWebhookEnabled(): boolean {
		return Boolean(this.getWebhookUrl());
	}

	/* =========================================================
	 * GA4 EVENT REPORTING (NON-BLOCKING)
	 * ========================================================= */

	/**
	 * Enqueue an operational event asynchronously without blocking caller.
	 */
	public static recordEvent(name: string, params: Record<string, string | number | boolean> = {}): void {
		if (this.isShutdown) return;

		this.totalEventsEnqueued++;

		// GA4 event names: lowercase letters, numbers, underscores, max 40 chars; must start with a letter
		let sanitizedName = name
			.toLowerCase()
			.replace(/[^a-z0-9_]/g, "_")
			.slice(0, 40);

		if (!/^[a-z]/.test(sanitizedName)) {
			sanitizedName = `evt_${sanitizedName}`.slice(0, 40);
		}

		// Sanitize parameters: remove high cardinality, sensitive data, long strings
		// GA4 Measurement Protocol params only accept strings or numbers (no booleans!)
		const sanitizedParams: Record<string, string | number> = {
			app_version: "26.7.20",
			environment: config.environment || "production",
		};

		for (const [key, val] of Object.entries(params)) {
			// Skip dangerous keys with PII, secrets, or unbounded user text
			if (/user_?id|guild_?id|token|ip|secret|address|email|password|key|content|stack|prompt|transcript/i.test(key)) {
				continue;
			}
			let paramKey = key.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 40);
			if (!/^[a-z]/.test(paramKey)) {
				paramKey = `p_${paramKey}`.slice(0, 40);
			}

			if (typeof val === "boolean") {
				sanitizedParams[paramKey] = val ? 1 : 0;
			} else if (typeof val === "number") {
				sanitizedParams[paramKey] = Number.isFinite(val) ? val : 0;
			} else if (typeof val === "string") {
				sanitizedParams[paramKey] = val.slice(0, 100);
			}
		}

		// Track in local ring buffer for inspection & status
		this.recentEvents.unshift({
			name: sanitizedName,
			params: sanitizedParams,
			timestamp: Date.now(),
		});
		if (this.recentEvents.length > this.MAX_RECENT_EVENTS) {
			this.recentEvents.pop();
		}

		// If GA4 is not enabled, do not accumulate stale events in memory
		if (!this.isGa4Enabled()) {
			return;
		}

		if (this.gaQueue.length >= this.MAX_QUEUE_SIZE) {
			this.gaQueue.shift(); // Drop oldest
			this.totalEventsDropped++;
			if (this.totalEventsDropped % 50 === 1) {
				logger.warn(`[Observability] GA4 queue full. Dropped ${this.totalEventsDropped} events.`);
			}
		}

		this.gaQueue.push({
			name: sanitizedName,
			params: sanitizedParams,
			timestamp: Date.now(),
		});
	}

	public static recordCommand(
		commandName: string,
		type: "prefix" | "slash" | "hybrid",
		success: boolean,
		durationMs: number,
		errorCategory?: string
	): void {
		this.recordEvent("command_execution", {
			command: commandName,
			command_type: type,
			success: success ? 1 : 0,
			duration_ms: Math.round(durationMs),
			error_category: errorCategory || (success ? "none" : "unknown"),
		});
	}

	public static recordError(category: string, summary: string, severity: "warn" | "error" = "error"): void {
		this.recordEvent("app_error", {
			category: category.slice(0, 40),
			summary: summary.slice(0, 80),
			severity,
		});

		// Also route to webhook if available
		this.logToWebhook({
			severity,
			title: `⚠️ Operational ${severity.toUpperCase()}: ${category.slice(0, 100)}`,
			description: summary.slice(0, 1000),
			fields: [
				{ name: "Category", value: `\`${category.slice(0, 50)}\``, inline: true },
				{ name: "Environment", value: `\`${config.environment}\``, inline: true },
			],
		});
	}

	public static recordLifecycleEvent(event: "startup" | "shutdown" | "recovery"): void {
		this.recordEvent(`app_${event}`, { status: "ok" });
		this.logToWebhook({
			severity: event === "shutdown" ? "warn" : "info",
			title: `🔄 System Event: ${event.toUpperCase()}`,
			description: `MomentumOne node reported lifecycle event \`${event}\`.`,
		});
	}

	public static recordTicketEvent(action: string, success: boolean): void {
		this.recordEvent("ticket_workflow", {
			action: action.slice(0, 40),
			success: success ? 1 : 0,
		});
	}

	public static recordWithdrawalEvent(action: string, success: boolean, amount?: number): void {
		this.recordEvent("withdrawal_workflow", {
			action: action.slice(0, 40),
			success: success ? 1 : 0,
			amount: amount !== undefined ? Math.round(amount) : 0,
		});
	}

	public static recordSchedulerEvent(action: string, success: boolean, details?: string): void {
		this.recordEvent("scheduler_event", {
			action: action.slice(0, 40),
			success: success ? 1 : 0,
			details: (details || "ok").slice(0, 80),
		});
	}

	public static recordDatabaseEvent(action: string, success: boolean, durationMs?: number): void {
		this.recordEvent("database_event", {
			action: action.slice(0, 40),
			success: success ? 1 : 0,
			duration_ms: durationMs !== undefined ? Math.round(durationMs) : 0,
		});
	}

	public static recordInteractionEvent(componentType: string, customId: string, success: boolean): void {
		this.recordEvent("component_interaction", {
			type: componentType.slice(0, 20),
			custom_id: customId.slice(0, 40),
			success: success ? 1 : 0,
		});
	}

	public static recordSecurityEvent(
		action: string,
		severity: "low" | "medium" | "high" | "critical",
		details: string
	): void {
		this.recordEvent("security_alert", {
			action: action.slice(0, 40),
			severity,
		});

		this.logToWebhook({
			severity: severity === "critical" || severity === "high" ? "error" : "warn",
			title: `🛡️ Security Alert: ${action.slice(0, 100)}`,
			description: details.slice(0, 1200),
			fields: [
				{ name: "Severity", value: `\`${severity.toUpperCase()}\``, inline: true },
				{ name: "Timestamp", value: `<t:${Math.floor(Date.now() / 1000)}:R>`, inline: true },
			],
		});
	}

	/* =========================================================
	 * WEBHOOK LOGGING (NON-BLOCKING)
	 * ========================================================= */

	public static logToWebhook(payload: WebhookLogPayload): void {
		if (this.isShutdown || !this.isWebhookEnabled()) return;

		// Deduplicate identical errors within 60 seconds
		const dedupeKey = `${payload.severity}:${payload.title}:${payload.description.slice(0, 100)}`;
		const now = Date.now();
		const existing = this.recentWebhookMessages.get(dedupeKey);

		if (existing && now - existing.lastSent < 60_000) {
			existing.count++;
			return; // Suppress spamming webhook
		}

		if (existing && existing.count > 1) {
			payload.description += `\n*(Repeated ${existing.count} times in the last minute)*`;
		}

		this.recentWebhookMessages.set(dedupeKey, { count: 1, firstSeen: now, lastSent: now });

		// Prune old dedupe keys
		if (this.recentWebhookMessages.size > 200) {
			for (const [k, v] of this.recentWebhookMessages.entries()) {
				if (now - v.lastSent > 120_000) {
					this.recentWebhookMessages.delete(k);
				}
			}
		}

		if (this.webhookQueue.length >= this.MAX_QUEUE_SIZE) {
			this.webhookQueue.shift();
			this.totalWebhooksDropped++;
			return;
		}

		this.webhookQueue.push({
			...payload,
			timestamp: payload.timestamp || new Date(),
		});
	}

	/* =========================================================
	 * BACKGROUND QUEUE WORKER
	 * ========================================================= */

	private static async processQueues(): Promise<void> {
		if (this.isFlushing) return;
		this.isFlushing = true;

		try {
			await Promise.all([
				this.flushGaBatch(),
				this.flushWebhookBatch(),
			]);
		} catch (err) {
			logger.error("[Observability] Error processing background queues:", err);
		} finally {
			this.isFlushing = false;
		}
	}

	private static async flushGaBatch(): Promise<void> {
		if (!this.isGa4Enabled() || this.gaQueue.length === 0) return;

		const batch = this.gaQueue.splice(0, this.BATCH_SIZE);
		if (batch.length === 0) return;

		const mId = this.getMeasurementId()!;
		const secret = this.getApiSecret()!;

		const endpoint = `https://www.google-analytics.com/mp/collect?measurement_id=${encodeURIComponent(
			mId
		)}&api_secret=${encodeURIComponent(secret)}`;

		const payload = {
			client_id: "momentumone_bot_node_1",
			non_personalized_ads: true,
			events: batch.map((item) => ({
				name: item.name,
				params: {
					...item.params,
					engagement_time_msec: 100,
				},
			})),
		};

		let retries = 0;
		while (retries < this.MAX_RETRIES) {
			try {
				const controller = new AbortController();
				const timeout = setTimeout(() => controller.abort(), 3500);

				const response = await fetch(endpoint, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload),
					signal: controller.signal,
				});
				clearTimeout(timeout);

				if (response.ok || response.status === 204) {
					this.totalEventsSent += batch.length;
					break; // Success
				}

				if (response.status === 429 || response.status >= 500) {
					retries++;
					await new Promise((r) => setTimeout(r, 200 * 2 ** retries));
					continue;
				}

				// Client error (400, 401) - do not retry endlessly
				logger.debug(`[Observability] GA4 returned HTTP ${response.status}`);
				break;
			} catch {
				retries++;
				if (retries >= this.MAX_RETRIES) {
					logger.debug(`[Observability] GA4 network delivery failed after ${this.MAX_RETRIES} attempts.`);
				}
			}
		}
	}

	private static async flushWebhookBatch(): Promise<void> {
		const whUrl = this.getWebhookUrl();
		if (!whUrl || this.webhookQueue.length === 0) return;

		// Discord webhooks accept up to 10 embeds per single POST request
		const batch = this.webhookQueue.splice(0, 10);
		if (batch.length === 0) return;

		const colorMap: Record<string, number> = {
			info: 0x3b82f6,
			warn: 0xf59e0b,
			error: 0xef4444,
			security: 0x8b5cf6,
		};

		const embeds = batch.map((item) => ({
			title: item.title.slice(0, 250),
			description: item.description.slice(0, 2000),
			color: colorMap[item.severity] || 0x64748b,
			fields: item.fields?.slice(0, 10),
			timestamp: (item.timestamp || new Date()).toISOString(),
			footer: { text: "MomentumOne Observability" },
		}));

		try {
			const controller = new AbortController();
			const timeout = setTimeout(() => controller.abort(), 3500);

			const res = await fetch(whUrl, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ embeds }),
				signal: controller.signal,
			});
			clearTimeout(timeout);

			if (res.status === 429) {
				const retryAfter = (await res.json().catch(() => ({})))?.retry_after ?? 2;
				await new Promise((r) => setTimeout(r, Math.min(retryAfter * 1000, 5000)));
			} else if (res.ok) {
				this.totalWebhooksSent += batch.length;
			}
		} catch {
			// Never throw or break caller on webhook failure
		}
	}

	/* =========================================================
	 * METRICS, DIAGNOSTICS & TESTING
	 * ========================================================= */

	public static getStats() {
		return {
			ga4: {
				enabled: this.isGa4Enabled(),
				measurementIdConfigured: Boolean(this.getMeasurementId()),
				apiSecretConfigured: Boolean(this.getApiSecret()),
				queued: this.gaQueue.length,
				sent: this.totalEventsSent,
				dropped: this.totalEventsDropped,
			},
			webhook: {
				enabled: this.isWebhookEnabled(),
				configured: Boolean(this.getWebhookUrl()),
				queued: this.webhookQueue.length,
				sent: this.totalWebhooksSent,
				dropped: this.totalWebhooksDropped,
			},
			eventsTotal: this.totalEventsEnqueued,
			recentEvents: [...this.recentEvents],
		};
	}

	/**
	 * Run a live validation test of configured endpoints.
	 */
	public static async testDelivery(): Promise<{
		ga4: { ok: boolean; status: number; message: string };
		webhook: { ok: boolean; status: number; message: string };
	}> {
		const results = {
			ga4: { ok: false, status: 0, message: "Not configured" },
			webhook: { ok: false, status: 0, message: "Not configured" },
		};

		// 1. Test GA4 via official debug endpoint
		const mId = this.getMeasurementId();
		const secret = this.getApiSecret();
		if (mId && secret) {
			try {
				const debugEndpoint = `https://www.google-analytics.com/debug/mp/collect?measurement_id=${encodeURIComponent(
					mId
				)}&api_secret=${encodeURIComponent(secret)}`;

				const payload = {
					client_id: "test_probe_client",
					non_personalized_ads: true,
					events: [
						{
							name: "test_probe",
							params: {
								environment: config.environment || "production",
								timestamp: Date.now(),
							},
						},
					],
				};

				const res = await fetch(debugEndpoint, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload),
				});

				const data = (await res.json().catch(() => ({}))) as any;
				const validationMsgs = data?.validationMessages || [];

				if (res.ok && validationMsgs.length === 0) {
					results.ga4 = { ok: true, status: res.status, message: "GA4 payload validated successfully." };
				} else {
					const issue = validationMsgs.map((m: any) => m.description).join("; ") || `HTTP ${res.status}`;
					results.ga4 = { ok: false, status: res.status, message: `Validation issue: ${issue}` };
				}
			} catch (err: any) {
				results.ga4 = { ok: false, status: 500, message: err?.message || "Connection failed" };
			}
		}

		// 2. Test Discord Webhook
		const whUrl = this.getWebhookUrl();
		if (whUrl) {
			try {
				const res = await fetch(whUrl, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						embeds: [
							{
								title: "🧪 Observability Diagnostic Probe",
								description: "This is an automated verification probe sent from MomentumOne.",
								color: 0x10b981,
								timestamp: new Date().toISOString(),
							},
						],
					}),
				});

				results.webhook = {
					ok: res.ok,
					status: res.status,
					message: res.ok ? "Webhook delivered successfully." : `Discord returned HTTP ${res.status}`,
				};
			} catch (err: any) {
				results.webhook = { ok: false, status: 500, message: err?.message || "Connection failed" };
			}
		}

		return results;
	}

	public static async shutdown(timeoutMs = 2000): Promise<void> {
		this.isShutdown = true;
		if (this.workerTimer) {
			clearInterval(this.workerTimer);
			this.workerTimer = null;
		}

		const deadline = Date.now() + timeoutMs;
		while ((this.gaQueue.length > 0 || this.webhookQueue.length > 0) && Date.now() < deadline) {
			await this.processQueues();
		}
	}
}

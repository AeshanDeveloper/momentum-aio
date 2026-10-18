import logger from "@logger";
import { ObservabilityManager } from "./ObservabilityManager";

export interface RateLimitEvent {
	timestamp: Date;
	timeoutMs: number;
	limit: number;
	method?: string;
	path?: string;
	route?: string;
	global: boolean;
}

export interface ApiFailureEvent {
	timestamp: Date;
	method?: string;
	path?: string;
	status?: number;
	code?: number | string;
	message: string;
}

export class DiscordTelemetry {
	private static rateLimitEvents: RateLimitEvent[] = [];
	private static apiFailures: ApiFailureEvent[] = [];
	private static readonly MAX_ENTRIES = 50;
	private static isHooked = false;

	public static hook(client: any): void {
		if (this.isHooked || !client?.rest) return;
		this.isHooked = true;

		try {
			client.rest.on("rateLimited", (info: any) => {
				const event: RateLimitEvent = {
					timestamp: new Date(),
					timeoutMs: info.timeToReset ?? info.timeout ?? 0,
					limit: info.limit ?? 0,
					method: info.method,
					path: info.url || info.path,
					route: info.route,
					global: Boolean(info.global),
				};
				this.rateLimitEvents.unshift(event);
				if (this.rateLimitEvents.length > this.MAX_ENTRIES) {
					this.rateLimitEvents.pop();
				}
				logger.warn(`[DiscordTelemetry] Rate limited on route ${event.route || event.path} (${event.timeoutMs}ms)`);
				ObservabilityManager.recordEvent("discord_ratelimit", {
					route: (event.route || event.path || "unknown").slice(0, 40),
					timeout_ms: event.timeoutMs,
					limit: event.limit,
					global: event.global ? 1 : 0,
				});
			});

			client.rest.on("invalidRequestWarning", (info: any) => {
				this.recordFailure({
					timestamp: new Date(),
					message: `Invalid request warning: count ${info.count}, remaining ${info.remainingTime}ms`,
				});
			});
		} catch (err) {
			logger.error("[DiscordTelemetry] Failed to attach client rest listeners:", err);
		}
	}

	public static recordRateLimit(event: Omit<RateLimitEvent, "timestamp">): void {
		this.rateLimitEvents.unshift({ ...event, timestamp: new Date() });
		if (this.rateLimitEvents.length > this.MAX_ENTRIES) {
			this.rateLimitEvents.pop();
		}
	}

	public static recordFailure(failure: ApiFailureEvent): void {
		this.apiFailures.unshift(failure);
		if (this.apiFailures.length > this.MAX_ENTRIES) {
			this.apiFailures.pop();
		}
	}

	public static getRateLimitEvents(): RateLimitEvent[] {
		return [...this.rateLimitEvents];
	}

	public static getApiFailures(): ApiFailureEvent[] {
		return [...this.apiFailures];
	}

	public static getStats() {
		return {
			rateLimitsTotal: this.rateLimitEvents.length,
			lastRateLimit: this.rateLimitEvents[0]?.timestamp ?? null,
			apiFailuresTotal: this.apiFailures.length,
			lastApiFailure: this.apiFailures[0]?.timestamp ?? null,
		};
	}
}

export default DiscordTelemetry;

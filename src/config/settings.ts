export default {
	bot: {
		name: "Mussoorie",
		description: "",
		prefix: "$",
		owner_ids: ["1131339559016333465"],
        min_tip: 1,
        invite: "https://discord.com/oauth2/authorize?client_id="+ (process.env.CLIENT_ID || ""),
        supportInvite: "https://discord.gg/EaD6efwNpa",
		currency: {
			name: "INR"
		},
        
        team: {
            name: "Momentum Development"
        }
	},
	intervals: {
		leaderboard_refresh: 300_000, // 5 minutes
		anti_spam_window: 30_000,     // 30 seconds
		blacklist_cache_sync: 60_000, // 1 minute
		no_prefix_cache_sync: 60_000, // 1 minute
		cache_ttl: 60_000,            // 1 minute default cache TTL
	},
	observability: {
		ga4MeasurementId: process.env.GA4_MEASUREMENT_ID || "",
		ga4ApiSecret: process.env.GA4_API_SECRET || "",
		webhookUrl: process.env.DISCORD_LOG_WEBHOOK_URL || process.env.LOG_WEBHOOK_URL || "",
		logLevel: process.env.LOG_LEVEL || "info",
	},
	ai: {
		defaultModel: process.env.GEMINI_MODEL || "gemini-3.8-flash",
		isConfigured: Boolean(process.env.GEMINI_API_KEY?.trim()),
	},
}
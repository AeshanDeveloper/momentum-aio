import assert from "node:assert";
import { createRequire } from "node:module";
import { ObservabilityManager } from "../src/core/telemetry/ObservabilityManager";
import DiscordTelemetry from "../src/core/telemetry/DiscordTelemetry";

const require = createRequire(import.meta.url);

async function runTests() {
	console.log("=======================================================");
	console.log("   MomentumOne: AI & Observability System Tests       ");
	console.log("=======================================================");

	// 1. ObservabilityManager Initialization
	console.log("\n1. Testing ObservabilityManager Initialization & Fallbacks...");
	ObservabilityManager.init();
	const initialStats = ObservabilityManager.getStats();
	assert.strictEqual(typeof initialStats.eventsTotal, "number");
	assert.strictEqual(typeof initialStats.ga4.enabled, "boolean");
	assert.strictEqual(typeof initialStats.webhook.enabled, "boolean");
	console.log("  ✅ [PASS] ObservabilityManager initialized cleanly without exceptions.");

	// 2. Event Recording & Parameter Sanitization
	console.log("\n2. Testing Event Recording & Sanitization (Booleans, PII removal)...");
	const beforeTotal = initialStats.eventsTotal;
	ObservabilityManager.recordEvent("test_action", {
		success: true, // Boolean must be sanitized for GA4
		count: 42,
		secret_token: "DO_NOT_LEAK", // Dangerous key must be stripped
		user_id: "123456789", // PII must be stripped
		details: "Normal operational event",
	});

	const statsAfter = ObservabilityManager.getStats();
	assert.strictEqual(statsAfter.eventsTotal, beforeTotal + 1, "Event count incremented");

	const lastEvent = statsAfter.recentEvents[0];
	assert.strictEqual(lastEvent.name, "test_action");
	assert.strictEqual(lastEvent.params.success, 1, "Boolean converted to numeric 1 for GA4 MP compliance");
	assert.strictEqual(lastEvent.params.count, 42);
	assert.strictEqual(lastEvent.params.secret_token, undefined, "Sensitive token stripped");
	assert.strictEqual(lastEvent.params.user_id, undefined, "PII user_id stripped");
	console.log("  ✅ [PASS] Event name and parameters sanitized strictly according to GA4 specs.");

	// 3. Command Execution & Error Recording
	console.log("\n3. Testing Command and Error Logging...");
	ObservabilityManager.recordCommand("balance", "slash", true, 45);
	ObservabilityManager.recordCommand("withdraw", "prefix", false, 120, "insufficient_funds");
	ObservabilityManager.recordError("test_db_error", "Simulated query timeout", "warn");
	ObservabilityManager.recordTicketEvent("create_withdrawal", true);
	ObservabilityManager.recordWithdrawalEvent("payout", true, 500);

	const statsCommands = ObservabilityManager.getStats();
	assert(statsCommands.recentEvents.some((e) => e.name === "command_execution"), "command_execution recorded");
	assert(statsCommands.recentEvents.some((e) => e.name === "app_error"), "app_error recorded");
	assert(statsCommands.recentEvents.some((e) => e.name === "ticket_workflow"), "ticket_workflow recorded");
	console.log("  ✅ [PASS] Specialized command, error, ticket, and withdrawal telemetry recorded.");

	// 4. DiscordTelemetry rate limits forwarding
	console.log("\n4. Testing DiscordTelemetry rate limit forwarding...");
	DiscordTelemetry.recordRateLimit({
		timeoutMs: 1200,
		limit: 5,
		route: "/channels/123/messages",
		global: false,
	});
	const dtStats = DiscordTelemetry.getStats();
	assert.strictEqual(dtStats.rateLimitsTotal >= 1, true, "Rate limit recorded in DiscordTelemetry");
	console.log("  ✅ [PASS] DiscordTelemetry tracks rate limits and API failures.");

	// 5. Test Live Diagnostics Probe
	console.log("\n5. Testing Live Diagnostics Probe (testDelivery)...");
	const testProbe = await ObservabilityManager.testDelivery();
	assert.strictEqual(typeof testProbe.ga4.ok, "boolean");
	assert.strictEqual(typeof testProbe.webhook.ok, "boolean");
	console.log(`  Probe status: GA4=${testProbe.ga4.message}, Webhook=${testProbe.webhook.message}`);
	console.log("  ✅ [PASS] testDelivery returns diagnostic report without throwing.");

	// 6. Test AI Command Module Loading & Validation
	console.log("\n6. Testing AI Command Structure...");
	const rawAiCommand = require("../src/plugins/MomentumOneToolkit/commands/ai/ai.ts");
	const aiCommand = rawAiCommand?.default ?? rawAiCommand;
	assert.strictEqual(aiCommand.name, "ai", "AI command name is 'ai'");
	assert.strictEqual(aiCommand.ownerOnly, false, "AI command is NOT owner-only (available to users)");
	assert.strictEqual(typeof aiCommand.execute, "function", "AI command has execute function");
	assert(aiCommand.builder !== undefined, "SlashCommandBuilder is defined");

	// Inspect slash options
	const builderJson = aiCommand.builder.toJSON();
	assert.strictEqual(builderJson.name, "ai");
	const promptOpt = builderJson.options?.find((o: any) => o.name === "prompt");
	assert(promptOpt !== undefined, "Has required 'prompt' string option");
	assert.strictEqual(promptOpt.required, true, "'prompt' option is required");

	console.log("  ✅ [PASS] AI Command has slash builder with prompt option and open permissions.");

	// 7. Test AI Execution without API key (Graceful notice)
	console.log("\n7. Testing AI Execution Graceful Notice when GEMINI_API_KEY is unset...");
	const originalApiKey = process.env.GEMINI_API_KEY;
	delete process.env.GEMINI_API_KEY;

	let replyPayload: any = null;
	const mockInteraction = {
		user: { id: "test_user_ai", tag: "tester#0001" },
		options: {
			getString: (name: string) => (name === "prompt" ? "Hello AI, what is 2+2?" : null),
		},
		deferReply: async () => {},
		editReply: async (p: any) => {
			replyPayload = p;
		},
		reply: async (p: any) => {
			replyPayload = p;
		},
	};

	await aiCommand.execute(null, 2, mockInteraction); // CommandType.SLASH = 2
	assert(replyPayload !== null, "Reply was delivered");
	assert(replyPayload.components && replyPayload.components.length > 0, "Components V2 rendered");
	console.log("  ✅ [PASS] AI gracefully provides setup instructions when API key is not configured.");

	// Restore original key if present
	if (originalApiKey) process.env.GEMINI_API_KEY = originalApiKey;

	console.log("\n=======================================================");
	console.log("   All AI & Observability Tests Passed Successfully!   ");
	console.log("=======================================================");
}

runTests().catch((err) => {
	console.error("Test failed:", err);
	process.exit(1);
});

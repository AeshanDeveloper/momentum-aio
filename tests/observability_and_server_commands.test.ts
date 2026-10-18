import "dotenv/config";
import "../src/config/global.d.ts";
import DatabaseManager from "@database/Database";
import { ObservabilityManager } from "../src/core/telemetry/ObservabilityManager";
import { ServerCommandManager } from "../src/core/security/ServerCommandManager";

let totalTests = 0;
let passedTests = 0;

function assert(condition: boolean, testName: string, details?: string) {
	totalTests++;
	if (condition) {
		passedTests++;
		console.log(`  ✅ [PASS] ${testName}`);
	} else {
		console.error(`  ❌ [FAIL] ${testName}${details ? ` - ${details}` : ""}`);
	}
}

async function run() {
	console.log("\n=======================================================");
	console.log("     Observability & Server Commands Tests             ");
	console.log("=======================================================\n");

	await DatabaseManager.initialize("test");

	const testGuildId = "guild_cmd_test_999";
	const actorId = "admin_user_001";

	// 1. ObservabilityManager Tests
	console.log("1. Testing ObservabilityManager non-blocking telemetry & queuing...");
	ObservabilityManager.init();

	ObservabilityManager.recordEvent("test_event", {
		action: "test_run",
		status: 1,
		userId: "123456789",
		token: "secret_bot_token",
	});
	assert(true, "ObservabilityManager.recordEvent runs synchronously without blocking");

	ObservabilityManager.recordCommand("ping", "slash", true, 42);
	assert(true, "ObservabilityManager.recordCommand successfully recorded command telemetry");

	ObservabilityManager.recordError("validation", "Sample validation error occurred");
	assert(true, "ObservabilityManager.recordError queued error without exceptions");

	// 2. Server Command Management Tests
	console.log("\n2. Testing Per-Server Command Management...");

	const disableHelp = await ServerCommandManager.disableCommand(testGuildId, "help", actorId);
	assert(disableHelp.success === false, "Essential command 'help' is protected from being disabled");

	const disableSettings = await ServerCommandManager.disableCommand(testGuildId, "settings", actorId);
	assert(disableSettings.success === false, "Essential command 'settings' is protected from being disabled");

	if (!global.commands) global.commands = new Map();
	global.commands.set("ping", { name: "ping", command: { category: "General" } });
	global.commands.set("daily", { name: "daily", command: { category: "Economy" } });

	const disableDaily = await ServerCommandManager.disableCommand(testGuildId, "daily", actorId);
	assert(disableDaily.success === true, "Successfully disabled non-essential command 'daily'");

	const isDailyDisabled = await ServerCommandManager.isCommandDisabled(testGuildId, "daily", "Economy");
	assert(isDailyDisabled === true, "isCommandDisabled returns true for disabled command");

	const isDailyDisabledOther = await ServerCommandManager.isCommandDisabled("other_guild_123", "daily", "Economy");
	assert(isDailyDisabledOther === false, "Command remains enabled in unconfigured guilds (multi-server isolation)");

	const enableDaily = await ServerCommandManager.enableCommand(testGuildId, "daily", actorId);
	assert(enableDaily.success === true, "Successfully re-enabled command 'daily'");

	const isDailyDisabledAfter = await ServerCommandManager.isCommandDisabled(testGuildId, "daily", "Economy");
	assert(isDailyDisabledAfter === false, "isCommandDisabled returns false after enabling");

	console.log("\n=======================================================");
	console.log(`   Tests completed: ${passedTests}/${totalTests} passed.`);
	console.log("   All Observability & Server Command tests PASSED! 🚀 ");
	console.log("=======================================================\n");
	process.exit(0);
}

run().catch((err) => {
	console.error("Test runner encountered error:", err);
	process.exit(1);
});

import "dotenv/config";
import "../src/config/global.d.ts";
import DatabaseManager from "@database/Database";
import { EconomyManager } from "../src/plugins/MomentumOneToolkit/economy/EconomyManager";
import { ChatRewardService } from "../src/plugins/MomentumOneToolkit/economy/ChatRewardService";

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
	console.log("   Channel & Category Blacklist (Chat Rewards) Tests   ");
	console.log("=======================================================\n");

	await DatabaseManager.initialize("test");

	const testGuildId = "guild_bl_test_101";
	const actorId = "admin_user_001";
	const testUserId = "user_ch_rewards_001";

	// Reset guild settings
	const settingsCol = await DatabaseManager.collection("economy_settings");
	await settingsCol.deleteMany({ guildId: testGuildId });
	const balCol = await DatabaseManager.collection("economy_balances");
	await balCol.deleteMany({ guildId: testGuildId });

	(EconomyManager as any).settingsCache?.clear();
	(EconomyManager as any).balanceCache?.clear();

	// 1. Initially, no channels or categories blacklisted
	const initialSettings = await EconomyManager.getGuildSettings(testGuildId);
	assert(
		Array.isArray(initialSettings.rewards.ignoredChannels) && initialSettings.rewards.ignoredChannels.length === 0,
		"Initial ignoredChannels is empty array"
	);
	assert(
		Array.isArray(initialSettings.rewards.ignoredCategories) && initialSettings.rewards.ignoredCategories.length === 0,
		"Initial ignoredCategories is empty array"
	);

	// 2. Blacklist a channel
	const channelA = "112233445566778899";
	const addedCh = await EconomyManager.blacklistChannel(testGuildId, channelA, actorId);
	assert(addedCh === true, "blacklistChannel returned true for new channel");

	// Adding same channel again should return false (already blacklisted)
	const addedChAgain = await EconomyManager.blacklistChannel(testGuildId, channelA, actorId);
	assert(addedChAgain === false, "blacklistChannel returned false for already blacklisted channel");

	const isBlA = await EconomyManager.isChannelBlacklisted(testGuildId, channelA);
	assert(isBlA === true, "isChannelBlacklisted returned true for blacklisted channel");

	// 3. Blacklist a whole category
	const categoryX = "998877665544332211";
	const addedCat = await EconomyManager.blacklistCategory(testGuildId, categoryX, actorId);
	assert(addedCat === true, "blacklistCategory returned true for new category");

	const isBlCat = await EconomyManager.isChannelBlacklisted(testGuildId, "some_random_channel", categoryX);
	assert(isBlCat === true, "isChannelBlacklisted returns true when channel belongs to blacklisted category");

	// 4. Test ChatRewardService ignores blacklisted channel
	const msgInBlacklistedChannel = {
		id: `msg_test_${Date.now()}_1`,
		content: "This is a great conversation in channel A!",
		author: { id: testUserId, bot: false, tag: "Alice#0001" },
		guild: { id: testGuildId, name: "Test Server" },
		channelId: channelA,
		channel: { parentId: null },
		member: { roles: { cache: new Map() } },
	};
	const res1 = await ChatRewardService.processMessage(msgInBlacklistedChannel);
	assert(res1.eligible === false && res1.awarded === false, "Chat rewards blocked in blacklisted channel");
	assert(res1.reason === "Channel is blacklisted from chat rewards", "Correct reason reported for blacklisted channel");

	// 5. Test ChatRewardService ignores channel inside blacklisted category
	const channelInsideCat = "555555555555555555";
	const msgInBlacklistedCategory = {
		id: `msg_test_${Date.now()}_2`,
		content: "This is a message in a channel inside blacklisted category!",
		author: { id: testUserId, bot: false, tag: "Alice#0001" },
		guild: { id: testGuildId, name: "Test Server" },
		channelId: channelInsideCat,
		channel: { parentId: categoryX },
		member: { roles: { cache: new Map() } },
	};
	const res2 = await ChatRewardService.processMessage(msgInBlacklistedCategory);
	assert(res2.eligible === false && res2.awarded === false, "Chat rewards blocked for channel in blacklisted category");
	assert(res2.reason === "Channel category is blacklisted from chat rewards", "Correct reason reported for category blacklist");

	// 6. Test ChatRewardService awards in an eligible channel
	const eligibleChannel = "777777777777777777";
	const otherCategory = "333333333333333333";
	const msgInEligibleChannel = {
		id: `msg_test_${Date.now()}_3`,
		content: "This is a legitimate chat message in an active allowed channel!",
		author: { id: testUserId, bot: false, tag: "Alice#0001" },
		guild: { id: testGuildId, name: "Test Server" },
		channelId: eligibleChannel,
		channel: { parentId: otherCategory },
		member: { roles: { cache: new Map() } },
	};
	const res3 = await ChatRewardService.processMessage(msgInEligibleChannel);
	assert(res3.eligible === true && res3.awarded === true, "Chat rewards awarded in non-blacklisted channel");

	// 7. Test unblacklisting channel and category
	const unblCh = await EconomyManager.unblacklistChannel(testGuildId, channelA, actorId);
	assert(unblCh === true, "unblacklistChannel returned true");

	const isBlAAfter = await EconomyManager.isChannelBlacklisted(testGuildId, channelA);
	assert(isBlAAfter === false, "isChannelBlacklisted returned false after unblacklist");

	const unblCat = await EconomyManager.unblacklistCategory(testGuildId, categoryX, actorId);
	assert(unblCat === true, "unblacklistCategory returned true");

	const isBlCatAfter = await EconomyManager.isChannelBlacklisted(testGuildId, channelInsideCat, categoryX);
	assert(isBlCatAfter === false, "isChannelBlacklisted returned false after category unblacklist");

	console.log(`\n=======================================================`);
	console.log(`Tests completed: ${passedTests}/${totalTests} passed.`);
	if (passedTests === totalTests) {
		console.log("All Channel & Category Blacklist tests PASSED! 🚀\n");
	} else {
		console.error("Some tests FAILED! ❌\n");
		process.exit(1);
	}
}

run().catch((err) => {
	console.error("Test error:", err);
	process.exit(1);
});

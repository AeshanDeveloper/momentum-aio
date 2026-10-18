import assert from "node:assert";
import { BlacklistManager } from "../src/core/security/BlacklistManager";
import { NoPrefixManager } from "../src/core/security/NoPrefixManager";
import { CooldownManager } from "../src/core/security/CooldownManager";
import { isBotOwner } from "../src/core/security/SecurityHelpers";
import { LeaderboardManager } from "../src/plugins/MomentumOneToolkit/economy/LeaderboardManager";
import { TicketManager } from "../src/plugins/MomentumOneToolkit/tickets/TicketManager";
import { EconomyManager } from "../src/plugins/MomentumOneToolkit/economy/EconomyManager";
import DatabaseManager from "@database/Database";
import config from "@config";

async function runTests() {
	console.log("=======================================================");
	console.log("   MomentumOne: Persistence, Cooldowns & Ticket Tests  ");
	console.log("=======================================================");

	// 1. Blacklist persistence & syncCache
	console.log("\n1. Testing blacklist persistence & cache sync...");
	const testUserId = "999888777666555444";
	const adminId = "111222333444555666";

	// Add blacklist
	const blRes = await BlacklistManager.blacklistUser(testUserId, "1h", "Spamming commands", adminId);
	assert(blRes.success, "Blacklist user succeeded");

	// Verify immediately in cache
	const check1 = await BlacklistManager.isUserBlacklisted(testUserId);
	assert(check1.blacklisted, "User is blacklisted in cache");

	// Sync cache from DB (simulating periodic cache sync or restart)
	await BlacklistManager.syncCache();
	const check2 = await BlacklistManager.isUserBlacklisted(testUserId);
	assert(check2.blacklisted, "User remains blacklisted after database cache sync");

	// Verify in database collection directly
	const blCol = await DatabaseManager.collection("global_blacklists");
	const blDoc = await blCol.findOne({ targetId: testUserId, type: "user" });
	assert(blDoc !== null, "User blacklist is persisted in global_blacklists database");
	assert.strictEqual(blDoc.targetId, testUserId, "Database record targetId matches");

	// Unblacklist
	const unblRes = await BlacklistManager.unblacklistUser(testUserId, adminId);
	assert(unblRes.success, "Unblacklist user succeeded");
	await BlacklistManager.syncCache();
	const check3 = await BlacklistManager.isUserBlacklisted(testUserId);
	assert(!check3.blacklisted, "User is not blacklisted after unblacklist and syncCache");
	console.log("  ✅ [PASS] Blacklist persists to database and survives cache sync");

	// 2. Blacklist exclusions & bot owner protection
	console.log("\n2. Testing blacklist exclusions & bot owner protection...");
	const ownerId = config.settings?.bot?.owner_ids?.[0] || "800888999111222333";
	if (!config.settings.bot.owner_ids.includes(ownerId)) {
		config.settings.bot.owner_ids.push(ownerId);
	}
	assert(isBotOwner(ownerId), "Owner check returns true");
	const ownerBlRes = await BlacklistManager.blacklistUser(ownerId, "1h", "Test", adminId);
	assert(!ownerBlRes.success, "Attempting to blacklist bot owner is strictly rejected");
	const ownerCheck = await BlacklistManager.isUserBlacklisted(ownerId);
	assert(!ownerCheck.blacklisted, "Bot owner is never blacklisted");
	console.log("  ✅ [PASS] Bot owner is protected from blacklisting");

	// 3. No-prefix persistence & cache sync
	console.log("\n3. Testing no-prefix persistence & cache sync...");
	const npUserId = "777888999000111222";
	const npRes = await NoPrefixManager.add(npUserId, "7d", adminId);
	assert(npRes.success, "Granted no-prefix privilege");

	// Check immediate lookup
	const hasNp1 = await NoPrefixManager.hasNoPrefix(npUserId);
	assert(hasNp1, "User has no-prefix in cache");

	// Sync cache from DB
	await NoPrefixManager.syncCache();
	const hasNp2 = await NoPrefixManager.hasNoPrefix(npUserId);
	assert(hasNp2, "User still has no-prefix after database sync");

	// Check DB collection directly
	const npCol = await DatabaseManager.collection("no_prefix_users");
	const npDoc = await npCol.findOne({ userId: npUserId });
	assert(npDoc !== null, "No-prefix user is persisted in no_prefix_users database collection");

	// Remove no-prefix
	const npRemRes = await NoPrefixManager.remove(npUserId, adminId);
	assert(npRemRes.success, "Revoked no-prefix privilege");
	await NoPrefixManager.syncCache();
	const hasNp3 = await NoPrefixManager.hasNoPrefix(npUserId);
	assert(!hasNp3, "User no longer has no-prefix after revocation");
	console.log("  ✅ [PASS] No-prefix persists to database and survives cache sync");

	// 4. CooldownManager seconds vs milliseconds and bot owner bypass
	console.log("\n4. Testing CooldownManager units & bypass...");
	const cmdMs = { name: "test_ms", cooldown: 5000 }; // 5000ms = 5s
	const cmdSec = { name: "test_sec", cooldown: 5 }; // 5s = 5000ms
	const regularUser = "123456789012345678";

	// Test regular user cooldown
	CooldownManager.reset("test_ms", regularUser);
	CooldownManager.reset("test_sec", regularUser);

	const cd1 = CooldownManager.check(cmdMs, regularUser);
	assert(!cd1.onCooldown, "User not initially on cooldown");
	CooldownManager.apply(cmdMs, regularUser);
	const cd2 = CooldownManager.check(cmdMs, regularUser);
	assert(cd2.onCooldown, "User is on cooldown after apply (ms)");
	assert(cd2.remainingSeconds <= 5.0 && cd2.remainingSeconds >= 4.0, `Cooldown remaining (${cd2.remainingSeconds}s) is around 5s, not 5000s`);

	CooldownManager.apply(cmdSec, regularUser);
	const cd3 = CooldownManager.check(cmdSec, regularUser);
	assert(cd3.onCooldown, "User is on cooldown after apply (sec)");
	assert(cd3.remainingSeconds <= 5.0 && cd3.remainingSeconds >= 4.0, `Cooldown remaining (${cd3.remainingSeconds}s) is around 5s`);

	// Test bot owner bypass
	const cdOwner = CooldownManager.check(cmdMs, ownerId);
	assert(!cdOwner.onCooldown, "Bot owner is never on cooldown");
	CooldownManager.apply(cmdMs, ownerId);
	const cdOwnerAfter = CooldownManager.check(cmdMs, ownerId);
	assert(!cdOwnerAfter.onCooldown, "Bot owner bypasses applied cooldown");
	console.log("  ✅ [PASS] Cooldown correctly normalizes units (5s vs 5000ms) and exempts owners");

	// 5. Leaderboard message auto-update & inspection
	console.log("\n5. Testing leaderboard setup, inspection & auto-refresh flow...");
	const testGuildId = "guild_test_lb_persist";
	const testChanId = "chan_test_lb_persist";
	const testMsgId = "msg_test_lb_initial";

	// Setup leaderboard with message ID
	const lbSetup = await LeaderboardManager.setupLeaderboard(
		testGuildId,
		"daily",
		testChanId,
		testMsgId,
		adminId,
		{ pageSize: 10, refreshIntervalMinutes: 5 }
	);
	assert(lbSetup.success, "Leaderboard setup succeeded");
	assert.strictEqual(lbSetup.config?.messageId, testMsgId, "Stored messageId correctly");

	// Verify query directly from DB
	const lbCol = await DatabaseManager.collection("economy_leaderboards");
	const lbDoc = await lbCol.findOne({ guildId: testGuildId, type: "daily" });
	assert(lbDoc !== null, "Leaderboard configuration persisted in database");
	assert.strictEqual(lbDoc.messageId, testMsgId, "Database contains correct messageId");

	// Test inspection
	const guildLbs = await LeaderboardManager.getGuildLeaderboards(testGuildId);
	assert.strictEqual(guildLbs.length, 1, "Exactly 1 leaderboard found for test guild");
	assert.strictEqual(guildLbs[0].type, "daily", "Leaderboard type matches");

	// Test headless refresh loop
	await LeaderboardManager.refreshAllLeaderboards(null);
	const lbRefreshed = await lbCol.findOne({ guildId: testGuildId, type: "daily" });
	assert(lbRefreshed.lastRefreshedAt !== null, "lastRefreshedAt updated after refresh cycle");

	// Clean up leaderboard
	const delRes = await LeaderboardManager.removeLeaderboard(testGuildId, "daily", adminId);
	const lbAfterRemove = await lbCol.findOne({ guildId: testGuildId, type: "daily" });
	if (lbAfterRemove !== null) {
		console.log("DEBUG: delRes=", delRes, "lbAfterRemove=", lbAfterRemove);
		const allMatching = await lbCol.find({ guildId: testGuildId }).toArray();
		console.log("DEBUG: allMatching=", allMatching);
	}
	assert.strictEqual(lbAfterRemove, null, "Leaderboard removed from database");
	console.log("  ✅ [PASS] Leaderboard persists messageId, supports inspection and cleans up on remove");

	// 6. Withdrawal tickets and button processing idempotency
	console.log("\n6. Testing withdrawal tickets, reservation, and button handling...");
	const wUser = "withdrawal_user_test";
	const wGuildId = "guild_withdraw_test";

	// Fund user balance
	await EconomyManager.adminResetBalance(wGuildId, "admin", wUser, "Reset before test");
	await EconomyManager.creditBalance(wGuildId, wUser, 100, "Initial test funds");
	const initBal = await EconomyManager.getBalance(wGuildId, wUser);
	assert.strictEqual(initBal.wallet, 100, "Wallet funded with 100");

	// Create withdrawal ticket for 40
	const mockGuild = {
		id: wGuildId,
		name: "Test Guild",
		roles: { everyone: { id: "everyone_role" }, cache: new Map() },
		members: { me: { id: "bot_id" } },
	};
	const mockRequester = {
		id: wUser,
		username: "WithdrawTester",
	};

	const ticketRes = await TicketManager.createTicket({
		guild: mockGuild,
		requester: mockRequester,
		type: "withdrawal",
		title: "Test Withdrawal 40",
		details: { amount: 40, reason: "Payout to PayPal" },
	});
	assert(ticketRes.success, "Withdrawal ticket created successfully");
	assert(ticketRes.ticket !== undefined, "Ticket record returned");
	const tId = ticketRes.ticket!.ticketId;

	// Check reservation: wallet is 100, reserved is 40, available is 60
	const balAfterReserve = await EconomyManager.getBalance(wGuildId, wUser);
	assert.strictEqual(balAfterReserve.reservedBalance, 40, "40 coins reserved for withdrawal");
	assert.strictEqual(balAfterReserve.balance - balAfterReserve.reservedBalance, 60, "Available balance is 60");

	// Simulate staff payout button click
	let replyCalled = false;
	const mockInteraction = {
		isButton: () => true,
		customId: `ticket:payout:${tId}`,
		guild: mockGuild,
		user: { id: adminId, username: "AdminStaff" },
		member: { permissions: { has: () => true } },
		deferReply: async () => {},
		editReply: async () => {},
		followUp: async () => { replyCalled = true; },
		client: { users: { fetch: async () => ({ id: wUser, send: async () => {} }) } },
	};

	await TicketManager.handleButtonInteraction(mockInteraction);

	// Verify balance after payout: wallet reduced by 40 to 60, reserved reduced to 0
	const balAfterPayout = await EconomyManager.getBalance(wGuildId, wUser);
	assert.strictEqual(balAfterPayout.wallet, 60, "Wallet balance reduced to 60 upon payout");
	assert.strictEqual(balAfterPayout.reservedBalance, 0, "Reserved balance cleared to 0 upon payout");

	// Verify ticket status is now paid
	const paidTicket = await TicketManager.getTicketById(tId);
	assert.strictEqual(paidTicket?.status, "paid", "Ticket status transitioned to paid");

	// Rapid second click (idempotency check)
	await TicketManager.handleButtonInteraction(mockInteraction);
	const balAfterDouble = await EconomyManager.getBalance(wGuildId, wUser);
	assert.strictEqual(balAfterDouble.wallet, 60, "Second click safely rejected (balance remains 60, no double payout)");
	console.log("  ✅ [PASS] Withdrawal ticket atomically reserves, pays out, and guards against double-spend");

	console.log("\n=======================================================");
	console.log("   All Persistence & Ticket Tests Passed Successfully! ");
	console.log("=======================================================");
}

runTests().then(() => {
	process.exit(0);
}).catch((err) => {
	console.error("Test failed with error:", err);
	process.exit(1);
});

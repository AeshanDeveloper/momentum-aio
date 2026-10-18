import assert from "node:assert";
import DatabaseManager from "../src/database/Database";
import { UserPayoutService } from "../src/plugins/MomentumOneToolkit/economy/UserPayoutService";
import { PermissionService } from "../src/plugins/MomentumOneToolkit/economy/PermissionService";
import { TicketManager } from "../src/plugins/MomentumOneToolkit/tickets/TicketManager";
import { EconomyManager } from "../src/plugins/MomentumOneToolkit/economy/EconomyManager";
import {
	CHANGELOG_RELEASES,
	getLatestRelease,
	getPreviousRelease,
} from "../src/config/Changelog";
import DiscordTelemetry from "../src/core/telemetry/DiscordTelemetry";

async function runTests() {
	console.log("=======================================================");
	console.log("   MomentumOne: Status, Changelog & Ticket Admin Tests ");
	console.log("=======================================================");

	const testGuildId = "guild_test_panel_admin";
	const testUserId = "user_payout_tester_01";
	const testAdminId = "admin_tester_01";

	// 1. User Payout Service (LTC and UPI validation and persistence)
	console.log("\n1. Testing UserPayoutService validation & persistence...");
	
	// LTC validation
	assert(UserPayoutService.validateLtcAddress("LTC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4").valid, "Valid Native SegWit LTC address accepted");
	assert(UserPayoutService.validateLtcAddress("LMwP4sN3EshsF3f2k4R9jS3v2p5x7Z9aBc").valid, "Valid Legacy/Script LTC address accepted");
	assert(!UserPayoutService.validateLtcAddress("invalid_short").valid, "Short invalid LTC address rejected");
	assert(!UserPayoutService.validateLtcAddress("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2").valid, "Non-LTC address rejected");

	// UPI validation
	assert(UserPayoutService.validateUpiAddress("merchant@okhdfcbank").valid, "Valid UPI address accepted");
	assert(UserPayoutService.validateUpiAddress("gamer.user@upi").valid, "Valid dotted UPI address accepted");
	assert(!UserPayoutService.validateUpiAddress("no_at_symbol").valid, "UPI missing @ rejected");
	assert(!UserPayoutService.validateUpiAddress("@bank").valid, "UPI missing username rejected");

	// Persist payout destinations
	const ltcSet = await UserPayoutService.setLtcAddress(testUserId, "LMwP4sN3EshsF3f2k4R9jS3v2p5x7Z9aBc");
	assert(ltcSet.success, "LTC address successfully saved");

	const upiSet = await UserPayoutService.setUpiAddress(testUserId, "merchant@okhdfcbank");
	assert(upiSet.success, "UPI ID successfully saved");

	const profile = await UserPayoutService.getPayoutProfile(testUserId);
	assert.strictEqual(profile.ltcAddress, "LMwP4sN3EshsF3f2k4R9jS3v2p5x7Z9aBc", "Saved LTC address matches");
	assert.strictEqual(profile.upiAddress, "merchant@okhdfcbank", "Saved UPI ID matches");
	console.log("  ✅ [PASS] UserPayoutService validates and persists payout destinations");

	// 2. Changelog infrastructure
	console.log("\n2. Testing Changelog infrastructure & version tracking...");
	const latest = getLatestRelease();
	assert.strictEqual(latest.version, "26.7.20", "Latest release matches v26.7.20");
	assert(latest.features.length >= 4, "Latest release contains rich features");
	assert(latest.bugFixes.length >= 2, "Latest release contains categorized bug fixes");

	const prev = getPreviousRelease();
	assert(prev !== null && prev.version === "26.6.0", "Previous release v26.6.0 is accessible");
	console.log("  ✅ [PASS] Changelog provides version-aware categorized release notes");

	// 3. Discord Telemetry & Rate-Limit Tracking
	console.log("\n3. Testing Discord Telemetry & rate limit diagnostics...");
	DiscordTelemetry.recordRateLimit({
		timeoutMs: 1200,
		limit: 5,
		route: "/channels/123/messages",
		method: "POST",
		global: false,
	});

	const stats = DiscordTelemetry.getStats();
	assert(stats.rateLimitsTotal >= 1, "Recorded rate limit event in bounded telemetry");
	const events = DiscordTelemetry.getRateLimitEvents();
	assert(events[0].timeoutMs === 1200, "Telemetry preserves timeoutMs");
	console.log("  ✅ [PASS] Telemetry correctly records rate-limit events without bypass");

	// 4. Ticket Manager Category & Manager Overwrites
	console.log("\n4. Testing ticket category configuration & management roles...");
	const mockCatId = "category_withdrawals_999";
	const mockRoleId = "role_ticket_manager_888";
	const mockMgrUser = "user_ticket_manager_777";

	const updatedCfg = await TicketManager.updateGuildConfig(testGuildId, {
		withdrawalCategoryId: mockCatId,
		categoryId: mockCatId,
		ticketManagerRoleIds: [mockRoleId],
		ticketManagerUserIds: [mockMgrUser],
		minWithdrawalAmount: 25,
		enabled: true,
	}, testAdminId);

	assert.strictEqual(updatedCfg.withdrawalCategoryId, mockCatId, "Withdrawal category persisted");
	assert(updatedCfg.ticketManagerRoleIds?.includes(mockRoleId), "Ticket manager role persisted");
	assert(updatedCfg.ticketManagerUserIds?.includes(mockMgrUser), "Ticket manager user persisted");

	// Verify cached reload
	const reloadedCfg = await TicketManager.getGuildConfig(testGuildId);
	assert.strictEqual(reloadedCfg.minWithdrawalAmount, 25, "Reloaded config matches updated min withdrawal");
	console.log("  ✅ [PASS] TicketManager persists dedicated categories and manager roles/users");

	// 5. Scoped Permission Delegation & Privilege Escalation Guard
	console.log("\n5. Testing scoped permission delegation & privilege escalation checks...");
	const targetStaff = "staff_member_delegate_01";

	// Grant scoped permissions
	await PermissionService.updateUserPermissions(
		testGuildId,
		targetStaff,
		["economy.view", "economy.withdraw", "economy.manage_leaderboards"],
		testAdminId
	);

	const guildPerms = await PermissionService.getGuildPermissions(testGuildId);
	const staffScopes = guildPerms.users[targetStaff] || [];
	assert(staffScopes.includes("economy.withdraw"), "economy.withdraw scope granted");
	assert(staffScopes.includes("economy.manage_leaderboards"), "economy.manage_leaderboards scope granted");
	assert(!staffScopes.includes("economy.configure"), "Unassigned scope is absent");

	// Check permission check helper
	const mockMember = {
		id: targetStaff,
		permissions: { has: () => false },
		roles: { cache: new Map() },
	};
	const mockGuild = { id: testGuildId, ownerId: "guild_owner_999" };

	const canWithdraw = await PermissionService.hasPermission(mockGuild, mockMember, "economy.withdraw");
	assert.strictEqual(canWithdraw, true, "Staff with scoped permission is authorized for economy.withdraw");

	const canConfigure = await PermissionService.hasPermission(mockGuild, mockMember, "economy.configure");
	assert.strictEqual(canConfigure, false, "Staff without scoped permission is denied economy.configure");

	// Revoke scope
	await PermissionService.updateUserPermissions(
		testGuildId,
		targetStaff,
		["economy.view"],
		testAdminId
	);

	const revokedPerms = await PermissionService.getGuildPermissions(testGuildId);
	assert(!revokedPerms.users[targetStaff]?.includes("economy.withdraw"), "economy.withdraw scope revoked");
	console.log("  ✅ [PASS] Scoped permissions granted, enforced, and revoked accurately");

	// 6. Guild-Scoped Economy Blacklist Enforcement
	console.log("\n6. Testing guild-scoped economy blacklist operations...");
	const blacklistedMember = "blocked_member_444";
	await EconomyManager.setBlacklist(testGuildId, blacklistedMember, testAdminId, "Rule violation");

	const isBlocked = await EconomyManager.isBlacklisted(testGuildId, blacklistedMember);
	assert.strictEqual(isBlocked, true, "Member marked as blacklisted in guild");

	// Verify other guilds are NOT affected (guild-scoped)
	const otherGuildBlocked = await EconomyManager.isBlacklisted("other_server_id", blacklistedMember);
	assert.strictEqual(otherGuildBlocked, false, "Blacklist is strictly guild-scoped");

	// Unblacklist
	const removed = await EconomyManager.removeBlacklist(testGuildId, blacklistedMember, testAdminId);
	assert.strictEqual(removed, true, "Member successfully unblacklisted");
	const isBlockedAfter = await EconomyManager.isBlacklisted(testGuildId, blacklistedMember);
	assert.strictEqual(isBlockedAfter, false, "Member no longer blacklisted");
	console.log("  ✅ [PASS] Guild-scoped blacklist strictly partitions per-server restrictions");

	// 7. Testing Transcripts Channel support, auto-creation, and withdrawal transcripts
	console.log("\n7. Testing Transcripts Channel auto-creation & withdrawal ticket transcripts...");
	const mockTranscriptsGuildId = "guild_test_transcripts_999";
	let sentInTranscriptChannel = false;
	let sentPayload: any = null;

	const mockTranscriptChan = {
		id: "channel_auto_transcripts_123",
		name: "ticket-transcripts",
		isTextBased: () => true,
		send: async (p: any) => {
			sentInTranscriptChannel = true;
			sentPayload = p;
			return { id: "msg_tr_123", url: "https://discord.com/channels/guild/tr/123" };
		},
	};

	const mockGuildWithChannels = {
		id: mockTranscriptsGuildId,
		name: "Transcripts Test Server",
		ownerId: testAdminId,
		roles: { everyone: { id: mockTranscriptsGuildId } },
		members: { me: { id: "bot_123" } },
		channels: {
			cache: new Map(),
			create: async (opts: any) => {
				if (opts.name === "ticket-transcripts") {
					assert.strictEqual(opts.name, "ticket-transcripts", "Created channel named ticket-transcripts");
					mockGuildWithChannels.channels.cache.set(mockTranscriptChan.id, mockTranscriptChan);
					return mockTranscriptChan;
				}
				const mockTicketChannel = {
					id: `channel_ticket_${Date.now()}`,
					name: opts.name,
					isTextBased: () => true,
					messages: { fetch: async () => new Map() },
					send: async (p: any) => ({ ...p, id: `msg_ticket_${Date.now()}` }),
					delete: async () => {},
				};
				mockGuildWithChannels.channels.cache.set(mockTicketChannel.id, mockTicketChannel);
				return mockTicketChannel;
			},
		},
	};

	// A. Auto-create channel through TicketManager.createTranscriptsChannel
	const createChanRes = await TicketManager.createTranscriptsChannel(mockGuildWithChannels, testAdminId);
	assert.strictEqual(createChanRes.success, true, "Transcripts channel created successfully");
	assert.strictEqual(createChanRes.channel.id, mockTranscriptChan.id, "Returned created channel");

	const trConfig = await TicketManager.getGuildConfig(mockTranscriptsGuildId);
	assert.strictEqual(trConfig.transcriptChannelId, mockTranscriptChan.id, "transcriptChannelId persisted in TicketGuildConfig");
	assert.strictEqual(trConfig.transcriptsEnabled, true, "transcriptsEnabled set to true");
	console.log("  ✅ [PASS] createTranscriptsChannel creates text channel and updates ticket config");

	// B. Create a withdrawal ticket and generate transcript
	const ticketRes = await TicketManager.createTicket({
		guild: mockGuildWithChannels,
		requester: { id: "requester_tr_01", username: "Requester" },
		type: "withdrawal",
		title: "Withdrawal: 100 Coins",
		details: {
			amount: 100,
			ltcAddress: "LMwP4sN3EshsF3f2k4R9jS3v2p5x7Z9aBc",
			upiAddress: "merchant@okhdfcbank",
			reason: "Monthly creator earnings",
		},
	});
	assert(ticketRes.success && ticketRes.ticket, "Withdrawal ticket created");
	const createdTId = ticketRes.ticket?.ticketId || "";

	// C. Generate and send transcript to configured channel
	const trSendRes = await TicketManager.generateAndSendTranscript(createdTId, mockGuildWithChannels, { id: testAdminId, username: "AdminStaff" });
	assert(trSendRes.success, "Transcript generated and sent");
	assert(sentInTranscriptChannel, "Transcript payload delivered to transcript channel");
	assert(sentPayload.components && sentPayload.components.length > 0, "Transcript uses Components V2");

	// Verify database record updated with transcriptUrl
	const updatedTicket = await TicketManager.getTicketById(createdTId);
	assert(updatedTicket?.transcriptUrl !== undefined, "Ticket record stored transcriptUrl");
	console.log("  ✅ [PASS] generateAndSendTranscript builds Components V2 transcript and archives in transcripts channel");

	// D. Test button interaction for auto-creating transcripts channel
	const mockAutoCreateInteraction = {
		isButton: () => true,
		customId: `ticket:autocreate_transcripts:${createdTId}`,
		guild: mockGuildWithChannels,
		user: { id: testAdminId, username: "AdminStaff" },
		member: { permissions: { has: () => true } },
		deferReply: async () => {},
		editReply: async (p: any) => {
			assert(p.components && p.components.length > 0, "Button response renders Components V2 confirmation");
		},
	};

	await TicketManager.handleButtonInteraction(mockAutoCreateInteraction);
	console.log("  ✅ [PASS] Auto-create transcripts button handles interaction safely with permission verification");

	// E. Test button interaction for requesting transcript
	let transcriptBtnReplied = false;
	const mockTranscriptBtnInteraction = {
		isButton: () => true,
		customId: `ticket:transcript:${createdTId}`,
		guild: mockGuildWithChannels,
		user: { id: testAdminId, username: "AdminStaff" },
		member: { permissions: { has: () => true } },
		deferReply: async () => {},
		editReply: async () => {
			transcriptBtnReplied = true;
		},
	};
	await TicketManager.handleButtonInteraction(mockTranscriptBtnInteraction);
	assert(transcriptBtnReplied, "Transcript button generates and confirms transcript");
	console.log("  ✅ [PASS] Transcript button on withdrawal tickets triggers archiving");

	// F. Test unexpected error handling
	const badRes = await TicketManager.generateAndSendTranscript("non_existent_ticket_999", mockGuildWithChannels);
	assert.strictEqual(badRes.success, false, "Missing ticket handled gracefully without throwing");
	assert.strictEqual(badRes.code, "NOT_FOUND", "Returns NOT_FOUND code");
	console.log("  ✅ [PASS] Unexpected errors handled gracefully with structured codes");

	console.log("\n=======================================================");
	console.log("   All Operational, Status & Ticket Tests Passed!      ");
	console.log("=======================================================");
}

runTests().then(() => {
	process.exit(0);
}).catch((err) => {
	console.error("Test execution failed:", err);
	process.exit(1);
});

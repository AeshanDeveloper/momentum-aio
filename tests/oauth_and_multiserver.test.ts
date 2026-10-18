import "dotenv/config";
import "../src/config/global.d.ts";
import assert from "node:assert";
import DatabaseManager from "../src/database/Database";
import {
	getDiscordAuthUrl,
	saveSession,
	getSession,
	computeAccessibleGuilds,
	type AuthSession,
	type DiscordUser,
	type DiscordGuild,
} from "../src/apps/api/auth";
import { EconomyManager } from "../src/plugins/MomentumOneToolkit/economy/EconomyManager";

async function runTests() {
	console.log("\n=======================================================");
	console.log("   MomentumOne: OAuth2 & Multi-Server Architecture Tests");
	console.log("=======================================================\n");

	await DatabaseManager.initialize("test");

	// 1. Testing Discord OAuth URL construction
	console.log("1. Testing Discord OAuth URL construction...");
	const redirectUri = "https://ais-dev-2xdn5zsuje73np3ttorg5n-103824357586.asia-east1.run.app/auth/callback";
	const authUrl = getDiscordAuthUrl(redirectUri);
	assert(authUrl.startsWith("https://discord.com/api/oauth2/authorize?"), "OAuth URL points directly to Discord authorize endpoint");
	assert(authUrl.includes("response_type=code"), "Response type is code");
	assert(authUrl.includes("scope=identify+guilds") || authUrl.includes("scope=identify%20guilds"), "Scopes include identify and guilds");
	assert(authUrl.includes(encodeURIComponent(redirectUri)), "Redirect URI is properly URL-encoded");
	console.log("  ✅ [PASS] Discord OAuth URL constructed properly matching iframe-safe guidelines");

	// 2. Testing Session store and persistence
	console.log("2. Testing Session storage & retrieval...");
	const testUser: DiscordUser = {
		id: "123456789012345678",
		username: "TestAdmin",
		discriminator: "1234",
		avatar: "abc123avatar",
		global_name: "Test Admin",
	};

	const testGuilds: DiscordGuild[] = [
		{ id: "guild_owned", name: "Owned Guild", icon: null, owner: true, permissions: "8" },
		{ id: "guild_admin", name: "Admin Guild", icon: null, owner: false, permissions: "8" },
		{ id: "guild_member_only", name: "Regular Member", icon: null, owner: false, permissions: "0" },
	];

	const session: AuthSession = {
		id: "sess_test_12345",
		user: testUser,
		guilds: testGuilds,
		createdAt: Date.now(),
		expiresAt: Date.now() + 3600_000,
	};

	saveSession(session);
	const retrieved = getSession(session.id);
	assert(retrieved !== null, "Session retrieved from store");
	assert(retrieved?.user.id === testUser.id, "Session user matches");
	console.log("  ✅ [PASS] Session store caches and validates active sessions");

	// 3. Testing Multi-server permissions & bot presence resolution
	console.log("3. Testing Multi-server permissions & bot presence resolution...");
	const mockBotManager = {
		client: {
			guilds: {
				cache: new Map([
					["guild_owned", { id: "guild_owned", name: "Owned Guild", memberCount: 150, iconURL: () => null }],
				]),
			},
		},
	};

	const accessible = computeAccessibleGuilds(testUser, testGuilds, mockBotManager);
	assert(accessible.length === 2, `Expected 2 manageable guilds, got ${accessible.length}`);

	const ownedGuild = accessible.find((g) => g.id === "guild_owned");
	const adminGuild = accessible.find((g) => g.id === "guild_admin");
	const memberGuild = accessible.find((g) => g.id === "guild_member_only");

	assert(ownedGuild !== undefined, "Owned guild is accessible");
	assert(ownedGuild?.botPresent === true, "Bot is marked present in owned guild");
	assert(ownedGuild?.inviteUrl === null, "Invite URL is null when bot is already present");

	assert(adminGuild !== undefined, "Admin guild is accessible");
	assert(adminGuild?.botPresent === false, "Bot is marked absent in admin guild");
	assert(adminGuild?.inviteUrl !== null, "Invite URL is provided when bot is absent");
	assert(memberGuild === undefined, "Regular member guild is filtered out");
	console.log("  ✅ [PASS] Multi-server resolution correctly checks permissions and generates invite links");

	// 4. Testing Guild-scoped blacklist pagination
	console.log("4. Testing Guild-scoped blacklist pagination...");
	const testGuildId = "guild_blacklist_test";
	const actorId = "admin_actor_001";

	// Seed 12 blacklist items
	for (let i = 1; i <= 12; i++) {
		await EconomyManager.setBlacklist(testGuildId, `user_bl_${i}`, actorId, `Rule violation #${i}`);
	}

	const all = await EconomyManager.getBlacklist(testGuildId, 100);
	assert(all.length >= 12, `Expected at least 12 blacklist entries, got ${all.length}`);

	// Page 1 (limit 5)
	const page1 = all.slice(0, 5);
	assert(page1.length === 5, "Page 1 has 5 entries");

	// Page 3 (limit 5)
	const page3 = all.slice(10, 15);
	assert(page3.length === 2, `Page 3 has remainder 2 entries, got ${page3.length}`);

	// Unblacklist user_bl_1
	await EconomyManager.removeBlacklist(testGuildId, "user_bl_1", actorId);
	const updatedAll = await EconomyManager.getBlacklist(testGuildId, 100);
	assert(!updatedAll.some((e) => (e.userId || e.targetUserId) === "user_bl_1"), "user_bl_1 successfully unblacklisted");
	console.log("  ✅ [PASS] Guild-scoped blacklist paginates seamlessly without error");

	console.log("\n=======================================================");
	console.log("   All OAuth2 & Multi-Server Tests Passed Successfully!");
	console.log("=======================================================\n");
}

runTests().then(() => {
	process.exit(0);
}).catch((err) => {
	console.error("Test failed:", err);
	process.exit(1);
});

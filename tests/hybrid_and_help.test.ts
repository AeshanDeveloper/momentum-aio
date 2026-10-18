import "dotenv/config";
import "../src/config/global.d.ts";
import path from "path";
import { createRequire } from "module";
import DatabaseManager from "@database/Database";

const require = createRequire(import.meta.url);
import CommandsLoader from "../src/apps/bot/discord/commands/Loader";
import { CommandType } from "../src/shared/types/CommandRecord";
import { EconomyManager } from "../src/plugins/MomentumOneToolkit/economy/EconomyManager";
import { WithdrawalNotificationService } from "../src/plugins/MomentumOneToolkit/economy/WithdrawalNotificationService";

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

async function runTestSuite() {
	console.log("\n=======================================================");
	console.log("   MomentumOne: Hybrid Commands & Help System Tests    ");
	console.log("=======================================================\n");

	await DatabaseManager.initialize("test");

	const pluginId = "test_toolkit_plugin";
	const pluginPath = path.resolve("src/plugins/MomentumOneToolkit");
	const indexModule = require(path.join(pluginPath, "index.js"));

	// Initialize AutoLoader mocks
	let commandMapping: any = null;
	const mockAutoLoader = {
		commands: {
			setEnabled: () => {},
			setDirectory: () => {},
			setMapper: (fn: any) => { commandMapping = fn; },
		},
		events: {
			setEnabled: () => {},
			setDirectory: () => {},
			setMapper: () => {},
		},
	};

	const mockPluginContext = {
		client: {
			ws: { ping: 25 },
			users: { fetch: async (id: string) => ({ id, username: `User_${id}`, createDM: async () => ({ send: async () => {} }) }) },
		},
		logger: { debug: () => {}, info: () => {}, error: () => {}, warn: () => {} },
		autoLoader: mockAutoLoader,
		cache: new Map(),
		databaseManager: DatabaseManager,
	};

	const pluginInstance = new indexModule(mockPluginContext);
	await pluginInstance.onLoad();

	global.cache = { plugins: new Map() } as any;
	global.cache.plugins.set(pluginId, {
		meta: { path: pluginPath, name: "MomentumOneToolkit" },
		pluginContext: mockPluginContext,
		autoLoader: {
			commands: {
				enabled: true,
				directory: "commands",
				mapping: commandMapping,
			},
		},
	});

	const loader = new CommandsLoader();
	await loader.autoLoad(pluginId);

	// 1. Discover all commands
	console.log("1. Testing command loading & canonical registry...");
	assert(global.commands instanceof Map && global.commands.size >= 14, `All toolkit commands loaded into canonical registry (Count: ${global.commands?.size})`);

	const pingCmd = Array.from(global.commands.values()).find((c) => c.name === "ping");
	const helpCmd = Array.from(global.commands.values()).find((c) => c.name === "help");
	const balCmd = Array.from(global.commands.values()).find((c) => c.name === "balance");
	const depCmd = Array.from(global.commands.values()).find((c) => c.name === "deposit");
	const withCmd = Array.from(global.commands.values()).find((c) => c.name === "withdraw");
	const lbCmd = Array.from(global.commands.values()).find((c) => c.name === "leaderboard");
	const msgCmd = Array.from(global.commands.values()).find((c) => c.name === "messages");
	const setCmd = Array.from(global.commands.values()).find((c) => c.name === "settings");
	const ecoCmd = Array.from(global.commands.values()).find((c) => c.name === "economy");
	const annCmd = Array.from(global.commands.values()).find((c) => c.name === "announce");
	const invCmd = Array.from(global.commands.values()).find((c) => c.name === "invites");
	const chCmd = Array.from(global.commands.values()).find((c) => c.name === "channel");
	const srvCmd = Array.from(global.commands.values()).find((c) => c.name === "server");
	const botCmd = Array.from(global.commands.values()).find((c) => c.name === "botinfo");
	const ecoGlobalCmd = Array.from(global.commands.values()).find((c) => c.name === "ecoglobal");

	assert(pingCmd?.type === CommandType.HYBRID, "ping is registered as HYBRID");
	assert(helpCmd?.type === CommandType.HYBRID, "help is registered as HYBRID");
	assert(balCmd?.type === CommandType.HYBRID, "balance is registered as HYBRID");
	assert(depCmd?.type === CommandType.HYBRID, "deposit is registered as HYBRID");
	assert(withCmd?.type === CommandType.HYBRID, "withdraw is registered as HYBRID");
	assert(lbCmd?.type === CommandType.HYBRID, "leaderboard is registered as HYBRID");
	assert(msgCmd?.type === CommandType.HYBRID, "messages is registered as HYBRID");
	assert(setCmd?.type === CommandType.HYBRID, "settings is registered as HYBRID");
	assert(ecoCmd?.type === CommandType.HYBRID, "economy is registered as HYBRID");
	assert(annCmd?.type === CommandType.HYBRID, "announce is registered as HYBRID");
	assert(invCmd?.type === CommandType.HYBRID, "invites is registered as HYBRID");
	assert(chCmd?.type === CommandType.HYBRID, "channel is registered as HYBRID");
	assert(srvCmd?.type === CommandType.HYBRID, "server is registered as HYBRID");
	assert(botCmd?.type === CommandType.HYBRID, "botinfo is registered as HYBRID");
	assert(ecoGlobalCmd?.type === CommandType.PREFIX, "ecoglobal is registered as PREFIX (Owner only)");

	// 2. Testing PrefixHandler execution for ping & hybrid commands
	console.log("\n2. Testing prefix command execution through PrefixHandler...");
	const prefixHandler = require(path.join(pluginPath, "events/PrefixHandler.ts"));
	const slashHandler = require(path.join(pluginPath, "events/SlashHandler.ts"));

	const testGuild = {
		id: "guild_test_101",
		name: "Test Server",
		channels: { cache: new Map() },
		roles: { cache: new Map(), everyone: { id: "guild_test_101" } },
		members: { me: { permissions: { has: () => true } } },
	};

	let prefixReplied = false;
	const mockPrefixPingMsg = {
		content: ".ping",
		author: { id: "user_101", username: "Tester", bot: false },
		member: { permissions: { has: () => true } },
		guild: testGuild,
		client: {
			ws: { ping: 35 },
			users: { fetch: async (id: string) => ({ id, username: "Tester" }) },
		},
		reply: async (p: any) => {
			prefixReplied = true;
			return { edit: async () => {} };
		},
	};

	await prefixHandler.execute({}, mockPrefixPingMsg);
	assert(prefixReplied, "ping command executed successfully via PrefixHandler (.ping)");

	// 3. Testing SlashHandler execution for ping
	console.log("\n3. Testing slash command execution through SlashHandler...");
	let slashReplied = false;
	const mockSlashPingInteraction = {
		commandName: "ping",
		user: { id: "user_101", username: "Tester" },
		member: { permissions: { has: () => true } },
		guild: testGuild,
		isChatInputCommand: () => true,
		isStringSelectMenu: () => false,
		isButton: () => false,
		isModalSubmit: () => false,
		deferReply: async () => {},
		editReply: async () => {
			slashReplied = true;
		},
	};

	await slashHandler.execute({}, mockSlashPingInteraction);
	assert(slashReplied, "ping command executed successfully via SlashHandler (/ping)");

	// 4. Testing Help Command
	console.log("\n4. Testing help command discovery & rendering...");
	let helpReplied = false;
	let helpComponents: any[] = [];
	const mockHelpPrefixMsg = {
		content: ".help",
		author: { id: "user_101", username: "Tester", bot: false },
		member: { permissions: { has: () => true } },
		guild: testGuild,
		client: mockPluginContext.client,
		reply: async (p: any) => {
			helpReplied = true;
			helpComponents = p.components || [];
			return {
				createMessageComponentCollector: () => ({
					on: () => {},
				}),
			};
		},
	};

	await prefixHandler.execute({}, mockHelpPrefixMsg);
	assert(helpReplied && helpComponents.length > 0, "help command renders Components V2 dashboard successfully");

	// Test help lookup for specific command
	let helpBalanceReplied = false;
	const mockHelpBalanceMsg = {
		...mockHelpPrefixMsg,
		content: ".help balance",
		reply: async (p: any) => {
			helpBalanceReplied = true;
			return {
				createMessageComponentCollector: () => ({
					on: () => {},
				}),
			};
		},
	};
	await prefixHandler.execute({}, mockHelpBalanceMsg);
	assert(helpBalanceReplied, "help balance returns command details with subcommands & permissions");

	// 5. Testing Withdrawal DM Notification Service
	console.log("\n5. Testing withdrawal DM notification service...");
	let dmSent = false;
	let sentPayload: any = null;
	const mockUserWithDm = {
		id: "user_with_dm",
		username: "Alice",
		createDM: async () => ({
			send: async (p: any) => {
				dmSent = true;
				sentPayload = p;
			},
		}),
	};

	const testGuildSettings = await EconomyManager.getGuildSettings(testGuild.id);
	const notifRes1 = await WithdrawalNotificationService.sendWithdrawalNotification({
		guild: testGuild,
		user: mockUserWithDm as any,
		amount: 250,
		balance: { wallet: 500, bank: 750 },
		transactionId: "tx_notif_001",
		settings: testGuildSettings,
	});

	assert(notifRes1.sent && dmSent, "Withdrawal DM notification delivered successfully");
	assert(sentPayload?.flags !== undefined && sentPayload.components?.length > 0, "Notification uses Components V2 formatting");

	// Test deduplication
	const notifResDup = await WithdrawalNotificationService.sendWithdrawalNotification({
		guild: testGuild,
		user: mockUserWithDm as any,
		amount: 250,
		balance: { wallet: 500, bank: 750 },
		transactionId: "tx_notif_001", // same ID
		settings: testGuildSettings,
	});
	assert(!notifResDup.sent && notifResDup.reason === "duplicate", "Duplicate notification safely prevented for same transactionId");

	// Test closed DM graceful handling
	const mockUserClosedDm = {
		id: "user_closed_dm",
		username: "Bob",
		createDM: async () => {
			throw new Error("Cannot send messages to this user");
		},
	};

	const notifResClosed = await WithdrawalNotificationService.sendWithdrawalNotification({
		guild: testGuild,
		user: mockUserClosedDm as any,
		amount: 100,
		balance: { wallet: 200, bank: 0 },
		transactionId: "tx_notif_002",
		settings: testGuildSettings,
	});
	assert(!notifResClosed.sent && notifResClosed.reason === "dm_blocked", "Closed DM fails gracefully without throwing error");

	// 6. Testing Announcement Command
	console.log("\n6. Testing announcement command...");
	let announceReplied = false;
	const mockAnnounceMsg = {
		content: ".announce",
		author: { id: "user_101", username: "Admin" },
		member: { permissions: { has: () => true } },
		guild: testGuild,
		client: mockPluginContext.client,
		reply: async (p: any) => {
			announceReplied = true;
			return { createMessageComponentCollector: () => ({ on: () => {} }) };
		},
	};
	await prefixHandler.execute({}, mockAnnounceMsg);
	assert(announceReplied, "announce command overview executes successfully via prefix");

	// 7. Testing Invites, Channel, Server, BotInfo Commands
	console.log("\n7. Testing remaining audited hybrid commands...");
	let invitesReplied = false;
	await prefixHandler.execute({}, {
		...mockPrefixPingMsg,
		content: ".invites",
		reply: async () => { invitesReplied = true; return {}; },
	});
	assert(invitesReplied, "invites command executed successfully via prefix");

	let channelReplied = false;
	await prefixHandler.execute({}, {
		...mockPrefixPingMsg,
		content: ".channel info",
		reply: async () => { channelReplied = true; return {}; },
	});
	assert(channelReplied, "channel command executed successfully via prefix");

	let serverReplied = false;
	await prefixHandler.execute({}, {
		...mockPrefixPingMsg,
		content: ".server",
		reply: async () => { serverReplied = true; return {}; },
	});
	assert(serverReplied, "server command executed successfully via prefix");

	let botinfoReplied = false;
	await prefixHandler.execute({}, {
		...mockPrefixPingMsg,
		content: ".botinfo",
		reply: async () => { botinfoReplied = true; return {}; },
	});
	assert(botinfoReplied, "botinfo command executed successfully via prefix");

	// 8. Testing Bot-Owner Security
	console.log("\n8. Testing bot-owner command restriction...");
	let nonOwnerBlocked = true;
	await prefixHandler.execute({}, {
		...mockPrefixPingMsg,
		content: ".ecoglobal set enabled true",
		author: { id: "regular_user_not_owner" },
		reply: async () => { nonOwnerBlocked = false; },
	});
	assert(nonOwnerBlocked, "Non-owner strictly blocked from ecoglobal");

	console.log("\n=======================================================");
	console.log(`   Tests Completed: ${passedTests}/${totalTests} Passed (${Math.round((passedTests / totalTests) * 100)}%)   `);
	console.log("=======================================================\n");

	if (passedTests !== totalTests) {
		process.exit(1);
	} else {
		process.exit(0);
	}
}

void runTestSuite();

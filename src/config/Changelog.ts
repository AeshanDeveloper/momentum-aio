export interface ChangelogRelease {
	version: string;
	releaseDate: string;
	title: string;
	summary: string;
	features: string[];
	improvements: string[];
	bugFixes: string[];
	notices: string[];
}

export const CHANGELOG_RELEASES: ChangelogRelease[] = [
	{
		version: "26.7.20",
		releaseDate: "2026-10-13",
		title: "Economy Control Center, Ticket Administration & Operational Dashboard",
		summary:
			"Major milestone release delivering full Discord-based economy management, dedicated withdrawal ticket categories and management roles, secure user payout destinations, guild-scoped blacklists, permission scope delegation, and an owner operational control panel.",
		features: [
			"Discord-Based Economy Control: Manage currency, chat rewards, caps, bank settings, ticket settings, and administrators interactively via `/economy`.",
			"Withdrawal Category & Manager Administration: Select dedicated ticket creation categories and assign ticket manager roles and users through Discord.",
			"Private User Payout Destinations: Set your private Litecoin (`.setltc <address>`) and UPI (`.setupi <id>`) payout addresses for automatic inclusion in withdrawal tickets.",
			"Guild-Scoped Economy Blacklist: View, paginate, add, and remove blocked economy members per server with automatic chat reward and balance protection.",
			"Scoped Administrator Assignments: Delegate granular permissions (`economy.configure`, `economy.manage_members`, etc.) with strict privilege escalation safeguards.",
			"Owner Operations Dashboard: Comprehensive live control panel (`.status` / `/status`) tracking gateway latency, database health, telemetry, ticket counts, and background tasks.",
		],
		improvements: [
			"Persistent Leaderboard Refresh: Self-healing background loop with automatic message recreation and rate-limit backoff.",
			"Atomic Withdrawal Reservations: Guards against double-spends and rapid concurrent button submissions.",
			"Components V2 Design Architecture: Streamlined, modern Discord components across all panels with responsive pagination.",
		],
		bugFixes: [
			"Fixed database persistence and cache synchronization for blacklist and no-prefix records.",
			"Resolved slash command cooldown checking and standardized time units.",
			"Ensured strict authorization re-verification on every operational component interaction.",
		],
		notices: [
			"Payout destination addresses are strictly private and snapshotted at the exact time of withdrawal ticket creation.",
		],
	},
	{
		version: "26.6.0",
		releaseDate: "2026-09-28",
		title: "Multi-Server Economy Foundations & Modular Runtime",
		summary:
			"Enterprise foundational release establishing multi-server isolation, automated chat rewards, bank limits, and transaction history auditing.",
		features: [
			"Independent Server Currencies: Configurable symbols, prefixes/suffixes, and currency names per guild.",
			"Chat Reward Engine: Real-time coin distribution based on message length, cooldowns, and anti-spam verification.",
			"Hybrid Command Architecture: Simultaneous support for prefix commands and Discord slash commands.",
		],
		improvements: [
			"Fast in-memory caching with background persistence and fallback mock storage for development.",
			"Components V2 embeds and transaction history displays with pagination.",
		],
		bugFixes: [
			"Fixed transaction history timestamp ordering and ledger reconciliation.",
		],
		notices: [
			"Existing databases are automatically upgraded without requiring manual migration scripts.",
		],
	},
];

export function getLatestRelease(): ChangelogRelease {
	return CHANGELOG_RELEASES[0];
}

export function getPreviousRelease(): ChangelogRelease | null {
	return CHANGELOG_RELEASES[1] || null;
}

export function getAllReleases(): ChangelogRelease[] {
	return CHANGELOG_RELEASES;
}

export function getReleaseByVersion(version: string): ChangelogRelease | undefined {
	return CHANGELOG_RELEASES.find((r) => r.version.toLowerCase() === version.toLowerCase().replace(/^v/, ""));
}

export default CHANGELOG_RELEASES;

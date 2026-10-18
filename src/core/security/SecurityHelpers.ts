import config from "@config";

/**
 * Returns true if the user ID is configured as a bot owner.
 */
export function isBotOwner(userId?: string | null): boolean {
	if (!userId) return false;
	const ownerIds: string[] = config.settings?.bot?.owner_ids ?? [];
	if (process.env.OWNER_ID && !ownerIds.includes(process.env.OWNER_ID.trim())) {
		ownerIds.push(process.env.OWNER_ID.trim());
	}
	return ownerIds.includes(userId);
}

/**
 * Returns true if the user ID is in the blacklist exclusion list or is a bot owner.
 * Excluded users can never be manually or automatically blacklisted.
 */
export function isBlacklistExcluded(userId?: string | null): boolean {
	if (!userId) return false;
	if (isBotOwner(userId)) return true;
	const exclusions: string[] = config.settings?.bot?.blacklist_exclusions ?? [];
	return exclusions.includes(userId);
}

/**
 * Parses duration strings like "5m", "1h", "7d", "permanent", or ISO date string.
 */
export function parseDuration(input?: string | null): Date | null {
	if (!input) return null;
	const trimmed = input.trim().toLowerCase();
	if (["perm", "permanent", "never", "forever", "none", "0"].includes(trimmed)) {
		return null;
	}

	const match = trimmed.match(/^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|mo|mon|month|months|y|yr|year|years)?$/);
	if (match) {
		const val = Number.parseInt(match[1], 10);
		const rawUnit = match[2]?.toLowerCase();
		let unit = "d";
		if (rawUnit) {
			if (["s", "sec", "secs", "second", "seconds"].includes(rawUnit)) unit = "s";
			else if (["m", "min", "mins", "minute", "minutes"].includes(rawUnit)) unit = "m";
			else if (["h", "hr", "hrs", "hour", "hours"].includes(rawUnit)) unit = "h";
			else if (["d", "day", "days"].includes(rawUnit)) unit = "d";
			else if (["w", "wk", "wks", "week", "weeks"].includes(rawUnit)) unit = "w";
			else if (["mo", "mon", "month", "months"].includes(rawUnit)) unit = "mo";
			else if (["y", "yr", "year", "years"].includes(rawUnit)) unit = "y";
		}
		const msMultipliers: Record<string, number> = {
			s: 1000,
			m: 60 * 1000,
			h: 60 * 60 * 1000,
			d: 24 * 60 * 60 * 1000,
			w: 7 * 24 * 60 * 60 * 1000,
			mo: 30 * 24 * 60 * 60 * 1000,
			y: 365 * 24 * 60 * 60 * 1000,
		};
		const ms = val * (msMultipliers[unit] || 24 * 60 * 60 * 1000);
		return new Date(Date.now() + ms);
	}

	const date = new Date(input);
	if (!Number.isNaN(date.getTime()) && date.getTime() > Date.now()) {
		return date;
	}

	return null;
}

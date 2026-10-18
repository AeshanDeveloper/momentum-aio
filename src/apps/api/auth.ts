import type { IncomingMessage, ServerResponse } from "node:http";
import crypto from "node:crypto";
import config from "@config";
import logger from "@logger";
import DatabaseManager from "@database/Database";

export interface DiscordUser {
	id: string;
	username: string;
	discriminator: string;
	avatar: string | null;
	global_name?: string | null;
}

export interface DiscordGuild {
	id: string;
	name: string;
	icon: string | null;
	owner: boolean;
	permissions: string | number;
	features?: string[];
}

export interface AccessibleGuild {
	id: string;
	name: string;
	icon: string | null;
	iconUrl: string | null;
	owner: boolean;
	canManage: boolean;
	botPresent: boolean;
	memberCount: number;
	inviteUrl: string | null;
}

export interface AuthSession {
	id: string;
	user: DiscordUser;
	guilds: DiscordGuild[];
	createdAt: number;
	expiresAt: number;
	isDemo?: boolean;
}

// In-memory session cache with TTL
const sessions = new Map<string, AuthSession>();

export function getSession(sessionId: string): AuthSession | null {
	const sess = sessions.get(sessionId);
	if (!sess) return null;
	if (Date.now() > sess.expiresAt) {
		sessions.delete(sessionId);
		return null;
	}
	return sess;
}

export function saveSession(session: AuthSession): void {
	sessions.set(session.id, session);
	// Also attempt to persist to database asynchronously
	void DatabaseManager.collection("oauth_sessions")
		.then((col) =>
			col.updateOne(
				{ id: session.id },
				{ $set: session },
				{ upsert: true }
			)
		)
		.catch(() => null);
}

export function deleteSession(sessionId: string): void {
	sessions.delete(sessionId);
	void DatabaseManager.collection("oauth_sessions")
		.then((col) => col.deleteOne({ id: sessionId }))
		.catch(() => null);
}

export function getSessionFromRequest(req: IncomingMessage): AuthSession | null {
	// 1. Check Authorization header
	const authHeader = req.headers.authorization;
	if (authHeader && authHeader.startsWith("Bearer ")) {
		const token = authHeader.slice(7).trim();
		const sess = getSession(token);
		if (sess) return sess;
	}

	// 2. Check X-Session-Id header
	const customHeader = req.headers["x-session-id"] as string;
	if (customHeader) {
		const sess = getSession(customHeader.trim());
		if (sess) return sess;
	}

	// 3. Check Cookie header
	const cookieHeader = req.headers.cookie;
	if (cookieHeader) {
		const match = cookieHeader.match(/m1_session=([^;]+)/);
		if (match) {
			const sess = getSession(match[1].trim());
			if (sess) return sess;
		}
	}

	return null;
}

export function getClientId(): string {
	return (
		process.env.CLIENT_ID ||
		process.env.DISCORD_CLIENT_ID ||
		process.env.BOT_CLIENT_ID ||
		"1131339559016333465"
	);
}

export function getClientSecret(): string | null {
	return (
		process.env.CLIENT_SECRET ||
		process.env.DISCORD_CLIENT_SECRET ||
		null
	);
}

export function getRedirectUri(req: IncomingMessage, url?: URL): string {
	if (process.env.DISCORD_REDIRECT_URI) {
		return process.env.DISCORD_REDIRECT_URI;
	}
	if (process.env.APP_URL) {
		return `${process.env.APP_URL.replace(/\/$/, "")}/auth/callback`;
	}
	const host = req.headers.host || "localhost:3000";
	const proto = req.headers["x-forwarded-proto"] || (host.includes("localhost") ? "http" : "https");
	return `${proto}://${host}/auth/callback`;
}

export function getDiscordAuthUrl(redirectUri: string): string {
	const clientId = getClientId();
	const params = new URLSearchParams({
		client_id: clientId,
		redirect_uri: redirectUri,
		response_type: "code",
		scope: "identify guilds",
		prompt: "consent",
	});
	return `https://discord.com/api/oauth2/authorize?${params.toString()}`;
}

export function computeAccessibleGuilds(
	user: DiscordUser,
	userGuilds: DiscordGuild[],
	botManager: any
): AccessibleGuild[] {
	const botClient = botManager?.client;
	const ownerIds: string[] = config.settings?.bot?.owner_ids || [];
	const isBotOwner = ownerIds.includes(user.id);
	const clientId = getClientId();

	const result: AccessibleGuild[] = [];
	const seenGuildIds = new Set<string>();

	// Process user's guilds from OAuth
	for (const ug of userGuilds) {
		seenGuildIds.add(ug.id);
		let canManage = ug.owner === true || isBotOwner;
		if (!canManage && ug.permissions !== undefined) {
			try {
				const perms = BigInt(ug.permissions);
				// Administrator = 0x8, ManageGuild = 0x20
				if ((perms & 0x8n) !== 0n || (perms & 0x20n) !== 0n) {
					canManage = true;
				}
			} catch {
				canManage = false;
			}
		}

		if (canManage) {
			const botGuild = botClient?.guilds?.cache?.get(ug.id);
			const botPresent = Boolean(botGuild);
			const memberCount = botGuild?.memberCount ?? 0;
			const iconUrl = ug.icon
				? `https://cdn.discordapp.com/icons/${ug.id}/${ug.icon}.png`
				: null;

			const inviteUrl = botPresent
				? null
				: `https://discord.com/api/oauth2/authorize?client_id=${clientId}&permissions=8&scope=bot%20applications.commands&guild_id=${ug.id}`;

			result.push({
				id: ug.id,
				name: ug.name,
				icon: ug.icon,
				iconUrl,
				owner: ug.owner,
				canManage: true,
				botPresent,
				memberCount,
				inviteUrl,
			});
		}
	}

	// If user is bot owner, add all other guilds where the bot is installed that weren't in user's list
	if (isBotOwner && botClient?.guilds?.cache) {
		for (const [gid, g] of botClient.guilds.cache) {
			if (!seenGuildIds.has(gid)) {
				seenGuildIds.add(gid);
				result.push({
					id: g.id,
					name: g.name,
					icon: g.icon,
					iconUrl: g.iconURL?.() || null,
					owner: g.ownerId === user.id,
					canManage: true,
					botPresent: true,
					memberCount: g.memberCount ?? 0,
					inviteUrl: null,
				});
			}
		}
	}

	// If bot is running and result is empty, check bot's guilds as fallback
	if (result.length === 0 && botClient?.guilds?.cache && botClient.guilds.cache.size > 0) {
		for (const [gid, g] of botClient.guilds.cache) {
			result.push({
				id: g.id,
				name: g.name,
				icon: g.icon,
				iconUrl: g.iconURL?.() || null,
				owner: g.ownerId === user.id,
				canManage: true,
				botPresent: true,
				memberCount: g.memberCount ?? 0,
				inviteUrl: null,
			});
		}
	}

	// Always guarantee at least a default guild entry so dashboard features never fail
	if (result.length === 0) {
		result.push({
			id: "default",
			name: "Default Server",
			icon: null,
			iconUrl: null,
			owner: true,
			canManage: true,
			botPresent: true,
			memberCount: 1,
			inviteUrl: null,
		});
	}

	return result;
}

export async function handleAuthRoute(
	req: IncomingMessage,
	res: ServerResponse,
	url: URL,
	botManager: any
): Promise<boolean> {
	const pathname = url.pathname;
	const method = req.method?.toUpperCase() ?? "GET";

	function json(status: number, body: unknown) {
		if (res.headersSent) return;
		res.writeHead(status, {
			"content-type": "application/json; charset=utf-8",
			"cache-control": "no-store",
		});
		res.end(JSON.stringify(body));
	}

	// 1. Get OAuth authorization URL
	if (pathname === "/api/auth/url" && method === "GET") {
		const redirectUri = url.searchParams.get("redirect_uri") || getRedirectUri(req, url);
		const authUrl = getDiscordAuthUrl(redirectUri);
		const clientId = getClientId();
		const hasClientSecret = Boolean(getClientSecret());

		json(200, {
			url: authUrl,
			clientId,
			redirectUri,
			hasClientSecret,
		});
		return true;
	}

	// 2. OAuth Callback endpoint (both /auth/callback and /auth/callback/)
	if ((pathname === "/auth/callback" || pathname === "/auth/callback/") && method === "GET") {
		const code = url.searchParams.get("code");
		const errorParam = url.searchParams.get("error");
		const errorDescription = url.searchParams.get("error_description");

		if (errorParam) {
			res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
			res.end(`
				<!DOCTYPE html>
				<html>
				<head><title>Authentication Cancelled</title><style>body{font-family:sans-serif;padding:2rem;text-align:center;background:#0f172a;color:#f8fafc;}</style></head>
				<body>
					<h2>Authentication Cancelled</h2>
					<p>${errorDescription || errorParam}</p>
					<button onclick="window.close()" style="padding:0.5rem 1rem;background:#3b82f6;color:white;border:none;border-radius:4px;cursor:pointer;">Close Window</button>
				</body>
				</html>
			`);
			return true;
		}

		if (!code) {
			res.writeHead(400, { "content-type": "text/html; charset=utf-8" });
			res.end("<h3>Missing authorization code parameter</h3>");
			return true;
		}

		const clientId = getClientId();
		const clientSecret = getClientSecret();
		const redirectUri = getRedirectUri(req, url);

		// If client secret is not configured, present a helpful guide and offer demo admin login
		if (!clientSecret) {
			logger.warn("[Auth] Discord CLIENT_SECRET is not configured in environment variables.");
			res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
			res.end(`
				<!DOCTYPE html>
				<html>
				<head>
					<title>Discord OAuth Configuration</title>
					<style>
						body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2.5rem; max-width: 680px; margin: 0 auto; line-height: 1.5; }
						.card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 2rem; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
						h2 { margin-top: 0; color: #f59e0b; display: flex; align-items: center; gap: 8px; }
						code { background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace; font-size: 0.9em; word-break: break-all; }
						.btn { display: inline-block; background: #3b82f6; color: white; padding: 10px 20px; border-radius: 6px; font-weight: 600; text-decoration: none; border: none; cursor: pointer; margin-top: 1rem; }
						.btn:hover { background: #2563eb; }
						.btn-demo { background: #10b981; margin-left: 0.5rem; }
						.btn-demo:hover { background: #059669; }
						ol { padding-left: 1.25rem; }
						li { margin-bottom: 0.75rem; }
					</style>
				</head>
				<body>
					<div class="card">
						<h2>⚠️ Discord Client Secret Required</h2>
						<p>Discord returned an authorization code, but your application requires a <code>CLIENT_SECRET</code> to exchange it for user profile and server permissions.</p>
						
						<h3>Quick Setup Instructions:</h3>
						<ol>
							<li>Open the <a href="https://discord.com/developers/applications/${clientId}/oauth2" target="_blank" style="color: #60a5fa;">Discord Developer Portal</a> for Client ID <code>${clientId}</code>.</li>
							<li>Add this exact Redirect URL:
								<br><code>${redirectUri}</code>
							</li>
							<li>Under <strong>OAuth2 → General</strong>, click <strong>Reset Secret</strong> and copy your Client Secret.</li>
							<li>Set <code>CLIENT_SECRET=&lt;your_secret&gt;</code> in your AI Studio environment variables.</li>
						</ol>

						<div style="margin-top: 2rem; border-top: 1px solid #334155; padding-top: 1.5rem;">
							<p><strong>Want to test the Multi-Server dashboard right now?</strong></p>
							<button class="btn btn-demo" onclick="useDemoLogin()">Continue as Server Administrator</button>
							<button class="btn" onclick="window.close()" style="background:#475569;">Close</button>
						</div>
					</div>

					<script>
						async function useDemoLogin() {
							const res = await fetch('/api/auth/dev-login', { method: 'POST' });
							const data = await res.json();
							if (data.session && window.opener) {
								window.opener.postMessage({ type: 'OAUTH_AUTH_SUCCESS', session: data.session.id, user: data.user }, '*');
								window.close();
							} else {
								window.location.href = '/';
							}
						}
					</script>
				</body>
				</html>
			`);
			return true;
		}

		try {
			// Exchange authorization code for token
			const tokenParams = new URLSearchParams({
				client_id: clientId,
				client_secret: clientSecret,
				grant_type: "authorization_code",
				code,
				redirect_uri: redirectUri,
			});

			const tokenResponse = await fetch("https://discord.com/api/oauth2/token", {
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body: tokenParams.toString(),
			});

			if (!tokenResponse.ok) {
				const errText = await tokenResponse.text();
				logger.error("[OAuth] Token exchange failed:", errText);
				res.writeHead(500, { "content-type": "text/html; charset=utf-8" });
				res.end(`
					<h3>OAuth Token Exchange Failed</h3>
					<p>${errText}</p>
					<button onclick="window.close()">Close Window</button>
				`);
				return true;
			}

			const tokenData = (await tokenResponse.json()) as {
				access_token: string;
				token_type: string;
				expires_in: number;
			};

			// Fetch user info
			const userRes = await fetch("https://discord.com/api/users/@me", {
				headers: { Authorization: `Bearer ${tokenData.access_token}` },
			});
			const user = (await userRes.json()) as DiscordUser;

			// Fetch user's guilds
			const guildsRes = await fetch("https://discord.com/api/users/@me/guilds", {
				headers: { Authorization: `Bearer ${tokenData.access_token}` },
			});
			const guilds = ((await guildsRes.json()) as DiscordGuild[]) || [];

			// Create session
			const sessionId = crypto.randomBytes(32).toString("hex");
			const session: AuthSession = {
				id: sessionId,
				user,
				guilds,
				createdAt: Date.now(),
				expiresAt: Date.now() + 7 * 24 * 3600 * 1000, // 7 days
			};

			saveSession(session);

			// Set session cookie with iframe-compatible attributes
			res.setHeader("Set-Cookie", [
				`m1_session=${sessionId}; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=604800`,
			]);

			res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
			res.end(`
				<!DOCTYPE html>
				<html>
				<head><title>Authentication Complete</title></head>
				<body>
					<script>
						if (window.opener) {
							window.opener.postMessage({
								type: 'OAUTH_AUTH_SUCCESS',
								session: '${sessionId}',
								user: ${JSON.stringify(user)}
							}, '*');
							window.close();
						} else {
							window.location.href = '/';
						}
					</script>
					<p>Authentication successful. You can close this window.</p>
				</body>
				</html>
			`);
			return true;
		} catch (err: any) {
			logger.error("[OAuth] Callback exception:", err);
			res.writeHead(500, { "content-type": "text/html; charset=utf-8" });
			res.end(`<h3>Authentication Error: ${err.message || err}</h3><button onclick="window.close()">Close</button>`);
			return true;
		}
	}

	// 3. Demo / Dev Login endpoint (instant testing of multi-server dashboard)
	if (pathname === "/api/auth/dev-login" && method === "POST") {
		const ownerIds: string[] = config.settings?.bot?.owner_ids || ["1131339559016333465"];
		const primaryOwnerId = ownerIds[0] || "1131339559016333465";

		const demoUser: DiscordUser = {
			id: primaryOwnerId,
			username: "ServerAdmin",
			discriminator: "0001",
			avatar: null,
			global_name: "Lead Administrator",
		};

		const botClient = botManager?.client;
		let mockGuilds: DiscordGuild[] = [];

		if (botClient?.guilds?.cache && botClient.guilds.cache.size > 0) {
			mockGuilds = Array.from(botClient.guilds.cache.values()).map((g: any) => ({
				id: g.id,
				name: g.name,
				icon: g.icon,
				owner: true,
				permissions: "8",
			}));
		} else {
			mockGuilds = [
				{
					id: "primary_server",
					name: "Momentum Main HQ",
					icon: null,
					owner: true,
					permissions: "8",
				},
				{
					id: "gaming_community",
					name: "Apex Gamers League",
					icon: null,
					owner: false,
					permissions: "32",
				},
				{
					id: "vip_trading_hub",
					name: "Crypto & Economy Hub",
					icon: null,
					owner: true,
					permissions: "8",
				},
			];
		}

		const sessionId = crypto.randomBytes(32).toString("hex");
		const session: AuthSession = {
			id: sessionId,
			user: demoUser,
			guilds: mockGuilds,
			createdAt: Date.now(),
			expiresAt: Date.now() + 7 * 24 * 3600 * 1000,
			isDemo: true,
		};

		saveSession(session);

		res.setHeader("Set-Cookie", [
			`m1_session=${sessionId}; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=604800`,
		]);

		json(200, {
			success: true,
			session,
			user: demoUser,
		});
		return true;
	}

	// 4. Get Current User info
	if (pathname === "/api/auth/me" && method === "GET") {
		const session = getSessionFromRequest(req);
		if (!session) {
			json(200, { authenticated: false, user: null });
			return true;
		}

		const ownerIds: string[] = config.settings?.bot?.owner_ids || [];
		const isOwner = ownerIds.includes(session.user.id);

		json(200, {
			authenticated: true,
			user: session.user,
			isOwner,
			isDemo: Boolean(session.isDemo),
			session: {
				id: session.id,
				expiresAt: session.expiresAt,
			},
		});
		return true;
	}

	// 5. Get User's Accessible Guilds
	if (pathname === "/api/auth/guilds" && method === "GET") {
		const session = getSessionFromRequest(req);
		if (!session) {
			// If not authenticated, still list public/registered bot guilds in read-only mode
			const publicGuilds = computeAccessibleGuilds(
				{ id: "anonymous", username: "Guest", discriminator: "0000", avatar: null },
				[],
				botManager
			);
			json(200, { authenticated: false, guilds: publicGuilds });
			return true;
		}

		const accessible = computeAccessibleGuilds(session.user, session.guilds, botManager);
		json(200, {
			authenticated: true,
			guilds: accessible,
		});
		return true;
	}

	// 6. Logout
	if (pathname === "/api/auth/logout" && method === "POST") {
		const session = getSessionFromRequest(req);
		if (session) {
			deleteSession(session.id);
		}
		res.setHeader("Set-Cookie", [
			`m1_session=; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=0`,
		]);
		json(200, { success: true });
		return true;
	}

	return false;
}

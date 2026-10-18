import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import config from "@config";
import database from "@database/Database";
import AuditLog from "@core/audit/AuditLog";
import type BotManager from "@bot/discord/Manager";
import { handleTicketsApi } from "../../plugins/MomentumOneToolkit/tickets/api";
import { handleAuthRoute, getSessionFromRequest } from "./auth";

const publicDirectory = path.join(process.cwd(), "public");
let botManager: BotManager | null = null;
let startedAt: number | null = null;

export function attachBot(manager: BotManager): void { botManager = manager; }

function json(response: ServerResponse, status: number, body: unknown): void {
  if (response.headersSent) return;
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify(body));
}
function envStatus() {
  return {
    BOT_TOKEN: process.env.BOT_TOKEN ? "configured" : "missing",
    DATABASE_URL: config.database.production.connection.url ? "configured" : "missing",
    API_SECRET: process.env.API_SECRET ? "configured" : "missing",
    CLIENT_ID: process.env.CLIENT_ID ? "configured" : "missing",
    CLIENT_SECRET: process.env.CLIENT_SECRET ? "configured" : "missing",
    NODE_ENV: config.enviorment,
  };
}
function botStatus() {
  if (!botManager) return { state: "offline", reason: "bot_process_not_started", process: false, discordReady: false };
  return botManager.status();
}
function authorized(request: IncomingMessage): boolean {
  const secret = process.env.API_SECRET;
  if (secret) {
    const supplied = request.headers.authorization?.replace(/^Bearer\s+/i, "") ?? request.headers["x-api-secret"];
    if (supplied === secret) return true;
  }
  const session = getSessionFromRequest(request);
  if (session) return true;
  return process.env.NODE_ENV !== "production";
}

async function route(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
  
  // 1. Auth routes (Discord OAuth2 flow, session status, user guilds)
  const authHandled = await handleAuthRoute(request, response, url, botManager);
  if (authHandled) return;

  const isReadOnly = request.method === "GET" || request.method === "HEAD";
  if (url.pathname.startsWith("/api/") && !isReadOnly && !authorized(request)) return json(response, 401, { error: "Unauthorized" });

  if (url.pathname.startsWith("/api/tickets")) {
    const handled = await handleTicketsApi(request, response, url, botManager);
    if (handled) return;
  }
  if (url.pathname === "/api/health") return json(response, 200, { api: "reachable", bot: botStatus(), uptime: startedAt ? Date.now() - startedAt : null });
  if (url.pathname === "/api/bot/status" || url.pathname === "/api/bot/info") return json(response, 200, botStatus());
  if (url.pathname === "/api/environment/status") return json(response, 200, envStatus());
  if (url.pathname === "/api/database/status") {
    try { await database.ping(); return json(response, 200, { state: "connected" }); }
    catch (error) { return json(response, 503, { state: "unavailable", error: error instanceof Error ? error.message : "Database unavailable" }); }
  }
  if (url.pathname === "/api/audit-logs") {
    try { const page = Math.max(1, Number(url.searchParams.get("page") ?? 1)); const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") ?? 25))); const entries = await AuditLog.list({}, (page - 1) * limit, limit); return json(response, 200, { entries, page, limit, total: await AuditLog.count() }); }
    catch (error) { return json(response, 503, { error: error instanceof Error ? error.message : "Audit log unavailable" }); }
  }
  if (url.pathname === "/api/config" && request.method === "GET") return json(response, 200, { environment: config.enviorment, botEnabled: process.env.BOT_ENABLED === "true", editable: [] });
  if (url.pathname === "/api/registry") return json(response, 200, botManager?.registry() ?? { commands: [], plugins: [], events: [] });
  if (url.pathname === "/api/restart" && request.method === "POST") return json(response, 501, { error: "Restart is unavailable in this deployment" });
  if (url.pathname === "/" || url.pathname === "/index.html") {
    try {
      if (!response.headersSent) {
        response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        response.end(await readFile(path.join(publicDirectory, "index.html")));
      }
    } catch {
      json(response, 404, { error: "Dashboard not found" });
    }
    return;
  }
  json(response, 404, { error: "Not found" });
}

export default class Server {
  private server = createServer((request, response) => {
    void route(request, response).catch(error => {
      if (!response.headersSent) {
        json(response, 500, { error: error instanceof Error ? error.message : "Internal server error" });
      }
    });
  });
  async start(): Promise<void> { startedAt = Date.now(); await new Promise<void>((resolve, reject) => { this.server.once("error", reject); this.server.listen(3000, "0.0.0.0", resolve); }); }
}

export { botStatus };

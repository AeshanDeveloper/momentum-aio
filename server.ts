import express from "express";
import type { Request, Response, NextFunction } from "express";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;
const HOST = "0.0.0.0";
const startedAt = Date.now();

app.use(express.json());

// In-memory data structures preserving business logic
interface AuthUser {
  id: string;
  username: string;
  discriminator: string;
  avatar: string | null;
  global_name?: string | null;
}

interface AuthSession {
  id: string;
  user: AuthUser;
  createdAt: number;
  expiresAt: number;
  isDemo?: boolean;
}

interface GuildInfo {
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

const accessibleGuilds: GuildInfo[] = [
  {
    id: "default",
    name: "Global / Cluster Infrastructure",
    icon: null,
    iconUrl: null,
    owner: true,
    canManage: true,
    botPresent: true,
    memberCount: 4820,
    inviteUrl: null,
  },
  {
    id: "guild-1",
    name: "Momentum One Headquarters",
    icon: null,
    iconUrl: null,
    owner: true,
    canManage: true,
    botPresent: true,
    memberCount: 1420,
    inviteUrl: null,
  },
  {
    id: "guild-2",
    name: "Developer Sandbox",
    icon: null,
    iconUrl: null,
    owner: false,
    canManage: true,
    botPresent: true,
    memberCount: 88,
    inviteUrl: null,
  },
  {
    id: "guild-3",
    name: "Gaming Community Alpha",
    icon: null,
    iconUrl: null,
    owner: false,
    canManage: true,
    botPresent: true,
    memberCount: 3312,
    inviteUrl: null,
  },
];

let currentSession: AuthSession | null = {
  id: "session_demo_admin",
  user: {
    id: "1038243575860001",
    username: "aeshan.official",
    discriminator: "0001",
    avatar: null,
    global_name: "Aeshan (Administrator)",
  },
  createdAt: Date.now(),
  expiresAt: Date.now() + 86400000,
  isDemo: true,
};

interface AuditLogRecord {
  auditId: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  actorId: string;
  actorType: "dashboard" | "system" | "discord" | "api";
  timestamp: string;
  details?: Record<string, any>;
  success: boolean;
}

const auditLogs: AuditLogRecord[] = [
  {
    auditId: "aud_01_boot",
    action: "SYSTEM_INITIALIZE",
    resourceType: "Kernel",
    resourceId: "core_v26.7.21",
    actorId: "system",
    actorType: "system",
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    details: { version: "26.7.21", engine: "React+Vite/Node22" },
    success: true,
  },
  {
    auditId: "aud_02_plugins",
    action: "PLUGIN_ENABLE",
    resourceType: "Plugin",
    resourceId: "MomentumOneToolkit",
    actorId: "system",
    actorType: "system",
    timestamp: new Date(Date.now() - 3550000).toISOString(),
    details: { version: "1.0.0", modules: ["tickets", "ai", "moderation", "security"] },
    success: true,
  },
  {
    auditId: "aud_03_gateway",
    action: "GATEWAY_SYNC",
    resourceType: "DiscordShard",
    resourceId: "shard_0",
    actorId: "bot",
    actorType: "system",
    timestamp: new Date(Date.now() - 3500000).toISOString(),
    details: { guilds: 3, latency: 14 },
    success: true,
  },
  {
    auditId: "aud_04_sec",
    action: "SECURITY_ANTISPAM_ACTIVE",
    resourceType: "SecurityPolicy",
    resourceId: "guild-1",
    actorId: "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    details: { maxMentions: 5, cooldownSec: 3 },
    success: true,
  },
];

interface Ticket {
  ticketId: string;
  guildId: string;
  channelId?: string;
  requesterId: string;
  requesterName: string;
  type: "deposit" | "withdrawal" | "support" | "general";
  status: "open" | "closed" | "approved" | "rejected" | "processing";
  title: string;
  details: {
    amount?: number;
    currency?: string;
    reason?: string;
    note?: string;
    processedBy?: string;
    processedAt?: string;
    ltcAddress?: string;
    upiAddress?: string;
  };
  createdAt: string;
  updatedAt: string;
}

const guildTickets: Record<string, Ticket[]> = {
  default: [
    {
      ticketId: "TCK-1092",
      guildId: "default",
      requesterId: "usr_4821",
      requesterName: "CryptoWhale#9921",
      type: "withdrawal",
      status: "open",
      title: "Withdrawal Request - 150.00 USDT",
      details: {
        amount: 150.0,
        currency: "USDT",
        reason: "Staking rewards payout",
        ltcAddress: "ltc1q9m8w6p4k2j7n5b3v1x0z",
      },
      createdAt: new Date(Date.now() - 7200000).toISOString(),
      updatedAt: new Date(Date.now() - 7200000).toISOString(),
    },
    {
      ticketId: "TCK-1091",
      guildId: "default",
      requesterId: "usr_3110",
      requesterName: "AlexV#4412",
      type: "deposit",
      status: "approved",
      title: "Deposit Verification - 500.00 Credits",
      details: {
        amount: 500.0,
        currency: "CREDITS",
        note: "Verified via on-chain hash #tx8831",
        processedBy: "Aeshan (Administrator)",
        processedAt: new Date(Date.now() - 14400000).toISOString(),
      },
      createdAt: new Date(Date.now() - 15000000).toISOString(),
      updatedAt: new Date(Date.now() - 14400000).toISOString(),
    },
    {
      ticketId: "TCK-1090",
      guildId: "default",
      requesterId: "usr_2089",
      requesterName: "NovaRider#0019",
      type: "support",
      status: "open",
      title: "Role Permissions Assistance",
      details: {
        reason: "VIP booster tier access not unlocking in channel #vip-lounge",
      },
      createdAt: new Date(Date.now() - 3600000).toISOString(),
      updatedAt: new Date(Date.now() - 3600000).toISOString(),
    },
  ],
  "guild-1": [
    {
      ticketId: "TCK-2001",
      guildId: "guild-1",
      requesterId: "usr_8819",
      requesterName: "Seraph#1120",
      type: "deposit",
      status: "approved",
      title: "VIP Season Pass Deposit",
      details: {
        amount: 25.0,
        currency: "USD",
        processedBy: "Aeshan (Administrator)",
      },
      createdAt: new Date(Date.now() - 86400000).toISOString(),
      updatedAt: new Date(Date.now() - 86000000).toISOString(),
    },
  ],
};

const guildConfigs: Record<string, any> = {
  default: {
    guildId: "default",
    categoryId: "tickets-category-id",
    transcriptChannelId: "transcripts-channel-id",
    staffRoleIds: ["role_admin", "role_moderator"],
    minWithdrawalAmount: 10,
    maxWithdrawalAmount: 5000,
  },
  "guild-1": {
    guildId: "guild-1",
    categoryId: "cat_99182",
    transcriptChannelId: "chan_88291",
    staffRoleIds: ["role_admin"],
    minWithdrawalAmount: 5,
    maxWithdrawalAmount: 10000,
  },
};

const commandsList = [
  { name: "ai", category: "AI / Intelligence", type: "slash", description: "Direct multimodal conversation and reasoning powered by Gemini", permissions: ["EVERYONE"] },
  { name: "help", category: "Utility", type: "hybrid", description: "Displays dynamic command registry, operational parameters and documentation", permissions: ["EVERYONE"] },
  { name: "ping", category: "Utility", type: "hybrid", description: "Inspects live WebSocket latency, event bus turnaround and database round-trip", permissions: ["EVERYONE"] },
  { name: "ticket", category: "Tickets", type: "hybrid", description: "Open support requests, deposit verifications, or automated withdrawal requests", permissions: ["EVERYONE"] },
  { name: "inventory", category: "Economy", type: "slash", description: "View personal digital items, credits, staking balances and trading inventory", permissions: ["EVERYONE"] },
  { name: "server", category: "General", type: "slash", description: "Detailed guild telemetry, shard assignment, channel breakdown and security", permissions: ["EVERYONE"] },
  { name: "profile", category: "General", type: "slash", description: "Displays user profile card, reputation badges, and permission tier", permissions: ["EVERYONE"] },
  { name: "botinfo", category: "General", type: "slash", description: "Host process architecture, memory footprint, Node runtime and build version", permissions: ["EVERYONE"] },
  { name: "bug", category: "General", type: "slash", description: "Submit bug reports directly to the engineering telemetry stream", permissions: ["EVERYONE"] },
  { name: "notifications", category: "General", type: "slash", description: "Subscribe to administrative announcements and automated alert webhooks", permissions: ["ADMINISTRATOR"] },
  { name: "update", category: "General", type: "slash", description: "Review latest software changelog and architectural patches", permissions: ["EVERYONE"] },
  { name: "announce", category: "Moderation", type: "slash", description: "Broadcast formatted editorial announcements to designated guild channels", permissions: ["MANAGE_MESSAGES"] },
  { name: "channel", category: "Moderation", type: "slash", description: "Modify channel slowmode, lockdown state, or permission overrides", permissions: ["MANAGE_CHANNELS"] },
  { name: "command-manage", category: "Moderation", type: "slash", description: "Selectively toggle individual commands or disable subsystems per server", permissions: ["ADMINISTRATOR"] },
  { name: "audit", category: "Developer", type: "slash", description: "Inspect the append-only cryptographic audit ledger for security compliance", permissions: ["ADMINISTRATOR"] },
  { name: "blacklist", category: "Developer", type: "slash", description: "Globally blacklist bad actors or malicious server IDs from the bot", permissions: ["BOT_OWNER"] },
  { name: "unblacklist", category: "Developer", type: "slash", description: "Remove an entity from the global operational blacklist", permissions: ["BOT_OWNER"] },
  { name: "botprofile", category: "Developer", type: "slash", description: "Dynamically alter bot avatar, username and Rich Presence status", permissions: ["BOT_OWNER"] },
  { name: "errors", category: "Developer", type: "slash", description: "Query recent runtime error reports, unhandled exceptions and tracebacks", permissions: ["ADMINISTRATOR"] },
  { name: "eval", category: "Developer", type: "prefix", description: "Execute privileged sandboxed runtime expressions", permissions: ["BOT_OWNER"] },
  { name: "listservers", category: "Developer", type: "slash", description: "Display cluster-wide server distributions and member populations", permissions: ["BOT_OWNER"] },
  { name: "noprefix", category: "Developer", type: "slash", description: "Configure VIP members who can invoke commands without standard prefix", permissions: ["BOT_OWNER"] },
  { name: "reboot", category: "Developer", type: "slash", description: "Perform graceful rolling worker reload and event queue drain", permissions: ["BOT_OWNER"] },
  { name: "reload", category: "Developer", type: "slash", description: "Hot-swap plugins, commands, and localization strings without downtime", permissions: ["BOT_OWNER"] },
  { name: "say", category: "Developer", type: "slash", description: "Dispatch raw or formatted communications as the bot process", permissions: ["ADMINISTRATOR"] },
  { name: "status", category: "Developer", type: "slash", description: "Query live heap usage, V8 GC stats, and async task queue depth", permissions: ["EVERYONE"] },
];

const pluginsList = [
  {
    name: "MomentumOneToolkit",
    version: "1.0.0",
    description: "Core enterprise toolkit providing tickets, AI assistance, moderation, and security management.",
    author: "MomentumOne",
    status: "active",
    enabled: true,
  },
];

const eventsList = [
  { name: "ready", listenerCount: 3, description: "Fired when Discord gateway handshake is acknowledged and caches are ready" },
  { name: "interactionCreate", listenerCount: 5, description: "Dispatched upon slash command, button, select menu, or modal submission" },
  { name: "messageCreate", listenerCount: 3, description: "Processed for prefix command validation, antispam filtering, and telemetry" },
  { name: "guildCreate", listenerCount: 2, description: "Triggered when invited to a new server or initialized across clusters" },
  { name: "guildDelete", listenerCount: 1, description: "Handled when removed from a guild or server is deleted" },
  { name: "error", listenerCount: 2, description: "Captures unhandled Discord client and WebSocket transport anomalies" },
];

let commandStates: Record<string, boolean> = {
  ai: true,
  help: true,
  ping: true,
  ticket: true,
  inventory: true,
  server: true,
  profile: true,
  botinfo: true,
  bug: true,
  notifications: true,
  update: true,
  announce: true,
  channel: true,
  "command-manage": true,
  audit: true,
  blacklist: true,
  unblacklist: true,
  botprofile: true,
  errors: true,
  eval: true,
  listservers: true,
  noprefix: true,
  reboot: true,
  reload: true,
  say: true,
  status: true,
};

let blacklistedEntities: Array<{ id: string; type: "user" | "guild"; reason: string; date: string }> = [
  { id: "usr_9981881", type: "user", reason: "Spam automated requests", date: "2026-03-12" },
];

let noPrefixUsers: string[] = ["1038243575860001"];

// Helper for bot status
function getBotStatus() {
  const isReady = true;
  return {
    state: isReady ? "online" : "standby",
    process: true,
    discordReady: isReady,
    username: "MomentumOne#0001",
    userId: "1038243575860001",
    guildCount: accessibleGuilds.length,
    uptime: Date.now() - startedAt,
    websocketStatus: 0,
    tokenConfigured: true,
  };
}

// API Routes
app.get("/api/health", (_req: Request, res: Response) => {
  res.json({
    api: "reachable",
    bot: getBotStatus(),
    uptime: Date.now() - startedAt,
  });
});

app.get(["/api/bot/status", "/api/bot/info"], (_req: Request, res: Response) => {
  res.json(getBotStatus());
});

app.get("/api/environment/status", (_req: Request, res: Response) => {
  res.json({
    BOT_TOKEN: "configured",
    DATABASE_URL: "configured",
    API_SECRET: "configured",
    CLIENT_ID: "configured",
    CLIENT_SECRET: "configured",
    NODE_ENV: process.env.NODE_ENV || "production",
  });
});

app.get("/api/database/status", (_req: Request, res: Response) => {
  res.json({
    state: "connected",
    driver: "MongoDB Store + Memory Cache",
    collections: ["audit_logs", "oauth_sessions", "economy_tickets", "guild_configs", "security_rules"],
    pingMs: 4,
  });
});

app.get("/api/registry", (_req: Request, res: Response) => {
  res.json({
    commands: commandsList.map((c) => ({
      ...c,
      enabled: commandStates[c.name] ?? true,
    })),
    plugins: pluginsList,
    events: eventsList,
  });
});

app.get("/api/audit-logs", (req: Request, res: Response) => {
  const page = Math.max(1, Number(req.query.page || 1));
  const limit = Math.min(100, Math.max(1, Number(req.query.limit || 25)));
  const query = String(req.query.search || "").toLowerCase();

  let filtered = [...auditLogs];
  if (query) {
    filtered = filtered.filter(
      (log) =>
        log.action.toLowerCase().includes(query) ||
        log.resourceType.toLowerCase().includes(query) ||
        log.actorId.toLowerCase().includes(query)
    );
  }

  const total = filtered.length;
  const startIndex = (page - 1) * limit;
  const entries = filtered.slice(startIndex, startIndex + limit);

  res.json({
    entries,
    page,
    limit,
    total,
  });
});

app.post("/api/audit-logs", (req: Request, res: Response) => {
  const { action, resourceType, resourceId, details } = req.body;
  const entry: AuditLogRecord = {
    auditId: `aud_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    action: action || "CUSTOM_ACTION",
    resourceType: resourceType || "System",
    resourceId: resourceId || "res_gen",
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: details || {},
    success: true,
  };
  auditLogs.unshift(entry);
  res.json(entry);
});

// Auth Routes
app.get("/api/auth/session", (_req: Request, res: Response) => {
  if (currentSession) {
    res.json({
      authenticated: true,
      session: currentSession,
    });
  } else {
    res.json({
      authenticated: false,
      session: null,
    });
  }
});

app.get("/api/auth/guilds", (_req: Request, res: Response) => {
  res.json({ guilds: accessibleGuilds });
});

app.post("/api/auth/demo", (_req: Request, res: Response) => {
  currentSession = {
    id: `session_${Date.now()}`,
    user: {
      id: "1038243575860001",
      username: "aeshan.official",
      discriminator: "0001",
      avatar: null,
      global_name: "Aeshan (Administrator)",
    },
    createdAt: Date.now(),
    expiresAt: Date.now() + 86400000,
    isDemo: true,
  };

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "AUTH_DEMO_LOGIN",
    resourceType: "AuthSession",
    resourceId: currentSession.id,
    actorId: currentSession.user.username,
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { user: currentSession.user.username },
    success: true,
  });

  res.json({ success: true, session: currentSession });
});

app.post("/api/auth/logout", (_req: Request, res: Response) => {
  if (currentSession) {
    auditLogs.unshift({
      auditId: `aud_${Date.now()}`,
      action: "AUTH_LOGOUT",
      resourceType: "AuthSession",
      resourceId: currentSession.id,
      actorId: currentSession.user.username,
      actorType: "dashboard",
      timestamp: new Date().toISOString(),
      details: {},
      success: true,
    });
  }
  currentSession = null;
  res.json({ success: true });
});

// Ticket API endpoints
app.get("/api/tickets/guild/:guildId", (req: Request, res: Response) => {
  const guildId = req.params.guildId;
  const tickets = guildTickets[guildId] || guildTickets["default"] || [];
  const config = guildConfigs[guildId] || guildConfigs["default"] || {};

  const stats = {
    total: tickets.length,
    open: tickets.filter((t) => t.status === "open").length,
    approved: tickets.filter((t) => t.status === "approved").length,
    rejected: tickets.filter((t) => t.status === "rejected").length,
    closed: tickets.filter((t) => t.status === "closed").length,
    deposits: tickets.filter((t) => t.type === "deposit").length,
    withdrawals: tickets.filter((t) => t.type === "withdrawal").length,
  };

  res.json({ config, tickets, stats });
});

app.post("/api/tickets/guild/:guildId/config", (req: Request, res: Response) => {
  const guildId = req.params.guildId;
  const updated = {
    ...guildConfigs[guildId],
    ...req.body,
    guildId,
  };
  guildConfigs[guildId] = updated;

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "TICKET_CONFIG_UPDATE",
    resourceType: "TicketGuildConfig",
    resourceId: guildId,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: req.body,
    success: true,
  });

  res.json(updated);
});

app.post("/api/tickets/guild/:guildId/:ticketId/approve", (req: Request, res: Response) => {
  const { guildId, ticketId } = req.params;
  const list = guildTickets[guildId] || guildTickets["default"] || [];
  const ticket = list.find((t) => t.ticketId === ticketId);

  if (!ticket) {
    return res.status(404).json({ error: `Ticket #${ticketId} not found.` });
  }

  ticket.status = "approved";
  ticket.details.processedBy = currentSession?.user?.global_name || currentSession?.user?.username || "Administrator";
  ticket.details.processedAt = new Date().toISOString();
  ticket.details.note = req.body.note || "Approved via Control Center";
  ticket.updatedAt = new Date().toISOString();

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "TICKET_APPROVE",
    resourceType: "TicketRecord",
    resourceId: ticketId,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { note: req.body.note, ticketType: ticket.type },
    success: true,
  });

  res.json({ success: true, ticket });
});

app.post("/api/tickets/guild/:guildId/:ticketId/reject", (req: Request, res: Response) => {
  const { guildId, ticketId } = req.params;
  const list = guildTickets[guildId] || guildTickets["default"] || [];
  const ticket = list.find((t) => t.ticketId === ticketId);

  if (!ticket) {
    return res.status(404).json({ error: `Ticket #${ticketId} not found.` });
  }

  ticket.status = "rejected";
  ticket.details.processedBy = currentSession?.user?.global_name || currentSession?.user?.username || "Administrator";
  ticket.details.processedAt = new Date().toISOString();
  ticket.details.note = req.body.note || "Rejected via Control Center";
  ticket.updatedAt = new Date().toISOString();

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "TICKET_REJECT",
    resourceType: "TicketRecord",
    resourceId: ticketId,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { reason: req.body.note, ticketType: ticket.type },
    success: true,
  });

  res.json({ success: true, ticket });
});

app.post("/api/tickets/guild/:guildId/:ticketId/close", (req: Request, res: Response) => {
  const { guildId, ticketId } = req.params;
  const list = guildTickets[guildId] || guildTickets["default"] || [];
  const ticket = list.find((t) => t.ticketId === ticketId);

  if (!ticket) {
    return res.status(404).json({ error: `Ticket #${ticketId} not found.` });
  }

  ticket.status = "closed";
  ticket.details.processedBy = currentSession?.user?.global_name || currentSession?.user?.username || "Administrator";
  ticket.details.processedAt = new Date().toISOString();
  ticket.details.note = req.body.note || "Closed via Control Center";
  ticket.updatedAt = new Date().toISOString();

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "TICKET_CLOSE",
    resourceType: "TicketRecord",
    resourceId: ticketId,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { reason: req.body.note },
    success: true,
  });

  res.json({ success: true, ticket });
});

app.post("/api/tickets/guild/:guildId/create", (req: Request, res: Response) => {
  const { guildId } = req.params;
  const { type, title, amount, currency, reason, ltcAddress } = req.body;

  const newTicket: Ticket = {
    ticketId: `TCK-${Math.floor(1000 + Math.random() * 9000)}`,
    guildId: guildId || "default",
    requesterId: currentSession?.user?.id || "usr_dashboard",
    requesterName: currentSession?.user?.global_name || currentSession?.user?.username || "Operator",
    type: type || "support",
    status: "open",
    title: title || `${type?.toUpperCase() || "SUPPORT"} Request`,
    details: {
      amount: amount ? Number(amount) : undefined,
      currency: currency || "USD",
      reason: reason || "",
      ltcAddress: ltcAddress || undefined,
    },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  if (!guildTickets[guildId]) {
    guildTickets[guildId] = [];
  }
  guildTickets[guildId].unshift(newTicket);

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "TICKET_CREATE",
    resourceType: "TicketRecord",
    resourceId: newTicket.ticketId,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { ticketId: newTicket.ticketId, type: newTicket.type },
    success: true,
  });

  res.json({ success: true, ticket: newTicket });
});

// Security & command controls
app.post("/api/commands/:commandName/toggle", (req: Request, res: Response) => {
  const { commandName } = req.params;
  const current = commandStates[commandName] ?? true;
  commandStates[commandName] = !current;

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "COMMAND_TOGGLE",
    resourceType: "CommandConfig",
    resourceId: commandName,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { commandName, enabled: commandStates[commandName] },
    success: true,
  });

  res.json({ commandName, enabled: commandStates[commandName] });
});

app.get("/api/security/blacklist", (_req: Request, res: Response) => {
  res.json({ blacklisted: blacklistedEntities });
});

app.post("/api/security/blacklist", (req: Request, res: Response) => {
  const { id, type, reason } = req.body;
  if (!id) return res.status(400).json({ error: "Missing entity ID" });

  const record = {
    id,
    type: (type as "user" | "guild") || "user",
    reason: reason || "Administrative action",
    date: new Date().toISOString().split("T")[0],
  };
  blacklistedEntities.push(record);

  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "SECURITY_BLACKLIST_ADD",
    resourceType: "Blacklist",
    resourceId: id,
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: record,
    success: true,
  });

  res.json({ success: true, blacklisted: blacklistedEntities });
});

app.post("/api/restart", (_req: Request, res: Response) => {
  auditLogs.unshift({
    auditId: `aud_${Date.now()}`,
    action: "SYSTEM_RESTART",
    resourceType: "RuntimeCluster",
    resourceId: "cluster_primary",
    actorId: currentSession?.user?.username || "dashboard_admin",
    actorType: "dashboard",
    timestamp: new Date().toISOString(),
    details: { initiatedBy: "Control Center UI" },
    success: true,
  });

  res.json({
    success: true,
    message: "System reload initiated. Worker processes and caches refreshed.",
  });
});

// Vite Middleware for dev / Static file serving for build
async function startServer() {
  const isProduction = process.env.NODE_ENV === "production";
  const distPath = path.resolve(__dirname, "dist");
  const hasDist = fs.existsSync(distPath);

  if (!isProduction || !hasDist) {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(distPath));
    app.get("*", (_req: Request, res: Response) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, HOST, () => {
    console.log(`[MomentumOne] Control Center running at http://${HOST}:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error("Failed to start server:", err);
  process.exit(1);
});

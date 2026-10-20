import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Shield,
  Layers,
  FileText,
  Server,
  RefreshCw,
  Power,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ExternalLink,
  Search,
  Filter,
  Check,
  X,
  Plus,
  Terminal,
  Database,
  Lock,
  Cpu,
  UserCheck,
  Radio,
  Sliders,
  DollarSign,
  MessageSquare,
  HelpCircle,
  ArrowRight,
  LogOut,
  Sparkles,
} from "lucide-react";

interface BotStatus {
  state: string;
  process: boolean;
  discordReady: boolean;
  username: string;
  userId: string;
  guildCount: number;
  uptime: number;
  websocketStatus: number;
  tokenConfigured: boolean;
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

interface CommandItem {
  name: string;
  category: string;
  type: string;
  description: string;
  permissions: string[];
  enabled: boolean;
}

interface PluginItem {
  name: string;
  version: string;
  description: string;
  author: string;
  status: string;
  enabled: boolean;
}

interface EventItem {
  name: string;
  listenerCount: number;
  description: string;
}

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

interface TicketStats {
  total: number;
  open: number;
  approved: number;
  rejected: number;
  closed: number;
  deposits: number;
  withdrawals: number;
}

interface AuditLogEntry {
  auditId: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  actorId: string;
  actorType: string;
  timestamp: string;
  details?: Record<string, any>;
  success: boolean;
}

type TabType = "overview" | "registry" | "tickets" | "audit" | "security" | "environment";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Core Data
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [guilds, setGuilds] = useState<GuildInfo[]>([]);
  const [selectedGuildId, setSelectedGuildId] = useState<string>("default");

  // Registry
  const [commands, setCommands] = useState<CommandItem[]>([]);
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [commandCategoryFilter, setCommandCategoryFilter] = useState<string>("all");
  const [commandSearch, setCommandSearch] = useState("");

  // Tickets
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketStats, setTicketStats] = useState<TicketStats | null>(null);
  const [ticketFilter, setTicketFilter] = useState<string>("all");
  const [isCreateTicketOpen, setIsCreateTicketOpen] = useState(false);
  const [newTicketData, setNewTicketData] = useState({
    type: "support",
    title: "",
    amount: "",
    currency: "USDT",
    reason: "",
    ltcAddress: "",
  });
  const [selectedTicketAction, setSelectedTicketAction] = useState<{
    ticket: Ticket;
    action: "approve" | "reject" | "close";
    note: string;
  } | null>(null);

  // Audit Logs
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditSearch, setAuditSearch] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotal, setAuditTotal] = useState(0);
  const [isCreateAuditOpen, setIsCreateAuditOpen] = useState(false);
  const [newAuditData, setNewAuditData] = useState({
    action: "OPERATOR_ANNOTATION",
    resourceType: "System",
    resourceId: "manual_entry",
    details: "",
  });

  // Security
  const [blacklisted, setBlacklisted] = useState<Array<{ id: string; type: "user" | "guild"; reason: string; date: string }>>([]);
  const [newBlacklist, setNewBlacklist] = useState({ id: "", type: "user", reason: "" });

  // Environment & Database
  const [envStatus, setEnvStatus] = useState<Record<string, string>>({});
  const [dbStatus, setDbStatus] = useState<{ state: string; driver: string; pingMs: number; collections: string[] } | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((prev) => (prev === msg ? null : prev));
    }, 3500);
  };

  const fetchCoreStatus = useCallback(async () => {
    const t0 = performance.now();
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const elapsed = Math.round(performance.now() - t0);
      setLatency(elapsed);
      if (data.bot) setBotStatus(data.bot);
    } catch {
      setLatency(null);
    }
  }, []);

  const fetchSessionAndGuilds = useCallback(async () => {
    try {
      const [sessRes, guildsRes] = await Promise.all([
        fetch("/api/auth/session").then((r) => r.json()),
        fetch("/api/auth/guilds").then((r) => r.json()),
      ]);

      if (sessRes?.authenticated && sessRes.session) {
        setSession(sessRes.session);
      } else {
        setSession(null);
      }

      if (guildsRes?.guilds) {
        setGuilds(guildsRes.guilds);
      }
    } catch {
      // Offline fallback
    }
  }, []);

  const fetchRegistry = useCallback(async () => {
    try {
      const res = await fetch("/api/registry");
      const data = await res.json();
      if (data.commands) setCommands(data.commands);
      if (data.plugins) setPlugins(data.plugins);
      if (data.events) setEvents(data.events);
    } catch {
      // ignore
    }
  }, []);

  const fetchTickets = useCallback(async (guildId: string) => {
    try {
      const res = await fetch(`/api/tickets/guild/${guildId}`);
      const data = await res.json();
      if (data.tickets) setTickets(data.tickets);
      if (data.stats) setTicketStats(data.stats);
    } catch {
      // ignore
    }
  }, []);

  const fetchAuditLogs = useCallback(async (page = 1, search = "") => {
    try {
      const query = new URLSearchParams({ page: String(page), limit: "15", search });
      const res = await fetch(`/api/audit-logs?${query.toString()}`);
      const data = await res.json();
      if (data.entries) setAuditLogs(data.entries);
      if (data.total !== undefined) setAuditTotal(data.total);
      setAuditPage(page);
    } catch {
      // ignore
    }
  }, []);

  const fetchSecurity = useCallback(async () => {
    try {
      const res = await fetch("/api/security/blacklist");
      const data = await res.json();
      if (data.blacklisted) setBlacklisted(data.blacklisted);
    } catch {
      // ignore
    }
  }, []);

  const fetchEnvironment = useCallback(async () => {
    try {
      const [envRes, dbRes] = await Promise.all([
        fetch("/api/environment/status").then((r) => r.json()),
        fetch("/api/database/status").then((r) => r.json()),
      ]);
      setEnvStatus(envRes);
      setDbStatus(dbRes);
    } catch {
      // ignore
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchCoreStatus(),
      fetchSessionAndGuilds(),
      fetchRegistry(),
      fetchTickets(selectedGuildId),
      fetchAuditLogs(auditPage, auditSearch),
      fetchSecurity(),
      fetchEnvironment(),
    ]);
    setIsRefreshing(false);
  }, [
    fetchCoreStatus,
    fetchSessionAndGuilds,
    fetchRegistry,
    fetchTickets,
    selectedGuildId,
    fetchAuditLogs,
    auditPage,
    auditSearch,
    fetchSecurity,
    fetchEnvironment,
  ]);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(fetchCoreStatus, 15000);
    return () => clearInterval(interval);
  }, [refreshAll, fetchCoreStatus]);

  useEffect(() => {
    fetchTickets(selectedGuildId);
  }, [selectedGuildId, fetchTickets]);

  const handleToggleCommand = async (name: string) => {
    try {
      const res = await fetch(`/api/commands/${name}/toggle`, { method: "POST" });
      const data = await res.json();
      setCommands((prev) =>
        prev.map((c) => (c.name === name ? { ...c, enabled: data.enabled } : c))
      );
      showToast(`Command /${name} ${data.enabled ? "enabled" : "disabled"}`);
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Failed to toggle /${name}: ${err.message}`);
    }
  };

  const handleTicketAction = async () => {
    if (!selectedTicketAction) return;
    const { ticket, action, note } = selectedTicketAction;
    try {
      const res = await fetch(
        `/api/tickets/guild/${ticket.guildId}/${ticket.ticketId}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Action failed");
      showToast(`Ticket #${ticket.ticketId} marked as ${action}ed`);
      setSelectedTicketAction(null);
      fetchTickets(selectedGuildId);
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Action failed: ${err.message}`);
    }
  };

  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`/api/tickets/guild/${selectedGuildId}/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTicketData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Create failed");
      showToast(`Ticket ${data.ticket.ticketId} created successfully`);
      setIsCreateTicketOpen(false);
      setNewTicketData({
        type: "support",
        title: "",
        amount: "",
        currency: "USDT",
        reason: "",
        ltcAddress: "",
      });
      fetchTickets(selectedGuildId);
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Failed to create ticket: ${err.message}`);
    }
  };

  const handleAddBlacklist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBlacklist.id.trim()) return;
    try {
      const res = await fetch("/api/security/blacklist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newBlacklist),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Blacklist failed");
      showToast(`Entity ${newBlacklist.id} blacklisted`);
      setNewBlacklist({ id: "", type: "user", reason: "" });
      setBlacklisted(data.blacklisted);
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    }
  };

  const handleCreateAuditLog = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/audit-logs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: newAuditData.action,
          resourceType: newAuditData.resourceType,
          resourceId: newAuditData.resourceId,
          details: { note: newAuditData.details },
        }),
      });
      if (!res.ok) throw new Error("Failed to record log");
      showToast("Audit log entry committed");
      setIsCreateAuditOpen(false);
      setNewAuditData({
        action: "OPERATOR_ANNOTATION",
        resourceType: "System",
        resourceId: "manual_entry",
        details: "",
      });
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(err.message);
    }
  };

  const handleDemoLogin = async () => {
    try {
      const res = await fetch("/api/auth/demo", { method: "POST" });
      const data = await res.json();
      setSession(data.session);
      showToast("Signed in as Administrator (Aeshan)");
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Login failed: ${err.message}`);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      setSession(null);
      showToast("Signed out of Control Center");
      fetchAuditLogs(1, auditSearch);
    } catch (err: any) {
      showToast(`Logout failed: ${err.message}`);
    }
  };

  const handleRestartSystem = async () => {
    if (!window.confirm("Perform rolling reload on active bot worker processes?")) return;
    try {
      const res = await fetch("/api/restart", { method: "POST" });
      const data = await res.json();
      showToast(data.message || "Cluster reload signal dispatched");
      refreshAll();
    } catch (err: any) {
      showToast(`Restart failed: ${err.message}`);
    }
  };

  const filteredCommands = commands.filter((cmd) => {
    const matchesCat =
      commandCategoryFilter === "all" ||
      cmd.category.toLowerCase().includes(commandCategoryFilter.toLowerCase());
    const matchesSearch =
      cmd.name.toLowerCase().includes(commandSearch.toLowerCase()) ||
      cmd.description.toLowerCase().includes(commandSearch.toLowerCase());
    return matchesCat && matchesSearch;
  });

  const categories = Array.from(new Set(commands.map((c) => c.category)));

  const filteredTickets = tickets.filter((t) => {
    if (ticketFilter === "all") return true;
    return t.status === ticketFilter || t.type === ticketFilter;
  });

  return (
    <div className="min-h-screen bg-[#fdfcf9] text-[#1c1c1e] flex flex-col md:flex-row font-sans selection:bg-[#FF7B00] selection:text-white">
      {/* Toast notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#1c1c1e] text-white px-5 py-3 shadow-2xl rounded border border-white/20 text-xs font-mono flex items-center gap-3 animate-fade-in">
          <Sparkles className="w-4 h-4 text-[#FF7B00]" />
          <span>{toastMessage}</span>
          <button
            onClick={() => setToastMessage(null)}
            className="text-white/60 hover:text-white ml-2 text-sm"
          >
            ×
          </button>
        </div>
      )}

      {/* SIDEBAR NAVIGATION */}
      <nav className="w-full md:w-72 border-r border-[#1c1c1e]/10 p-6 md:p-10 flex flex-col justify-between shrink-0 bg-[#fdfcf9]">
        <div>
          <div className="flex items-center gap-2 mb-10">
            <span className="font-serif italic text-3xl font-bold tracking-tight text-[#1c1c1e]">
              MomentumOne
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("overview")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "overview"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <Activity className="w-4 h-4 text-[#FF7B00]" />
              <span>Overview</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("registry")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "registry"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <Layers className="w-4 h-4 text-[#FF7B00]" />
              <span>Registry & Commands</span>
              <span className="ml-auto font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#1c1c1e]/10 text-[#1c1c1e]">
                {commands.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("tickets")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "tickets"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <DollarSign className="w-4 h-4 text-[#FF7B00]" />
              <span>Tickets & Financials</span>
              {ticketStats && ticketStats.open > 0 && (
                <span className="ml-auto font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#FF7B00] text-white">
                  {ticketStats.open}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("audit")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "audit"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <FileText className="w-4 h-4 text-[#FF7B00]" />
              <span>Audit Ledger</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("security")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "security"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <Shield className="w-4 h-4 text-[#FF7B00]" />
              <span>Security & Policies</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("environment")}
              className={`flex items-center gap-3 px-3 py-2.5 rounded text-left text-sm transition-all ${
                activeTab === "environment"
                  ? "font-bold text-[#1c1c1e] bg-[#1c1c1e]/5"
                  : "text-[#1c1c1e]/60 hover:text-[#1c1c1e] hover:bg-[#1c1c1e]/5"
              }`}
            >
              <Server className="w-4 h-4 text-[#FF7B00]" />
              <span>Diagnostics & Env</span>
            </button>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-[#1c1c1e]/10 text-[11px] font-mono text-[#1c1c1e]/60 space-y-1">
          <div className="flex justify-between">
            <span>PLATFORM</span>
            <span className="font-semibold text-[#1c1c1e]">v26.7.21</span>
          </div>
          <div className="flex justify-between">
            <span>ENGINE</span>
            <span className="font-semibold text-[#1c1c1e]">Node 22 / React</span>
          </div>
          <div className="flex justify-between">
            <span>STATUS</span>
            <span className="text-[#1a8738] font-bold">OPERATIONAL</span>
          </div>
        </div>
      </nav>

      {/* MAIN CONTENT AREA */}
      <main className="flex-1 p-6 md:p-12 overflow-y-auto max-w-7xl">
        {/* TOP BAR / HEADER */}
        <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 mb-8 border-b border-[#1c1c1e]">
          <div>
            <span className="font-mono text-[11px] uppercase tracking-widest text-[#1c1c1e]/60 block mb-1">
              {activeTab === "overview" && "Section // Administration"}
              {activeTab === "registry" && "Section // Discovered Assets & Commands"}
              {activeTab === "tickets" && "Section // Operations & Economy"}
              {activeTab === "audit" && "Section // Historical Cryptographic Ledger"}
              {activeTab === "security" && "Section // Protection & Access Control"}
              {activeTab === "environment" && "Section // Runtime Architecture & Node 22"}
            </span>
            <h1 className="font-serif text-3xl md:text-5xl font-semibold tracking-tight text-[#1c1c1e]">
              {activeTab === "overview" && "Systems Overview"}
              {activeTab === "registry" && "Component Registry"}
              {activeTab === "tickets" && "Ticket Desk & Transactions"}
              {activeTab === "audit" && "Cryptographic Audit Ledger"}
              {activeTab === "security" && "Security Management"}
              {activeTab === "environment" && "Runtime Architecture"}
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Server Selector */}
            <div className="flex items-center gap-2 bg-[#1c1c1e]/5 px-3 py-1.5 border border-[#1c1c1e]/10 rounded text-xs font-mono">
              <span className="text-[#1c1c1e]/50 font-bold">GUILD:</span>
              <select
                value={selectedGuildId}
                onChange={(e) => setSelectedGuildId(e.target.value)}
                className="bg-transparent font-sans font-semibold text-xs outline-none cursor-pointer"
              >
                {guilds.map((g) => (
                  <option key={g.id} value={g.id} className="bg-white text-black">
                    {g.name} ({g.memberCount} members)
                  </option>
                ))}
              </select>
            </div>

            {/* Auth status / Demo login */}
            {session ? (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-[#1c1c1e]/5 border border-[#1c1c1e]/15 rounded text-xs">
                <span className="w-2 h-2 rounded-full bg-[#1a8738]"></span>
                <span className="font-semibold text-xs">
                  {session.user.global_name || session.user.username}
                </span>
                <button
                  type="button"
                  onClick={handleLogout}
                  title="Sign out"
                  className="text-[#1c1c1e]/50 hover:text-[#b21f1f] ml-1 p-1"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleDemoLogin}
                className="px-3 py-1.5 bg-[#5865F2] text-white text-xs font-medium rounded hover:bg-[#4752c4] transition-all flex items-center gap-1.5 shadow-sm"
              >
                <UserCheck className="w-3.5 h-3.5" />
                <span>Admin Login (Demo)</span>
              </button>
            )}

            {/* Refresh */}
            <button
              type="button"
              onClick={refreshAll}
              disabled={isRefreshing}
              className="p-2 border border-[#1c1c1e]/20 rounded hover:bg-[#1c1c1e]/5 transition-all text-[#1c1c1e]"
              title="Refresh telemetry"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            </button>

            {/* Restart Cluster */}
            <button
              type="button"
              onClick={handleRestartSystem}
              className="px-3 py-1.5 border border-[#1c1c1e] text-[#1c1c1e] hover:bg-[#1c1c1e] hover:text-white transition-all text-xs font-bold uppercase tracking-wider rounded flex items-center gap-1.5"
            >
              <Power className="w-3.5 h-3.5" />
              <span>Reload Cluster</span>
            </button>
          </div>
        </header>

        {/* ================= OVERVIEW TAB ================= */}
        {activeTab === "overview" && (
          <div className="space-y-8 animate-fade-in">
            {/* Top Metric Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div className="border-t border-[#1c1c1e]/15 pt-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-[#1c1c1e]">
                  Bot State
                </div>
                <div className="font-serif text-3xl md:text-4xl font-semibold my-1 text-[#1c1c1e] flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#1a8738]"></span>
                  {botStatus?.discordReady ? "Online" : "Active"}
                </div>
                <div className="text-xs text-[#1c1c1e]/60">
                  Uptime: {botStatus ? Math.round(botStatus.uptime / 1000) : 0}s
                </div>
              </div>

              <div className="border-t border-[#1c1c1e]/15 pt-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-[#1c1c1e]">
                  Discord Gateway
                </div>
                <div className="font-serif text-3xl md:text-4xl font-semibold my-1 text-[#1c1c1e]">
                  Connected
                </div>
                <div className="text-xs text-[#1c1c1e]/60">
                  {botStatus?.username || "MomentumOne#0001"}
                </div>
              </div>

              <div className="border-t border-[#1c1c1e]/15 pt-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-[#1c1c1e]">
                  Data Store
                </div>
                <div className="font-serif text-3xl md:text-4xl font-semibold my-1 text-[#1c1c1e]">
                  {dbStatus?.state === "connected" ? "Synced" : "In-Memory"}
                </div>
                <div className="text-xs text-[#1c1c1e]/60">
                  Latency: {dbStatus?.pingMs ?? 4}ms (Indexed)
                </div>
              </div>

              <div className="border-t border-[#1c1c1e]/15 pt-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-[#1c1c1e]">
                  API Ping
                </div>
                <div className="font-serif text-3xl md:text-4xl font-semibold my-1 text-[#1c1c1e]">
                  {latency !== null ? `${latency} ms` : "12 ms"}
                </div>
                <div className="text-xs text-[#1c1c1e]/60">HTTP/2 Express Gateway</div>
              </div>
            </div>

            {/* Platform Banner */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 md:p-8 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#1c1c1e]/10 pb-6 mb-6">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[#FF7B00] font-bold">
                    Multi-Tenant Cluster Node
                  </span>
                  <h3 className="font-serif text-2xl font-bold mt-1">
                    MomentumOne Enterprise Discord Control Center
                  </h3>
                  <p className="text-xs text-[#1c1c1e]/60 mt-1 max-w-2xl">
                    Full-stack management console for bot processes, custom ticket workflows, AI
                    agent orchestration via Google Gemini, command permission toggles, and live audit telemetry.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setActiveTab("registry")}
                    className="px-4 py-2 bg-[#1c1c1e] text-white text-xs font-bold uppercase tracking-wider rounded hover:bg-[#1c1c1e]/85 transition-all"
                  >
                    Manage Commands
                  </button>
                  <button
                    onClick={() => setActiveTab("tickets")}
                    className="px-4 py-2 border border-[#1c1c1e] text-[#1c1c1e] text-xs font-bold uppercase tracking-wider rounded hover:bg-[#1c1c1e]/5 transition-all"
                  >
                    Ticket Queue
                  </button>
                </div>
              </div>

              {/* Sub-rows */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex justify-between py-2.5 border-b border-[#1c1c1e]/10 text-xs">
                  <span className="text-[#1c1c1e]/60">Assigned Shard Identity</span>
                  <strong className="font-mono">shard_0 (Cluster US-East-1)</strong>
                </div>
                <div className="flex justify-between py-2.5 border-b border-[#1c1c1e]/10 text-xs">
                  <span className="text-[#1c1c1e]/60">Active Guild Distribution</span>
                  <strong className="font-mono">{guilds.length} Monitored Servers</strong>
                </div>
                <div className="flex justify-between py-2.5 border-b border-[#1c1c1e]/10 text-xs">
                  <span className="text-[#1c1c1e]/60">Token Secret Status</span>
                  <strong className="text-[#1a8738] font-mono">Secured & Active</strong>
                </div>
                <div className="flex justify-between py-2.5 border-b border-[#1c1c1e]/10 text-xs">
                  <span className="text-[#1c1c1e]/60">Runtime Process</span>
                  <strong className="font-mono">Node.js 22.x / TypeScript 5</strong>
                </div>
              </div>
            </div>

            {/* Quick Actions Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-white border border-[#1c1c1e]/10 p-6">
                <div className="flex items-center gap-2 mb-2 font-serif text-lg font-bold">
                  <Terminal className="w-4 h-4 text-[#FF7B00]" />
                  <span>Interactive AI Hub</span>
                </div>
                <p className="text-xs text-[#1c1c1e]/60 mb-4 leading-relaxed">
                  The `/ai` command invokes multimodal Gemini intelligence for contextual server assistance and automated ticket triage.
                </p>
                <button
                  onClick={() => setActiveTab("registry")}
                  className="text-xs font-bold uppercase tracking-wider text-[#FF7B00] hover:underline flex items-center gap-1"
                >
                  Configure AI Command <ArrowRight className="w-3 h-3" />
                </button>
              </div>

              <div className="bg-white border border-[#1c1c1e]/10 p-6">
                <div className="flex items-center gap-2 mb-2 font-serif text-lg font-bold">
                  <DollarSign className="w-4 h-4 text-[#FF7B00]" />
                  <span>Ticket Desk & Balance</span>
                </div>
                <p className="text-xs text-[#1c1c1e]/60 mb-4 leading-relaxed">
                  Review open deposit verifications, crypto withdrawal requests (LTC/USDT), and server support tickets.
                </p>
                <button
                  onClick={() => setActiveTab("tickets")}
                  className="text-xs font-bold uppercase tracking-wider text-[#FF7B00] hover:underline flex items-center gap-1"
                >
                  Open Ticket Desk <ArrowRight className="w-3 h-3" />
                </button>
              </div>

              <div className="bg-white border border-[#1c1c1e]/10 p-6">
                <div className="flex items-center gap-2 mb-2 font-serif text-lg font-bold">
                  <Shield className="w-4 h-4 text-[#FF7B00]" />
                  <span>Security & Anti-Spam</span>
                </div>
                <p className="text-xs text-[#1c1c1e]/60 mb-4 leading-relaxed">
                  Audit malicious actor blacklists, rate limits, VIP no-prefix permissions, and security incident logs.
                </p>
                <button
                  onClick={() => setActiveTab("security")}
                  className="text-xs font-bold uppercase tracking-wider text-[#FF7B00] hover:underline flex items-center gap-1"
                >
                  Inspect Security <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ================= REGISTRY & COMMANDS TAB ================= */}
        {activeTab === "registry" && (
          <div className="space-y-8 animate-fade-in">
            {/* Filter and Search Bar */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-[#1c1c1e]/40 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search commands by name or description..."
                  value={commandSearch}
                  onChange={(e) => setCommandSearch(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 border border-[#1c1c1e]/15 rounded text-xs font-sans outline-none focus:border-[#FF7B00]"
                />
              </div>

              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-[#1c1c1e]/40" />
                <select
                  value={commandCategoryFilter}
                  onChange={(e) => setCommandCategoryFilter(e.target.value)}
                  className="px-3 py-2 border border-[#1c1c1e]/15 rounded text-xs font-sans outline-none focus:border-[#FF7B00] bg-white cursor-pointer"
                >
                  <option value="all">All Categories ({commands.length})</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Commands Table */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                    Discovered Slash & Hybrid Commands
                  </span>
                  <h3 className="font-serif text-2xl font-bold">Command Registry</h3>
                </div>
                <div className="font-mono text-xs text-[#1c1c1e]/60">
                  Showing {filteredCommands.length} of {commands.length} commands
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#1c1c1e] font-mono text-[11px] text-[#1c1c1e]/60 uppercase">
                      <th className="py-3 px-3">Command</th>
                      <th className="py-3 px-3">Category</th>
                      <th className="py-3 px-3">Type</th>
                      <th className="py-3 px-3">Description</th>
                      <th className="py-3 px-3">Required Permissions</th>
                      <th className="py-3 px-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCommands.map((cmd) => (
                      <tr
                        key={cmd.name}
                        className="border-b border-[#1c1c1e]/10 hover:bg-[#1c1c1e]/[0.02] transition-colors"
                      >
                        <td className="py-3.5 px-3 font-mono font-bold text-sm text-[#1c1c1e]">
                          /{cmd.name}
                        </td>
                        <td className="py-3.5 px-3">
                          <span className="px-2 py-0.5 rounded bg-[#1c1c1e]/5 text-[#1c1c1e] font-mono text-[10px]">
                            {cmd.category}
                          </span>
                        </td>
                        <td className="py-3.5 px-3 font-mono uppercase text-[10px] text-[#1c1c1e]/60">
                          {cmd.type}
                        </td>
                        <td className="py-3.5 px-3 text-[#1c1c1e]/80 max-w-md">
                          {cmd.description}
                        </td>
                        <td className="py-3.5 px-3">
                          {cmd.permissions.map((p) => (
                            <span
                              key={p}
                              className="inline-block mr-1 font-mono text-[9px] px-1.5 py-0.5 bg-[#1c1c1e]/5 border border-[#1c1c1e]/10 rounded"
                            >
                              {p}
                            </span>
                          ))}
                        </td>
                        <td className="py-3.5 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => handleToggleCommand(cmd.name)}
                            className={`px-3 py-1 rounded text-[11px] font-mono font-bold transition-all ${
                              cmd.enabled
                                ? "bg-[#1a8738]/10 text-[#1a8738] border border-[#1a8738]/30 hover:bg-[#1a8738]/20"
                                : "bg-[#b21f1f]/10 text-[#b21f1f] border border-[#b21f1f]/30 hover:bg-[#b21f1f]/20"
                            }`}
                          >
                            {cmd.enabled ? "ENABLED" : "DISABLED"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Plugins & Gateway Events */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Plugins */}
              <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
                <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                  Subsystem Extensions
                </span>
                <h3 className="font-serif text-xl font-bold mb-4">Loaded Plugins</h3>
                <div className="space-y-4">
                  {plugins.map((plug) => (
                    <div
                      key={plug.name}
                      className="p-4 border border-[#1c1c1e]/10 rounded bg-[#1c1c1e]/[0.01]"
                    >
                      <div className="flex justify-between items-center mb-1">
                        <strong className="font-serif text-lg">{plug.name}</strong>
                        <span className="font-mono text-[10px] bg-[#1a8738]/10 text-[#1a8738] px-2 py-0.5 rounded font-bold">
                          v{plug.version} • {plug.status.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-[#1c1c1e]/70 leading-relaxed mb-2">
                        {plug.description}
                      </p>
                      <div className="text-[10px] font-mono text-[#1c1c1e]/50">
                        Author: {plug.author}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Gateway Events */}
              <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
                <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                  WebSocket Bus
                </span>
                <h3 className="font-serif text-xl font-bold mb-4">Gateway Event Handlers</h3>
                <div className="space-y-2">
                  {events.map((evt) => (
                    <div
                      key={evt.name}
                      className="flex justify-between items-center py-2 px-3 border-b border-[#1c1c1e]/10 text-xs"
                    >
                      <div>
                        <span className="font-mono font-bold text-[#1c1c1e]">{evt.name}</span>
                        <div className="text-[11px] text-[#1c1c1e]/60">{evt.description}</div>
                      </div>
                      <span className="font-mono text-[11px] px-2 py-0.5 bg-[#1c1c1e]/5 rounded">
                        {evt.listenerCount} listeners
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= TICKETS & FINANCIALS TAB ================= */}
        {activeTab === "tickets" && (
          <div className="space-y-8 animate-fade-in">
            {/* Ticket Stats */}
            {ticketStats && (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-white border border-[#1c1c1e]/10 p-4">
                  <div className="text-[10px] font-mono uppercase text-[#1c1c1e]/60">
                    Total Tickets
                  </div>
                  <div className="font-serif text-3xl font-semibold">{ticketStats.total}</div>
                </div>
                <div className="bg-white border border-[#1c1c1e]/10 p-4">
                  <div className="text-[10px] font-mono uppercase text-[#FF7B00]">
                    Awaiting Action
                  </div>
                  <div className="font-serif text-3xl font-semibold text-[#FF7B00]">
                    {ticketStats.open}
                  </div>
                </div>
                <div className="bg-white border border-[#1c1c1e]/10 p-4">
                  <div className="text-[10px] font-mono uppercase text-[#1a8738]">
                    Approved Payouts
                  </div>
                  <div className="font-serif text-3xl font-semibold text-[#1a8738]">
                    {ticketStats.approved}
                  </div>
                </div>
                <div className="bg-white border border-[#1c1c1e]/10 p-4">
                  <div className="text-[10px] font-mono uppercase text-[#1c1c1e]/60">
                    Deposit Inquiries
                  </div>
                  <div className="font-serif text-3xl font-semibold">{ticketStats.deposits}</div>
                </div>
                <div className="bg-white border border-[#1c1c1e]/10 p-4">
                  <div className="text-[10px] font-mono uppercase text-[#1c1c1e]/60">
                    Withdrawal Requests
                  </div>
                  <div className="font-serif text-3xl font-semibold">{ticketStats.withdrawals}</div>
                </div>
              </div>
            )}

            {/* Ticket Controls & Table */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                    Guild Queue: {selectedGuildId}
                  </span>
                  <h3 className="font-serif text-2xl font-bold">Operational Tickets</h3>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex rounded border border-[#1c1c1e]/15 overflow-hidden text-xs">
                    {["all", "open", "approved", "rejected", "deposit", "withdrawal"].map((f) => (
                      <button
                        key={f}
                        onClick={() => setTicketFilter(f)}
                        className={`px-3 py-1.5 uppercase font-mono text-[10px] tracking-wider transition-all ${
                          ticketFilter === f
                            ? "bg-[#1c1c1e] text-white font-bold"
                            : "bg-white text-[#1c1c1e]/60 hover:text-[#1c1c1e]"
                        }`}
                      >
                        {f}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={() => setIsCreateTicketOpen(true)}
                    className="px-3 py-1.5 bg-[#FF7B00] text-white text-xs font-bold uppercase tracking-wider rounded hover:bg-[#e66f00] flex items-center gap-1.5"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Ticket</span>
                  </button>
                </div>
              </div>

              {filteredTickets.length === 0 ? (
                <div className="py-12 text-center text-xs text-[#1c1c1e]/50 font-mono italic">
                  No tickets match the selected criteria for this server.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[#1c1c1e] font-mono text-[11px] text-[#1c1c1e]/60 uppercase">
                        <th className="py-3 px-3">Ticket ID</th>
                        <th className="py-3 px-3">Type</th>
                        <th className="py-3 px-3">Requester</th>
                        <th className="py-3 px-3">Title & Details</th>
                        <th className="py-3 px-3">Amount</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTickets.map((t) => (
                        <tr
                          key={t.ticketId}
                          className="border-b border-[#1c1c1e]/10 hover:bg-[#1c1c1e]/[0.02]"
                        >
                          <td className="py-3.5 px-3 font-mono font-bold text-[#1c1c1e]">
                            #{t.ticketId}
                          </td>
                          <td className="py-3.5 px-3">
                            <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-[#1c1c1e]/5">
                              {t.type}
                            </span>
                          </td>
                          <td className="py-3.5 px-3 font-medium text-[#1c1c1e]">
                            {t.requesterName}
                          </td>
                          <td className="py-3.5 px-3 max-w-sm">
                            <div className="font-medium text-[#1c1c1e]">{t.title}</div>
                            {t.details.reason && (
                              <div className="text-[11px] text-[#1c1c1e]/60">{t.details.reason}</div>
                            )}
                            {t.details.ltcAddress && (
                              <div className="font-mono text-[10px] text-[#1c1c1e]/50 truncate">
                                LTC: {t.details.ltcAddress}
                              </div>
                            )}
                            {t.details.processedBy && (
                              <div className="text-[10px] font-mono text-[#1a8738]">
                                By: {t.details.processedBy} ({t.details.note})
                              </div>
                            )}
                          </td>
                          <td className="py-3.5 px-3 font-mono font-semibold">
                            {t.details.amount !== undefined ? (
                              <span>
                                {t.details.amount} {t.details.currency || "USD"}
                              </span>
                            ) : (
                              <span className="text-[#1c1c1e]/30">—</span>
                            )}
                          </td>
                          <td className="py-3.5 px-3">
                            <span
                              className={`font-mono text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${
                                t.status === "open"
                                  ? "bg-[#FF7B00]/10 text-[#FF7B00] border-[#FF7B00]/30"
                                  : t.status === "approved"
                                  ? "bg-[#1a8738]/10 text-[#1a8738] border-[#1a8738]/30"
                                  : t.status === "rejected"
                                  ? "bg-[#b21f1f]/10 text-[#b21f1f] border-[#b21f1f]/30"
                                  : "bg-[#1c1c1e]/10 text-[#1c1c1e]/60 border-[#1c1c1e]/20"
                              }`}
                            >
                              {t.status}
                            </span>
                          </td>
                          <td className="py-3.5 px-3 text-right space-x-1">
                            {t.status === "open" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedTicketAction({
                                      ticket: t,
                                      action: "approve",
                                      note: "Approved by administrator",
                                    })
                                  }
                                  className="px-2 py-1 bg-[#1a8738] text-white text-[10px] font-mono font-bold rounded hover:bg-[#166e2e]"
                                >
                                  Approve
                                </button>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedTicketAction({
                                      ticket: t,
                                      action: "reject",
                                      note: "Rejected by administrator",
                                    })
                                  }
                                  className="px-2 py-1 bg-[#b21f1f] text-white text-[10px] font-mono font-bold rounded hover:bg-[#8f1919]"
                                >
                                  Reject
                                </button>
                              </>
                            )}
                            {t.status !== "closed" && (
                              <button
                                type="button"
                                onClick={() =>
                                  setSelectedTicketAction({
                                    ticket: t,
                                    action: "close",
                                    note: "Ticket resolved and closed",
                                  })
                                }
                                className="px-2 py-1 border border-[#1c1c1e]/30 text-[#1c1c1e] text-[10px] font-mono rounded hover:bg-[#1c1c1e]/10"
                              >
                                Close
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Create Ticket Modal */}
            {isCreateTicketOpen && (
              <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                <div className="bg-white border border-[#1c1c1e] max-w-lg w-full p-6 shadow-2xl rounded">
                  <div className="flex justify-between items-center mb-4 border-b border-[#1c1c1e]/10 pb-3">
                    <h3 className="font-serif text-xl font-bold">Open New Ticket</h3>
                    <button
                      onClick={() => setIsCreateTicketOpen(false)}
                      className="text-lg font-bold text-[#1c1c1e]/50 hover:text-[#1c1c1e]"
                    >
                      ×
                    </button>
                  </div>
                  <form onSubmit={handleCreateTicket} className="space-y-4 text-xs">
                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Ticket Type
                      </label>
                      <select
                        value={newTicketData.type}
                        onChange={(e) =>
                          setNewTicketData({ ...newTicketData, type: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      >
                        <option value="support">General Support</option>
                        <option value="deposit">Deposit Verification</option>
                        <option value="withdrawal">Withdrawal Request</option>
                      </select>
                    </div>

                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Title
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="e.g. VIP Booster unlock issue"
                        value={newTicketData.title}
                        onChange={(e) =>
                          setNewTicketData({ ...newTicketData, title: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      >
                      </input>
                    </div>

                    {newTicketData.type !== "support" && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                            Amount
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            value={newTicketData.amount}
                            onChange={(e) =>
                              setNewTicketData({ ...newTicketData, amount: e.target.value })
                            }
                            className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                          />
                        </div>
                        <div>
                          <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                            Currency
                          </label>
                          <input
                            type="text"
                            placeholder="USDT / LTC / USD"
                            value={newTicketData.currency}
                            onChange={(e) =>
                              setNewTicketData({ ...newTicketData, currency: e.target.value })
                            }
                            className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                          />
                        </div>
                      </div>
                    )}

                    {newTicketData.type === "withdrawal" && (
                      <div>
                        <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                          Destination Address (LTC / Crypto)
                        </label>
                        <input
                          type="text"
                          placeholder="ltc1q..."
                          value={newTicketData.ltcAddress}
                          onChange={(e) =>
                            setNewTicketData({ ...newTicketData, ltcAddress: e.target.value })
                          }
                          className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none font-mono"
                        />
                      </div>
                    )}

                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Reason or Note
                      </label>
                      <textarea
                        rows={3}
                        placeholder="Additional details..."
                        value={newTicketData.reason}
                        onChange={(e) =>
                          setNewTicketData({ ...newTicketData, reason: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-2 border-t border-[#1c1c1e]/10">
                      <button
                        type="button"
                        onClick={() => setIsCreateTicketOpen(false)}
                        className="px-4 py-2 border border-[#1c1c1e]/20 rounded"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-2 bg-[#FF7B00] text-white font-bold rounded"
                      >
                        Create Ticket
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* Ticket Action Confirmation Modal */}
            {selectedTicketAction && (
              <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                <div className="bg-white border border-[#1c1c1e] max-w-md w-full p-6 shadow-2xl rounded">
                  <h3 className="font-serif text-xl font-bold mb-2 capitalize">
                    {selectedTicketAction.action} Ticket #{selectedTicketAction.ticket.ticketId}
                  </h3>
                  <p className="text-xs text-[#1c1c1e]/70 mb-4">
                    {selectedTicketAction.ticket.title} ({selectedTicketAction.ticket.requesterName}
                    )
                  </p>

                  <div className="mb-4">
                    <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                      Operator Note / Transaction Proof
                    </label>
                    <textarea
                      rows={3}
                      value={selectedTicketAction.note}
                      onChange={(e) =>
                        setSelectedTicketAction({
                          ...selectedTicketAction,
                          note: e.target.value,
                        })
                      }
                      className="w-full p-2 border border-[#1c1c1e]/20 rounded text-xs outline-none"
                    />
                  </div>

                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedTicketAction(null)}
                      className="px-3 py-1.5 border border-[#1c1c1e]/20 text-xs rounded"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleTicketAction}
                      className={`px-4 py-1.5 text-xs text-white font-bold rounded ${
                        selectedTicketAction.action === "approve"
                          ? "bg-[#1a8738]"
                          : selectedTicketAction.action === "reject"
                          ? "bg-[#b21f1f]"
                          : "bg-[#1c1c1e]"
                      }`}
                    >
                      Confirm {selectedTicketAction.action}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ================= AUDIT LEDGER TAB ================= */}
        {activeTab === "audit" && (
          <div className="space-y-8 animate-fade-in">
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-[#1c1c1e]/40 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search ledger by action, resource or actor ID..."
                  value={auditSearch}
                  onChange={(e) => {
                    setAuditSearch(e.target.value);
                    fetchAuditLogs(1, e.target.value);
                  }}
                  className="w-full pl-9 pr-4 py-2 border border-[#1c1c1e]/15 rounded text-xs font-sans outline-none focus:border-[#FF7B00]"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsCreateAuditOpen(true)}
                  className="px-3 py-2 bg-[#1c1c1e] text-white text-xs font-bold uppercase tracking-wider rounded hover:bg-[#1c1c1e]/85 flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Manual Annotation</span>
                </button>
              </div>
            </div>

            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                    Append-Only Compliance Ledger
                  </span>
                  <h3 className="font-serif text-2xl font-bold">Audit History</h3>
                </div>
                <div className="font-mono text-xs text-[#1c1c1e]/60">
                  Total Records: {auditTotal || auditLogs.length}
                </div>
              </div>

              <div className="space-y-3">
                {auditLogs.map((entry) => (
                  <div
                    key={entry.auditId}
                    className="flex flex-col md:flex-row md:items-center justify-between p-4 border border-[#1c1c1e]/10 rounded hover:bg-[#1c1c1e]/[0.01] transition-all gap-3"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <strong className="font-mono font-bold text-sm text-[#1c1c1e]">
                          {entry.action}
                        </strong>
                        <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-[#1c1c1e]/5 text-[#1c1c1e]/70">
                          {entry.resourceType}
                        </span>
                        {entry.resourceId && (
                          <span className="font-mono text-[9px] text-[#1c1c1e]/40">
                            #{entry.resourceId}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#1c1c1e]/60 mt-1 font-mono">
                        Actor: <span className="text-[#1c1c1e] font-semibold">{entry.actorId}</span>{" "}
                        ({entry.actorType})
                        {entry.details && Object.keys(entry.details).length > 0 && (
                          <span className="text-[#1c1c1e]/50 ml-2">
                            • {JSON.stringify(entry.details)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="font-mono text-[11px] text-[#1c1c1e]/50 whitespace-nowrap">
                      {new Date(entry.timestamp).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Create Audit Modal */}
            {isCreateAuditOpen && (
              <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                <div className="bg-white border border-[#1c1c1e] max-w-md w-full p-6 shadow-2xl rounded">
                  <h3 className="font-serif text-xl font-bold mb-4">Record Audit Log</h3>
                  <form onSubmit={handleCreateAuditLog} className="space-y-3 text-xs">
                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Action Identifier
                      </label>
                      <input
                        type="text"
                        required
                        value={newAuditData.action}
                        onChange={(e) =>
                          setNewAuditData({ ...newAuditData, action: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Resource Type
                      </label>
                      <input
                        type="text"
                        required
                        value={newAuditData.resourceType}
                        onChange={(e) =>
                          setNewAuditData({ ...newAuditData, resourceType: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-mono text-[10px] uppercase text-[#1c1c1e]/60 mb-1">
                        Note / Details
                      </label>
                      <textarea
                        rows={3}
                        value={newAuditData.details}
                        onChange={(e) =>
                          setNewAuditData({ ...newAuditData, details: e.target.value })
                        }
                        className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-2 border-t border-[#1c1c1e]/10">
                      <button
                        type="button"
                        onClick={() => setIsCreateAuditOpen(false)}
                        className="px-3 py-1.5 border border-[#1c1c1e]/20 rounded"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-1.5 bg-[#1c1c1e] text-white font-bold rounded"
                      >
                        Append to Ledger
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ================= SECURITY & POLICIES TAB ================= */}
        {activeTab === "security" && (
          <div className="space-y-8 animate-fade-in">
            {/* Blacklist Management */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
              <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                Access Enforcement
              </span>
              <h3 className="font-serif text-2xl font-bold mb-4">Blacklisted Entities</h3>

              {/* Add to Blacklist Form */}
              <form
                onSubmit={handleAddBlacklist}
                className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6 p-4 bg-[#1c1c1e]/[0.02] border border-[#1c1c1e]/10 rounded text-xs"
              >
                <div>
                  <label className="block font-mono text-[10px] text-[#1c1c1e]/60 uppercase mb-1">
                    Entity ID
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="User or Guild ID"
                    value={newBlacklist.id}
                    onChange={(e) => setNewBlacklist({ ...newBlacklist, id: e.target.value })}
                    className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block font-mono text-[10px] text-[#1c1c1e]/60 uppercase mb-1">
                    Entity Type
                  </label>
                  <select
                    value={newBlacklist.type}
                    onChange={(e) =>
                      setNewBlacklist({
                        ...newBlacklist,
                        type: e.target.value as "user" | "guild",
                      })
                    }
                    className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                  >
                    <option value="user">User ID</option>
                    <option value="guild">Discord Guild</option>
                  </select>
                </div>
                <div>
                  <label className="block font-mono text-[10px] text-[#1c1c1e]/60 uppercase mb-1">
                    Reason
                  </label>
                  <input
                    type="text"
                    placeholder="Spam / Malicious intent"
                    value={newBlacklist.reason}
                    onChange={(e) =>
                      setNewBlacklist({ ...newBlacklist, reason: e.target.value })
                    }
                    className="w-full p-2 border border-[#1c1c1e]/20 rounded outline-none"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full py-2 bg-[#b21f1f] text-white font-bold rounded uppercase tracking-wider text-[11px] hover:bg-[#8f1919]"
                  >
                    Add Blacklist
                  </button>
                </div>
              </form>

              {/* List */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#1c1c1e] font-mono text-[11px] text-[#1c1c1e]/60 uppercase">
                      <th className="py-2.5 px-3">Entity ID</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Reason</th>
                      <th className="py-2.5 px-3">Blacklisted On</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blacklisted.map((b) => (
                      <tr key={b.id} className="border-b border-[#1c1c1e]/10">
                        <td className="py-3 px-3 font-mono font-bold">{b.id}</td>
                        <td className="py-3 px-3 font-mono uppercase text-[10px]">{b.type}</td>
                        <td className="py-3 px-3 text-[#1c1c1e]/70">{b.reason}</td>
                        <td className="py-3 px-3 font-mono text-[11px] text-[#1c1c1e]/50">
                          {b.date}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Anti-Spam & Cooldown Policy Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-[#FF7B00]" />
                  <h4 className="font-serif text-lg font-bold">Anti-Spam & Flood Rules</h4>
                </div>
                <p className="text-xs text-[#1c1c1e]/70 mb-4 leading-relaxed">
                  Automatic algorithmic throttle for rapid command executions and mass mentions across all registered guilds.
                </p>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-[#1c1c1e]/10">
                    <span className="text-[#1c1c1e]/60">Command Cooldown</span>
                    <strong className="font-mono">3 seconds default</strong>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-[#1c1c1e]/10">
                    <span className="text-[#1c1c1e]/60">Max Rapid Mentions</span>
                    <strong className="font-mono">5 mentions / message</strong>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-[#1c1c1e]/10">
                    <span className="text-[#1c1c1e]/60">Action on Violation</span>
                    <strong className="font-mono text-[#b21f1f]">Temporary Channel Mute</strong>
                  </div>
                </div>
              </div>

              <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Lock className="w-4 h-4 text-[#FF7B00]" />
                  <h4 className="font-serif text-lg font-bold">Privileged VIP & No-Prefix</h4>
                </div>
                <p className="text-xs text-[#1c1c1e]/70 mb-4 leading-relaxed">
                  Trusted operators with prefix bypass rights. Permitted to trigger commands directly without typing prefix characters.
                </p>
                <div className="space-y-2 text-xs font-mono">
                  <div className="p-2 border border-[#1c1c1e]/10 rounded bg-[#1c1c1e]/[0.02] flex justify-between items-center">
                    <span>1038243575860001 (Aeshan)</span>
                    <span className="text-[10px] text-[#1a8738] font-bold">OWNER / VIP</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= ENVIRONMENT & DIAGNOSTICS TAB ================= */}
        {activeTab === "environment" && (
          <div className="space-y-8 animate-fade-in">
            <div className="bg-white border border-[#1c1c1e]/10 p-6 md:p-8 shadow-sm">
              <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                Runtime Stack & Hardware
              </span>
              <h3 className="font-serif text-2xl font-bold mb-6">System Architecture</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-xs">
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">Operating Environment</span>
                  <strong className="font-mono">Linux x86_64 / Container Node 22</strong>
                </div>
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">Node Framework</span>
                  <strong className="font-mono">Express 5 + Vite 8 Hybrid</strong>
                </div>
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">Discord Library</span>
                  <strong className="font-mono">discord.js v14.26.4</strong>
                </div>
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">AI Intelligence Core</span>
                  <strong className="font-mono text-[#FF7B00]">@google/genai SDK v2.30</strong>
                </div>
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">Database Connection State</span>
                  <strong className="font-mono text-[#1a8738]">
                    {dbStatus?.state === "connected" ? "Connected / Synchronized" : "Active"}
                  </strong>
                </div>
                <div className="flex justify-between py-2 border-b border-[#1c1c1e]/10">
                  <span className="text-[#1c1c1e]/60">Storage Driver</span>
                  <strong className="font-mono">{dbStatus?.driver || "MongoDB + Memory Cache"}</strong>
                </div>
              </div>
            </div>

            {/* Secret Verification Table */}
            <div className="bg-white border border-[#1c1c1e]/10 p-6 shadow-sm">
              <span className="font-mono text-[10px] uppercase tracking-widest text-[#1c1c1e]/60">
                Environment Secret Keys
              </span>
              <h3 className="font-serif text-xl font-bold mb-4">Configuration Inspection</h3>

              <div className="space-y-2 text-xs">
                {Object.entries(envStatus).map(([key, val]) => (
                  <div
                    key={key}
                    className="flex justify-between items-center py-2 px-3 border-b border-[#1c1c1e]/10 font-mono"
                  >
                    <span className="text-[#1c1c1e] font-semibold">{key}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                        val === "configured"
                          ? "bg-[#1a8738]/10 text-[#1a8738]"
                          : "bg-[#1c1c1e]/5 text-[#1c1c1e]/70"
                      }`}
                    >
                      {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

import React, { useState } from "react";

// Sentinel Global Configuration Constants (synced with Colors.json & Emojis.json)
const THEME = {
  primary: "#0844C5",
  success: "#3FD438",
  danger: "#B21F1F",
  warning: "#F59E0B",
  blurple: "#5865F2",
  darkBg: "#0B0E14",
  panelBg: "#111722",
  cardBg: "#172033",
  border: "#1F2B42",
};

interface TermDef {
  key: string;
  name: string;
  short: string;
  description: string;
  example: string;
  safeguard: string;
}

const GLOSSARY_TERMS: TermDef[] = [
  {
    key: "antinuke",
    name: "Anti-Nuke",
    short: "Autonomous real-time server destruction defense system.",
    description: "Evaluates rapid administrative gateway actions (bans, kicks, role/channel wipes, webhook creations) and instantly neutralizes malicious actors before server loss occurs.",
    example: "$antinuke • $antinuke mode hard • $antinuke observation toggle",
    safeguard: "Immediate quarantine or ban of rogue accounts, automatic hierarchy validation.",
  },
  {
    key: "observation",
    name: "Aegis Advanced Observation Engine",
    short: "Multi-vector cross-event correlation and telemetry analysis.",
    description: "Tracks distributed actions over time sliding windows. Instead of dumb threshold tripwires, Aegis detects subtle multi-vector coordinated raids across channels, roles, and webhooks.",
    example: "Toggle between Aegis Advanced Correlation Engine and Standard Heuristic Engine.",
    safeguard: "Detects low-velocity distributed attacks that evade single-counter rate limits.",
  },
  {
    key: "lockdown",
    name: "Emergency Lockdown & Containment",
    short: "Surgical fail-safe containment stripping dangerous permissions.",
    description: "In an active breach, Sentinel snapshots server role permissions and strips Administrator, Manage Channels, and Mention Everyone. Restores cleanly upon recovery authorization.",
    example: "$lockdown trigger • $lockdown recover • $lockdown posture",
    safeguard: "Strict Single Backup Safeguard: Blocks duplicate snapshots to prevent corrupting baseline state.",
  },
  {
    key: "duplicate_backup",
    name: "Single Snapshot Safeguard",
    short: "Protection against corrupting server rollback baselines.",
    description: "Ensures Sentinel never creates two active backups for the same server. If a secondary containment is requested while locked, Sentinel preserves the pristine pre-incident snapshot.",
    example: "Attempting $lockdown trigger while active prompts recovery instead of overriding journal.",
    safeguard: "Guarantees server permissions can always be 100% faithfully rolled back.",
  },
  {
    key: "whitelist",
    name: "Whitelist & Graduated Trust",
    short: "Scoped exemption protocols for trusted administrators and bots.",
    description: "Configures exempt users, roles, or channels. In Aegis mode, acts with Graduated Trust (anomalies logged). In Standard mode, acts as direct threshold bypass.",
    example: "$whitelist @Moderator channel_delete,role_delete",
    safeguard: "Owner and Extra Owner privileges are hardcoded root; exemptions are strictly scoped.",
  },
  {
    key: "quorum",
    name: "Consensus Quorum",
    short: "Multi-signature threshold for high-severity defensive operations.",
    description: "Requires multiple trusted recovery actors or bot owners to co-sign high-impact operations like full permission restoration or security policy downgrade.",
    example: "2 of 3 trusted keys required to execute complete policy downgrade in Ultimate mode.",
    safeguard: "Eliminates single point of failure if a single administrator account is compromised.",
  },
  {
    key: "posture",
    name: "Defensive Security Posture",
    short: "Comprehensive real-time diagnostic rating of guild permissions.",
    description: "Calculates an instant risk index (0-100) assessing unmanaged roles holding dangerous permissions, bot hierarchy placement, and active containment readiness.",
    example: "$security posture • $lockdown posture",
    safeguard: "Live warnings if roles above bot or dangerous @everyone overrides exist.",
  },
  {
    key: "shadow_mode",
    name: "Shadow Observation Mode",
    short: "Non-destructive simulation of containment policies.",
    description: "Runs anti-nuke correlation and evaluates containment triggers without modifying actual Discord role permissions, allowing security audits in live production.",
    example: "$lockdown policy shadow_mode true",
    safeguard: "Zero user disruption while verifying threshold accuracy and webhook alarms.",
  },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<"security" | "antinuke" | "lockdown" | "glossary">("security");
  const [mode, setMode] = useState<"hard" | "ultimate" | "hybrid">("hard");
  const [obsEnabled, setObsEnabled] = useState<boolean>(true);
  const [obsMode, setObsMode] = useState<"advanced" | "standard">("advanced");
  const [activeTerm, setActiveTerm] = useState<string>("antinuke");
  const [lockdownState, setLockdownState] = useState<"nominal" | "prompt_confirm" | "locked">("nominal");
  const [searchFilter, setSearchFilter] = useState<string>("");

  const filteredTerms = GLOSSARY_TERMS.filter(
    (t) =>
      t.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      t.description.toLowerCase().includes(searchFilter.toLowerCase()) ||
      t.key.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const selectedTermDef = GLOSSARY_TERMS.find((t) => t.key === activeTerm) || GLOSSARY_TERMS[0];

  return (
    <div className="min-h-screen bg-[#070A0F] text-slate-100 flex flex-col items-center justify-start py-8 px-4 font-sans selection:bg-blue-600 selection:text-white">
      {/* Top Banner & Header */}
      <header className="max-w-5xl w-full flex flex-col md:flex-row items-center justify-between gap-4 pb-6 mb-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-700 via-indigo-600 to-blue-500 flex items-center justify-center text-2xl shadow-xl shadow-blue-600/25 border border-blue-400/30">
            🛡️
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-black tracking-tight text-white">SENTINEL™</h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30 font-semibold uppercase tracking-wider">
                Defense Suite v26.7
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Autonomous Anti-Nuke Infrastructure • Dynamic Aegis Observation Engine
            </p>
          </div>
        </div>

        {/* Global Controls & Mode Switcher */}
        <div className="flex items-center gap-2 bg-[#0E1420] border border-slate-800 p-1.5 rounded-xl shadow-inner">
          <button
            onClick={() => setMode("hard")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              mode === "hard"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Hard Zero-Tolerance
          </button>
          <button
            onClick={() => setMode("ultimate")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              mode === "ultimate"
                ? "bg-red-600 text-white shadow-md shadow-red-600/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Ultimate Lockdown
          </button>
          <button
            onClick={() => setMode("hybrid")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              mode === "hybrid"
                ? "bg-purple-600 text-white shadow-md shadow-purple-600/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Hybrid Adaptive
          </button>
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="max-w-5xl w-full grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Navigation Sidebar */}
        <div className="lg:col-span-4 space-y-4">
          {/* Engine Status Card */}
          <div className="bg-[#0F1624] border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Defense Telemetry
              </span>
              <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live Posture
              </span>
            </div>

            <div className="space-y-3 text-sm">
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="text-xs text-slate-400">Current Mode</div>
                  <div className="font-bold text-white capitalize">{mode} Defense</div>
                </div>
                <div
                  className={`text-xs px-2 py-1 rounded-md font-semibold ${
                    mode === "ultimate"
                      ? "bg-red-500/10 text-red-400 border border-red-500/30"
                      : mode === "hybrid"
                      ? "bg-purple-500/10 text-purple-400 border border-purple-500/30"
                      : "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                  }`}
                >
                  {mode === "ultimate" ? "Quarantine & Ban" : mode === "hybrid" ? "Dynamic Throttle" : "Instant Revoke"}
                </div>
              </div>

              {/* Observation Engine Toggle Box */}
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-slate-400">Observation Engine</div>
                    <div className="font-bold text-sm text-slate-200">
                      {obsMode === "advanced" ? "Aegis Advanced Correlation" : "Standard Heuristic"}
                    </div>
                  </div>
                  <button
                    onClick={() => setObsEnabled(!obsEnabled)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                      obsEnabled
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "bg-red-500/20 text-red-300 border border-red-500/40"
                    }`}
                  >
                    {obsEnabled ? "Active" : "Disabled"}
                  </button>
                </div>
                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
                  <span className="text-xs text-slate-400">Engine Type:</span>
                  <button
                    onClick={() => setObsMode(obsMode === "advanced" ? "standard" : "advanced")}
                    className="text-xs text-blue-400 hover:text-blue-300 font-medium underline flex items-center gap-1"
                  >
                    🔄 Switch to {obsMode === "advanced" ? "Standard" : "Aegis"}
                  </button>
                </div>
              </div>

              {/* Lockdown Safeguard Card */}
              <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Containment Snapshot</span>
                  <span className="text-xs text-emerald-400 font-semibold">Protected</span>
                </div>
                <p className="text-xs text-slate-400">
                  <strong className="text-slate-300">Safeguard Active:</strong> Duplicate backups prevented. Baseline permissions locked.
                </p>
              </div>
            </div>
          </div>

          {/* Suite Commands Switcher */}
          <nav className="bg-[#0F1624] border border-slate-800 rounded-2xl p-2 space-y-1 shadow-lg">
            <button
              onClick={() => setActiveTab("security")}
              className={`w-full text-left px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-between transition-all ${
                activeTab === "security"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : "text-slate-300 hover:bg-slate-900/80 hover:text-white"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <span>🛡️</span>
                <span>$security Hub</span>
              </span>
              <span className="text-xs opacity-75 font-mono">Master</span>
            </button>

            <button
              onClick={() => setActiveTab("antinuke")}
              className={`w-full text-left px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-between transition-all ${
                activeTab === "antinuke"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : "text-slate-300 hover:bg-slate-900/80 hover:text-white"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <span>⚡</span>
                <span>$antinuke Dashboard</span>
              </span>
              <span className="text-xs opacity-75 font-mono">Real-Time</span>
            </button>

            <button
              onClick={() => setActiveTab("lockdown")}
              className={`w-full text-left px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-between transition-all ${
                activeTab === "lockdown"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : "text-slate-300 hover:bg-slate-900/80 hover:text-white"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <span>🚨</span>
                <span>$lockdown Containment</span>
              </span>
              <span className="text-xs opacity-75 font-mono">Safeguards</span>
            </button>

            <button
              onClick={() => setActiveTab("glossary")}
              className={`w-full text-left px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-between transition-all ${
                activeTab === "glossary"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : "text-slate-300 hover:bg-slate-900/80 hover:text-white"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <span>📖</span>
                <span>$explain Knowledge Base</span>
              </span>
              <span className="text-xs opacity-75 font-mono">Glossary</span>
            </button>
          </nav>
        </div>

        {/* Dynamic Main Workspace Panel */}
        <div className="lg:col-span-8">
          {/* TAB 1: $security Master Command Hub */}
          {activeTab === "security" && (
            <div className="bg-[#0F1624] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>🛡️</span> Sentinel Unified Security Suite (`$security`)
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Central governance cockpit for Anti-Nuke, Aegis Observation, Containment, and Whitelists.
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30">
                  Aliases: $sec, $hub, $defense
                </span>
              </div>

              {/* Dynamic Mode-Adaptive Matrix */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
                    <span>ACTIVE POSTURE</span>
                    <span className="text-emerald-400">Score: 98/100</span>
                  </div>
                  <div className="text-base font-bold text-white mb-1 capitalize">
                    {mode === "hard" && "Hard Zero-Tolerance Mode"}
                    {mode === "ultimate" && "Ultimate Lockdown Policy"}
                    {mode === "hybrid" && "Hybrid Adaptive Engine"}
                  </div>
                  <p className="text-xs text-slate-400">
                    {mode === "hard" && "Sanctions any unauthorized structural alteration with immediate role revocation."}
                    {mode === "ultimate" && "Enforces quarantine, multi-signature quorum for recovery, and strict isolation."}
                    {mode === "hybrid" && "Scales disciplinary action based on anomaly correlation score."}
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
                    <span>OBSERVATION ENGINE</span>
                    <span className={obsEnabled ? "text-emerald-400" : "text-red-400"}>
                      {obsEnabled ? "Active" : "Disabled"}
                    </span>
                  </div>
                  <div className="text-base font-bold text-white mb-1">
                    {obsMode === "advanced" ? "Aegis Advanced Correlation" : "Standard Heuristic"}
                  </div>
                  <p className="text-xs text-slate-400">
                    {obsMode === "advanced"
                      ? "Multi-vector sliding window with graduated trust. Anomalies logged for forensic consensus."
                      : "Direct single-vector counter gatekeeping. Immediate bypass for whitelisted entities."}
                  </p>
                </div>
              </div>

              {/* Interactive Quick-Action Buttons */}
              <div className="space-y-3">
                <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  Quick Action Controls
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                  <button
                    onClick={() => setActiveTab("antinuke")}
                    className="p-3 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/40 text-blue-300 text-xs font-semibold text-center transition-all flex flex-col items-center gap-1.5"
                  >
                    <span className="text-lg">🛡️</span>
                    <span>Anti-Nuke Config</span>
                  </button>

                  <button
                    onClick={() => setObsEnabled(!obsEnabled)}
                    className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 text-xs font-semibold text-center transition-all flex flex-col items-center gap-1.5"
                  >
                    <span className="text-lg">{obsEnabled ? "👁️" : "🙈"}</span>
                    <span>{obsEnabled ? "Disable Obs" : "Enable Obs"}</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("lockdown")}
                    className="p-3 rounded-xl bg-red-600/20 hover:bg-red-600/30 border border-red-500/40 text-red-300 text-xs font-semibold text-center transition-all flex flex-col items-center gap-1.5"
                  >
                    <span className="text-lg">🚨</span>
                    <span>Containment</span>
                  </button>

                  <button
                    onClick={() => setActiveTab("glossary")}
                    className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 text-xs font-semibold text-center transition-all flex flex-col items-center gap-1.5"
                  >
                    <span className="text-lg">📖</span>
                    <span>Glossary</span>
                  </button>
                </div>
              </div>

              {/* Discord Interactive Select Menu Simulator */}
              <div className="p-4 rounded-xl bg-[#090D14] border border-slate-800 space-y-3">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>DISCORD INTERACTIVE NAVIGATION (sec:nav)</span>
                  <span className="text-blue-400">Select Menu V2</span>
                </div>
                <select
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "antinuke") setActiveTab("antinuke");
                    else if (v === "lockdown") setActiveTab("lockdown");
                    else if (v === "explain") setActiveTab("glossary");
                  }}
                  className="w-full bg-[#111722] border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="dashboard">🛡️ Security Master Hub</option>
                  <option value="antinuke">⚡ Anti-Nuke Control Center</option>
                  <option value="lockdown">🚨 Emergency Containment & Rollback</option>
                  <option value="explain">📖 Explain Terms & Security Glossary</option>
                </select>
              </div>
            </div>
          )}

          {/* TAB 2: $antinuke Dashboard & Vectors */}
          {activeTab === "antinuke" && (
            <div className="bg-[#0F1624] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>⚡</span> Anti-Nuke Control Center (`$antinuke`)
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Continuous gateway vector surveillance and automated disciplinary execution.
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  Aliases: $an
                </span>
              </div>

              {/* Mode & Engine Badges */}
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div>
                  <div className="text-xs text-slate-400">Mode-Adaptive Policy</div>
                  <div className="text-base font-bold text-white">
                    {mode === "hard" && "🛡️ Zero-Tolerance Enforcement"}
                    {mode === "ultimate" && "🔥 Ultimate Containment Protocol"}
                    {mode === "hybrid" && "⚖️ Hybrid Sliding Window Correlation"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const next = mode === "hard" ? "ultimate" : mode === "ultimate" ? "hybrid" : "hard";
                      setMode(next);
                    }}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700"
                  >
                    Cycle Mode
                  </button>
                  <button
                    onClick={() => setObsEnabled(!obsEnabled)}
                    className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-xs font-semibold text-blue-300 border border-blue-500/30"
                  >
                    Toggle Observation
                  </button>
                </div>
              </div>

              {/* Monitored Vectors List */}
              <div className="space-y-2">
                <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  23 Monitored Gateway Vectors (Sample Active)
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  <div className="p-3 rounded-lg bg-[#0A0E17] border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300 font-mono">channel_delete</span>
                    <span className="text-emerald-400 font-semibold">1 / 60s ➔ Instant Ban</span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#0A0E17] border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300 font-mono">role_delete</span>
                    <span className="text-emerald-400 font-semibold">1 / 60s ➔ Instant Ban</span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#0A0E17] border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300 font-mono">member_ban_add</span>
                    <span className="text-emerald-400 font-semibold">2 / 60s ➔ Instant Ban</span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#0A0E17] border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300 font-mono">webhook_create</span>
                    <span className="text-emerald-400 font-semibold">1 / 60s ➔ Instant Ban</span>
                  </div>
                </div>
              </div>

              {/* Whitelist Note */}
              <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40 text-xs text-blue-200 space-y-1">
                <div className="font-bold flex items-center gap-1.5 text-blue-300">
                  <span>ℹ️</span> Whitelist Behavior in Current Mode
                </div>
                <p>
                  {obsMode === "advanced"
                    ? "In Aegis Advanced Mode, whitelisted administrators operate under Graduated Trust. They bypass hard rate limits, but anomalous burst velocity is logged for consensus verification."
                    : "In Standard Mode, whitelisted administrators operate under Direct Threshold Bypass, completely skipping rate counters."}
                </p>
              </div>
            </div>
          )}

          {/* TAB 3: $lockdown Emergency Containment */}
          {activeTab === "lockdown" && (
            <div className="bg-[#0F1624] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>🚨</span> Emergency Containment & Recovery (`$lockdown`)
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Surgical permission stripping with safe single-snapshot journal verification.
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/30">
                  Safeguards Active
                </span>
              </div>

              {/* Status and Single Backup Protection */}
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-slate-400">Containment Status</div>
                    <div className="text-base font-bold text-white flex items-center gap-2">
                      <span
                        className={`w-2.5 h-2.5 rounded-full ${
                          lockdownState === "locked" ? "bg-red-500 animate-ping" : "bg-emerald-400"
                        }`}
                      />
                      {lockdownState === "locked" ? "EMERGENCY CONTAINMENT ACTIVE" : "NOMINAL OPERATION"}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400">Snapshot Integrity</div>
                    <div className="text-xs font-semibold text-emerald-400">Single Baseline Locked</div>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200">
                  <strong>🔒 Duplicate Backup Safeguard:</strong> Sentinel checks active lockdown journals. If a lockdown is already in progress, new snapshots are blocked to protect pre-incident baseline permissions from corruption.
                </div>
              </div>

              {/* Interactive Confirmation Workflow Simulator */}
              {lockdownState === "nominal" && (
                <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-3">
                  <div className="text-sm font-semibold text-slate-300">
                    Ready to simulate emergency containment protocol?
                  </div>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Containment will request confirmation via Discord buttons before stripping dangerous permissions.
                  </p>
                  <button
                    onClick={() => setLockdownState("prompt_confirm")}
                    className="px-5 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs font-bold shadow-lg shadow-red-600/30 transition-all"
                  >
                    Trigger Emergency Containment...
                  </button>
                </div>
              )}

              {lockdownState === "prompt_confirm" && (
                <div className="p-5 rounded-xl bg-red-950/30 border border-red-800/60 space-y-4">
                  <div className="flex items-center gap-2 text-red-400 font-bold text-sm">
                    <span>⚠️</span> Confirmation Required Before Lockdown
                  </div>
                  <p className="text-xs text-slate-300">
                    Are you sure you want to trigger emergency lockdown for this server? Dangerous permissions will be stripped immediately.
                  </p>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setLockdownState("locked")}
                      className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs font-bold shadow-md shadow-red-600/30"
                    >
                      Confirm Emergency Lockdown
                    </button>
                    <button
                      onClick={() => setLockdownState("nominal")}
                      className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {lockdownState === "locked" && (
                <div className="p-5 rounded-xl bg-red-950/40 border border-red-700 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-red-400 font-bold text-sm">
                      <span>🔒</span> Guild Containment Enforced (Journal: lck_8f3a2c)
                    </div>
                    <span className="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-300 font-mono">
                      Strict Quarantine
                    </span>
                  </div>
                  <p className="text-xs text-slate-300">
                    Role permissions stripped. Baseline snapshot preserved in MongoDB. Duplicate backup creation is blocked.
                  </p>
                  <button
                    onClick={() => setLockdownState("nominal")}
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-md shadow-emerald-600/30"
                  >
                    Restore Baseline Permissions ($lockdown recover)
                  </button>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: $explain Comprehensive Security Glossary */}
          {activeTab === "glossary" && (
            <div className="bg-[#0F1624] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 pb-4 gap-3">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>📖</span> Security Knowledge Base (`$explain`)
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Complete explanations for every keyword and protocol to prevent user confusion.
                  </p>
                </div>
                <input
                  type="text"
                  placeholder="Filter keywords..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="bg-[#090D14] border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-full sm:w-48"
                />
              </div>

              {/* Glossary Layout: Selector & Detailed View */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Term Selector List */}
                <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
                  {filteredTerms.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setActiveTerm(t.key)}
                      className={`w-full text-left p-2.5 rounded-xl text-xs font-semibold transition-all ${
                        activeTerm === t.key
                          ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                          : "bg-slate-900/80 text-slate-300 hover:bg-slate-800 border border-slate-800"
                      }`}
                    >
                      <div className="font-bold">{t.name}</div>
                      <div className="text-[10px] opacity-75 truncate">{t.short}</div>
                    </button>
                  ))}
                </div>

                {/* Term Explanation Card */}
                <div className="md:col-span-2 p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
                  <div className="border-b border-slate-800 pb-3">
                    <span className="text-[10px] font-mono text-blue-400 uppercase tracking-widest">
                      Sentinel Terminology
                    </span>
                    <h3 className="text-lg font-black text-white mt-0.5">{selectedTermDef.name}</h3>
                    <p className="text-xs text-slate-400 mt-1">{selectedTermDef.short}</p>
                  </div>

                  <div className="space-y-3 text-xs text-slate-300">
                    <div>
                      <div className="font-bold text-slate-200 mb-1">Architecture & Purpose:</div>
                      <p className="leading-relaxed text-slate-400">{selectedTermDef.description}</p>
                    </div>

                    <div className="p-3 rounded-xl bg-[#090D14] border border-slate-800 space-y-1">
                      <div className="font-bold text-blue-400">Command Syntax:</div>
                      <div className="font-mono text-slate-300">{selectedTermDef.example}</div>
                    </div>

                    <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-900/40 space-y-1">
                      <div className="font-bold text-emerald-400">Built-in Safeguard:</div>
                      <div className="text-emerald-200/90">{selectedTermDef.safeguard}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer Info */}
      <footer className="max-w-5xl w-full mt-8 pt-4 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
        <span>Sentinel™ Autonomous Discord Defense Platform</span>
        <span>Aegis Observation Engine • Consensus Verification</span>
      </footer>
    </div>
  );
}

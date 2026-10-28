import React from "react";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 selection:bg-blue-600 selection:text-white">
      <div className="max-w-md w-full bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-2xl backdrop-blur">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-xl shadow-lg shadow-blue-500/20 font-bold">
            🛡️
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              Sentinel™
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                Active
              </span>
            </h1>
            <p className="text-xs text-slate-400">Autonomous Discord Security Infrastructure</p>
          </div>
        </div>

        <div className="space-y-3 my-5 text-sm text-slate-300">
          <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-slate-400">Anti-Nuke Protection</span>
            <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Armed (Hard Mode)
            </span>
          </div>

          <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-slate-400">Audit & Forensic Logs</span>
            <span className="font-medium text-blue-400">Webhook Pipeline</span>
          </div>

          <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-slate-400">Ghost Ping Detection</span>
            <span className="font-medium text-purple-400">Real-Time Monitor</span>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
          <span>Sentinel™ Defense Engine</span>
          <span>v26.7.20</span>
        </div>
      </div>
    </div>
  );
}

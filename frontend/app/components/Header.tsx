"use client";

import React from "react";
import {
  Menu,
  Sparkles,
  Zap,
  Globe,
  Code2,
  BarChart3,
  FileText,
  Search,
} from "lucide-react";
import { AgentRole } from "./types";

interface HeaderProps {
  onToggleSidebar: () => void;
  selectedRole: AgentRole;
  onSelectRole: (role: AgentRole) => void;
  onOpenSkills: () => void;
  activeTool: string | null;
}

const AGENT_MODES: { id: AgentRole; label: string; icon: React.ReactNode; color: string }[] = [
  { id: "auto", label: "Auto-Pilot", icon: <Zap size={13} />, color: "text-cyan-400" },
  { id: "research", label: "Research", icon: <Globe size={13} />, color: "text-blue-400" },
  { id: "code", label: "Code Agent", icon: <Code2 size={13} />, color: "text-emerald-400" },
  { id: "data", label: "Data Agent", icon: <BarChart3 size={13} />, color: "text-amber-400" },
  { id: "docs", label: "DocuPilot", icon: <FileText size={13} />, color: "text-purple-400" },
];

export default function Header({
  onToggleSidebar,
  selectedRole,
  onSelectRole,
  onOpenSkills,
  activeTool,
}: HeaderProps) {
  return (
    <header className="shrink-0 flex items-center justify-between border-b border-white/[0.08] bg-[#07090e]/90 px-5 py-3 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/5 transition"
        >
          <Menu size={18} />
        </button>

        {/* Mobile branding */}
        <div className="flex items-center gap-2 md:hidden">
          <img src="/icon.svg" alt="Agent-Pilot" className="h-6 w-6" />
          <span className="text-sm font-bold text-white">Agent-Pilot</span>
        </div>

        {/* Agent Mode Selector (Desktop) */}
        <div className="hidden sm:flex items-center gap-1.5 rounded-xl border border-white/[0.08] bg-white/[0.02] p-1">
          {AGENT_MODES.map((mode) => (
            <button
              key={mode.id}
              onClick={() => onSelectRole(mode.id)}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                selectedRole === mode.id
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow-sm shadow-cyan-500/10"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
              }`}
            >
              <span className={mode.color}>{mode.icon}</span>
              <span>{mode.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        {/* Active Tool Execution Pill */}
        {activeTool && (
          <div className="hidden lg:flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-300 animate-pulse">
            <span className="h-2 w-2 rounded-full bg-cyan-400" />
            <span className="font-mono text-[11px] font-semibold">{activeTool}</span>
          </div>
        )}

        {/* Skills Search Button */}
        <button
          onClick={onOpenSkills}
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-400/40 hover:bg-cyan-500/10 hover:text-cyan-200 transition"
        >
          <Search size={13} className="text-cyan-400" />
          <span className="hidden sm:inline">Search Skills</span>
          <kbd className="hidden sm:inline rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-400 font-mono">
            ⌘K
          </kbd>
        </button>

        {/* Live Status indicator */}
        <div className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1 text-xs text-slate-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
          <span className="hidden sm:inline font-mono text-[11px]">Ready</span>
        </div>
      </div>
    </header>
  );
}

"use client";

import React from "react";
import {
  Menu,
  Zap,
  Globe,
  Code2,
  BarChart3,
  FileText,
  Search,
  Loader2,
} from "lucide-react";
import { AgentRole } from "./types";

interface HeaderProps {
  onToggleSidebar: () => void;
  selectedRole: AgentRole;
  onSelectRole: (role: AgentRole) => void;
  onOpenSkills: () => void;
  activeTool: string | null;
}

const AGENT_MODES: { id: AgentRole; label: string; icon: React.ReactNode }[] = [
  { id: "auto", label: "Auto-Pilot", icon: <Zap size={13} /> },
  { id: "research", label: "Research", icon: <Globe size={13} /> },
  { id: "code", label: "Code", icon: <Code2 size={13} /> },
  { id: "data", label: "Data", icon: <BarChart3 size={13} /> },
  { id: "docs", label: "DocuPilot", icon: <FileText size={13} /> },
];

export default function Header({
  onToggleSidebar,
  selectedRole,
  onSelectRole,
  onOpenSkills,
  activeTool,
}: HeaderProps) {
  return (
    <header className="shrink-0 flex items-center justify-between border-b border-zinc-800/80 bg-[#09090b] px-4 py-2.5">
      <div className="flex items-center gap-2.5">
        <button
          onClick={onToggleSidebar}
          className="rounded-md p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition"
        >
          <Menu size={16} />
        </button>

        {/* Mobile brand title */}
        <div className="flex items-center gap-2 md:hidden">
          <img src="/icon.svg" alt="Agent-Pilot" className="h-5 w-5" />
          <span className="text-xs font-semibold text-zinc-200">Agent-Pilot</span>
        </div>

        {/* Segmented Mode Selector (Human/Linear Style) */}
        <div className="hidden sm:flex items-center rounded-lg border border-zinc-800 bg-zinc-900/80 p-0.5">
          {AGENT_MODES.map((mode) => {
            const isActive = selectedRole === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onSelectRole(mode.id)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  isActive
                    ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/60"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
                }`}
              >
                <span className={isActive ? "text-zinc-200" : "text-zinc-500"}>
                  {mode.icon}
                </span>
                <span>{mode.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Active Tool Execution Pill */}
        {activeTool && (
          <div className="hidden md:flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300">
            <Loader2 size={12} className="animate-spin text-zinc-400" />
            <span className="font-mono text-[11px] text-zinc-200">{activeTool}</span>
          </div>
        )}

        {/* Search Command Trigger (Raycast style) */}
        <button
          onClick={onOpenSkills}
          className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/60 px-2.5 py-1 text-xs text-zinc-400 hover:border-zinc-700 hover:text-zinc-200 transition"
        >
          <Search size={12} className="text-zinc-500" />
          <span className="hidden sm:inline">Commands</span>
          <kbd className="hidden sm:inline rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400 font-mono">
            ⌘K
          </kbd>
        </button>

        {/* Status */}
        <div className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-zinc-500">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          <span className="hidden sm:inline">Online</span>
        </div>
      </div>
    </header>
  );
}

"use client";

import React from "react";
import { Menu, Loader2, Plus } from "lucide-react";

interface HeaderProps {
  onToggleSidebar: () => void;
  onNewChat?: () => void;
  activeTool: string | null;
}

export default function Header({
  onToggleSidebar,
  onNewChat,
  activeTool,
}: HeaderProps) {
  return (
    <header className="shrink-0 flex items-center justify-between glass-nav px-4 py-2.5 z-20">
      {/* Left side: Navigation toggle and clean brand label */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="rounded-lg p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.06] transition"
          title="Toggle sidebar"
        >
          <Menu size={16} />
        </button>

        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center">
            <img
              src="/icon.jpg"
              alt="Agent-Pilot Logo"
              className="h-6 w-6 rounded-md border border-white/10 object-cover shadow-sm ring-1 ring-white/5"
            />
          </div>
          <span className="text-xs font-medium text-zinc-200 tracking-tight">
            Agent-Pilot
          </span>
          <span className="text-zinc-600 text-xs">/</span>
          <span className="text-[11px] text-zinc-400 hidden sm:inline px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">
            Autonomous Workspace
          </span>
        </div>
      </div>

      {/* Right side: Active tool execution indicator & New Chat shortcut */}
      <div className="flex items-center gap-2">
        {activeTool && (
          <div className="flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-200 shadow-sm animate-pulse">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />
            <span className="font-mono text-[11px] font-medium tracking-wide">{activeTool}</span>
          </div>
        )}

        {onNewChat && (
          <button
            type="button"
            onClick={() => onNewChat()}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-white/[0.08] hover:text-white hover:border-white/20 transition active:scale-95 shadow-sm"
            title="Start new chat"
          >
            <Plus size={13} />
            <span className="hidden sm:inline">New Chat</span>
          </button>
        )}
      </div>
    </header>
  );
}

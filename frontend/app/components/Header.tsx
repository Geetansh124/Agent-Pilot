"use client";

import React from "react";
import { Menu, Loader2 } from "lucide-react";

interface HeaderProps {
  onToggleSidebar: () => void;
  activeTool: string | null;
}

export default function Header({
  onToggleSidebar,
  activeTool,
}: HeaderProps) {
  return (
    <header className="shrink-0 flex items-center justify-between border-b border-zinc-800/80 bg-[#09090b] px-4 py-2.5">
      {/* Left side: Navigation toggle and clean brand label */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="rounded-md p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850 transition"
          title="Toggle sidebar"
        >
          <Menu size={16} />
        </button>

        <div className="flex items-center gap-2">
          <img
            src="/icon.jpg"
            alt="Agent-Pilot Logo"
            className="h-6 w-6 rounded-md border border-zinc-800 object-cover shadow-sm"
          />
          <span className="text-xs font-semibold text-zinc-200 tracking-tight">
            Agent-Pilot
          </span>
          <span className="text-zinc-600">/</span>
          <span className="text-xs text-zinc-400 hidden sm:inline">Workspace</span>
        </div>
      </div>

      {/* Right side: Active tool execution indicator */}
      <div className="flex items-center gap-2">
        {activeTool && (
          <div className="flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300">
            <Loader2 size={12} className="animate-spin text-zinc-400" />
            <span className="font-mono text-[11px] text-zinc-200">{activeTool}</span>
          </div>
        )}
      </div>
    </header>
  );
}

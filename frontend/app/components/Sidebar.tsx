"use client";

import React, { useRef, useState } from "react";
import {
  Plus,
  Upload,
  FileText,
  Search,
  Pencil,
  Trash2,
  X,
  Sparkles,
  Zap,
  Activity,
} from "lucide-react";
import { Thread } from "./types";

interface SidebarProps {
  threads: Thread[];
  activeThreadId: string;
  onSelectThread: (thread: Thread) => void;
  onNewChat: () => void;
  onDeleteThread: (id: string) => void;
  onRenameThread: (id: string, title: string) => void;
  document: Record<string, unknown> | null;
  uploading: boolean;
  onUpload: (file: File) => void;
  sidebarOpen: boolean;
  onCloseSidebar: () => void;
  onOpenSkills: () => void;
}

export default function Sidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onNewChat,
  onDeleteThread,
  onRenameThread,
  document,
  uploading,
  onUpload,
  sidebarOpen,
  onCloseSidebar,
  onOpenSkills,
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filteredThreads = threads.filter((t) =>
    (t.title || "New Thread").toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleStartRename = (thread: Thread) => {
    setEditingId(thread.id);
    setEditTitle(thread.title || "");
  };

  const handleSaveRename = (id: string) => {
    if (editTitle.trim()) {
      onRenameThread(id, editTitle.trim());
    }
    setEditingId(null);
  };

  if (!sidebarOpen) return null;

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex h-screen w-[320px] shrink-0 flex-col border-r border-white/[0.08] bg-[#0b0e16]/95 backdrop-blur-xl md:static">
      {/* Brand Header */}
      <div className="shrink-0 p-5 pb-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-400/30 shadow-lg shadow-cyan-500/10">
              <img src="/icon.svg" alt="Agent-Pilot" className="h-7 w-7" />
              <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-[#0b0e16]" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-lg font-bold tracking-tight text-white">
                <span>Agent</span>
                <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent">
                  -Pilot
                </span>
              </div>
              <p className="text-[11px] font-medium text-slate-400 tracking-wide">
                ORCHESTRATE · AUTOMATE · EXECUTE
              </p>
            </div>
          </div>
          <button
            onClick={onCloseSidebar}
            className="rounded-lg p-1.5 text-slate-400 hover:text-white md:hidden"
          >
            <X size={18} />
          </button>
        </div>

        {/* New Chat & Skills Quick Buttons */}
        <div className="mt-5 grid grid-cols-2 gap-2">
          <button
            onClick={onNewChat}
            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-2.5 text-xs font-semibold text-white shadow-md shadow-cyan-500/20 hover:opacity-95 transition"
          >
            <Plus size={15} />
            <span>New Chat</span>
          </button>

          <button
            onClick={onOpenSkills}
            className="flex items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-xs font-semibold text-slate-200 hover:border-cyan-400/40 hover:bg-cyan-500/10 hover:text-cyan-300 transition"
          >
            <Sparkles size={14} className="text-cyan-400" />
            <span>Skills Library</span>
          </button>
        </div>

        {/* Document Knowledge Source */}
        <div className="mt-4">
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <span>Knowledge Base</span>
            <span className="text-[10px] text-cyan-400 font-mono">RAG Vector</span>
          </div>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="mt-2 flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-cyan-500/30 bg-cyan-500/[0.03] p-3.5 text-center transition hover:border-cyan-400 hover:bg-cyan-500/[0.07] disabled:opacity-50"
          >
            <Upload size={18} className={`text-cyan-400 ${uploading ? "animate-bounce" : ""}`} />
            <span className="mt-1 text-xs font-medium text-slate-200">
              {uploading ? "Indexing chunks…" : document ? `${document.filename}` : "Upload Document"}
            </span>
            <span className="text-[10px] text-slate-500">PDF, DOCX, CSV, TXT (up to 200MB)</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md,.markdown,.csv,application/pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = "";
            }}
          />

          {document && (
            <div className="mt-2 flex items-center justify-between rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-xs text-emerald-300">
              <span className="flex items-center gap-1.5 truncate">
                <FileText size={13} className="shrink-0" />
                <span className="truncate">{String(document.filename || "Active Document")}</span>
              </span>
              <span className="text-[10px] font-mono text-emerald-400 shrink-0">
                {String(document.chunks || 0)} chunks
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Threads List with Search */}
      <div className="flex flex-1 flex-col overflow-hidden px-4 py-3">
        <div className="relative mb-2.5">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full rounded-lg border border-white/5 bg-white/[0.03] py-1.5 pl-8 pr-3 text-xs text-white placeholder:text-slate-500 outline-none focus:border-cyan-500/40"
          />
        </div>

        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {filteredThreads.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500">
              No conversations found.
            </div>
          ) : (
            filteredThreads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              const isEditing = editingId === thread.id;

              return (
                <div
                  key={thread.id}
                  onClick={() => !isEditing && onSelectThread(thread)}
                  className={`group relative flex items-center justify-between rounded-xl px-3 py-2.5 text-xs transition cursor-pointer ${
                    isActive
                      ? "bg-gradient-to-r from-cyan-500/15 to-blue-500/10 text-cyan-200 border border-cyan-500/30"
                      : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200 border border-transparent"
                  }`}
                >
                  {isEditing ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSaveRename(thread.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      onBlur={() => handleSaveRename(thread.id)}
                      autoFocus
                      className="w-full rounded bg-black/60 px-2 py-0.5 text-xs text-white outline-none ring-1 ring-cyan-400"
                    />
                  ) : (
                    <>
                      <span className="truncate pr-2">{thread.title || "New Thread"}</span>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStartRename(thread);
                          }}
                          className="p-1 rounded text-slate-400 hover:text-cyan-300 hover:bg-white/10"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteThread(thread.id);
                          }}
                          className="p-1 rounded text-slate-400 hover:text-red-400 hover:bg-white/10"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Footer System Telemetry */}
      <div className="shrink-0 p-3.5 border-t border-white/[0.06] bg-white/[0.01]">
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-emerald-400/20" />
            <span className="font-medium text-slate-300">Agents Online</span>
          </div>
          <span className="font-mono text-[10px] text-cyan-400">v2.4 Live</span>
        </div>
      </div>
    </aside>
  );
}

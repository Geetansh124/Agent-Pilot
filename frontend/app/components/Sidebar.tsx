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
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const threadList = Array.isArray(threads) ? threads : [];
  const filteredThreads = threadList.filter((t) =>
    (t.title || "New Chat").toLowerCase().includes(searchQuery.toLowerCase())
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
    <aside className="fixed inset-y-0 left-0 z-30 flex h-screen w-[290px] shrink-0 flex-col glass-sidebar md:static">
      {/* Brand Header */}
      <div className="shrink-0 p-4 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img
              src="/icon.jpg"
              alt="Agent-Pilot Logo"
              className="h-8 w-8 rounded-lg border border-white/10 object-cover shadow-sm ring-1 ring-white/5"
            />
            <div>
              <div className="text-sm font-semibold tracking-tight text-zinc-100">
                Agent-Pilot
              </div>
              <p className="text-[11px] text-zinc-500">
                Autonomous Workspace
              </p>
            </div>
          </div>
          <button
            onClick={onCloseSidebar}
            className="rounded-lg p-1 text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.06] md:hidden transition"
          >
            <X size={16} />
          </button>
        </div>

        {/* Action Controls */}
        <div className="mt-3.5">
          <button
            type="button"
            onClick={() => onNewChat()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-100 px-3.5 py-2 text-xs font-medium text-zinc-950 hover:bg-white active:bg-zinc-200 transition shadow-sm hover:shadow-md cursor-pointer select-none"
          >
            <Plus size={14} />
            <span>New Chat</span>
          </button>
        </div>

        {/* Knowledge Base */}
        <div className="mt-3.5">
          <div className="flex items-center justify-between text-[11px] font-medium text-zinc-400 mb-1.5 px-0.5">
            <span>Knowledge Base</span>
            {document && (
              <span className="text-[10px] text-indigo-300 font-mono px-1.5 py-0.2 rounded bg-indigo-500/10 border border-indigo-500/20">
                {String(document.chunks || 0)} chunks
              </span>
            )}
          </div>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-2.5 text-xs text-zinc-300 hover:bg-white/[0.06] hover:border-white/15 transition disabled:opacity-50"
          >
            <Upload size={14} className={`text-indigo-400 ${uploading ? "animate-pulse" : ""}`} />
            <span className="truncate">
              {uploading ? "Indexing document…" : document ? String(document.filename) : "Upload Document"}
            </span>
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
        </div>
      </div>

      {/* Conversations List with Search */}
      <div className="flex flex-1 flex-col overflow-hidden p-3">
        <div className="relative mb-2.5">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full rounded-lg border border-white/[0.06] bg-white/[0.03] py-1.5 pl-7 pr-2.5 text-xs text-zinc-200 placeholder:text-zinc-500 outline-none focus:border-indigo-500/40 focus:ring-1 focus:ring-indigo-500/30 transition"
          />
        </div>

        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {filteredThreads.length === 0 ? (
            <div className="py-8 text-center text-xs text-zinc-600">
              No conversations yet
            </div>
          ) : (
            filteredThreads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              const isEditing = editingId === thread.id;

              return (
                <div
                  key={thread.id}
                  onClick={() => !isEditing && onSelectThread(thread)}
                  className={`group relative flex items-center justify-between rounded-lg px-2.5 py-2 text-xs transition cursor-pointer ${
                    isActive
                      ? "bg-white/[0.08] text-white font-medium border-l-2 border-indigo-400 shadow-sm"
                      : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
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
                      className="w-full rounded bg-black/80 px-2 py-0.5 text-xs text-white outline-none ring-1 ring-indigo-500"
                    />
                  ) : (
                    <>
                      <span className="truncate pr-2">{thread.title || "New Chat"}</span>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStartRename(thread);
                          }}
                          className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.08] transition"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteThread(thread.id);
                          }}
                          className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-white/[0.08] transition"
                        >
                          <Trash2 size={11} />
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
    </aside>
  );
}

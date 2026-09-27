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
    <aside className="fixed inset-y-0 left-0 z-30 flex h-screen w-[290px] shrink-0 flex-col border-r border-zinc-800/80 bg-[#0d0d10] md:static">
      {/* Brand Header */}
      <div className="shrink-0 p-4 border-b border-zinc-800/80">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img
              src="/icon.jpg"
              alt="Agent-Pilot Logo"
              className="h-8 w-8 rounded-lg border border-zinc-800 object-cover shadow-sm"
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
            className="rounded-md p-1 text-zinc-400 hover:text-zinc-200 md:hidden"
          >
            <X size={16} />
          </button>
        </div>

        {/* Action Controls */}
        <div className="mt-3.5">
          <button
            type="button"
            onClick={() => onNewChat()}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-2 text-xs font-medium text-zinc-900 hover:bg-white active:bg-zinc-200 transition shadow-sm cursor-pointer select-none"
          >
            <Plus size={14} />
            <span>New Chat</span>
          </button>
        </div>

        {/* Knowledge Base */}
        <div className="mt-3.5">
          <div className="flex items-center justify-between text-[11px] font-medium text-zinc-500 mb-1.5">
            <span>Knowledge Base</span>
            {document && (
              <span className="text-[10px] text-zinc-400 font-mono">
                {String(document.chunks || 0)} chunks
              </span>
            )}
          </div>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 text-xs text-zinc-300 hover:bg-zinc-800/60 hover:border-zinc-700 transition disabled:opacity-50"
          >
            <Upload size={14} className={`text-zinc-400 ${uploading ? "animate-pulse" : ""}`} />
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
        <div className="relative mb-2">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full rounded-md border border-zinc-800 bg-zinc-900/60 py-1.5 pl-7 pr-2.5 text-xs text-zinc-200 placeholder:text-zinc-500 outline-none focus:border-zinc-700"
          />
        </div>

        <div className="flex-1 overflow-y-auto space-y-0.5 pr-1">
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
                  className={`group relative flex items-center justify-between rounded-md px-2.5 py-2 text-xs transition cursor-pointer ${
                    isActive
                      ? "bg-zinc-800/90 text-zinc-100 font-medium"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
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
                      className="w-full rounded bg-black/60 px-2 py-0.5 text-xs text-white outline-none ring-1 ring-zinc-500"
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
                          className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700/50"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteThread(thread.id);
                          }}
                          className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-700/50"
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

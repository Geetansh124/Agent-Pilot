"use client";

import React, { FormEvent, useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Square,
  Loader2,
  Upload,
  Globe,
  Code2,
  BarChart3,
  FileText,
  X,
} from "lucide-react";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import ChatMessage from "./components/ChatMessage";
import { Message, Thread } from "./components/types";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function safeUUID(): string {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch { /* fallback */ }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

const QUICK_CHIPS = [
  { label: "Deep Web Research", icon: Globe, iconClass: "text-sky-400", prompt: "Fetch and summarize the latest updates from https://news.ycombinator.com" },
  { label: "Python Sandbox", icon: Code2, iconClass: "text-emerald-400", prompt: "Run Python to calculate compound interest on $25,000 at 8% annual return over 15 years." },
  { label: "Tabular Data Profiling", icon: BarChart3, iconClass: "text-amber-400", prompt: "Analyze this dataset structure: Month,Signups,Churn,Revenue\nJan,1200,45,24000\nFeb,1500,50,30000\nMar,1850,52,37000" },
  { label: "Document Vector Search", icon: FileText, iconClass: "text-indigo-400", prompt: "What are the primary conclusions, metrics, and risks highlighted in my uploaded document?" },
];

export default function Home() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [document, setDocument] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const chatFileInputRef = useRef<HTMLInputElement>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void loadThreads();
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, streaming]);

  // ----------------------------- data loaders ----------------------------

  async function loadThreads() {
    try {
      const response = await fetch(`${API}/api/threads`);
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data)) {
        setThreads(data);
        if (!threadId) newChat(data);
      }
    } catch {
      /* server waking up */
    }
  }

  function resetChat(id: string, msgs: Message[] = []) {
    try { abortRef.current?.abort(); } catch { /* ignore */ }
    setBusy(false);
    setStreaming(false);
    setActiveTool(null);
    setThreadId(id);
    setMessages(msgs);
  }

  function newChat(existing?: Thread[] | unknown) {
    resetChat(safeUUID(), []);
    setInput("");
    setDocument(null);
    if (Array.isArray(existing)) setThreads(existing);
  }

  function selectThread(thread: Thread) {
    resetChat(thread.id || safeUUID(), Array.isArray(thread.messages) ? thread.messages : []);
  }

  async function deleteThread(id: string) {
    try {
      await fetch(`${API}/api/threads/${id}`, { method: "DELETE" });
    } catch {
      /* best-effort */
    }
    setThreads((current) => (Array.isArray(current) ? current.filter((t) => t && t.id !== id) : []));
    if (threadId === id) newChat();
  }

  async function renameThread(id: string, newTitle: string) {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    try {
      await fetch(`${API}/api/threads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
    } catch {
      /* best-effort */
    }
    setThreads((current) =>
      Array.isArray(current)
        ? current.map((t) => (t && t.id === id ? { ...t, title: trimmed } : t))
        : []
    );
  }

  // ----------------------------- SSE streaming chat ----------------------

  async function send(event?: FormEvent) {
    if (event) event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setInput("");
    setMessages((current) => [...current, { role: "user", content: text }]);
    setBusy(true);
    setStreaming(true);
    setActiveTool(null);

    // Empty assistant bubble to fill via SSE
    setMessages((current) => [...current, { role: "assistant", content: "" }]);

    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 120_000);

    try {
      const response = await fetch(`${API}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, thread_id: threadId }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error((data as { detail?: string }).detail || "Request failed");
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          let payload: {
            type: string;
            content?: string;
            name?: string;
            message?: string;
          };
          try {
            payload = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (payload.type === "token" && payload.content) {
            const fragment = payload.content;
            setMessages((cur) => {
              const next = [...cur];
              const last = next[next.length - 1];
              if (last?.role === "assistant") {
                next[next.length - 1] = { role: "assistant", content: last.content + fragment };
              }
              return next;
            });
          } else if (payload.type === "tool") {
            setActiveTool(payload.name || "tool");
          } else if (payload.type === "done") {
            setActiveTool(null);
          } else if (payload.type === "error") {
            throw new Error(payload.message || "AI error");
          }
        }
      }

      setThreads((cur) => [
        { id: threadId, title: text.slice(0, 48), messages: [] },
        ...(Array.isArray(cur) ? cur.filter((t) => t && t.id !== threadId) : []),
      ]);
    } catch (error) {
      const msg =
        error instanceof DOMException && error.name === "AbortError"
          ? "Request timed out. The agent is still processing — please try again."
          : error instanceof Error
          ? error.message
          : "Something went wrong.";
      const errorContent =
        msg.includes("Failed to fetch") || msg.includes("NetworkError")
          ? "Server is starting..."
          : msg;

      setMessages((cur) => {
        const next = [...cur];
        const last = next[next.length - 1];
        if (last?.role === "assistant" && !last.content) {
          next[next.length - 1] = { role: "assistant", content: errorContent };
        } else {
          next.push({ role: "assistant", content: errorContent });
        }
        return next;
      });
    } finally {
      clearTimeout(timeout);
      setBusy(false);
      setStreaming(false);
      setActiveTool(null);
      abortRef.current = null;
    }
  }

  function stopStreaming() {
    abortRef.current?.abort();
  }

  // ----------------------------- upload ----------------------------------

  async function upload(file?: File) {
    if (!file) return;
    const allowed = [".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".csv", ".json"];
    const isSupported = allowed.some((ext) => file.name.toLowerCase().endsWith(ext));
    if (!isSupported) {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "Please upload a supported file (.pdf, .docx, .txt, .md, .csv)." },
      ]);
      return;
    }

    let activeThreadId = threadId;
    if (!activeThreadId) {
      activeThreadId = safeUUID();
      setThreadId(activeThreadId);
    }

    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file, file.name);
      const response = await fetch(`${API}/api/threads/${activeThreadId}/document`, {
        method: "POST",
        body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setDocument(data);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `📄 **${data.filename || file.name}** indexed successfully (${data.chunks || 0} chunks, ${data.documents || 1} pages).\n\nYou can now ask questions about this document!`,
        },
      ]);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Upload failed.";
      const errorContent =
        msg.includes("Failed to fetch") || msg.includes("NetworkError")
          ? "Server is starting..."
          : `Upload error: ${msg}`;
      setMessages((current) => [
        ...current,
        { role: "assistant", content: errorContent },
      ]);
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#09090b] text-zinc-100">
      {/* Sidebar */}
      <Sidebar
        threads={threads}
        activeThreadId={threadId}
        onSelectThread={selectThread}
        onNewChat={() => newChat()}
        onDeleteThread={deleteThread}
        onRenameThread={renameThread}
        document={document}
        uploading={uploading}
        onUpload={upload}
        sidebarOpen={sidebarOpen}
        onCloseSidebar={() => setSidebarOpen(false)}
      />

      {/* Main Chat Workspace */}
      <section className="relative flex h-screen min-w-0 flex-1 flex-col overflow-hidden ambient-glow">
        <Header
          onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
          onNewChat={() => newChat()}
          activeTool={activeTool}
        />

        {/* Messages container */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
          <div className="mx-auto flex w-full max-w-3xl flex-col min-h-full justify-between">
            {messages.length === 0 ? (
              <div className="my-auto flex flex-col items-center justify-center text-center py-12">
                <div className="relative mb-4 group">
                  <div className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-indigo-500/20 to-sky-500/20 blur-xl opacity-70 group-hover:opacity-100 transition duration-500" />
                  <img
                    src="/logo.jpg"
                    alt="Agent-Pilot Logo"
                    className="relative h-16 w-16 rounded-2xl border border-white/10 shadow-2xl object-cover ring-1 ring-white/10 transition-transform duration-300 group-hover:scale-105"
                  />
                </div>

                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white">
                  Where will we explore today?
                </h1>
                <p className="mt-2 max-w-md text-xs sm:text-sm text-zinc-400 leading-relaxed">
                  Autonomous workspace for deep web research, code execution, and document intelligence.
                </p>

                {/* Quick Capability Chips */}
                <div className="mt-8 flex flex-wrap items-center justify-center gap-2 max-w-xl">
                  {QUICK_CHIPS.map((chip, idx) => {
                    const Icon = chip.icon;
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => setInput(chip.prompt)}
                        className="group flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-3.5 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/[0.08] hover:border-white/20 transition-all duration-150 active:scale-95 shadow-sm"
                      >
                        <Icon size={13} className={chip.iconClass} />
                        <span>{chip.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <ChatMessage
                    key={index}
                    message={message}
                    isLastAssistant={message.role === "assistant" && index === messages.length - 1}
                    streaming={streaming}
                  />
                ))}

                {/* Active Tool Indicator */}
                {activeTool && (
                  <div className="flex items-center gap-2.5 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3.5 py-2 text-xs text-indigo-200 w-fit backdrop-blur-md shadow-md animate-pulse">
                    <Loader2 size={13} className="animate-spin text-indigo-400" />
                    <span className="text-zinc-400">Agent executing:</span>
                    <code className="font-mono text-indigo-200 font-medium bg-indigo-500/20 px-1.5 py-0.5 rounded text-[11px]">
                      {activeTool}
                    </code>
                  </div>
                )}

                {/* Thinking Indicator */}
                {busy && !streaming && !activeTool && (
                  <div className="flex items-center gap-2.5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2 text-xs text-zinc-400 w-fit backdrop-blur-md shadow-sm">
                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />
                    <span className="animate-pulse">Thinking…</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Input Bar */}
        <div className="shrink-0 px-4 sm:px-6 py-3.5">
          <form
            onSubmit={send}
            className="mx-auto flex w-full max-w-3xl flex-col rounded-2xl glass-input-box overflow-hidden"
          >
            {document && (
              <div className="flex items-center justify-between border-b border-white/[0.06] px-3.5 py-1.5 text-xs text-zinc-400 bg-white/[0.02]">
                <div className="flex items-center gap-2 truncate">
                  <FileText size={13} className="text-indigo-400 shrink-0" />
                  <span className="font-medium text-zinc-200 truncate">{String(document.filename || "Attached document")}</span>
                  <span className="text-[10px] text-zinc-500 shrink-0">({String(document.chunks || 0)} chunks)</span>
                </div>
                <button
                  type="button"
                  onClick={() => setDocument(null)}
                  className="text-zinc-500 hover:text-zinc-200 p-0.5 rounded transition ml-2"
                  title="Detach document"
                >
                  <X size={12} />
                </button>
              </div>
            )}

            <div className="flex items-end gap-2 p-2.5">
              <button
                type="button"
                onClick={() => chatFileInputRef.current?.click()}
                disabled={uploading}
                className="p-2 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.06] transition disabled:opacity-50"
                title="Attach document (.pdf, .docx, .csv, .txt)"
              >
                <Upload size={15} className={uploading ? "animate-pulse text-indigo-400" : ""} />
              </button>
              <input
                ref={chatFileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt,.md,.markdown,.csv,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                  e.target.value = "";
                }}
              />

              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(e);
                  }
                }}
                rows={1}
                disabled={busy}
                placeholder={uploading ? "Indexing attached document..." : "Ask anything, run code, scrape URLs, or query documents..."}
                className="min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-xs sm:text-sm text-zinc-100 placeholder:text-zinc-500 outline-none max-h-32 leading-relaxed"
              />

              {streaming ? (
                <button
                  type="button"
                  onClick={stopStreaming}
                  className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs text-zinc-200 hover:bg-white/[0.1] transition active:scale-95"
                  title="Stop generation"
                >
                  <Square size={12} />
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  disabled={busy || !input.trim()}
                  type="submit"
                  className="flex items-center justify-center rounded-xl bg-zinc-100 p-2 text-zinc-950 transition hover:bg-white hover:shadow-md disabled:cursor-not-allowed disabled:opacity-20 active:scale-95 shadow-sm"
                >
                  <ArrowUp size={15} />
                </button>
              )}
            </div>
          </form>

          <div className="mx-auto mt-2 flex w-full max-w-3xl items-center justify-between text-[11px] text-zinc-500 px-2">
            <span>Agent-Pilot 2.0</span>
            <span>Enter to send · Shift+Enter for new line</span>
          </div>
        </div>
      </section>
    </main>
  );
}

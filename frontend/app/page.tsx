"use client";

import React, { FormEvent, useEffect, useRef, useState } from "react";
import { Send, Square, Sparkles, AlertCircle, Bot } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import HeroSection from "./components/HeroSection";
import ChatMessage from "./components/ChatMessage";
import SkillsModal from "./components/SkillsModal";
import { Message, Thread, AgentRole, AgentSkill } from "./components/types";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

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
  const [skillsModalOpen, setSkillsModalOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<AgentRole>("auto");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Keyboard shortcut: Cmd+K / Ctrl+K opens Skills Modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSkillsModalOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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
      setThreads(data);
      if (!threadId) newChat(data);
    } catch {
      /* server may be waking up */
    }
  }

  function newChat(existing = threads) {
    abortRef.current?.abort();
    setBusy(false);
    setStreaming(false);
    setActiveTool(null);
    const id = crypto.randomUUID();
    setThreadId(id);
    setMessages([]);
    setDocument(null);
    setThreads(existing);
  }

  function selectThread(thread: Thread) {
    abortRef.current?.abort();
    setBusy(false);
    setStreaming(false);
    setActiveTool(null);
    setThreadId(thread.id);
    setMessages(thread.messages);
  }

  async function deleteThread(id: string) {
    try {
      await fetch(`${API}/api/threads/${id}`, { method: "DELETE" });
    } catch {
      /* best-effort */
    }
    setThreads((current) => current.filter((t) => t.id !== id));
    if (threadId === id) newChat(threads.filter((t) => t.id !== id));
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
      current.map((t) => (t.id === id ? { ...t, title: trimmed } : t))
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
        ...cur.filter((t) => t.id !== threadId),
      ]);
    } catch (error) {
      const msg =
        error instanceof DOMException && error.name === "AbortError"
          ? "Request timed out. The agent is still processing — please try again."
          : error instanceof Error
          ? error.message
          : "Something went wrong.";
      const errorContent = msg.includes("Failed to fetch")
        ? "Could not reach the server — it may be waking up (free tier). Please wait 30s and try again."
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
      activeThreadId = crypto.randomUUID();
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
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `Upload error: ${msg}` },
      ]);
    } finally {
      setUploading(false);
    }
  }

  const handleSelectSkill = (skill: AgentSkill) => {
    setSelectedRole(skill.agentRole);
    setInput(skill.prompt);
    setSkillsModalOpen(false);
  };

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#07090e] text-slate-100">
      {/* Sleek Sidebar */}
      <Sidebar
        threads={threads}
        activeThreadId={threadId}
        onSelectThread={selectThread}
        onNewChat={newChat}
        onDeleteThread={deleteThread}
        onRenameThread={renameThread}
        document={document}
        uploading={uploading}
        onUpload={upload}
        sidebarOpen={sidebarOpen}
        onCloseSidebar={() => setSidebarOpen(false)}
        onOpenSkills={() => setSkillsModalOpen(true)}
      />

      {/* Main Chat Workspace */}
      <section className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <Header
          onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
          selectedRole={selectedRole}
          onSelectRole={setSelectedRole}
          onOpenSkills={() => setSkillsModalOpen(true)}
          activeTool={activeTool}
        />

        {/* Scrollable messages container */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 scrollbar-none">
          <div className="mx-auto flex w-full max-w-4xl flex-col">
            {messages.length === 0 ? (
              <HeroSection
                onSelectPrompt={(prompt) => setInput(prompt)}
                onOpenSkills={() => setSkillsModalOpen(true)}
              />
            ) : (
              <div className="space-y-6">
                {messages.map((message, index) => (
                  <ChatMessage
                    key={index}
                    message={message}
                    isLastAssistant={message.role === "assistant" && index === messages.length - 1}
                    streaming={streaming}
                  />
                ))}

                {/* Active Tool Indicator Pill */}
                {activeTool && (
                  <div className="flex items-center gap-2.5 rounded-2xl border border-cyan-400/30 bg-cyan-500/[0.06] px-4 py-2.5 text-xs text-cyan-300 w-fit backdrop-blur-md">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
                    </span>
                    <span>Executing agent tool:</span>
                    <code className="font-mono font-bold text-white bg-black/40 px-1.5 py-0.5 rounded border border-white/10">
                      {activeTool}
                    </code>
                  </div>
                )}

                {/* Thinking Pulse */}
                {busy && !streaming && !activeTool && (
                  <div className="flex items-center gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-slate-400 w-fit">
                    <Bot size={16} className="text-cyan-400 animate-spin" />
                    <span>Agent-Pilot synthesizing response…</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Supercharged Bottom Input Bar */}
        <div className="shrink-0 border-t border-white/[0.08] bg-[#07090e]/95 px-4 sm:px-6 py-4 backdrop-blur-xl">
          <form
            onSubmit={send}
            className="mx-auto flex w-full max-w-4xl items-center gap-3 rounded-2xl border border-white/10 bg-[#0e121b] p-2 shadow-2xl shadow-black/40 focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/20 transition-all"
          >
            <button
              type="button"
              onClick={() => setSkillsModalOpen(true)}
              className="p-2.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-white/5 transition"
              title="Explore Skills (⌘K)"
            >
              <Sparkles size={17} className="text-cyan-400" />
            </button>

            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              placeholder="Ask anything, execute Python, scrape URLs, or analyze documents..."
              className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm text-white placeholder:text-slate-500 outline-none"
            />

            {streaming ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="flex items-center gap-1.5 rounded-xl bg-red-500/80 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-red-500"
                title="Stop generation"
              >
                <Square size={14} />
                <span>Stop</span>
              </button>
            ) : (
              <button
                disabled={busy || !input.trim()}
                type="submit"
                className="flex items-center justify-center rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 p-2.5 text-white shadow-lg shadow-cyan-500/20 transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            )}
          </form>

          <div className="mx-auto mt-2 flex w-full max-w-4xl items-center justify-between text-[11px] text-slate-500 px-1">
            <span className="hidden sm:inline">Press <kbd className="font-mono text-slate-400">Enter</kbd> to execute</span>
            <span>Agent-Pilot Multi-Agent Architecture</span>
          </div>
        </div>
      </section>

      {/* Skills Library Modal */}
      <SkillsModal
        isOpen={skillsModalOpen}
        onClose={() => setSkillsModalOpen(false)}
        onSelectSkill={handleSelectSkill}
      />
    </main>
  );
}

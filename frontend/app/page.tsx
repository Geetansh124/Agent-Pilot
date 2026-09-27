"use client";

import React, { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, Square, Layers, Loader2 } from "lucide-react";
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
      /* server waking up */
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
    <main className="flex h-screen w-full overflow-hidden bg-[#09090b] text-zinc-100">
      {/* Sidebar */}
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

        {/* Messages container */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
          <div className="mx-auto flex w-full max-w-3xl flex-col">
            {messages.length === 0 ? (
              <HeroSection
                onSelectPrompt={(prompt) => setInput(prompt)}
                onOpenSkills={() => setSkillsModalOpen(true)}
              />
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
                  <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/80 px-3 py-1.5 text-xs text-zinc-300 w-fit">
                    <Loader2 size={12} className="animate-spin text-zinc-400" />
                    <span>Executing:</span>
                    <code className="font-mono text-zinc-200 bg-zinc-800 px-1 py-0.5 rounded text-[11px]">
                      {activeTool}
                    </code>
                  </div>
                )}

                {/* Thinking Indicator */}
                {busy && !streaming && !activeTool && (
                  <div className="flex items-center gap-2 rounded-md border border-zinc-800/80 bg-zinc-900/40 px-3 py-2 text-xs text-zinc-400 w-fit">
                    <Loader2 size={12} className="animate-spin text-zinc-500" />
                    <span>Thinking…</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Input Bar (Linear / Claude Style) */}
        <div className="shrink-0 border-t border-zinc-800/80 bg-[#09090b] px-4 sm:px-6 py-3">
          <form
            onSubmit={send}
            className="mx-auto flex w-full max-w-3xl items-center gap-2 rounded-xl border border-zinc-800 bg-[#121215] p-2 focus-within:border-zinc-700 transition"
          >
            <button
              type="button"
              onClick={() => setSkillsModalOpen(true)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition"
              title="Skills & Tools (⌘K)"
            >
              <Layers size={15} />
            </button>

            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              placeholder="Ask anything, execute code, scrape URLs, or analyze documents..."
              className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-xs sm:text-sm text-zinc-100 placeholder:text-zinc-500 outline-none"
            />

            {streaming ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-750 transition"
                title="Stop generation"
              >
                <Square size={12} />
                <span>Stop</span>
              </button>
            ) : (
              <button
                disabled={busy || !input.trim()}
                type="submit"
                className="flex items-center justify-center rounded-lg bg-zinc-100 p-2 text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-30"
              >
                <ArrowUp size={15} />
              </button>
            )}
          </form>

          <div className="mx-auto mt-2 flex w-full max-w-3xl items-center justify-between text-[11px] text-zinc-500 px-1">
            <span>Press <kbd className="text-zinc-400 font-mono">↵</kbd> to send</span>
            <span>Agent-Pilot</span>
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

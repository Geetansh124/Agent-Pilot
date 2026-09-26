"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  Plus,
  Send,
  Sparkles,
  Upload,
  Menu,
  X,
  Bot,
  User,
  Trash2,
  Square,
  Pencil,
  Check,
} from "lucide-react";

type Message = { role: "user" | "assistant"; content: string };
type Thread = { id: string; title: string; messages: Message[] };
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
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
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
    if (!trimmed) {
      setEditingThreadId(null);
      return;
    }
    try {
      await fetch(`${API}/api/threads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
    } catch {
      /* best effort */
    }
    setThreads((current) =>
      current.map((t) => (t.id === id ? { ...t, title: trimmed } : t))
    );
    setEditingThreadId(null);
  }

  // ----------------------------- SSE streaming chat ----------------------

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setInput("");
    setMessages((current) => [...current, { role: "user", content: text }]);
    setBusy(true);
    setStreaming(true);
    setActiveTool(null);

    // Create empty assistant bubble to fill via SSE
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
            tools_used?: string[];
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
              if (last?.role === "assistant") next[next.length - 1] = { role: "assistant", content: last.content + fragment };
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

      setThreads((cur) => [{ id: threadId, title: text.slice(0, 48), messages: [] }, ...cur.filter((t) => t.id !== threadId)]);
    } catch (error) {
      const msg = error instanceof DOMException && error.name === "AbortError"
        ? "Request timed out. The AI is still processing — please try again."
        : error instanceof Error ? error.message : "Something went wrong.";
      const errorContent = msg.includes("Failed to fetch")
        ? "Could not reach the server — it may be waking up (free tier). Please wait 30 s and try again."
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
      const response = await fetch(
        `${API}/api/threads/${activeThreadId}/document`,
        { method: "POST", body }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setDocument(data);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `📄 **${data.filename || file.name}** has been indexed successfully (${data.chunks || 0} chunks, ${data.documents || 1} pages).\n\nYou can now ask questions about this document!`,
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

  // ----------------------------- render ----------------------------------

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#090a10]">
      {sidebarOpen && (
        <aside className="flex h-screen w-[310px] shrink-0 flex-col border-r border-white/10 bg-[#11131d] max-md:fixed max-md:inset-y-0 max-md:z-20">
          {/* Top fixed controls in sidebar */}
          <div className="shrink-0 p-5 pb-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xl font-bold tracking-tight">
                  Agent-<span className="text-violet-400">Pilot</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Your intelligent document workspace
                </p>
              </div>
              <button className="md:hidden" onClick={() => setSidebarOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <button onClick={() => newChat()} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold transition hover:border-violet-400 hover:bg-violet-400/10">
              <Plus size={17} /> New chat
            </button>

            <div className="mt-6 text-[11px] font-bold uppercase tracking-[.18em] text-slate-500">Knowledge source</div>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="mt-2.5 flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-violet-400/60 bg-violet-400/10 px-4 py-5 text-sm text-slate-300 transition hover:bg-violet-400/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Upload size={19} className={`text-violet-300 ${uploading ? "animate-pulse" : ""}`} />
              <span className="font-medium text-xs">{uploading ? "Indexing document…" : document ? `${document.filename}` : "Upload document"}</span>
              <span className="text-[11px] text-slate-500">PDF, DOCX, CSV, TXT up to 200 MB</span>
            </button>
            <input
              ref={fileRef}
              className="hidden"
              type="file"
              accept=".pdf,.docx,.doc,.txt,.md,.markdown,.csv,application/pdf"
              onChange={(e) => {
                const selected = e.target.files?.[0];
                if (selected) void upload(selected);
                e.target.value = "";
              }}
            />

            {document && (
              <div className="mt-2.5 rounded-lg bg-emerald-400/10 p-2.5 text-xs text-emerald-300">
                <FileText size={13} className="mb-0.5 inline-block mr-1" /> {String(document.chunks)} chunks · {String(document.documents)} pages
              </div>
            )}
          </div>

          {/* Independently scrollable recent conversations list */}
          <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="text-[11px] font-bold uppercase tracking-[.18em] text-slate-500">
              Recent conversations
            </div>
            <div className="mt-3 space-y-1">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`group flex items-center rounded-lg transition ${
                    thread.id === threadId ? "bg-violet-400/15 text-violet-200" : "text-slate-400 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {editingThreadId === thread.id ? (
                    <div className="flex flex-1 items-center px-2 py-1">
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void renameThread(thread.id, editTitle);
                          if (e.key === "Escape") setEditingThreadId(null);
                        }}
                        autoFocus
                        className="min-w-0 flex-1 rounded bg-black/40 px-2 py-1 text-xs text-white outline-none ring-1 ring-violet-400"
                      />
                      <button
                        onClick={() => void renameThread(thread.id, editTitle)}
                        className="ml-1 p-1 text-emerald-400 hover:text-emerald-300"
                        title="Save"
                      >
                        <Check size={13} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => selectThread(thread)}
                        className="min-w-0 flex-1 truncate px-3 py-2.5 text-left text-sm"
                      >
                        {thread.title || "New chat"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingThreadId(thread.id);
                          setEditTitle(thread.title || "");
                        }}
                        title="Rename thread"
                        className="hidden shrink-0 rounded p-1 text-slate-500 transition hover:bg-violet-500/20 hover:text-violet-300 group-hover:block"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void deleteThread(thread.id);
                        }}
                        title="Delete thread"
                        className="mr-2 hidden shrink-0 rounded p-1 text-slate-500 transition hover:bg-red-500/20 hover:text-red-400 group-hover:block"
                      >
                        <Trash2 size={13} />
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        </aside>
      )}

      {/* Main chat section with fixed header, independently scrollable messages, and fixed input bar */}
      <section className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header className="shrink-0 flex items-center justify-between border-b border-white/10 bg-[#090a10] px-6 py-4">
          <button className="md:hidden" onClick={() => setSidebarOpen(true)}>
            <Menu size={20} />
          </button>
          <div className="hidden md:block" />
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-400" /> Ready
          </div>
        </header>

        {/* Scrollable messages container */}
        <div className="flex-1 overflow-y-auto px-5 py-8">
          <div className="mx-auto flex w-full max-w-4xl flex-col">
            <div className="mb-8 flex items-center gap-3">
              <div className="rounded-xl bg-violet-400/15 p-3 text-violet-300"><Sparkles size={22} /></div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight">What would you like to explore?</h1>
                <p className="mt-1 text-sm text-slate-400">Ask questions, analyze documents, or use your AI tools.</p>
              </div>
            </div>

            <div className="space-y-6">
              {messages.length === 0 && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    "Summarize my PDF",
                    "Search web for latest tech news",
                    "Run Python to calculate compound interest",
                    "What tools can you use?",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => setInput(prompt)}
                      className="rounded-xl border border-white/10 bg-white/[.03] p-4 text-left text-sm text-slate-300 transition hover:border-violet-400/50 hover:bg-violet-400/10"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              )}

              {messages.map((message, index) => {
                const isLastAssistant = message.role === "assistant" && index === messages.length - 1;
                const isUser = message.role === "user";
                return (
                  <div key={index} className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
                    <div className={`flex max-w-[80%] gap-3 rounded-2xl px-4 py-3 ${isUser ? "bg-violet-500 text-white" : "border border-white/10 bg-white/[.04] text-slate-200"}`}>
                      {isUser ? <User size={17} className="mt-1 shrink-0" /> : <Bot size={17} className="mt-1 shrink-0 text-violet-300" />}
                      <div className="min-w-0 flex-1 text-sm leading-6">
                        {isUser ? (
                          <div className="whitespace-pre-wrap">{message.content}</div>
                        ) : (
                          <div className="prose prose-invert max-w-none space-y-2 text-slate-200">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                h1: ({ ...props }) => <h1 className="mb-2 mt-4 text-lg font-bold text-white" {...props} />,
                                h2: ({ ...props }) => <h2 className="mb-2 mt-3 text-base font-bold text-white" {...props} />,
                                h3: ({ ...props }) => <h3 className="mb-1 mt-2 text-sm font-semibold text-violet-200" {...props} />,
                                p: ({ ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props} />,
                                ul: ({ ...props }) => <ul className="mb-2 list-disc pl-5 space-y-1" {...props} />,
                                ol: ({ ...props }) => <ol className="mb-2 list-decimal pl-5 space-y-1" {...props} />,
                                li: ({ ...props }) => <li className="leading-relaxed" {...props} />,
                                strong: ({ ...props }) => <strong className="font-semibold text-white" {...props} />,
                                code: ({ className, children, ...props }) => {
                                  const isInline = !className && typeof children === "string" && !children.includes("\n");
                                  return isInline ? (
                                    <code className="rounded bg-violet-950/60 px-1.5 py-0.5 font-mono text-xs font-medium text-violet-300 border border-violet-800/40" {...props}>
                                      {children}
                                    </code>
                                  ) : (
                                    <code className="block overflow-x-auto rounded-lg bg-slate-950/80 p-3 font-mono text-xs text-slate-200 border border-white/10 my-2" {...props}>
                                      {children}
                                    </code>
                                  );
                                },
                                a: ({ ...props }) => <a className="text-violet-400 underline hover:text-violet-300" target="_blank" rel="noopener noreferrer" {...props} />,
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          </div>
                        )}
                        {isLastAssistant && streaming && <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-violet-400 align-middle" />}
                      </div>
                    </div>
                  </div>
                );
              })}

              {activeTool && (
                <div className="flex justify-start gap-3">
                  <div className="flex items-center gap-2 rounded-2xl border border-violet-400/30 bg-violet-400/5 px-4 py-2 text-xs text-violet-300">
                    <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-violet-400" />
                    Using <code className="font-mono font-bold">{activeTool}</code>…
                  </div>
                </div>
              )}

              {busy && !streaming && !activeTool && (
                <div className="flex justify-start gap-3">
                  <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[.04] px-4 py-3 text-sm text-slate-400">
                    <Bot size={17} className="shrink-0 animate-pulse text-violet-300" />
                    <span className="animate-pulse">Thinking…</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>

        {/* Fixed bottom input form */}
        <div className="shrink-0 border-t border-white/10 bg-[#090a10]/95 px-5 py-4 backdrop-blur-md">
          <form onSubmit={send} className="mx-auto flex w-full max-w-4xl items-center gap-3 rounded-2xl border border-white/10 bg-[#151824] p-2 shadow-2xl shadow-black/20">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              placeholder="Ask about your document or use tools…"
              className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm text-white outline-none placeholder:text-slate-500"
            />
            {streaming ? (
              <button type="button" onClick={stopStreaming} className="rounded-xl bg-red-500/80 p-3 text-white transition hover:bg-red-500" title="Stop generating">
                <Square size={18} />
              </button>
            ) : (
              <button disabled={busy || !input.trim()} className="rounded-xl bg-violet-500 p-3 text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-40">
                <Send size={18} />
              </button>
            )}
          </form>
        </div>
      </section>
    </main>
  );
}

"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Copy, Check } from "lucide-react";
import { Message } from "./types";
import { useAuth } from "../context/AuthContext";

interface ChatMessageProps {
  message: Message;
  isLastAssistant: boolean;
  streaming: boolean;
}

function CodeBlock({ children, className, ...props }: React.ComponentPropsWithoutRef<"code">) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1] : "code";
  const codeString = String(children).replace(/\n$/, "");

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(codeString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* fallback */
    }
  };

  return (
    <div className="relative my-3 rounded-xl border border-white/[0.08] bg-[#0b0b0e] overflow-hidden shadow-lg shadow-black/40">
      <div className="flex items-center justify-between px-3.5 py-1.5 border-b border-white/[0.06] bg-white/[0.02]">
        <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-medium">
          {lang}
        </span>
        <button
          onClick={handleCopyCode}
          type="button"
          className="flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition py-0.5 px-1.5 rounded hover:bg-white/[0.05]"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3.5 overflow-x-auto text-xs text-zinc-200 font-mono leading-relaxed">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    </div>
  );
}

export default function ChatMessage({
  message,
  isLastAssistant,
  streaming,
}: ChatMessageProps) {
  const { user } = useAuth();
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    if (!message.content) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard API fallback */
    }
  };

  return (
    <div className={`group flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="shrink-0 mt-0.5">
          <img
            src="/logo.jpg"
            alt="Agent-Pilot"
            className="h-7 w-7 rounded-lg border border-white/10 object-cover shadow-md ring-1 ring-white/5"
          />
        </div>
      )}

      <div
        className={`relative flex max-w-[85%] flex-col rounded-2xl px-4 py-3 text-sm leading-relaxed transition-all ${
          isUser
            ? "bg-gradient-to-br from-zinc-800/90 to-zinc-850/90 text-zinc-100 border border-white/[0.1] shadow-lg shadow-black/20"
            : "border border-white/[0.08] bg-[#121216]/80 backdrop-blur-md text-zinc-200 shadow-md shadow-black/30"
        }`}
      >
        {/* Copy Button on Message Hover */}
        {!isUser && message.content && (
          <button
            onClick={handleCopy}
            title="Copy message"
            className="absolute top-2.5 right-2.5 p-1 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.08] opacity-0 group-hover:opacity-100 transition shadow-sm"
          >
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          </button>
        )}

        <div className="min-w-0">
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <div className="prose prose-invert max-w-none space-y-2 text-zinc-200 text-xs sm:text-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ ...props }) => (
                    <h1 className="mb-2 mt-3 text-base font-semibold text-zinc-100 tracking-tight" {...props} />
                  ),
                  h2: ({ ...props }) => (
                    <h2 className="mb-2 mt-2.5 text-sm font-semibold text-zinc-200 tracking-tight" {...props} />
                  ),
                  h3: ({ ...props }) => (
                    <h3 className="mb-1 mt-2 text-xs font-semibold text-zinc-300" {...props} />
                  ),
                  p: ({ ...props }) => <p className="mb-2 last:mb-0 leading-relaxed text-zinc-300" {...props} />,
                  ul: ({ ...props }) => <ul className="mb-2 list-disc pl-4 space-y-1 text-zinc-300" {...props} />,
                  ol: ({ ...props }) => <ol className="mb-2 list-decimal pl-4 space-y-1 text-zinc-300" {...props} />,
                  li: ({ ...props }) => <li className="leading-relaxed" {...props} />,
                  strong: ({ ...props }) => <strong className="font-semibold text-zinc-100" {...props} />,
                  blockquote: ({ ...props }) => (
                    <blockquote className="border-l-2 border-indigo-500/60 pl-3 italic text-zinc-400 my-2 bg-indigo-500/[0.03] py-1 rounded-r" {...props} />
                  ),
                  table: ({ ...props }) => (
                    <div className="my-2.5 overflow-x-auto rounded-xl border border-white/[0.08] shadow-sm">
                      <table className="w-full text-left text-xs border-collapse" {...props} />
                    </div>
                  ),
                  th: ({ ...props }) => (
                    <th className="border-b border-white/[0.08] bg-white/[0.03] p-2.5 font-medium text-zinc-300" {...props} />
                  ),
                  td: ({ ...props }) => (
                    <td className="border-b border-white/[0.06] p-2.5 text-zinc-400" {...props} />
                  ),
                  code: ({ className, children, ...props }) => {
                    const isInline = !className && typeof children === "string" && !children.includes("\n");
                    return isInline ? (
                      <code
                        className="rounded-md bg-white/[0.07] px-1.5 py-0.5 font-mono text-[11px] text-zinc-200 border border-white/[0.08]"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <CodeBlock className={className} {...props}>
                        {children}
                      </CodeBlock>
                    );
                  },
                  a: ({ ...props }) => (
                    <a
                      className="text-indigo-400 hover:text-indigo-300 underline decoration-indigo-500/40 hover:decoration-indigo-400 transition"
                      target="_blank"
                      rel="noopener noreferrer"
                      {...props}
                    />
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {isLastAssistant && streaming && (
            <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-indigo-400 shadow-[0_0_8px_rgba(99,102,241,0.8)] ml-1.5 align-middle" />
          )}
        </div>
      </div>

      {isUser && (
        <div className="shrink-0 mt-0.5">
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.full_name || user.email || "You"}
              referrerPolicy="no-referrer"
              className="h-7 w-7 rounded-lg object-cover border border-white/10 shadow-sm"
              onError={(e) => {
                (e.currentTarget as HTMLElement).style.display = "none";
              }}
            />
          ) : (
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-800 border border-white/10 text-zinc-300 shadow-sm font-semibold text-xs">
              {user?.full_name?.charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || <User size={14} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

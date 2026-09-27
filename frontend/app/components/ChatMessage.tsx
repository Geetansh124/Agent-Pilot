"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Copy, Check } from "lucide-react";
import { Message } from "./types";

interface ChatMessageProps {
  message: Message;
  isLastAssistant: boolean;
  streaming: boolean;
}

export default function ChatMessage({
  message,
  isLastAssistant,
  streaming,
}: ChatMessageProps) {
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
    <div className={`group flex gap-3.5 ${isUser ? "justify-end" : "justify-start"} animate-fadeIn`}>
      {!isUser && (
        <div className="shrink-0 mt-0.5">
          <img
            src="/icon.svg"
            alt="Agent-Pilot"
            className="h-7 w-7 rounded-lg border border-cyan-400/30 shadow-md shadow-cyan-500/10"
          />
        </div>
      )}

      <div
        className={`relative flex max-w-[85%] flex-col rounded-2xl px-5 py-4 transition-all ${
          isUser
            ? "bg-gradient-to-r from-blue-600 via-cyan-600 to-cyan-500 text-white shadow-lg shadow-cyan-900/20"
            : "border border-white/10 bg-[#0e121b]/90 text-slate-200 backdrop-blur-md hover:border-white/15"
        }`}
      >
        {/* Copy Button on Message Hover */}
        {!isUser && message.content && (
          <button
            onClick={handleCopy}
            title="Copy message"
            className="absolute top-3 right-3 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 opacity-0 group-hover:opacity-100 transition"
          >
            {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
          </button>
        )}

        <div className="min-w-0 text-sm leading-relaxed">
          {isUser ? (
            <div className="whitespace-pre-wrap font-medium">{message.content}</div>
          ) : (
            <div className="prose prose-invert max-w-none space-y-2.5 text-slate-200">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ ...props }) => (
                    <h1 className="mb-2 mt-4 text-lg font-bold text-white tracking-tight" {...props} />
                  ),
                  h2: ({ ...props }) => (
                    <h2 className="mb-2 mt-3 text-base font-semibold text-cyan-200" {...props} />
                  ),
                  h3: ({ ...props }) => (
                    <h3 className="mb-1 mt-2 text-sm font-semibold text-cyan-300" {...props} />
                  ),
                  p: ({ ...props }) => <p className="mb-2 last:mb-0 leading-relaxed text-slate-200" {...props} />,
                  ul: ({ ...props }) => <ul className="mb-2 list-disc pl-5 space-y-1 text-slate-300" {...props} />,
                  ol: ({ ...props }) => <ol className="mb-2 list-decimal pl-5 space-y-1 text-slate-300" {...props} />,
                  li: ({ ...props }) => <li className="leading-relaxed" {...props} />,
                  strong: ({ ...props }) => <strong className="font-semibold text-white" {...props} />,
                  blockquote: ({ ...props }) => (
                    <blockquote className="border-l-2 border-cyan-400/50 pl-3 italic text-slate-400 my-2" {...props} />
                  ),
                  table: ({ ...props }) => (
                    <div className="my-3 overflow-x-auto rounded-xl border border-white/10">
                      <table className="w-full text-left text-xs border-collapse" {...props} />
                    </div>
                  ),
                  th: ({ ...props }) => (
                    <th className="border-b border-white/10 bg-white/5 p-2.5 font-semibold text-cyan-300" {...props} />
                  ),
                  td: ({ ...props }) => (
                    <td className="border-b border-white/5 p-2.5 text-slate-300" {...props} />
                  ),
                  code: ({ className, children, ...props }) => {
                    const isInline = !className && typeof children === "string" && !children.includes("\n");
                    return isInline ? (
                      <code
                        className="rounded-md bg-cyan-950/50 px-1.5 py-0.5 font-mono text-xs font-medium text-cyan-300 border border-cyan-800/40"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <div className="relative my-3 rounded-xl border border-white/10 bg-[#090b10] overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/10 bg-white/[0.03] text-[11px] text-slate-400 font-mono">
                          <span>Snippet</span>
                        </div>
                        <pre className="p-3.5 overflow-x-auto text-xs text-slate-200 font-mono">
                          <code {...props}>{children}</code>
                        </pre>
                      </div>
                    );
                  },
                  a: ({ ...props }) => (
                    <a
                      className="text-cyan-400 underline decoration-cyan-400/40 hover:text-cyan-300 hover:decoration-cyan-300 transition"
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
            <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-cyan-400 ml-1.5 align-middle" />
          )}
        </div>
      </div>

      {isUser && (
        <div className="shrink-0 mt-0.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 border border-white/10 text-white">
            <User size={15} />
          </div>
        </div>
      )}
    </div>
  );
}

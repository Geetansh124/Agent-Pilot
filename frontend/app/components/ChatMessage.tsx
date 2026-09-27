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
    <div className={`group flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="shrink-0 mt-0.5">
          <img
            src="/icon.jpg"
            alt="Agent-Pilot"
            className="h-7 w-7 rounded-lg border border-zinc-800 object-cover shadow-sm"
          />
        </div>
      )}

      <div
        className={`relative flex max-w-[85%] flex-col rounded-2xl px-4 py-3 text-sm leading-relaxed transition-all ${
          isUser
            ? "bg-zinc-800 text-zinc-100 border border-zinc-700/60 shadow-sm"
            : "border border-zinc-800/80 bg-zinc-900/40 text-zinc-200"
        }`}
      >
        {/* Copy Button on Message Hover */}
        {!isUser && message.content && (
          <button
            onClick={handleCopy}
            title="Copy message"
            className="absolute top-2.5 right-2.5 p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 opacity-0 group-hover:opacity-100 transition"
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
                    <h1 className="mb-2 mt-3 text-base font-semibold text-zinc-100" {...props} />
                  ),
                  h2: ({ ...props }) => (
                    <h2 className="mb-2 mt-2.5 text-sm font-semibold text-zinc-200" {...props} />
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
                    <blockquote className="border-l-2 border-zinc-700 pl-3 italic text-zinc-400 my-2" {...props} />
                  ),
                  table: ({ ...props }) => (
                    <div className="my-2.5 overflow-x-auto rounded-lg border border-zinc-800">
                      <table className="w-full text-left text-xs border-collapse" {...props} />
                    </div>
                  ),
                  th: ({ ...props }) => (
                    <th className="border-b border-zinc-800 bg-zinc-900/80 p-2 font-medium text-zinc-300" {...props} />
                  ),
                  td: ({ ...props }) => (
                    <td className="border-b border-zinc-800/80 p-2 text-zinc-400" {...props} />
                  ),
                  code: ({ className, children, ...props }) => {
                    const isInline = !className && typeof children === "string" && !children.includes("\n");
                    return isInline ? (
                      <code
                        className="rounded bg-zinc-800/90 px-1.5 py-0.5 font-mono text-[11px] text-zinc-200 border border-zinc-700/60"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <div className="relative my-2.5 rounded-lg border border-zinc-800 bg-[#0d0d10] overflow-hidden">
                        <pre className="p-3 overflow-x-auto text-xs text-zinc-200 font-mono">
                          <code {...props}>{children}</code>
                        </pre>
                      </div>
                    );
                  },
                  a: ({ ...props }) => (
                    <a
                      className="text-blue-400 hover:text-blue-300 underline decoration-zinc-600 transition"
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
            <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-zinc-400 ml-1.5 align-middle" />
          )}
        </div>
      </div>

      {isUser && (
        <div className="shrink-0 mt-0.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300">
            <User size={14} />
          </div>
        </div>
      )}
    </div>
  );
}

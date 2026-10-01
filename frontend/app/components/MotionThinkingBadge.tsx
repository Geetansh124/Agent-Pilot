"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, Globe, Code2, FileText, Cpu, Zap, Activity } from "lucide-react";

interface MotionThinkingBadgeProps {
  activeTool?: string | null;
  isThinking?: boolean;
}

function getToolMeta(toolName?: string | null) {
  const normalized = (toolName || "").toLowerCase();
  if (normalized.includes("web") || normalized.includes("search") || normalized.includes("scrape")) {
    return { label: "Web Intelligence", icon: Globe, color: "text-sky-400", border: "border-sky-500/30", bg: "bg-sky-500/10" };
  }
  if (normalized.includes("python") || normalized.includes("code") || normalized.includes("repl")) {
    return { label: "Python Execution", icon: Code2, color: "text-emerald-400", border: "border-emerald-500/30", bg: "bg-emerald-500/10" };
  }
  if (normalized.includes("vector") || normalized.includes("doc") || normalized.includes("chunk")) {
    return { label: "Document Vector Search", icon: FileText, color: "text-indigo-400", border: "border-indigo-500/30", bg: "bg-indigo-500/10" };
  }
  return { label: toolName || "Agent Telemetry", icon: Terminal, color: "text-indigo-300", border: "border-indigo-500/30", bg: "bg-indigo-500/10" };
}

export default function MotionThinkingBadge({ activeTool, isThinking = false }: MotionThinkingBadgeProps) {
  const meta = getToolMeta(activeTool);
  const Icon = meta.icon;

  const barColors = ["bg-indigo-400", "bg-sky-400", "bg-emerald-400", "bg-purple-400"];

  return (
    <AnimatePresence mode="wait">
      {/* Motion.dev: Fluid Spring Entrance Card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: -8 }}
        transition={{ type: "spring", stiffness: 400, damping: 25 }}
        className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-zinc-950/85 px-4 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.6)] backdrop-blur-2xl ring-1 ring-white/5"
      >
        {/* =========================================================================
            Motion.dev: Concentric Orbital Tracer Ring
            ========================================================================= */}
        <div className="relative flex h-7 w-7 items-center justify-center shrink-0">
          {/* Static track */}
          <div className="absolute inset-0 rounded-full border border-indigo-500/20" />

          {/* Rotating orbital carrier */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 1.8, ease: "linear" }}
            className="absolute inset-0 flex items-start justify-center"
          >
            <motion.span
              animate={{ scale: [0.85, 1.25, 0.85] }}
              transition={{ repeat: Infinity, duration: 1.2, ease: "easeInOut" }}
              className="h-1.5 w-1.5 -mt-0.5 rounded-full bg-indigo-400 shadow-[0_0_10px_#818cf8]"
            />
          </motion.div>

          {/* Center pulsating core dot */}
          <motion.span
            animate={{ opacity: [0.4, 1, 0.4], scale: [0.9, 1.1, 0.9] }}
            transition={{ repeat: Infinity, duration: 1.5, ease: "easeInOut" }}
            className="h-2 w-2 rounded-full bg-indigo-500/70"
          />
        </div>

        {/* =========================================================================
            Motion.dev: Telemetry & Tool Readout
            ========================================================================= */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs">
            <Cpu size={12} className="text-zinc-500 animate-pulse" />
            <span className="text-[11px] text-zinc-400 font-medium">Status:</span>
          </div>

          {activeTool ? (
            <motion.div
              key="tool-active"
              initial={{ opacity: 0, x: -8, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 8, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 450, damping: 25 }}
              className={`flex items-center gap-1.5 rounded-lg border ${meta.border} ${meta.bg} px-2.5 py-0.5 shadow-sm`}
            >
              <Icon size={12} className={meta.color} />
              <span className="font-mono text-[11px] font-semibold tracking-tight text-white">
                {meta.label}
              </span>
              <span className="text-[10px] font-mono text-zinc-400 bg-white/[0.06] px-1 py-0.2 rounded border border-white/[0.08]">
                {activeTool}
              </span>
            </motion.div>
          ) : (
            <motion.div
              key="thinking-active"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2"
            >
              <span className="shimmer-text text-xs font-semibold tracking-wide">
                {isThinking ? "Synthesizing contextual reasoning..." : "Active"}
              </span>
              <Zap size={11} className="text-indigo-400 animate-pulse" />
            </motion.div>
          )}
        </div>

        {/* =========================================================================
            Motion.dev: Staggered Equalizer Activity Bars
            ========================================================================= */}
        <div
          className="ml-auto hidden sm:flex items-center gap-1 text-[10px] font-mono text-zinc-500 border-l border-white/[0.08] pl-3"
          title="Motion.dev Telemetry Engine"
        >
          <div className="flex items-end gap-0.5 h-3.5 mr-1.5">
            {[0, 1, 2, 3].map((i) => (
              <motion.span
                key={i}
                animate={{ scaleY: [0.2, 1, 0.2] }}
                transition={{
                  repeat: Infinity,
                  duration: 0.75,
                  delay: i * 0.16,
                  ease: "easeInOut",
                }}
                className={`w-[2px] h-3.5 rounded-full origin-bottom ${barColors[i]}`}
              />
            ))}
          </div>
          <Activity size={10} className="text-emerald-400" />
          <span className="text-zinc-400 text-[10px]">Motion Engine</span>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

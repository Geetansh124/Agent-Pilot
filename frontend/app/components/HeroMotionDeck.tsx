"use client";

import React from "react";
import { motion } from "framer-motion";
import { Globe, Code2, BarChart3, FileText, LucideIcon } from "lucide-react";

interface QuickChip {
  label: string;
  icon: LucideIcon;
  iconClass: string;
  prompt: string;
}

const QUICK_CHIPS: QuickChip[] = [
  {
    label: "Deep Web Research",
    icon: Globe,
    iconClass: "text-sky-400",
    prompt: "Fetch and summarize the latest updates from https://news.ycombinator.com",
  },
  {
    label: "Python Sandbox",
    icon: Code2,
    iconClass: "text-emerald-400",
    prompt: "Run Python to calculate compound interest on $25,000 at 8% annual return over 15 years.",
  },
  {
    label: "Tabular Data Profiling",
    icon: BarChart3,
    iconClass: "text-amber-400",
    prompt: "Analyze this dataset structure: Month,Signups,Churn,Revenue\nJan,1200,45,24000\nFeb,1500,50,30000\nMar,1850,52,37000",
  },
  {
    label: "Document Vector Search",
    icon: FileText,
    iconClass: "text-indigo-400",
    prompt: "What are the primary conclusions, metrics, and risks highlighted in my uploaded document?",
  },
];

interface HeroMotionDeckProps {
  onSelectPrompt: (prompt: string) => void;
}

export default function HeroMotionDeck({ onSelectPrompt }: HeroMotionDeckProps) {
  return (
    <div className="my-auto flex flex-col items-center justify-center text-center py-12 select-none">
      {/* Motion.dev Spring Floating Logo with Aura Glow */}
      <motion.div
        initial={{ opacity: 0, scale: 0.85, y: -10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 350, damping: 20 }}
        className="relative mb-4 group cursor-pointer"
      >
        <div className="absolute -inset-1.5 rounded-2xl bg-gradient-to-r from-indigo-500/20 to-sky-500/20 blur-xl opacity-70 group-hover:opacity-100 transition duration-500" />
        <motion.div
          animate={{ y: [-3, 3, -3] }}
          transition={{ repeat: Infinity, duration: 4.2, ease: "easeInOut" }}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.95 }}
        >
          <img
            src="/logo.jpg"
            alt="Agent-Pilot Logo"
            className="relative h-16 w-16 rounded-2xl border border-white/10 shadow-2xl object-cover ring-1 ring-white/10"
          />
        </motion.div>
      </motion.div>

      {/* Motion.dev Heading */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.1 }}
        className="text-2xl sm:text-3xl font-semibold tracking-tight text-white"
      >
        Where will we explore today?
      </motion.h1>

      {/* Motion.dev Subtitle */}
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.18 }}
        className="mt-2 max-w-md text-xs sm:text-sm text-zinc-400 leading-relaxed"
      >
        Autonomous workspace for deep web research, code execution, and document intelligence.
      </motion.p>

      {/* Motion.dev Spring Interactive Prompt Chips */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.26 }}
        className="mt-8 flex flex-wrap items-center justify-center gap-2 max-w-xl"
      >
        {QUICK_CHIPS.map((chip, idx) => {
          const Icon = chip.icon;
          return (
            <motion.button
              key={idx}
              type="button"
              whileHover={{ scale: 1.05, y: -2 }}
              whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 450, damping: 22 }}
              onClick={() => onSelectPrompt(chip.prompt)}
              className="group flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-3.5 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/[0.08] hover:border-white/20 transition-all duration-150 active:scale-95 shadow-sm cursor-pointer"
            >
              <Icon size={13} className={chip.iconClass} />
              <span>{chip.label}</span>
            </motion.button>
          );
        })}
      </motion.div>
    </div>
  );
}

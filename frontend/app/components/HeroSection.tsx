"use client";

import React from "react";
import {
  Globe,
  Code2,
  BarChart3,
  FileText,
  Sparkles,
  ArrowUpRight,
} from "lucide-react";
import { AgentSkill } from "./types";
import { AGENT_SKILLS } from "./skillsData";

interface HeroSectionProps {
  onSelectPrompt: (prompt: string) => void;
  onOpenSkills: () => void;
}

export default function HeroSection({ onSelectPrompt, onOpenSkills }: HeroSectionProps) {
  const quickCards = [
    {
      title: "Web Deep Research",
      desc: "Scrape and synthesize live web pages and technical documentation.",
      prompt: "Fetch and summarize the latest developments from https://news.ycombinator.com",
      icon: <Globe size={20} className="text-cyan-400" />,
      tag: "Live Scraper",
      border: "hover:border-cyan-500/50",
    },
    {
      title: "Python Compute Sandbox",
      desc: "Execute safe sandboxed Python code to solve math, data, or algorithms.",
      prompt: "Run Python to calculate compound interest on $25,000 at 8% annual return over 15 years.",
      icon: <Code2 size={20} className="text-emerald-400" />,
      tag: "Code Runner",
      border: "hover:border-emerald-500/50",
    },
    {
      title: "Tabular & CSV Profiling",
      desc: "Analyze datasets, calculate column statistics, and inspect schema metrics.",
      prompt: "Analyze this dataset structure: Month,Signups,Churn,Revenue\nJan,1200,45,24000\nFeb,1500,50,30000\nMar,1850,52,37000",
      icon: <BarChart3 size={20} className="text-amber-400" />,
      tag: "Analytics",
      border: "hover:border-amber-500/50",
    },
    {
      title: "Document Vector RAG",
      desc: "Semantic Q&A, executive summaries, and extraction from uploaded files.",
      prompt: "What are the key technical takeaways, metrics, and risks highlighted in my uploaded document?",
      icon: <FileText size={20} className="text-purple-400" />,
      tag: "Vector Search",
      border: "hover:border-purple-500/50",
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col items-center justify-center pt-8 pb-12">
      {/* Central Brand Badge */}
      <div className="relative mb-6 flex flex-col items-center text-center">
        <div className="relative flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-cyan-500/20 via-blue-600/10 to-violet-600/20 border border-cyan-400/30 p-3 shadow-2xl shadow-cyan-500/20">
          <img
            src="/icon.svg"
            alt="Agent-Pilot"
            className="h-14 w-14 drop-shadow-[0_0_15px_rgba(0,242,254,0.4)]"
          />
          <div className="absolute -inset-1 -z-10 rounded-3xl bg-gradient-to-r from-cyan-500 to-blue-500 opacity-20 blur-xl" />
        </div>

        <h1 className="mt-5 text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
          Agent-
          <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent">
            Pilot
          </span>
        </h1>
        <p className="mt-2 max-w-lg text-sm text-slate-400 leading-relaxed">
          Your autonomous workspace for deep web research, sandboxed computation, and document intelligence.
        </p>

        {/* Explore all skills button */}
        <button
          onClick={onOpenSkills}
          className="mt-4 flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-4 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-400 transition"
        >
          <Sparkles size={13} />
          <span>Explore All {AGENT_SKILLS.length} Skills & Tools</span>
          <ArrowUpRight size={13} />
        </button>
      </div>

      {/* 4 Feature Action Cards */}
      <div className="grid w-full grid-cols-1 sm:grid-cols-2 gap-3.5 mt-4">
        {quickCards.map((card, idx) => (
          <div
            key={idx}
            onClick={() => onSelectPrompt(card.prompt)}
            className={`group flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-[#0c1017]/80 p-4.5 backdrop-blur-md cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-cyan-500/5 ${card.border}`}
          >
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <div className="p-2 rounded-xl bg-white/[0.04] border border-white/10 group-hover:scale-105 transition">
                  {card.icon}
                </div>
                <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-400 border border-white/5">
                  {card.tag}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-white group-hover:text-cyan-300 transition">
                {card.title}
              </h3>
              <p className="mt-1 text-xs text-slate-400 leading-relaxed">
                {card.desc}
              </p>
            </div>

            <div className="mt-4 flex items-center gap-1 text-[11px] font-medium text-cyan-400 opacity-0 group-hover:opacity-100 transition">
              <span>Execute prompt</span>
              <ArrowUpRight size={12} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

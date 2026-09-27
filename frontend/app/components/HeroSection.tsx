"use client";

import React from "react";
import {
  Globe,
  Code2,
  BarChart3,
  FileText,
  ArrowRight,
  Sparkles,
} from "lucide-react";

interface HeroSectionProps {
  onSelectPrompt: (prompt: string) => void;
  onOpenSkills: () => void;
}

export default function HeroSection({ onSelectPrompt, onOpenSkills }: HeroSectionProps) {
  const quickCards = [
    {
      title: "Web Research & Scraping",
      desc: "Extract clean text and summarize live documentation or articles.",
      prompt: "Fetch and summarize the latest updates from https://news.ycombinator.com",
      icon: <Globe size={16} />,
      tag: "Live Scraper",
    },
    {
      title: "Python Sandbox",
      desc: "Execute safe sandboxed Python code to calculate, model, or simulate.",
      prompt: "Run Python to calculate compound interest on $25,000 at 8% annual return over 15 years.",
      icon: <Code2 size={16} />,
      tag: "Code Runner",
    },
    {
      title: "Tabular Data Profiling",
      desc: "Parse structured CSV/JSON data, inspect schema, and calculate statistics.",
      prompt: "Analyze this dataset structure: Month,Signups,Churn,Revenue\nJan,1200,45,24000\nFeb,1500,50,30000\nMar,1850,52,37000",
      icon: <BarChart3 size={16} />,
      tag: "Data Analysis",
    },
    {
      title: "Document Vector Search",
      desc: "Semantic Q&A and key findings extraction from your uploaded files.",
      prompt: "What are the primary conclusions, metrics, and risks highlighted in my uploaded document?",
      icon: <FileText size={16} />,
      tag: "Vector RAG",
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center justify-center pt-8 pb-10">
      <div className="flex flex-col items-center text-center">
        <div className="relative mb-3">
          <img
            src="/icon.jpg"
            alt="Agent-Pilot Logo"
            className="h-20 w-20 rounded-2xl border border-zinc-800/80 shadow-2xl shadow-black/80 object-cover hover:scale-105 transition-transform duration-200"
          />
        </div>

        <h1 className="mt-2 text-2xl sm:text-3xl font-semibold tracking-tight text-zinc-100">
          Agent-Pilot
        </h1>
        <p className="mt-1.5 max-w-md text-xs sm:text-sm text-zinc-400 leading-relaxed">
          Autonomous workspace for deep web research, code execution, and document intelligence.
        </p>

        <button
          onClick={onOpenSkills}
          className="mt-3.5 inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:border-zinc-700 transition"
        >
          <Sparkles size={12} className="text-zinc-400" />
          <span>Explore 8 Agent Skills & Tools</span>
          <ArrowRight size={11} className="text-zinc-500" />
        </button>
      </div>

      {/* Action Cards (Neutral Zinc) */}
      <div className="mt-8 grid w-full grid-cols-1 sm:grid-cols-2 gap-2.5">
        {quickCards.map((card, idx) => (
          <div
            key={idx}
            onClick={() => onSelectPrompt(card.prompt)}
            className="group flex flex-col justify-between rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 transition-all duration-150 hover:bg-zinc-900/90 hover:border-zinc-700 cursor-pointer"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="p-1.5 rounded-md bg-zinc-800/60 text-zinc-400 group-hover:text-zinc-200 transition">
                  {card.icon}
                </div>
                <span className="text-[10px] font-mono text-zinc-500 px-1.5 py-0.5 rounded bg-zinc-800/40">
                  {card.tag}
                </span>
              </div>
              <h3 className="text-xs font-semibold text-zinc-200 group-hover:text-white transition">
                {card.title}
              </h3>
              <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
                {card.desc}
              </p>
            </div>

            <div className="mt-3 flex items-center gap-1 text-[11px] text-zinc-500 group-hover:text-zinc-300 font-medium transition">
              <span>Use prompt</span>
              <ArrowRight size={11} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

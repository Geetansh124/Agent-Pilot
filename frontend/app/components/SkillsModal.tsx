"use client";

import React, { useState, useMemo } from "react";
import {
  Search,
  X,
  Sparkles,
  Globe,
  Code2,
  BarChart3,
  FileSearch,
  Clock,
  Network,
  Cpu,
  TrendingUp,
  ArrowRight,
} from "lucide-react";
import { AgentSkill, AgentRole } from "./types";
import { AGENT_SKILLS } from "./skillsData";

interface SkillsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSkill: (skill: AgentSkill) => void;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  Globe: <Globe size={18} className="text-cyan-400" />,
  Code2: <Code2 size={18} className="text-emerald-400" />,
  BarChart3: <BarChart3 size={18} className="text-amber-400" />,
  FileSearch: <FileSearch size={18} className="text-blue-400" />,
  Clock: <Clock size={18} className="text-purple-400" />,
  Network: <Network size={18} className="text-violet-400" />,
  Cpu: <Cpu size={18} className="text-pink-400" />,
  TrendingUp: <TrendingUp size={18} className="text-teal-400" />,
};

export default function SkillsModal({ isOpen, onClose, onSelectSkill }: SkillsModalProps) {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const categories = [
    { id: "all", label: "All Skills" },
    { id: "research", label: "Web & Research" },
    { id: "code", label: "Code & Sandbox" },
    { id: "data", label: "Data Analytics" },
    { id: "analysis", label: "Document Intel" },
    { id: "automation", label: "Automation" },
  ];

  const filteredSkills = useMemo(() => {
    return AGENT_SKILLS.filter((skill) => {
      const matchesCategory = selectedCategory === "all" || skill.category === selectedCategory;
      const q = query.toLowerCase().trim();
      const matchesQuery =
        !q ||
        skill.name.toLowerCase().includes(q) ||
        skill.description.toLowerCase().includes(q) ||
        skill.badge?.toLowerCase().includes(q);
      return matchesCategory && matchesQuery;
    });
  }, [query, selectedCategory]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md transition-all">
      <div
        className="relative flex flex-col w-full max-w-2xl max-h-[85vh] rounded-3xl border border-white/10 bg-[#0c1017]/95 shadow-2xl shadow-cyan-500/10 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with Search Input */}
        <div className="shrink-0 p-5 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Sparkles size={16} className="text-cyan-400" />
              <span>Agent Skills & Tools Library</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                {AGENT_SKILLS.length} Capabilities
              </span>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            >
              <X size={18} />
            </button>
          </div>

          <div className="relative">
            <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search skills, tools, web scraping, python..."
              autoFocus
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-white/10 bg-white/5 text-sm text-white placeholder:text-slate-500 outline-none focus:border-cyan-400/60 focus:ring-1 focus:ring-cyan-400/30 transition"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-1.5 mt-3 overflow-x-auto pb-1 scrollbar-none">
            {categories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition ${
                  selectedCategory === cat.id
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Skills Grid */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {filteredSkills.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-sm">
              No skills found matching &ldquo;{query}&rdquo;.
            </div>
          ) : (
            filteredSkills.map((skill) => (
              <div
                key={skill.id}
                onClick={() => onSelectSkill(skill)}
                className="group flex items-start gap-4 p-4 rounded-2xl border border-white/[0.08] bg-white/[0.02] hover:bg-cyan-500/[0.06] hover:border-cyan-500/30 cursor-pointer transition-all"
              >
                <div className="p-2.5 rounded-xl bg-white/5 border border-white/10 group-hover:scale-105 group-hover:border-cyan-400/40 transition">
                  {ICON_MAP[skill.icon] || <Sparkles size={18} className="text-cyan-400" />}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-white group-hover:text-cyan-300 transition">
                      {skill.name}
                    </h4>
                    {skill.badge && (
                      <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-md bg-white/5 text-slate-300 border border-white/10">
                        {skill.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-400 leading-relaxed line-clamp-2">
                    {skill.description}
                  </p>
                  <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-cyan-400 font-medium opacity-0 group-hover:opacity-100 transition">
                    <span>Use this skill</span>
                    <ArrowRight size={12} />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 p-3.5 border-t border-white/10 bg-white/[0.01] flex items-center justify-between text-xs text-slate-500 px-5">
          <span>Click any skill to auto-fill the prompt and execute</span>
          <kbd className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] text-slate-400">
            ESC to close
          </kbd>
        </div>
      </div>
    </div>
  );
}

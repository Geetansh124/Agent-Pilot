"use client";

import React, { useState, useMemo } from "react";
import {
  Search,
  X,
  Globe,
  Code2,
  BarChart3,
  FileSearch,
  Clock,
  Network,
  Cpu,
  TrendingUp,
  ArrowRight,
  Layers,
} from "lucide-react";
import { AgentSkill } from "./types";
import { AGENT_SKILLS } from "./skillsData";

interface SkillsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSkill: (skill: AgentSkill) => void;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  Globe: <Globe size={16} className="text-zinc-400" />,
  Code2: <Code2 size={16} className="text-zinc-400" />,
  BarChart3: <BarChart3 size={16} className="text-zinc-400" />,
  FileSearch: <FileSearch size={16} className="text-zinc-400" />,
  Clock: <Clock size={16} className="text-zinc-400" />,
  Network: <Network size={16} className="text-zinc-400" />,
  Cpu: <Cpu size={16} className="text-zinc-400" />,
  TrendingUp: <TrendingUp size={16} className="text-zinc-400" />,
};

export default function SkillsModal({ isOpen, onClose, onSelectSkill }: SkillsModalProps) {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const categories = [
    { id: "all", label: "All" },
    { id: "research", label: "Research" },
    { id: "code", label: "Code" },
    { id: "data", label: "Data" },
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div
        className="relative flex flex-col w-full max-w-xl max-h-[80vh] rounded-xl border border-zinc-800 bg-[#121215] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Header (Raycast Style) */}
        <div className="shrink-0 p-3.5 border-b border-zinc-800">
          <div className="flex items-center justify-between mb-3 px-1">
            <div className="flex items-center gap-2 text-xs font-medium text-zinc-300">
              <Layers size={14} className="text-zinc-400" />
              <span>Agent Skills Library</span>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded text-zinc-400 hover:text-zinc-200 transition"
            >
              <X size={15} />
            </button>
          </div>

          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search skills, tools, web scraper, python..."
              autoFocus
              className="w-full pl-8 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-700"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-1 mt-2.5 overflow-x-auto pb-0.5">
            {categories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`text-xs px-2.5 py-1 rounded-md font-medium whitespace-nowrap transition ${
                  selectedCategory === cat.id
                    ? "bg-zinc-800 text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Skills List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {filteredSkills.length === 0 ? (
            <div className="py-8 text-center text-zinc-500 text-xs">
              No skills found for &ldquo;{query}&rdquo;.
            </div>
          ) : (
            filteredSkills.map((skill) => (
              <div
                key={skill.id}
                onClick={() => onSelectSkill(skill)}
                className="group flex items-start gap-3 p-3 rounded-lg border border-zinc-800 bg-zinc-900/30 hover:bg-zinc-800/60 hover:border-zinc-700/80 cursor-pointer transition"
              >
                <div className="p-2 rounded-md bg-zinc-800/80 text-zinc-300">
                  {ICON_MAP[skill.icon] || <Layers size={16} />}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-xs font-semibold text-zinc-200 group-hover:text-white">
                      {skill.name}
                    </h4>
                    {skill.badge && (
                      <span className="text-[10px] font-mono text-zinc-500 px-1.5 py-0.5 rounded bg-zinc-800/50">
                        {skill.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-400 leading-relaxed line-clamp-2">
                    {skill.description}
                  </p>
                </div>

                <div className="mt-1 text-zinc-500 opacity-0 group-hover:opacity-100 transition">
                  <ArrowRight size={13} />
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 p-2.5 border-t border-zinc-800 bg-zinc-950/40 flex items-center justify-between text-[11px] text-zinc-500 px-4">
          <span>Click to populate prompt</span>
          <kbd className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400 font-mono">
            ESC
          </kbd>
        </div>
      </div>
    </div>
  );
}

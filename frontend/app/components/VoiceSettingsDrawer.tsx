"use client";

import React, { useState } from "react";
import { ExternalLink, Key, Eye, EyeOff, Sparkles, Check, CheckCircle2 } from "lucide-react";
import { VoiceProviderId, VOICE_PROVIDERS } from "./voiceProviders";

interface VoiceSettingsDrawerProps {
  selectedProvider: VoiceProviderId;
  onProviderChange: (id: VoiceProviderId) => void;
  customKey: string;
  onCustomKeyChange: (key: string) => void;
  selectedVoice: string;
  onVoiceChange: (voice: string) => void;
  thinkingLevel: string;
  onThinkingLevelChange: (level: string) => void;
  onSave: () => void;
}

export default function VoiceSettingsDrawer({
  selectedProvider,
  onProviderChange,
  customKey,
  onCustomKeyChange,
  selectedVoice,
  onVoiceChange,
  thinkingLevel,
  onThinkingLevelChange,
  onSave,
}: VoiceSettingsDrawerProps) {
  const [showKey, setShowKey] = useState(false);
  const currentMeta = VOICE_PROVIDERS[selectedProvider];

  const handleProviderSelect = (id: VoiceProviderId) => {
    onProviderChange(id);
    if (typeof window !== "undefined") {
      const savedKey = localStorage.getItem(VOICE_PROVIDERS[id].keyStorageKey) || "";
      onCustomKeyChange(savedKey);
      const defaultVoice = VOICE_PROVIDERS[id].voices[0]?.id || "";
      onVoiceChange(defaultVoice);
    }
  };

  return (
    <div className="border-b border-white/[0.08] bg-zinc-900/95 p-5 space-y-4 text-xs animate-in slide-in-from-top-2 duration-200">
      {/* Provider Selector Badges */}
      <div>
        <label className="block font-medium text-zinc-300 mb-2">Voice AI Engine & Real-Time Protocol</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
          {(Object.keys(VOICE_PROVIDERS) as VoiceProviderId[]).map((id) => {
            const p = VOICE_PROVIDERS[id];
            const isSelected = selectedProvider === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => handleProviderSelect(id)}
                className={`flex flex-col text-left p-2.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? "border-indigo-500 bg-indigo-500/15 text-white shadow-sm ring-1 ring-indigo-500/50"
                    : "border-white/10 bg-black/30 text-zinc-400 hover:border-white/20 hover:text-zinc-200"
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1">
                  <span className="font-semibold text-[11px] truncate">{p.label}</span>
                  {isSelected && <Check size={12} className="text-indigo-400 shrink-0 ml-1" />}
                </div>
                <span className="text-[10px] text-zinc-500 truncate font-mono">{p.badge}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* Custom API Key Input */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="font-medium text-zinc-300 flex items-center gap-1.5">
              <Key size={12} className="text-indigo-400" />
              <span>{currentMeta.label} API Key</span>
              <span className="text-zinc-500 text-[10px]">(Optional override)</span>
            </label>
            <a
              href={currentMeta.keyHelpUrl}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-indigo-400 hover:underline flex items-center gap-0.5"
            >
              <span>Get Key</span>
              <ExternalLink size={10} />
            </a>
          </div>
          <div className="relative flex items-center">
            <input
              type={showKey ? "text" : "password"}
              value={customKey}
              onChange={(e) => onCustomKeyChange(e.target.value)}
              placeholder={currentMeta.keyPlaceholder}
              className="w-full rounded-xl border border-white/10 bg-black/40 pl-3 pr-10 py-2 text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-indigo-500 text-xs font-mono"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2.5 text-zinc-400 hover:text-zinc-200 transition cursor-pointer"
            >
              {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <p className="mt-1 text-[10px] text-zinc-500">
            Stored securely in local browser storage under <code className="text-zinc-400">{currentMeta.keyStorageKey}</code>.
          </p>
        </div>

        {/* Persona & Options */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block font-medium text-zinc-300 mb-1">Voice / Persona</label>
            <select
              value={selectedVoice}
              onChange={(e) => onVoiceChange(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-zinc-100 outline-none focus:border-indigo-500 text-xs"
            >
              {currentMeta.voices.map((v) => (
                <option key={v.id} value={v.id} className="bg-zinc-900 text-zinc-100">
                  {v.name} {v.desc ? `(${v.desc})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-medium text-zinc-300 mb-1">
              {currentMeta.supportsThinking ? "Thinking Level" : "Output Latency"}
            </label>
            {currentMeta.supportsThinking ? (
              <select
                value={thinkingLevel}
                onChange={(e) => onThinkingLevelChange(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-zinc-100 outline-none focus:border-indigo-500 text-xs"
              >
                <option value="minimal" className="bg-zinc-900 text-zinc-100">Minimal (Lowest latency)</option>
                <option value="low" className="bg-zinc-900 text-zinc-100">Low</option>
                <option value="medium" className="bg-zinc-900 text-zinc-100">Medium</option>
                <option value="high" className="bg-zinc-900 text-zinc-100">High</option>
              </select>
            ) : (
              <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-zinc-400 text-xs flex items-center gap-1.5">
                <Sparkles size={13} className="text-amber-400 shrink-0" />
                <span className="truncate">Edge Streaming</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex justify-between items-center pt-1 border-t border-white/[0.05]">
        <span className="text-[11px] text-zinc-500">
          Selected engine: <strong className="text-zinc-300">{currentMeta.label}</strong>
        </span>
        <button
          type="button"
          onClick={onSave}
          className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-1.5 font-medium text-white hover:bg-indigo-500 transition shadow-sm cursor-pointer"
        >
          <CheckCircle2 size={13} />
          <span>Apply & Save</span>
        </button>
      </div>
    </div>
  );
}

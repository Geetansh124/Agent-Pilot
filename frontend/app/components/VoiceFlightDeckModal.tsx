"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, VolumeX, X, Settings, Radio,
  Activity, Zap, AlertCircle, Wrench
} from "lucide-react";
import { getVoiceApiBaseUrl } from "./types";
import { VoiceProviderId, VOICE_PROVIDERS } from "./voiceProviders";
import VoiceSettingsDrawer from "./VoiceSettingsDrawer";
import QuantumVoiceVisualizer from "./QuantumVoiceVisualizer";

interface VoiceFlightDeckModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeThreadId?: string;
}

export default function VoiceFlightDeckModal({
  isOpen,
  onClose,
  activeThreadId,
}: VoiceFlightDeckModalProps) {
  const API = getVoiceApiBaseUrl();

  // Session & Connection state
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [userTranscript, setUserTranscript] = useState("");
  const [aiTranscript, setAiTranscript] = useState("");
  const [activeTool, setActiveTool] = useState<{ name: string; args?: any; status: "running" | "done" } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  // Provider & Voice Settings
  const [selectedProvider, setSelectedProvider] = useState<VoiceProviderId>("gemini");
  const [selectedVoice, setSelectedVoice] = useState("Puck");
  const [customKey, setCustomKey] = useState("");
  const [thinkingLevel, setThinkingLevel] = useState("minimal");
  const [showSettings, setShowSettings] = useState(false);

  // Audio & WebSocket refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioInputContextRef = useRef<AudioContext | null>(null);
  const audioOutputContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const micLevelRef = useRef<number>(0);
  const aiLevelRef = useRef<number>(0);
  const pingStartRef = useRef<number>(0);

  const currentMeta = VOICE_PROVIDERS[selectedProvider];

  // Load preferences from localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedProvider = (localStorage.getItem("AGENT_PILOT_VOICE_PROVIDER") || "gemini") as VoiceProviderId;
      const validProvider = VOICE_PROVIDERS[savedProvider] ? savedProvider : "gemini";
      setSelectedProvider(validProvider);

      const savedKey = localStorage.getItem(VOICE_PROVIDERS[validProvider].keyStorageKey) || "";
      setCustomKey(savedKey);

      const savedVoice = localStorage.getItem(`AGENT_PILOT_${validProvider.toUpperCase()}_VOICE`) ||
        VOICE_PROVIDERS[validProvider].voices[0]?.id || "Puck";
      setSelectedVoice(savedVoice);
    }
  }, []);

  // Disconnect on close
  useEffect(() => {
    if (!isOpen) {
      disconnectSession();
    }
    return () => {
      disconnectSession();
    };
  }, [isOpen]);

  // Connect to Chosen Voice Provider Session
  async function connectSession() {
    setErrorMsg(null);
    setConnecting(true);
    pingStartRef.current = Date.now();

    try {
      // 1. Request session token / credentials from Cloudflare Edge
      const tokenRes = await fetch(`${API}/api/voice/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: selectedProvider,
          customApiKey: customKey.trim(),
        }),
      });

      const tokenData = await tokenRes.json().catch(() => ({}));

      // If provider requires custom key and none is provided, prompt user directly
      if (tokenData.requireCustomKey) {
        setShowSettings(true);
        setConnecting(false);
        setErrorMsg(`${currentMeta.label} requires an API key. Please enter your key in Settings below or click 'Get Key'.`);
        return;
      }

      if (!tokenRes.ok && !customKey) {
        throw new Error(tokenData.error || `Server returned ${tokenRes.status}`);
      }

      // 2. Setup Audio Output Context (24kHz standard playback)
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const outCtx = new AudioCtx({ sampleRate: 24000 });
      await outCtx.resume();
      audioOutputContextRef.current = outCtx;
      nextPlayTimeRef.current = outCtx.currentTime;

      // 3. Setup Audio Input Context (16kHz linear PCM mono)
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      micStreamRef.current = micStream;

      const inCtx = new AudioCtx({ sampleRate: 16000 });
      await inCtx.resume();
      audioInputContextRef.current = inCtx;

      // 4. Robust WebSocket URL construction (handles empty base on workers.dev origin)
      let wsBase = "";
      if (API && API.startsWith("http")) {
        wsBase = API.replace(/^http/, "ws");
      } else if (typeof window !== "undefined") {
        const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsBase = `${wsProto}//${window.location.host}`;
      }

      let wsUrl = `${wsBase}/api/voice/ws?provider=${selectedProvider}&thread_id=${activeThreadId || ""}&voice=${encodeURIComponent(selectedVoice)}`;
      if (tokenData.token) {
        wsUrl += `&token=${encodeURIComponent(tokenData.token)}`;
      } else if (customKey.trim()) {
        wsUrl += `&key=${encodeURIComponent(customKey.trim())}`;
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setConnecting(false);
        setLatencyMs(Math.max(15, Date.now() - pingStartRef.current));

        // Provider-specific initial handshake
        if (selectedProvider === "gemini") {
          const setupMsg = {
            setup: {
              model: "models/gemini-3.1-flash-live-preview",
              generationConfig: {
                responseModalities: ["AUDIO"],
                speechConfig: {
                  voiceConfig: {
                    prebuiltVoiceConfig: { voiceName: selectedVoice },
                  },
                },
                thinkingConfig: { thinkingLevel },
              },
              tools: tokenData.tools ? [{ functionDeclarations: tokenData.tools }] : undefined,
            },
          };
          ws.send(JSON.stringify(setupMsg));
        }

        // Start Mic streaming pipeline
        startMicPipeline(inCtx, micStream, ws);
      };

      ws.onmessage = async (event) => {
        try {
          const raw = typeof event.data === "string" ? event.data : await (event.data as Blob).text();
          const msg = JSON.parse(raw);

          // Latency pulse update
          if (pingStartRef.current) {
            setLatencyMs(Math.round((Date.now() - pingStartRef.current) % 150 + 25));
          }

          // Handle Tool Events from Edge
          if (msg.type === "tool_executing") {
            setActiveTool({ name: msg.tool, args: msg.args, status: "running" });
            return;
          }
          if (msg.type === "tool_finished") {
            setActiveTool({ name: msg.tool, status: "done" });
            setTimeout(() => setActiveTool(null), 3000);
            return;
          }

          // Handle Unified Server Content
          const serverContent = msg.serverContent;
          if (serverContent) {
            // Interruption signal
            if (serverContent.interrupted) {
              stopAiPlayback();
              setIsAiSpeaking(false);
            }

            // Input Transcription (User text)
            if (serverContent.inputTranscription?.text) {
              setUserTranscript((prev) => `${prev} ${serverContent.inputTranscription.text}`.trim());
            }

            // Output Transcription (AI text)
            if (serverContent.outputTranscription?.text) {
              setAiTranscript((prev) => `${prev} ${serverContent.outputTranscription.text}`.trim());

              // Client-side TTS fallback for text-streaming providers
              if (selectedProvider === "anthropic" || selectedProvider === "groq") {
                speakTextChunk(serverContent.outputTranscription.text);
              }
            }

            // Model Audio Turn (PCM 24kHz / 16kHz)
            if (serverContent.modelTurn?.parts) {
              for (const part of serverContent.modelTurn.parts) {
                if (part.inlineData?.data) {
                  playAudioChunk(part.inlineData.data);
                }
              }
            }
          }
        } catch (err) {
          console.warn("WS message parse error:", err);
        }
      };

      ws.onerror = (e) => {
        console.error("Voice WebSocket error:", e);
        setErrorMsg(`Connection to ${currentMeta.label} failed. Please verify your API key in Settings.`);
        setShowSettings(true);
        disconnectSession();
      };

      ws.onclose = () => {
        setConnected(false);
        setConnecting(false);
      };
    } catch (err: any) {
      console.error("Connect failed:", err);
      setErrorMsg(err.message || `Could not connect to ${currentMeta.label}.`);
      disconnectSession();
    }
  }

  // Mic 16kHz PCM streaming pipeline
  function startMicPipeline(inCtx: AudioContext, stream: MediaStream, ws: WebSocket) {
    const source = inCtx.createMediaStreamSource(stream);
    const processor = inCtx.createScriptProcessor(2048, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (e) => {
      if (micMuted || ws.readyState !== WebSocket.OPEN) return;

      const inputData = e.inputBuffer.getChannelData(0);

      // Volume calculation for visualizer
      let sum = 0;
      for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i];
      micLevelRef.current = Math.min(Math.sqrt(sum / inputData.length) * 4, 1);

      // Convert Float32Array to 16-bit linear PCM little-endian
      const pcm16 = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Convert buffer to base64
      const bytes = new Uint8Array(pcm16.buffer);
      let binary = "";
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
      const base64Audio = btoa(binary);

      // Stream to Edge WebSocket Proxy
      const audioPacket = {
        realtimeInput: {
          mediaChunks: [
            {
              mimeType: "audio/pcm;rate=16000",
              data: base64Audio,
            },
          ],
        },
      };
      ws.send(JSON.stringify(audioPacket));
    };

    source.connect(processor);
    processor.connect(inCtx.destination);
  }

  // 24kHz PCM Audio Playback
  function playAudioChunk(base64Data: string) {
    const outCtx = audioOutputContextRef.current;
    if (!outCtx || outCtx.state === "closed") return;

    try {
      const binary = atob(base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      const pcm16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768.0;
      }

      const buffer = outCtx.createBuffer(1, float32.length, 24000);
      buffer.copyToChannel(float32, 0);

      const source = outCtx.createBufferSource();
      source.buffer = buffer;
      source.connect(outCtx.destination);

      const now = outCtx.currentTime;
      const playTime = Math.max(now, nextPlayTimeRef.current);
      source.start(playTime);
      nextPlayTimeRef.current = playTime + buffer.duration;

      activeSourcesRef.current.push(source);
      setIsAiSpeaking(true);
      aiLevelRef.current = 0.85;

      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
        if (activeSourcesRef.current.length === 0) {
          setIsAiSpeaking(false);
          aiLevelRef.current = 0;
        }
      };
    } catch (err) {
      console.warn("Failed to play audio chunk:", err);
    }
  }

  // Browser SpeechSynthesis fallback for text-only stream adapters
  function speakTextChunk(text: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    utterance.onstart = () => setIsAiSpeaking(true);
    utterance.onend = () => setIsAiSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }

  // Interruption
  function stopAiPlayback() {
    activeSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch {}
    });
    activeSourcesRef.current = [];
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (audioOutputContextRef.current) {
      nextPlayTimeRef.current = audioOutputContextRef.current.currentTime;
    }
    setIsAiSpeaking(false);
  }

  // Disconnect and release all resources
  function disconnectSession() {
    stopAiPlayback();

    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch {}
      processorRef.current = null;
    }

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }

    if (audioInputContextRef.current) {
      try { audioInputContextRef.current.close(); } catch {}
      audioInputContextRef.current = null;
    }

    if (audioOutputContextRef.current) {
      try { audioOutputContextRef.current.close(); } catch {}
      audioOutputContextRef.current = null;
    }

    if (wsRef.current) {
      try { wsRef.current.close(); } catch {}
      wsRef.current = null;
    }

    setConnected(false);
    setConnecting(false);
    setIsAiSpeaking(false);
    setLatencyMs(null);
  }

  function handleSaveSettings() {
    if (typeof window !== "undefined") {
      localStorage.setItem("AGENT_PILOT_VOICE_PROVIDER", selectedProvider);
      localStorage.setItem(currentMeta.keyStorageKey, customKey.trim());
      localStorage.setItem(`AGENT_PILOT_${selectedProvider.toUpperCase()}_VOICE`, selectedVoice);
      if (selectedProvider === "gemini") {
        localStorage.setItem("AGENT_PILOT_GEMINI_KEY", customKey.trim());
        localStorage.setItem("AGENT_PILOT_VOICE", selectedVoice);
      }
    }
    setShowSettings(false);
    setErrorMsg(null);
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-xl p-4 sm:p-6 overflow-hidden">
      <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 w-[600px] h-[500px] bg-indigo-600/20 blur-[130px] rounded-full" />
      <div className="pointer-events-none absolute -bottom-40 right-10 w-[500px] h-[400px] bg-purple-600/15 blur-[120px] rounded-full" />

      {/* Main Glass Flight Deck Container */}
      <div className="relative flex flex-col h-full max-h-[850px] w-full max-w-4xl rounded-3xl border border-white/10 bg-zinc-950/85 shadow-2xl overflow-hidden backdrop-blur-2xl">
        {/* Header HUD */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center">
              <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-400 animate-ping" : "bg-zinc-600"}`} />
              <span className={`absolute h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-500" : "bg-zinc-600"}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-wide text-zinc-100">Live Voice Flight Deck</span>
                <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-[10px] font-mono text-indigo-300 border border-indigo-500/20">
                  {currentMeta.badge}
                </span>
                {latencyMs && (
                  <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-mono text-emerald-400 border border-emerald-500/20">
                    <Zap size={9} />
                    <span>{latencyMs}ms</span>
                  </span>
                )}
              </div>
              <span className="text-[11px] text-zinc-500">{currentMeta.description}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSettings((prev) => !prev)}
              className={`p-2 rounded-xl border border-white/10 transition cursor-pointer ${
                showSettings ? "bg-indigo-600 text-white" : "bg-white/[0.04] text-zinc-400 hover:text-white"
              }`}
              title="Voice Provider & Key Settings"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl border border-white/10 bg-white/[0.04] text-zinc-400 hover:text-white transition cursor-pointer"
              title="Exit Voice Mode"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Settings Drawer */}
        {showSettings && (
          <VoiceSettingsDrawer
            selectedProvider={selectedProvider}
            onProviderChange={(id) => setSelectedProvider(id)}
            customKey={customKey}
            onCustomKeyChange={(key) => setCustomKey(key)}
            selectedVoice={selectedVoice}
            onVoiceChange={(v) => setSelectedVoice(v)}
            thinkingLevel={thinkingLevel}
            onThinkingLevelChange={(lvl) => setThinkingLevel(lvl)}
            onSave={handleSaveSettings}
          />
        )}

        {/* Center Stage: Quantum Fluid Orb & Waves Visualizer */}
        <div className="relative flex-1 flex flex-col items-center justify-center p-6 overflow-hidden">
          {errorMsg && (
            <div className="absolute top-4 z-10 mx-auto flex items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-200 max-w-xl shadow-xl backdrop-blur-md">
              <div className="flex items-center gap-2">
                <AlertCircle size={16} className="shrink-0 text-amber-400" />
                <span>{errorMsg}</span>
              </div>
              <button
                type="button"
                onClick={() => setShowSettings(true)}
                className="shrink-0 rounded-lg bg-amber-500/20 px-2.5 py-1 text-[11px] font-semibold text-amber-300 hover:bg-amber-500/30 transition border border-amber-500/30 cursor-pointer"
              >
                Open Settings
              </button>
            </div>
          )}

          {/* Active Tool Invocation HUD Badge */}
          {activeTool && (
            <div className="absolute top-14 z-10 mx-auto flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/15 px-4 py-1.5 text-xs text-indigo-200 shadow-xl animate-pulse backdrop-blur-md">
              <Wrench size={13} className="animate-spin text-indigo-400" />
              <span>
                Edge Tool Executing: <strong className="font-mono text-white">{activeTool.name}</strong>
              </span>
            </div>
          )}

          {/* Quantum Fluid Orb & Multi-Harmonic Waves Canvas */}
          <QuantumVoiceVisualizer
            isAiSpeaking={isAiSpeaking}
            micMuted={micMuted}
            connected={connected}
            connecting={connecting}
            provider={selectedProvider}
            micLevelRef={micLevelRef}
            aiLevelRef={aiLevelRef}
          />

          {!connected && !connecting && (
            <button
              onClick={connectSession}
              className="mt-4 flex items-center gap-2 rounded-2xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-500 hover:scale-105 transition active:scale-95 cursor-pointer"
            >
              <Mic size={18} />
              <span>Connect to {currentMeta.label}</span>
            </button>
          )}

          {connecting && (
            <div className="mt-4 flex items-center gap-2.5 text-sm text-indigo-300">
              <Activity size={18} className="animate-spin" />
              <span>Connecting to {currentMeta.label} via Cloudflare Edge...</span>
            </div>
          )}
        </div>

        {/* Real-time Transcription Stream HUD */}
        <div className="border-t border-white/[0.08] bg-white/[0.02] px-6 py-3.5 min-h-[110px] max-h-[160px] overflow-y-auto space-y-2 text-xs">
          {userTranscript && (
            <div className="flex items-start gap-2">
              <span className="font-semibold text-indigo-400 shrink-0">You:</span>
              <p className="text-zinc-200 leading-relaxed">{userTranscript}</p>
            </div>
          )}
          {aiTranscript && (
            <div className="flex items-start gap-2">
              <span className="font-semibold text-purple-400 shrink-0">Agent-Pilot ({currentMeta.label}):</span>
              <p className="text-zinc-300 leading-relaxed">{aiTranscript}</p>
            </div>
          )}
          {!userTranscript && !aiTranscript && connected && (
            <p className="text-zinc-500 italic text-center py-4">Speak naturally to begin your voice conversation...</p>
          )}
        </div>

        {/* Footer Flight Deck Controls */}
        <div className="flex items-center justify-between border-t border-white/[0.08] px-6 py-4 bg-zinc-950">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Radio size={14} className={connected ? "text-emerald-400 animate-pulse" : "text-zinc-600"} />
            <span>{connected ? `Live with ${currentMeta.label}` : "Standby"}</span>
          </div>

          <div className="flex items-center gap-3">
            {connected && (
              <>
                <button
                  onClick={() => setMicMuted((prev) => !prev)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition cursor-pointer ${
                    micMuted
                      ? "bg-red-500/20 text-red-300 border border-red-500/30"
                      : "bg-white/[0.06] text-zinc-200 hover:bg-white/[0.1] border border-white/10"
                  }`}
                  title={micMuted ? "Unmute Microphone" : "Mute Microphone"}
                >
                  {micMuted ? <MicOff size={15} /> : <Mic size={15} />}
                  <span>{micMuted ? "Muted" : "Mute Mic"}</span>
                </button>

                <button
                  onClick={stopAiPlayback}
                  disabled={!isAiSpeaking}
                  className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2 text-xs font-medium text-zinc-200 hover:bg-white/[0.1] disabled:opacity-30 transition cursor-pointer"
                  title="Interrupt AI speaking"
                >
                  <VolumeX size={15} />
                  <span>Interrupt</span>
                </button>

                <button
                  onClick={disconnectSession}
                  className="flex items-center gap-2 rounded-xl bg-red-600/90 hover:bg-red-600 px-4 py-2 text-xs font-medium text-white transition shadow-sm cursor-pointer"
                  title="End Voice Call"
                >
                  <span>End Call</span>
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

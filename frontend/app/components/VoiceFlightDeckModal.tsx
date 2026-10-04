"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Volume2, VolumeX, X, Settings, Radio,
  Cpu, Activity, Zap, Sparkles, CheckCircle2, AlertCircle, Wrench
} from "lucide-react";
import { getApiBaseUrl } from "./types";

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
  const API = getApiBaseUrl();

  // Session & Connection state
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [userTranscript, setUserTranscript] = useState("");
  const [aiTranscript, setAiTranscript] = useState("");
  const [activeTool, setActiveTool] = useState<{ name: string; args?: any; status: "running" | "done" } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Settings
  const [showSettings, setShowSettings] = useState(false);
  const [customKey, setCustomKey] = useState("");
  const [selectedVoice, setSelectedVoice] = useState("Puck");
  const [thinkingLevel, setThinkingLevel] = useState("minimal");

  // Audio & WebSocket refs
  const wsRef = useRef<WebSocket | null>(null);
  const audioInputContextRef = useRef<AudioContext | null>(null);
  const audioOutputContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const micLevelRef = useRef<number>(0);
  const aiLevelRef = useRef<number>(0);

  // Load custom key and voice preference
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedKey = localStorage.getItem("AGENT_PILOT_GEMINI_KEY") || "";
      const savedVoice = localStorage.getItem("AGENT_PILOT_VOICE") || "Puck";
      setCustomKey(savedKey);
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

  // Audio Visualizer loop
  useEffect(() => {
    if (!isOpen) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let phase = 0;

    const render = () => {
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      const targetAmp = isAiSpeaking
        ? Math.max(aiLevelRef.current, 0.45)
        : micMuted
        ? 0.05
        : Math.max(micLevelRef.current, 0.15);

      // Draw multi-layered glowing sine waves
      const waves = [
        { color: "rgba(99, 102, 241, 0.6)", freq: 0.015, speed: 0.04, amp: targetAmp * 60 },
        { color: "rgba(168, 85, 247, 0.5)", freq: 0.02, speed: 0.03, amp: targetAmp * 45 },
        { color: "rgba(56, 189, 248, 0.7)", freq: 0.025, speed: 0.06, amp: targetAmp * 30 },
      ];

      waves.forEach((w) => {
        ctx.beginPath();
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = w.color;
        for (let x = 0; x < width; x += 3) {
          const y = height / 2 + Math.sin(x * w.freq + phase * w.speed) * w.amp;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      });

      // Core pulse center circle
      const radius = 35 + targetAmp * 25;
      const grad = ctx.createRadialGradient(width / 2, height / 2, 5, width / 2, height / 2, radius);
      grad.addColorStop(0, isAiSpeaking ? "rgba(168, 85, 247, 0.8)" : "rgba(99, 102, 241, 0.7)");
      grad.addColorStop(1, "rgba(99, 102, 241, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 2);
      ctx.fill();

      phase += 1;
      animFrameRef.current = requestAnimationFrame(render);
    };

    render();
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isOpen, isAiSpeaking, micMuted]);

  // Connect to Gemini Live Session
  async function connectSession() {
    setErrorMsg(null);
    setConnecting(true);

    try {
      // 1. Request session token from Cloudflare Edge
      const tokenRes = await fetch(`${API}/api/voice/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customApiKey: customKey }),
      });

      const tokenData = await tokenRes.json().catch(() => ({}));

      if (tokenData.requireCustomKey) {
        setShowSettings(true);
        setConnecting(false);
        setErrorMsg("Gemini API key is required. Enter your key in Settings below to begin.");
        return;
      }

      if (!tokenRes.ok && !customKey) {
        throw new Error(tokenData.error || `Server returned ${tokenRes.status}`);
      }

      // 2. Setup Audio Output Context (24kHz for Gemini Live)
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

      // 4. Connect via Edge WebSocket Proxy
      const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = API.replace(/^https?:\/\//, "");
      let wsUrl = `${wsProto}//${host}/api/voice/ws?thread_id=${activeThreadId || ""}`;
      if (tokenData.token) {
        wsUrl += `&token=${encodeURIComponent(tokenData.token)}`;
      } else if (customKey) {
        wsUrl += `&key=${encodeURIComponent(customKey)}`;
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setConnecting(false);

        // Send Gemini Live Initial Setup message
        const setupMsg = {
          setup: {
            model: "models/gemini-3.1-flash-live-preview",
            generationConfig: {
              responseModalities: ["AUDIO"],
              speechConfig: {
                voiceConfig: {
                  prebuiltVoiceConfig: {
                    voiceName: selectedVoice,
                  },
                },
              },
              thinkingConfig: {
                thinkingLevel: thinkingLevel,
              },
            },
            tools: tokenData.tools ? [{ functionDeclarations: tokenData.tools }] : undefined,
          },
        };
        ws.send(JSON.stringify(setupMsg));

        // Start Mic streaming pipeline
        startMicPipeline(inCtx, micStream, ws);
      };

      ws.onmessage = async (event) => {
        try {
          const raw = typeof event.data === "string" ? event.data : await (event.data as Blob).text();
          const msg = JSON.parse(raw);

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

          // Handle Gemini Live Server Content
          const serverContent = msg.serverContent;
          if (serverContent) {
            // Interruption signal: AI was interrupted by user
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
            }

            // Model Audio Turn
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
        setErrorMsg("WebSocket connection error. Check credentials or connection.");
        disconnectSession();
      };

      ws.onclose = () => {
        setConnected(false);
        setConnecting(false);
      };
    } catch (err: any) {
      console.error("Connect failed:", err);
      setErrorMsg(err.message || "Could not access microphone or connect.");
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

      // Compute volume for visualizer
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

      // Stream to Gemini Live
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
      aiLevelRef.current = 0.8;

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

  // Immediate interruption
  function stopAiPlayback() {
    activeSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch {}
    });
    activeSourcesRef.current = [];
    if (audioOutputContextRef.current) {
      nextPlayTimeRef.current = audioOutputContextRef.current.currentTime;
    }
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
  }

  function saveSettings() {
    if (typeof window !== "undefined") {
      localStorage.setItem("AGENT_PILOT_GEMINI_KEY", customKey.trim());
      localStorage.setItem("AGENT_PILOT_VOICE", selectedVoice);
    }
    setShowSettings(false);
    setErrorMsg(null);
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-xl p-4 sm:p-6 overflow-hidden">
      {/* Background glow effects */}
      <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 w-[600px] h-[500px] bg-indigo-600/20 blur-[130px] rounded-full" />
      <div className="pointer-events-none absolute -bottom-40 right-10 w-[500px] h-[400px] bg-purple-600/15 blur-[120px] rounded-full" />

      {/* Main Glass Flight Deck Container */}
      <div className="relative flex flex-col h-full max-h-[850px] w-full max-w-4xl rounded-3xl border border-white/10 bg-zinc-950/80 shadow-2xl overflow-hidden">
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
                  gemini-3.1-flash-live-preview
                </span>
              </div>
              <span className="text-[11px] text-zinc-500">Bidirectional 16kHz/24kHz PCM Audio · Cloudflare Edge Tools</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSettings((prev) => !prev)}
              className={`p-2 rounded-xl border border-white/10 transition cursor-pointer ${
                showSettings ? "bg-indigo-600 text-white" : "bg-white/[0.04] text-zinc-400 hover:text-white"
              }`}
              title="Voice Settings"
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
          <div className="border-b border-white/[0.08] bg-zinc-900/90 p-5 space-y-4 text-xs animate-in slide-in-from-top-2 duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block font-medium text-zinc-300 mb-1">
                  Custom Gemini API Key <span className="text-zinc-500">(Optional override)</span>
                </label>
                <input
                  type="password"
                  value={customKey}
                  onChange={(e) => setCustomKey(e.target.value)}
                  placeholder="AIzaSy..."
                  className="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-indigo-500"
                />
                <p className="mt-1 text-[11px] text-zinc-500">
                  Stored securely in your browser. Get one at{" "}
                  <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">
                    Google AI Studio
                  </a>.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-medium text-zinc-300 mb-1">Voice Persona</label>
                  <select
                    value={selectedVoice}
                    onChange={(e) => setSelectedVoice(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-zinc-100 outline-none focus:border-indigo-500"
                  >
                    <option value="Puck">Puck (Natural)</option>
                    <option value="Charon">Charon (Deep)</option>
                    <option value="Kore">Kore (Smooth)</option>
                    <option value="Fenrir">Fenrir (Authoritative)</option>
                    <option value="Aoede">Aoede (Warm)</option>
                  </select>
                </div>
                <div>
                  <label className="block font-medium text-zinc-300 mb-1">Thinking Level</label>
                  <select
                    value={thinkingLevel}
                    onChange={(e) => setThinkingLevel(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-zinc-100 outline-none focus:border-indigo-500"
                  >
                    <option value="minimal">Minimal (Lowest latency)</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={saveSettings}
                className="rounded-xl bg-indigo-600 px-4 py-1.5 font-medium text-white hover:bg-indigo-500 transition shadow-sm cursor-pointer"
              >
                Apply & Save
              </button>
            </div>
          </div>
        )}

        {/* Center Stage: Audio Wave Visualizer */}
        <div className="relative flex-1 flex flex-col items-center justify-center p-6 overflow-hidden">
          {errorMsg && (
            <div className="absolute top-4 mx-auto flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-300 max-w-lg shadow-lg">
              <AlertCircle size={15} className="shrink-0 text-red-400" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Active Tool Invocation HUD Badge */}
          {activeTool && (
            <div className="absolute top-14 mx-auto flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/15 px-4 py-1.5 text-xs text-indigo-200 shadow-xl animate-pulse">
              <Wrench size={13} className="animate-spin text-indigo-400" />
              <span>
                Edge Tool Executing: <strong className="font-mono text-white">{activeTool.name}</strong>
              </span>
            </div>
          )}

          <canvas ref={canvasRef} width={700} height={260} className="w-full max-w-[650px] h-[240px]" />

          {/* Center Call to Action or Status */}
          {!connected && !connecting && (
            <button
              onClick={connectSession}
              className="mt-6 flex items-center gap-2 rounded-2xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-500 hover:scale-105 transition active:scale-95 cursor-pointer"
            >
              <Mic size={18} />
              <span>Launch Live Voice Flight Deck</span>
            </button>
          )}

          {connecting && (
            <div className="mt-6 flex items-center gap-2.5 text-sm text-indigo-300">
              <Activity size={18} className="animate-spin" />
              <span>Connecting to Gemini Live Edge WebSocket...</span>
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
              <span className="font-semibold text-purple-400 shrink-0">Agent-Pilot:</span>
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
            <span>{connected ? "Live Stream Active" : "Standby"}</span>
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

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

function formatVoiceTranscript(raw: string): string {
  if (!raw) return "";
  return raw
    .replace(/^#+\s*/gm, "") // remove heading hash tags like ###
    .replace(/\*\*([^*]+)\*\*/g, "$1") // remove bold asterisks
    .replace(/\*([^*]+)\*/g, "$1") // remove italic asterisks
    .replace(/^[\*\-]\s+/gm, "") // remove bullet asterisks/dashes
    .replace(/`([^`]+)`/g, "$1") // remove inline code backticks
    .replace(/\n{2,}/g, "\n")
    .trim();
}

function cleanUserSpeech(raw: string): string {
  if (!raw) return "";
  let clean = raw.trim();
  // Auto-correct common speech-to-text phonetic typos
  clean = clean.replace(/\bproperny\b/gi, "properly");
  clean = clean.replace(/\bteh\b/gi, "the");
  clean = clean.replace(/\brecieve\b/gi, "receive");
  clean = clean.replace(/\bseperate\b/gi, "separate");
  clean = clean.replace(/\buntill\b/gi, "until");
  // Capitalize sentence start
  if (clean.length > 0) {
    clean = clean.charAt(0).toUpperCase() + clean.slice(1);
  }
  return clean;
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

  // Web Speech API & Streaming refs
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const isWebSpeechSpeakingRef = useRef<boolean>(false);
  const streamAbortControllerRef = useRef<AbortController | null>(null);
  const currentAiSentenceRef = useRef<string>("");
  const currentQueryRef = useRef<string>("");

  const currentMeta = VOICE_PROVIDERS[selectedProvider];

  // Instant barge-in interruption & reset to listening state
  function interruptAndListen(reason = "barge_in") {
    // 1. Abort any active streaming HTTP request immediately
    if (streamAbortControllerRef.current) {
      try { streamAbortControllerRef.current.abort(); } catch {}
      streamAbortControllerRef.current = null;
    }

    // 2. Cancel browser speech synthesis immediately
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try { window.speechSynthesis.cancel(); } catch {}
    }

    // 3. Stop all scheduled Web Audio sources immediately
    activeSourcesRef.current.forEach((s) => {
      try { s.stop(); } catch {}
    });
    activeSourcesRef.current = [];
    if (audioOutputContextRef.current) {
      nextPlayTimeRef.current = audioOutputContextRef.current.currentTime;
    }

    // 4. Send interrupt message to WebSocket if connected so upstream stops streaming (only when client-initiated)
    if (reason !== "server_interrupted" && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "interrupt", reason }));
      } catch {}
    }

    // 5. Reset states so assistant immediately listens
    setIsAiSpeaking(false);
    aiLevelRef.current = 0;
    isWebSpeechSpeakingRef.current = false;
    currentAiSentenceRef.current = "";

    // 6. Ensure speech recognition is active and listening
    if (!micMuted && selectedProvider === "web_speech" && recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch {}
    }
  }

  // Load preferences from localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedProvider = (localStorage.getItem("AGENT_PILOT_VOICE_PROVIDER") || "web_speech") as VoiceProviderId;
      const validProvider = VOICE_PROVIDERS[savedProvider] ? savedProvider : "web_speech";
      setSelectedProvider(validProvider);

      const savedKey = localStorage.getItem(VOICE_PROVIDERS[validProvider].keyStorageKey) || "";
      setCustomKey(savedKey);

      const savedVoice = localStorage.getItem(`AGENT_PILOT_${validProvider.toUpperCase()}_VOICE`) ||
        VOICE_PROVIDERS[validProvider].voices[0]?.id || "default";
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

  // Execute a conversational turn using Free Web Speech API + backend Chat API
  async function executeWebSpeechTurn(queryText: string) {
    const trimmed = queryText.trim();
    if (!trimmed) return;

    // Fast-path stop voice command check:
    const isStopCommand = /^(stop|please stop|stop it|shut up|be quiet|quiet|pause|hold on|wait|listen|stop talking)[.!]?$/i.test(trimmed);
    if (isStopCommand) {
      interruptAndListen("stop_command");
      setUserTranscript(trimmed);
      setAiTranscript("Stopped. I'm listening...");
      currentQueryRef.current = "";
      return;
    }

    currentQueryRef.current = trimmed.toLowerCase();

    // If already speaking, halt previous response before starting new turn
    interruptAndListen("new_turn");

    isWebSpeechSpeakingRef.current = true;
    setIsAiSpeaking(true);
    setAiTranscript("Thinking...");
    aiLevelRef.current = 0.5;

    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    try {
      const token = typeof window !== "undefined"
        ? (localStorage.getItem("agent_pilot_token") || localStorage.getItem("docupilot_token"))
        : null;

      let pendingUtterances = 0;
      let streamFinished = false;

      const finishSpeaking = () => {
        if (abortController.signal.aborted) return;
        setIsAiSpeaking(false);
        aiLevelRef.current = 0;
        isWebSpeechSpeakingRef.current = false;
        currentAiSentenceRef.current = "";
        currentQueryRef.current = "";
        setUserTranscript("");
      };

      const speakSentence = (sentenceText: string) => {
        if (abortController.signal.aborted) return;
        const clean = sentenceText.replace(/[*#`_\[\]()]/g, " ").replace(/\s+/g, " ").trim();
        if (!clean || !/[a-zA-Z0-9]/.test(clean)) return;

        if (typeof window !== "undefined" && "speechSynthesis" in window) {
          pendingUtterances++;
          currentAiSentenceRef.current = clean;
          const utter = new SpeechSynthesisUtterance(clean);
          utter.rate = 1.05;
          utter.pitch = 1.0;
          utter.onstart = () => {
            if (abortController.signal.aborted) {
              window.speechSynthesis.cancel();
              return;
            }
            setIsAiSpeaking(true);
            aiLevelRef.current = 0.7;
          };
          utter.onend = () => {
            currentAiSentenceRef.current = "";
            pendingUtterances = Math.max(0, pendingUtterances - 1);
            if (streamFinished && pendingUtterances === 0) {
              finishSpeaking();
            }
          };
          utter.onerror = () => {
            currentAiSentenceRef.current = "";
            pendingUtterances = Math.max(0, pendingUtterances - 1);
            if (streamFinished && pendingUtterances === 0) {
              finishSpeaking();
            }
          };
          window.speechSynthesis.speak(utter);
        }
      };

      // Connect to real-time streaming endpoint
      const res = await fetch(`${API}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: trimmed,
          thread_id: activeThreadId || undefined,
          mode: "voice",
        }),
        signal: abortController.signal,
      });

      if (!res.ok) {
        throw new Error(`Chat API error (${res.status})`);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error("No readable stream response");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let fullTranscript = "";
      let spokenOffset = 0;

      while (!abortController.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (abortController.signal.aborted) break;
          const lineTrimmed = line.trim();
          if (!lineTrimmed.startsWith("data:")) continue;
          const dataStr = lineTrimmed.slice(5).trim();
          if (dataStr === "[DONE]") continue;

          try {
            const parsed = JSON.parse(dataStr);
            if (parsed.type === "token" && parsed.content) {
              fullTranscript += parsed.content;
              setAiTranscript(fullTranscript);

              // Check if a complete sentence or clause has formed
              const unspoken = fullTranscript.slice(spokenOffset);
              const sentenceMatch = unspoken.match(/^([\s\S]*?[.!?\n])(?:\s+|$)/);
              if (sentenceMatch && sentenceMatch[1].trim().length > 2) {
                const sentence = sentenceMatch[1].trim();
                spokenOffset += sentenceMatch[0].length;
                speakSentence(sentence);
              }
            } else if (parsed.type === "done") {
              break;
            }
          } catch {
            // Non-JSON SSE line
          }
        }
      }

      if (abortController.signal.aborted) return;

      // Speak any remaining unspoken tail
      const leftover = fullTranscript.slice(spokenOffset).trim();
      if (leftover) {
        speakSentence(leftover);
      }

      streamFinished = true;
      if (pendingUtterances === 0) {
        finishSpeaking();
      }
    } catch (err: any) {
      if (err.name === "AbortError" || abortController.signal.aborted) {
        return; // Interrupted intentionally
      }
      setAiTranscript(`Could not generate response: ${err.message}`);
      setIsAiSpeaking(false);
      aiLevelRef.current = 0;
      isWebSpeechSpeakingRef.current = false;
      currentQueryRef.current = "";
      if (!micMuted && recognitionRef.current) {
        try { recognitionRef.current.start(); } catch {}
      }
    }
  }

  // Connect to Chosen Voice Provider Session
  async function connectSession(overrideProvider?: VoiceProviderId, overrideKey?: string) {
    const providerToUse = overrideProvider || selectedProvider;
    const keyToUse = overrideKey !== undefined ? overrideKey : customKey;
    setSelectedProvider(providerToUse);
    if (overrideKey !== undefined) setCustomKey(overrideKey);
    setErrorMsg(null);
    setConnecting(true);
    pingStartRef.current = Date.now();

    try {
      // Free Native Browser Voice mode via Web Speech API
      if (providerToUse === "web_speech") {
        const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRec) {
          throw new Error("Speech recognition is not supported in this browser. Please use Google Chrome, Microsoft Edge, or Safari.");
        }

        const rec = new SpeechRec();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = (typeof navigator !== "undefined" && navigator.language) ? navigator.language : "en-US";
        rec.maxAlternatives = 3;
        recognitionRef.current = rec;

        rec.onstart = () => {
          setConnected(true);
          setConnecting(false);
          setLatencyMs(18);
        };

        rec.onresult = (e: any) => {
          let fullTranscript = "";
          let hasFinal = false;

          for (let i = 0; i < e.results.length; i++) {
            const item = e.results[i];
            if (item && item[0]) {
              fullTranscript += item[0].transcript + " ";
              if (item.isFinal) hasFinal = true;
            }
          }

          const cleaned = cleanUserSpeech(fullTranscript);
          if (!cleaned) return;

          // Check if AI is currently playing audio through speaker
          const isActivelyPlayingAudio = (typeof window !== "undefined" && window.speechSynthesis?.speaking) || activeSourcesRef.current.length > 0;
          const normalizeForCompare = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
          const normCleaned = normalizeForCompare(cleaned);
          const normCurrentQuery = normalizeForCompare(currentQueryRef.current || "");
          const isSameQuery = Boolean(normCurrentQuery && (
            normCleaned === normCurrentQuery ||
            normCurrentQuery.startsWith(normCleaned) ||
            normCleaned.startsWith(normCurrentQuery)
          ));

          // Only barge-in if the assistant is ACTUALLY outputting audio, and this is NOT the same query we just submitted
          if (isActivelyPlayingAudio && !isSameQuery) {
            // Compare against current sentence to avoid self-echo from laptop speakers
            const currentSentence = normalizeForCompare(currentAiSentenceRef.current || "");
            const isEcho = Boolean(currentSentence && currentSentence.includes(normCleaned) && normCleaned.length < currentSentence.length * 0.8);

            if (!isEcho) {
              // User spoke while AI was speaking: stop immediately and listen!
              interruptAndListen("user_spoke");
              setAiTranscript("Listening to you...");
              currentQueryRef.current = "";
            } else {
              return; // Ignore speaker echo
            }
          }

          setUserTranscript(cleaned);

          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          // Intelligent natural pause detection: 900ms after final phrase, 1900ms on interim thought
          const debounceMs = hasFinal ? 900 : 1900;
          silenceTimerRef.current = setTimeout(() => {
            if (cleaned && normalizeForCompare(cleaned) !== normalizeForCompare(currentQueryRef.current || "")) {
              void executeWebSpeechTurn(cleaned);
            }
          }, debounceMs);
        };

        rec.onerror = (e: any) => {
          console.warn("Speech recognition error:", e.error);
          if (e.error === "not-allowed" || e.error === "service-not-allowed") {
            setErrorMsg("Microphone permission was denied. Please allow microphone access in your browser address bar.");
            disconnectSession();
          } else if (e.error === "network") {
            setErrorMsg("Speech recognition network error. Please verify your connection.");
            disconnectSession();
          }
        };

        rec.onend = () => {
          // Keep recognition alive whenever mic is not muted, so user can speak anytime to interrupt
          if (!micMuted && recognitionRef.current) {
            try { rec.start(); } catch {}
          }
        };

        // Start listening
        try {
          rec.start();
        } catch (startErr: any) {
          console.warn("rec.start error:", startErr);
        }
        setConnected(true);
        setConnecting(false);
        setLatencyMs(18);

        // Initial audio greeting so user immediately hears voice working
        if (typeof window !== "undefined" && "speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const greeting = new SpeechSynthesisUtterance("Hello! I am listening. How can I help you today?");
          greeting.rate = 1.05;
          greeting.pitch = 1.0;
          setIsAiSpeaking(true);
          currentAiSentenceRef.current = "Hello! I am listening. How can I help you today?";
          setAiTranscript("Hello! I am listening. How can I help you today?");
          greeting.onend = () => {
            currentAiSentenceRef.current = "";
            setIsAiSpeaking(false);
          };
          window.speechSynthesis.speak(greeting);
        }

        // Non-blocking mic visualizer & Acoustic VAD setup in background
        void (async () => {
          try {
            if (navigator?.mediaDevices?.getUserMedia) {
              const micStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                  echoCancellation: true,
                  noiseSuppression: true,
                  autoGainControl: true,
                },
              }).catch(() => null);
              if (!micStream) return;
              micStreamRef.current = micStream;
              const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
              if (!AudioCtx) return;
              const inCtx = new AudioCtx();
              audioInputContextRef.current = inCtx;
              const source = inCtx.createMediaStreamSource(micStream);
              const analyser = inCtx.createAnalyser();
              analyser.fftSize = 256;
              source.connect(analyser);
              const dataArray = new Uint8Array(analyser.frequencyBinCount);

              let vadFrames = 0;
              const updateVolume = () => {
                if (!micStreamRef.current) return;
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                const level = Math.min((sum / dataArray.length) / 80, 1);
                micLevelRef.current = level;

                // Acoustic Barge-in VAD: Only if audio is actively playing through speakers
                const isActivelyPlayingAudio = (typeof window !== "undefined" && window.speechSynthesis?.speaking) || activeSourcesRef.current.length > 0;
                if (isActivelyPlayingAudio) {
                  if (level > 0.35) {
                    vadFrames++;
                    if (vadFrames >= 4) { // ~60ms of voice
                      interruptAndListen("vad_user_voice");
                      setAiTranscript("Listening to you...");
                      currentQueryRef.current = "";
                      vadFrames = 0;
                    }
                  } else {
                    vadFrames = Math.max(0, vadFrames - 1);
                  }
                } else {
                  vadFrames = 0;
                }

                requestAnimationFrame(updateVolume);
              };
              updateVolume();
            }
          } catch {}
        })();

        return;
      }

      // 1. Request session token / credentials from Cloudflare Edge
      const tokenRes = await fetch(`${API}/api/voice/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: providerToUse,
          customApiKey: keyToUse.trim(),
        }),
      });

      const tokenData = await tokenRes.json().catch(() => ({}));

      // If provider requires custom key and none is provided, prompt user directly
      if (tokenData.requireCustomKey) {
        setConnecting(false);
        setErrorMsg(`${currentMeta.label} requires an API key. You can switch to Free Browser Voice or enter your key in Settings.`);
        return;
      }

      if (!tokenRes.ok && !keyToUse.trim()) {
        throw new Error(tokenData.error || `Server returned ${tokenRes.status}`);
      }

      // 2. Setup Audio Output Context (24kHz standard playback)
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const outCtx = new AudioCtx({ sampleRate: 24000 });
      await outCtx.resume();
      audioOutputContextRef.current = outCtx;
      nextPlayTimeRef.current = outCtx.currentTime;

      // 3. Setup Audio Input Context
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      micStreamRef.current = micStream;

      const targetSampleRate = providerToUse === "openai" ? 24000 : 16000;
      let inCtx: AudioContext;
      try {
        inCtx = new AudioCtx({ sampleRate: targetSampleRate });
      } catch {
        inCtx = new AudioCtx();
      }
      if (inCtx.state === "suspended") {
        await inCtx.resume();
      }
      audioInputContextRef.current = inCtx;

      // 4. Robust WebSocket URL construction (handles empty base on workers.dev origin)
      let wsBase = "";
      if (API && API.startsWith("http")) {
        wsBase = API.replace(/^http/, "ws");
      } else if (typeof window !== "undefined") {
        const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsBase = `${wsProto}//${window.location.host}`;
      }

      let wsUrl = `${wsBase}/api/voice/ws?provider=${providerToUse}&thread_id=${activeThreadId || ""}&voice=${encodeURIComponent(selectedVoice)}`;
      if (tokenData.token) {
        wsUrl += `&token=${encodeURIComponent(tokenData.token)}`;
      } else if (keyToUse.trim()) {
        wsUrl += `&key=${encodeURIComponent(keyToUse.trim())}`;
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setConnecting(false);
        setLatencyMs(Math.max(15, Date.now() - pingStartRef.current));

        // Provider-specific initial handshake
        if (providerToUse === "gemini") {
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

          // Handle Error Events from Upstream
          if (msg.type === "error") {
            setErrorMsg(msg.message || `Error from ${currentMeta.label}. Please verify your key.`);
            setShowSettings(true);
            disconnectSession();
            return;
          }

          // Handle Unified Server Content
          const serverContent = msg.serverContent;
          if (serverContent) {
            // Interruption signal
            if (serverContent.interrupted) {
              interruptAndListen("server_interrupted");
            }

            // Input Transcription (User text)
            if (serverContent.inputTranscription?.text) {
              setUserTranscript(serverContent.inputTranscription.text);
            }

            // Output Transcription (AI text)
            if (serverContent.outputTranscription?.text) {
              setAiTranscript((prev) => prev + serverContent.outputTranscription.text);

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

  // Mic 16kHz PCM streaming pipeline with smart VAD barge-in
  function startMicPipeline(inCtx: AudioContext, stream: MediaStream, ws: WebSocket) {
    const source = inCtx.createMediaStreamSource(stream);
    const processor = inCtx.createScriptProcessor(2048, 1, 1);
    processorRef.current = processor;
    if (typeof window !== "undefined") {
      (window as any).__voiceProcessor = processor;
    }

    let pcmVadFrames = 0;

    processor.onaudioprocess = (e) => {
      if (micMuted || ws.readyState !== WebSocket.OPEN) return;

      const inputData = e.inputBuffer.getChannelData(0);

      // Volume calculation for visualizer
      let sum = 0;
      for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i];
      const level = Math.min(Math.sqrt(sum / inputData.length) * 4, 1);
      micLevelRef.current = level;

      // Smart Barge-in VAD: If AI is actively outputting audio and user speaks into mic
      if (activeSourcesRef.current.length > 0 || isAiSpeaking) {
        if (level > 0.18) {
          pcmVadFrames++;
          // If voice energy sustained for ~120ms (3 chunks): stop AI playback and listen!
          if (pcmVadFrames >= 3) {
            interruptAndListen("pcm_vad_barge_in");
            setAiTranscript((prev) => (prev ? `${prev} (Interrupted)` : ""));
            pcmVadFrames = 0;
          }
        } else {
          pcmVadFrames = Math.max(0, pcmVadFrames - 1);
        }
      } else {
        pcmVadFrames = 0;
      }

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
              mimeType: `audio/pcm;rate=${inCtx.sampleRate}`,
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
    interruptAndListen("manual_stop");
  }

  // Disconnect and release all resources
  function disconnectSession() {
    stopAiPlayback();

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    if (recognitionRef.current) {
      try { recognitionRef.current.abort(); } catch {}
      recognitionRef.current = null;
    }
    isWebSpeechSpeakingRef.current = false;

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

  function handleSaveSettings(
    newProvider: VoiceProviderId,
    newKey: string,
    newVoice: string,
    newThinkingLevel: string
  ) {
    const provider = newProvider;
    const key = newKey.trim();
    const voice = newVoice;
    const thinking = newThinkingLevel;

    if (typeof window !== "undefined") {
      localStorage.setItem("AGENT_PILOT_VOICE_PROVIDER", provider);
      localStorage.setItem(VOICE_PROVIDERS[provider].keyStorageKey, key);
      localStorage.setItem(`AGENT_PILOT_${provider.toUpperCase()}_VOICE`, voice);
      if (provider === "gemini") {
        localStorage.setItem("AGENT_PILOT_GEMINI_KEY", key);
        localStorage.setItem("AGENT_PILOT_VOICE", voice);
      } else if (provider === "openai") {
        localStorage.setItem("AGENT_PILOT_OPENAI_KEY", key);
        localStorage.setItem("AGENT_PILOT_OPENAI_VOICE", voice);
      }
    }

    setSelectedProvider(provider);
    setCustomKey(key);
    setSelectedVoice(voice);
    setThinkingLevel(thinking);
    setShowSettings(false);
    setErrorMsg(null);

    // Disconnect previous session and clear transcripts
    disconnectSession();
    setUserTranscript("");
    setAiTranscript("");

    // Automatically connect to the newly selected provider and key
    void connectSession(provider, key);
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
            initialProvider={selectedProvider}
            initialKey={customKey}
            initialVoice={selectedVoice}
            initialThinkingLevel={thinkingLevel}
            onSave={handleSaveSettings}
          />
        )}

        {/* Center Stage: Quantum Fluid Orb & Waves Visualizer */}
        <div className="relative flex-1 flex flex-col items-center justify-center p-6 overflow-hidden">
          {errorMsg && (
            <div className="absolute top-4 z-10 mx-auto flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-200 max-w-xl shadow-xl backdrop-blur-md">
              <div className="flex items-center gap-2">
                <AlertCircle size={16} className="shrink-0 text-amber-400" />
                <span>{errorMsg}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {selectedProvider !== "web_speech" && (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedProvider("web_speech");
                      setErrorMsg(null);
                      setShowSettings(false);
                      void connectSession("web_speech");
                    }}
                    className="rounded-lg bg-emerald-500/25 px-2.5 py-1 text-[11px] font-semibold text-emerald-300 hover:bg-emerald-500/35 transition border border-emerald-500/35 cursor-pointer"
                  >
                    Switch to Free Voice
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowSettings(true)}
                  className="rounded-lg bg-amber-500/20 px-2.5 py-1 text-[11px] font-semibold text-amber-300 hover:bg-amber-500/30 transition border border-amber-500/30 cursor-pointer"
                >
                  Open Settings
                </button>
              </div>
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
              onClick={() => void connectSession()}
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
              <p className="text-zinc-300 leading-relaxed whitespace-pre-wrap">{formatVoiceTranscript(aiTranscript)}</p>
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
                  onClick={() => {
                    setMicMuted((prev) => {
                      const next = !prev;
                      if (selectedProvider === "web_speech") {
                        if (next) {
                          try { recognitionRef.current?.stop(); } catch {}
                        } else {
                          try { recognitionRef.current?.start(); } catch {}
                        }
                      }
                      return next;
                    });
                  }}
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

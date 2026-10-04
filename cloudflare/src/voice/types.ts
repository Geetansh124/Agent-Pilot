/**
 * Voice Provider Adapter Layer — Shared Types
 *
 * Provider-agnostic interface for real-time voice backends.
 * Each provider adapter implements VoiceProvider to bridge
 * the Cloudflare Edge WebSocket proxy with its upstream API.
 */

/** Supported voice provider identifiers */
export type VoiceProviderName =
  | 'gemini'
  | 'openai'
  | 'elevenlabs'
  | 'anthropic'
  | 'groq'
  | 'deepgram';

/** Events emitted by a provider adapter back to the client WebSocket */
export interface VoiceProviderEvents {
  /** Raw upstream message to forward as-is to the client */
  onRawMessage: (data: string | ArrayBuffer) => void;
  /** Structured transcript event */
  onTranscript: (payload: TranscriptEvent) => void;
  /** Provider requests edge tool execution */
  onToolCall: (payload: ToolCallEvent) => void;
  /** Provider signals audio playback data */
  onAudio: (payload: AudioEvent) => void;
  /** Connection status changed */
  onStatus: (payload: StatusEvent) => void;
  /** Error occurred */
  onError: (error: Error) => void;
}

export interface TranscriptEvent {
  role: 'user' | 'assistant';
  text: string;
  isFinal: boolean;
}

export interface ToolCallEvent {
  callId: string;
  name: string;
  args: Record<string, any>;
}

export interface AudioEvent {
  /** Base64-encoded PCM audio chunk */
  data: string;
  /** MIME type with sample rate, e.g. "audio/pcm;rate=24000" */
  mimeType: string;
}

export interface StatusEvent {
  state: 'connecting' | 'connected' | 'disconnected' | 'error';
  message?: string;
}

/** Configuration passed from the voice route to a provider adapter */
export interface VoiceSessionConfig {
  /** API key (server-side or user-provided) */
  apiKey: string;
  /** Ephemeral session token (provider-specific) */
  token?: string;
  /** Active thread ID for tool context */
  threadId?: string;
  /** Desired voice persona name */
  voice?: string;
  /** Thinking/reasoning level */
  thinkingLevel?: string;
  /** Tool definitions in provider-native format */
  tools?: any[];
}

/**
 * Abstract voice provider adapter interface.
 *
 * Each provider implements this to bridge the client WebSocket
 * with its own upstream real-time API.
 */
export interface VoiceProvider {
  /** Human-readable provider label */
  readonly name: VoiceProviderName;

  /**
   * Open the upstream connection and begin relaying.
   * @param config - Session configuration (key, token, voice, etc.)
   * @param clientSend - Callback to send data to the client WebSocket.
   */
  connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void>;

  /**
   * Forward a client message (audio or control) to the upstream provider.
   * @param data - Raw string or binary message from the client WebSocket.
   */
  sendToUpstream(data: string | ArrayBuffer): void;

  /**
   * Send a tool execution result back to the upstream provider
   * so it can incorporate the output into its response.
   */
  sendToolResult(callId: string, output: any): void;

  /**
   * Gracefully close the upstream connection and release resources.
   */
  disconnect(): void;

  /** Whether the upstream WebSocket is currently open */
  readonly isConnected: boolean;
}

/**
 * Default provider configuration constants per provider.
 */
export const PROVIDER_DEFAULTS: Record<VoiceProviderName, {
  label: string;
  defaultModel: string;
  audioInputRate: number;
  audioOutputRate: number;
  voices: string[];
}> = {
  gemini: {
    label: 'Google Gemini Live',
    defaultModel: 'gemini-3.1-flash-live-preview',
    audioInputRate: 16000,
    audioOutputRate: 24000,
    voices: ['Puck', 'Charon', 'Kore', 'Fenrir', 'Aoede'],
  },
  openai: {
    label: 'OpenAI Realtime',
    defaultModel: 'gpt-4o-realtime-preview',
    audioInputRate: 24000,
    audioOutputRate: 24000,
    voices: ['alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'],
  },
  elevenlabs: {
    label: 'ElevenLabs Conversational AI',
    defaultModel: 'convai',
    audioInputRate: 16000,
    audioOutputRate: 16000,
    voices: [],  // Dynamic from ElevenLabs voice library
  },
  anthropic: {
    label: 'Anthropic Claude Voice',
    defaultModel: 'claude-sonnet-4-20250514',
    audioInputRate: 16000,
    audioOutputRate: 24000,
    voices: [],  // Text-based, TTS delegated to client
  },
  groq: {
    label: 'Groq Whisper + TTS',
    defaultModel: 'whisper-large-v3-turbo',
    audioInputRate: 16000,
    audioOutputRate: 24000,
    voices: [],  // Depends on TTS backend
  },
  deepgram: {
    label: 'Deepgram Voice Agent',
    defaultModel: 'nova-3',
    audioInputRate: 16000,
    audioOutputRate: 16000,
    voices: ['aura-asteria-en', 'aura-luna-en', 'aura-stella-en', 'aura-athena-en', 'aura-hera-en', 'aura-orion-en', 'aura-arcas-en', 'aura-perseus-en', 'aura-angus-en', 'aura-orpheus-en', 'aura-helios-en', 'aura-zeus-en'],
  },
};

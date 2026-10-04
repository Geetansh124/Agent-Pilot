/**
 * Voice Provider Definitions & Metadata for the Flight Deck HUD
 */

export type VoiceProviderId =
  | 'gemini'
  | 'openai'
  | 'elevenlabs'
  | 'deepgram'
  | 'anthropic'
  | 'groq';

export interface VoiceOption {
  id: string;
  name: string;
  desc?: string;
}

export interface VoiceProviderMeta {
  id: VoiceProviderId;
  label: string;
  badge: string;
  description: string;
  defaultModel: string;
  voices: VoiceOption[];
  keyPlaceholder: string;
  keyHelpUrl: string;
  keyStorageKey: string;
  supportsThinking?: boolean;
}

export const VOICE_PROVIDERS: Record<VoiceProviderId, VoiceProviderMeta> = {
  gemini: {
    id: 'gemini',
    label: 'Google Gemini Live',
    badge: 'gemini-3.1-flash-live-preview',
    description: 'Bidirectional low-latency audio via Gemini Live API on Cloudflare Edge',
    defaultModel: 'gemini-3.1-flash-live-preview',
    voices: [
      { id: 'Puck', name: 'Puck', desc: 'Natural & Energetic' },
      { id: 'Charon', name: 'Charon', desc: 'Deep & Grounded' },
      { id: 'Kore', name: 'Kore', desc: 'Smooth & Calming' },
      { id: 'Fenrir', name: 'Fenrir', desc: 'Authoritative' },
      { id: 'Aoede', name: 'Aoede', desc: 'Warm & Expressive' },
    ],
    keyPlaceholder: 'AIzaSy...',
    keyHelpUrl: 'https://aistudio.google.com/apikey',
    keyStorageKey: 'AGENT_PILOT_GEMINI_KEY',
    supportsThinking: true,
  },
  openai: {
    id: 'openai',
    label: 'OpenAI Realtime',
    badge: 'gpt-4o-realtime-preview',
    description: 'Full-duplex speech-to-speech with server VAD and 24kHz audio',
    defaultModel: 'gpt-4o-realtime-preview',
    voices: [
      { id: 'alloy', name: 'Alloy', desc: 'Versatile & Balanced' },
      { id: 'ash', name: 'Ash', desc: 'Clear & Confident' },
      { id: 'ballad', name: 'Ballad', desc: 'Warm & Melodic' },
      { id: 'coral', name: 'Coral', desc: 'Playful & Friendly' },
      { id: 'echo', name: 'Echo', desc: 'Smooth & Resonant' },
      { id: 'sage', name: 'Sage', desc: 'Authoritative & Calm' },
      { id: 'shimmer', name: 'Shimmer', desc: 'Bright & Expressive' },
      { id: 'verse', name: 'Verse', desc: 'Dynamically Dynamic' },
    ],
    keyPlaceholder: 'sk-proj-...',
    keyHelpUrl: 'https://platform.openai.com/api-keys',
    keyStorageKey: 'AGENT_PILOT_OPENAI_KEY',
  },
  elevenlabs: {
    id: 'elevenlabs',
    label: 'ElevenLabs ConvAI',
    badge: 'convai-agent',
    description: 'Ultra-realistic conversational synthetic & cloned voices',
    defaultModel: 'convai',
    voices: [
      { id: 'Rachel', name: 'Rachel', desc: 'Calm & Professional' },
      { id: 'Domi', name: 'Domi', desc: 'Engaging & Direct' },
      { id: 'Bella', name: 'Bella', desc: 'Bright & Friendly' },
      { id: 'Antoni', name: 'Antoni', desc: 'Warm Storyteller' },
      { id: 'Elli', name: 'Elli', desc: 'Young & Expressive' },
      { id: 'Josh', name: 'Josh', desc: 'Deep & Conversational' },
      { id: 'Arnold', name: 'Arnold', desc: 'Crisp & Narrative' },
      { id: 'Adam', name: 'Adam', desc: 'Deep & Authoritative' },
      { id: 'Sam', name: 'Sam', desc: 'Dynamic & Casual' },
    ],
    keyPlaceholder: 'xi-api-key-...',
    keyHelpUrl: 'https://elevenlabs.io/app/conversational-ai',
    keyStorageKey: 'AGENT_PILOT_ELEVENLABS_KEY',
  },
  deepgram: {
    id: 'deepgram',
    label: 'Deepgram Voice Agent',
    badge: 'nova-3 + aura',
    description: 'Nova-3 real-time speech-to-text with Aura natural speech synthesis',
    defaultModel: 'nova-3',
    voices: [
      { id: 'aura-asteria-en', name: 'Asteria', desc: 'Warm & Natural (Female)' },
      { id: 'aura-luna-en', name: 'Luna', desc: 'Calm & Precise (Female)' },
      { id: 'aura-stella-en', name: 'Stella', desc: 'Clear & Expressive (Female)' },
      { id: 'aura-athena-en', name: 'Athena', desc: 'Professional & Crisp (Female)' },
      { id: 'aura-orion-en', name: 'Orion', desc: 'Deep & Engaging (Male)' },
      { id: 'aura-arcas-en', name: 'Arcas', desc: 'Resonant & Grounded (Male)' },
      { id: 'aura-helios-en', name: 'Helios', desc: 'Bright & Conversational (Male)' },
      { id: 'aura-zeus-en', name: 'Zeus', desc: 'Authoritative & Strong (Male)' },
    ],
    keyPlaceholder: 'Token or Key...',
    keyHelpUrl: 'https://console.deepgram.com',
    keyStorageKey: 'AGENT_PILOT_DEEPGRAM_KEY',
  },
  anthropic: {
    id: 'anthropic',
    label: 'Anthropic Claude Voice',
    badge: 'claude-3-7-sonnet',
    description: 'Claude 3.7 Sonnet streaming with client-side speech synthesis & tools',
    defaultModel: 'claude-3-7-sonnet-20250219',
    voices: [
      { id: 'claude-3-7-sonnet-20250219', name: 'Claude 3.7 Sonnet', desc: 'Hybrid reasoning & creative' },
      { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', desc: 'Fast & highly capable' },
      { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', desc: 'Ultra-low latency' },
    ],
    keyPlaceholder: 'sk-ant-api03-...',
    keyHelpUrl: 'https://console.anthropic.com/settings/keys',
    keyStorageKey: 'AGENT_PILOT_ANTHROPIC_KEY',
  },
  groq: {
    id: 'groq',
    label: 'Groq Whisper + LLM',
    badge: 'whisper-v3 + llama-3.3',
    description: 'Sub-second Whisper STT + Llama 3.3 70B inference pipeline',
    defaultModel: 'whisper-large-v3-turbo',
    voices: [
      { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B Versatile', desc: 'Best reasoning & speed' },
      { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant', desc: 'Lowest TTFB latency' },
      { id: 'gemma2-9b-it', name: 'Gemma 2 9B IT', desc: 'Google Open Model' },
    ],
    keyPlaceholder: 'gsk_...',
    keyHelpUrl: 'https://console.groq.com/keys',
    keyStorageKey: 'AGENT_PILOT_GROQ_KEY',
  },
};

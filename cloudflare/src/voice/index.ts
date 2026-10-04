/**
 * Voice Provider Factory & Registry
 *
 * Central entry point for creating provider adapters.
 * Maps provider name → adapter class instantiation.
 */

export { VoiceProvider, VoiceProviderName, VoiceSessionConfig, PROVIDER_DEFAULTS } from './types';
export { GeminiLiveProvider } from './gemini';
export { OpenAIRealtimeProvider } from './openai';
export { ElevenLabsProvider } from './elevenlabs';
export { DeepgramVoiceProvider } from './deepgram';
export { AnthropicVoiceProvider } from './anthropic';
export { GroqVoiceProvider } from './groq';

import { VoiceProvider, VoiceProviderName } from './types';
import { GeminiLiveProvider } from './gemini';
import { OpenAIRealtimeProvider } from './openai';
import { ElevenLabsProvider } from './elevenlabs';
import { DeepgramVoiceProvider } from './deepgram';
import { AnthropicVoiceProvider } from './anthropic';
import { GroqVoiceProvider } from './groq';

/**
 * Create a voice provider adapter by name.
 * Returns null if the provider is not yet implemented.
 */
export function createVoiceProvider(name: VoiceProviderName): VoiceProvider | null {
  switch (name) {
    case 'gemini':
      return new GeminiLiveProvider();
    case 'openai':
      return new OpenAIRealtimeProvider();
    case 'elevenlabs':
      return new ElevenLabsProvider();
    case 'deepgram':
      return new DeepgramVoiceProvider();
    case 'anthropic':
      return new AnthropicVoiceProvider();
    case 'groq':
      return new GroqVoiceProvider();

    default:
      return null;
  }
}

/** List all available (implemented) providers */
export function getAvailableProviders(): VoiceProviderName[] {
  return ['gemini', 'openai', 'elevenlabs', 'deepgram', 'anthropic', 'groq'];
}

/** List all planned providers */
export function getAllProviders(): VoiceProviderName[] {
  return ['gemini', 'openai', 'elevenlabs', 'deepgram', 'anthropic', 'groq'];
}


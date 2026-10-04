/**
 * Groq Whisper + LLM Voice Pipeline Provider Adapter
 *
 * Real-time voice pipeline leveraging:
 * 1. Groq Whisper (whisper-large-v3-turbo) for ultra-fast STT
 * 2. Groq LLM (llama-3.3-70b-versatile) with streaming tool calling
 * 3. Unified Flight Deck wire events
 *
 * Reference: https://console.groq.com/docs/speech-text
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';
import { OPENAI_TOOLS } from '../tools/definitions';

const GROQ_AUDIO_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';
const GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions';
const DEFAULT_LLM_MODEL = 'llama-3.3-70b-versatile';
const DEFAULT_STT_MODEL = 'whisper-large-v3-turbo';

interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content?: string | null;
  tool_calls?: any[];
  tool_call_id?: string;
  name?: string;
}

export class GroqVoiceProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'groq';

  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;
  private config: VoiceSessionConfig | null = null;
  private messages: ChatMessage[] = [];
  private activeAbortController: AbortController | null = null;
  private isGenerating = false;

  // Audio accumulation buffer for STT (16kHz 16-bit linear PCM)
  private audioChunks: Uint8Array[] = [];
  private totalAudioBytes = 0;
  private sttTimeout: any = null;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;
    this.config = config;
    this._isConnected = true;
    this.messages = [
      {
        role: 'system',
        content: 'You are Agent-Pilot, an intelligent voice flight deck assistant. Keep spoken answers concise, direct, natural, and helpful for audio delivery.',
      },
    ];

    this.send({
      type: 'status',
      message: 'connected_to_groq',
      provider: 'groq',
    });
  }

  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this._isConnected) return;

    if (typeof data !== 'string') return;

    try {
      const msg = JSON.parse(data);

      // Handle user interruption
      if (msg.interrupted || msg.type === 'interrupt') {
        this.abortGeneration();
        this.resetAudioBuffer();
        return;
      }

      // Check for incoming audio chunks (from Flight Deck microphone)
      if (msg.realtimeInput?.mediaChunks) {
        for (const chunk of msg.realtimeInput.mediaChunks) {
          if (chunk.data) {
            this.handleIncomingAudio(chunk.data);
          }
        }
        return;
      }

      // Direct text or transcription from client
      let userText: string | null = null;
      if (msg.text) {
        userText = msg.text;
      } else if (msg.clientContent?.turns) {
        for (const turn of msg.clientContent.turns) {
          if (turn.role === 'user' && turn.parts) {
            userText = turn.parts.map((p: any) => p.text || '').join(' ').trim();
          }
        }
      }

      if (userText) {
        this.resetAudioBuffer();
        this.send({
          serverContent: {
            inputTranscription: { text: userText },
          },
        });
        this.appendUserMessageAndGenerate(userText);
      }
    } catch {
      if (typeof data === 'string' && data.trim()) {
        this.appendUserMessageAndGenerate(data.trim());
      }
    }
  }

  private handleIncomingAudio(base64Data: string): void {
    try {
      const binary = atob(base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }

      this.audioChunks.push(bytes);
      this.totalAudioBytes += bytes.length;

      // Throttle STT submission when speech pause is detected (1 second of silence / pause)
      if (this.sttTimeout) clearTimeout(this.sttTimeout);

      // If we have at least 0.5s of audio (16000 bytes at 16kHz 16-bit)
      if (this.totalAudioBytes > 16000) {
        this.sttTimeout = setTimeout(() => {
          void this.transcribeAndProcessAudio();
        }, 800);
      }
    } catch (e) {
      console.error('Error buffering Groq audio:', e);
    }
  }

  private resetAudioBuffer(): void {
    if (this.sttTimeout) {
      clearTimeout(this.sttTimeout);
      this.sttTimeout = null;
    }
    this.audioChunks = [];
    this.totalAudioBytes = 0;
  }

  /**
   * Transcribe buffered PCM audio using Groq Whisper
   */
  private async transcribeAndProcessAudio(): Promise<void> {
    if (this.totalAudioBytes < 8000 || !this.config?.apiKey) {
      this.resetAudioBuffer();
      return;
    }

    const mergedPcm = new Uint8Array(this.totalAudioBytes);
    let offset = 0;
    for (const chunk of this.audioChunks) {
      mergedPcm.set(chunk, offset);
      offset += chunk.length;
    }
    this.resetAudioBuffer();

    const wavBlob = this.pcmToWavBlob(mergedPcm, 16000);

    try {
      const formData = new FormData();
      formData.append('file', wavBlob, 'audio.wav');
      formData.append('model', DEFAULT_STT_MODEL);
      formData.append('response_format', 'json');

      const res = await fetch(GROQ_AUDIO_URL, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.config.apiKey}`,
        },
        body: formData,
      });

      if (!res.ok) {
        return;
      }

      const json: any = await res.json();
      const transcript = (json.text || '').trim();

      if (transcript && transcript.length > 1) {
        this.send({
          serverContent: {
            inputTranscription: { text: transcript },
          },
        });
        this.appendUserMessageAndGenerate(transcript);
      }
    } catch (err) {
      console.error('Groq Whisper STT error:', err);
    }
  }

  /**
   * Generate a valid 44-byte WAV header over 16-bit mono PCM bytes
   */
  private pcmToWavBlob(pcmData: Uint8Array, sampleRate: number): Blob {
    const numChannels = 1;
    const bitsPerSample = 16;
    const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
    const blockAlign = (numChannels * bitsPerSample) / 8;
    const dataSize = pcmData.length;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    // RIFF chunk descriptor
    this.writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    this.writeString(view, 8, 'WAVE');

    // fmt sub-chunk
    this.writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);

    // data sub-chunk
    this.writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);

    new Uint8Array(buffer, 44).set(pcmData);
    return new Blob([buffer], { type: 'audio/wav' });
  }

  private writeString(view: DataView, offset: number, string: string): void {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  private appendUserMessageAndGenerate(userText: string): void {
    this.messages.push({
      role: 'user',
      content: userText,
    });

    void this.generateGroqCompletion();
  }

  /**
   * Stream LLM response from Groq
   */
  private async generateGroqCompletion(): Promise<void> {
    if (!this.config?.apiKey || this.isGenerating) return;

    this.abortGeneration();
    this.activeAbortController = new AbortController();
    this.isGenerating = true;

    const model = this.config.voice && this.config.voice.includes('llama')
      ? this.config.voice
      : DEFAULT_LLM_MODEL;

    try {
      const res = await fetch(GROQ_CHAT_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.config.apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: this.messages,
          tools: OPENAI_TOOLS,
          tool_choice: 'auto',
          stream: true,
          temperature: 0.6,
          max_tokens: 1024,
        }),
        signal: this.activeAbortController.signal,
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => '');
        this.send({
          type: 'error',
          provider: 'groq',
          message: `Groq API error (${res.status}): ${errorText}`,
        });
        this.isGenerating = false;
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        this.isGenerating = false;
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let assistantText = '';
      const toolCallsMap: Record<number, { id: string; name: string; arguments: string }> = {};

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const dataStr = trimmed.slice(6);
          if (dataStr === '[DONE]') continue;

          try {
            const chunk = JSON.parse(dataStr);
            const delta = chunk.choices?.[0]?.delta;
            if (!delta) continue;

            if (delta.content) {
              assistantText += delta.content;
              this.send({
                serverContent: {
                  outputTranscription: { text: delta.content },
                },
              });
            }

            if (delta.tool_calls) {
              for (const tc of delta.tool_calls) {
                const index = tc.index ?? 0;
                if (!toolCallsMap[index]) {
                  toolCallsMap[index] = {
                    id: tc.id || `call_${Date.now()}_${index}`,
                    name: tc.function?.name || '',
                    arguments: '',
                  };
                }
                if (tc.function?.name) toolCallsMap[index].name = tc.function.name;
                if (tc.function?.arguments) toolCallsMap[index].arguments += tc.function.arguments;
              }
            }
          } catch {}
        }
      }

      // Check if any tool calls were constructed
      const toolCalls = Object.values(toolCallsMap);

      if (toolCalls.length > 0) {
        this.messages.push({
          role: 'assistant',
          content: assistantText || null,
          tool_calls: toolCalls.map((tc) => ({
            id: tc.id,
            type: 'function',
            function: {
              name: tc.name,
              arguments: tc.arguments,
            },
          })),
        });

        // Emit each tool call for Edge execution
        for (const tc of toolCalls) {
          let parsedArgs = {};
          try {
            parsedArgs = JSON.parse(tc.arguments || '{}');
          } catch {}

          this.send({
            type: 'tool_call',
            provider: 'groq',
            callId: tc.id,
            name: tc.name,
            args: parsedArgs,
          });
        }
      } else if (assistantText) {
        this.messages.push({
          role: 'assistant',
          content: assistantText,
        });
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Groq LLM streaming error:', err);
        this.send({
          type: 'error',
          provider: 'groq',
          message: err.message || 'Groq connection failed',
        });
      }
    } finally {
      this.isGenerating = false;
    }
  }

  sendToolResult(callId: string, output: any): void {
    this.messages.push({
      role: 'tool',
      tool_call_id: callId,
      content: typeof output === 'string' ? output : JSON.stringify(output),
    });

    void this.generateGroqCompletion();
  }

  private abortGeneration(): void {
    if (this.activeAbortController) {
      this.activeAbortController.abort();
      this.activeAbortController = null;
    }
    this.isGenerating = false;
  }

  disconnect(): void {
    this._isConnected = false;
    this.abortGeneration();
    this.resetAudioBuffer();
    this.messages = [];
    this.send({
      type: 'status',
      message: 'disconnected',
      provider: 'groq',
    });
  }

  private send(data: any): void {
    if (this.clientSend) {
      try {
        this.clientSend(JSON.stringify(data));
      } catch (err) {
        console.error('Failed to send Groq message to client:', err);
      }
    }
  }
}

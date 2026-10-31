/**
 * OpenAI Realtime API Provider Adapter
 *
 * Bidirectional WebSocket bridge to the OpenAI Realtime API
 * (gpt-4o-realtime-preview). Supports server VAD, native
 * function calling, and 24kHz PCM audio I/O.
 *
 * Protocol reference: https://platform.openai.com/docs/guides/realtime
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';
import { OPENAI_TOOLS } from '../tools/definitions';

const OPENAI_REALTIME_BASE = 'wss://api.openai.com/v1/realtime';
const OPENAI_REALTIME_MODEL = 'gpt-4o-realtime-preview';

/** Resample linear PCM16 mono audio from any rate to 24kHz (linear interpolation) */
function resamplePcm16To24k(base64Pcm16: string, sourceRate = 24000): string {
  if (sourceRate === 24000 || !sourceRate) return base64Pcm16;

  try {
    const binary = atob(base64Pcm16);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const in16 = new Int16Array(bytes.buffer);
    if (in16.length === 0) return base64Pcm16;

    const ratio = sourceRate / 24000;
    const outLen = Math.floor(in16.length / ratio);
    const out16 = new Int16Array(outLen);

    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * ratio;
      const idx0 = Math.floor(srcIdx);
      const idx1 = Math.min(idx0 + 1, in16.length - 1);
      const frac = srcIdx - idx0;
      out16[i] = Math.round(in16[idx0] * (1 - frac) + in16[idx1] * frac);
    }

    const outBytes = new Uint8Array(out16.buffer);
    let outBinary = '';
    for (let i = 0; i < outBytes.length; i++) outBinary += String.fromCharCode(outBytes[i]);
    return btoa(outBinary);
  } catch {
    return base64Pcm16;
  }
}

export class OpenAIRealtimeProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'openai';

  private upstreamWs: WebSocket | null = null;
  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;
  private config: VoiceSessionConfig | null = null;
  private isResponseInProgress = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;
    this.config = config;

    const authKey = config.token || config.apiKey;
    if (!authKey) {
      throw new Error('API key or token is required for OpenAI Realtime.');
    }

    const url = `https://api.openai.com/v1/realtime?model=${encodeURIComponent(OPENAI_REALTIME_MODEL)}`;

    // Cloudflare Workers requires fetch with Upgrade: websocket for authenticated upstream sockets
    const resp = await fetch(url, {
      headers: {
        'Upgrade': 'websocket',
        'Authorization': `Bearer ${authKey}`,
        'OpenAI-Beta': 'realtime=v1',
      },
    });

    const ws = (resp as any).webSocket;
    if (!ws) {
      const errText = await resp.text().catch(() => '');
      throw new Error(`OpenAI Realtime WebSocket upgrade failed (${resp.status}): ${errText || resp.statusText}`);
    }

    ws.accept();
    this.upstreamWs = ws;
    this._isConnected = true;
    this.send({ type: 'status', message: 'connected_to_openai', provider: 'openai' });

    // Send session.update to configure session (modalities, voice, server VAD, etc.)
    this.sendSessionUpdate();

    ws.addEventListener('message', (event: any) => {
      this.handleUpstreamMessage(event);
    });

    ws.addEventListener('close', () => {
      this._isConnected = false;
      this.isResponseInProgress = false;
      this.send({ type: 'status', message: 'disconnected', provider: 'openai' });
    });

    ws.addEventListener('error', (e: any) => {
      console.error('OpenAI Realtime upstream WebSocket error:', e);
      this._isConnected = false;
      this.isResponseInProgress = false;
      this.send({ type: 'error', message: 'OpenAI Realtime WebSocket error', provider: 'openai' });
    });
  }

  /**
   * Forward client messages to OpenAI Realtime.
   * Translates Gemini-format audio input → OpenAI format.
   * Resamples PCM from any source rate to native 24kHz PCM.
   */
  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this.upstreamWs || !this._isConnected) return;
    if (this.upstreamWs.readyState !== undefined && this.upstreamWs.readyState !== 1) return;

    if (typeof data !== 'string') {
      return;
    }

    try {
      const msg = JSON.parse(data);

      // Translate audio input packets → OpenAI format (with 24kHz check/resampling)
      if (msg.realtimeInput?.mediaChunks) {
        for (const chunk of msg.realtimeInput.mediaChunks) {
          const rateMatch = chunk.mimeType?.match(/rate=(\d+)/);
          const sampleRate = rateMatch ? parseInt(rateMatch[1], 10) : 24000;
          const audioPayload = resamplePcm16To24k(chunk.data, sampleRate);

          this.upstreamWs.send(JSON.stringify({
            type: 'input_audio_buffer.append',
            audio: audioPayload,
          }));
        }
        return;
      }

      // Translate Gemini-format setup → handled in sendSessionUpdate()
      if (msg.setup) {
        return;
      }

      // Handle interrupt signal from client (only cancel if a model response is actually in progress)
      if (msg.type === 'interrupt') {
        if (this.isResponseInProgress) {
          try {
            this.upstreamWs.send(JSON.stringify({ type: 'response.cancel' }));
          } catch {}
          this.isResponseInProgress = false;
        }
        return;
      }

      // Forward any other messages as-is
      this.upstreamWs.send(data);
    } catch {
      this.upstreamWs.send(data);
    }
  }

  sendToolResult(callId: string, output: any): void {
    if (!this.upstreamWs || !this._isConnected) return;
    if (this.upstreamWs.readyState !== undefined && this.upstreamWs.readyState !== 1) return;

    // Send function call output
    this.upstreamWs.send(JSON.stringify({
      type: 'conversation.item.create',
      item: {
        type: 'function_call_output',
        call_id: callId,
        output: typeof output === 'string' ? output : JSON.stringify(output),
      },
    }));

    // Trigger the model to continue generating after tool result
    this.upstreamWs.send(JSON.stringify({
      type: 'response.create',
    }));
  }

  disconnect(): void {
    this._isConnected = false;
    try {
      if (this.upstreamWs) this.upstreamWs.close();
    } catch {}
    this.upstreamWs = null;
    this.clientSend = null;
    this.config = null;
  }

  /** Configure the OpenAI Realtime session after connection */
  private sendSessionUpdate(): void {
    if (!this.upstreamWs || !this.config) return;

    const tools = OPENAI_TOOLS.map((t) => ({
      type: 'function' as const,
      name: t.function.name,
      description: t.function.description,
      parameters: t.function.parameters,
    }));

    const sessionUpdate = {
      type: 'session.update',
      session: {
        modalities: ['text', 'audio'],
        instructions: 'You are Agent-Pilot, a helpful AI assistant. Respond concisely and naturally in voice conversation.',
        voice: this.config.voice || 'alloy',
        input_audio_format: 'pcm16',
        output_audio_format: 'pcm16',
        input_audio_transcription: {
          model: 'whisper-1',
        },
        turn_detection: {
          type: 'server_vad',
          threshold: 0.5,
          prefix_padding_ms: 300,
          silence_duration_ms: 500,
          create_response: true,
        },
        tools,
        tool_choice: 'auto',
      },
    };

    this.upstreamWs.send(JSON.stringify(sessionUpdate));
  }

  /** Handle messages from OpenAI Realtime and translate to unified client format */
  private handleUpstreamMessage(event: MessageEvent): void {
    try {
      const rawData = event.data;
      if (typeof rawData !== 'string') return;

      const msg = JSON.parse(rawData);

      switch (msg.type) {
        case 'session.created':
        case 'session.updated':
          // Session metadata — no-op, already notified
          break;

        case 'response.created':
          this.isResponseInProgress = true;
          break;

        case 'response.audio.delta':
          // Audio chunk from the model — translate to Gemini-compatible format
          this.send({
            serverContent: {
              modelTurn: {
                parts: [{
                  inlineData: {
                    data: msg.delta,
                    mimeType: 'audio/pcm;rate=24000',
                  },
                }],
              },
            },
          });
          break;

        case 'response.audio_transcript.delta':
          // AI output transcript chunk
          this.send({
            serverContent: {
              outputTranscription: {
                text: msg.delta,
              },
            },
          });
          break;

        case 'conversation.item.input_audio_transcription.completed':
          // User input transcript
          this.send({
            serverContent: {
              inputTranscription: {
                text: msg.transcript,
              },
            },
          });
          break;

        case 'response.function_call_arguments.done':
          // Function call completed — emit tool_call for edge execution
          this.send({
            type: 'tool_call',
            provider: 'openai',
            callId: msg.call_id,
            name: msg.name,
            args: JSON.parse(msg.arguments || '{}'),
          });
          break;

        case 'input_audio_buffer.speech_started':
          // User started speaking — signal interruption to client so client stops playing previous AI audio
          this.send({
            serverContent: { interrupted: true },
          });
          break;

        case 'error':
          this.send({
            type: 'error',
            provider: 'openai',
            message: msg.error?.message || 'OpenAI Realtime error',
            code: msg.error?.code,
          });
          break;

        case 'response.done':
        case 'response.cancelled':
          this.isResponseInProgress = false;
          break;

        default:
          // Forward unrecognized events for debugging
          break;
      }
    } catch (err: any) {
      console.error('OpenAI Realtime message handling error:', err);
    }
  }

  /** Send structured JSON to client WebSocket */
  private send(payload: Record<string, any>): void {
    try {
      this.clientSend?.(JSON.stringify(payload));
    } catch {}
  }

  /**
   * Generate an ephemeral session token via the OpenAI REST API.
   * Uses the /v1/realtime/sessions endpoint.
   */
  static async createSessionToken(apiKey: string): Promise<{
    token?: string;
    expireTime?: string;
    error?: string;
    requireCustomKey?: boolean;
  }> {
    if (!apiKey) {
      return { requireCustomKey: true };
    }

    try {
      const res = await fetch('https://api.openai.com/v1/realtime/sessions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: OPENAI_REALTIME_MODEL,
          voice: 'alloy',
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        return {
          error: `OpenAI Token API error (${res.status}): ${errText}`,
          requireCustomKey: res.status === 401 || res.status === 403,
        };
      }

      const data = await res.json() as any;
      return {
        token: data.client_secret?.value,
        expireTime: data.expires_at ? new Date(data.expires_at * 1000).toISOString() : undefined,
      };
    } catch (err: any) {
      return { error: `Failed to generate OpenAI session token: ${err.message}` };
    }
  }
}

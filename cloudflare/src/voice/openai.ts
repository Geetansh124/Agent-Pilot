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

export class OpenAIRealtimeProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'openai';

  private upstreamWs: WebSocket | null = null;
  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;
  private config: VoiceSessionConfig | null = null;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;
    this.config = config;

    const model = OPENAI_REALTIME_MODEL;
    const wsUrl = `${OPENAI_REALTIME_BASE}?model=${encodeURIComponent(model)}`;

    return new Promise<void>((resolve, reject) => {
      try {
        // OpenAI Realtime uses header auth — Cloudflare Workers WebSocket
        // doesn't support custom headers, so we use the protocol-based auth.
        // The API key is sent in a subprotocol header array.
        this.upstreamWs = new WebSocket(wsUrl, [
          'realtime',
          `openai-insecure-api-key.${config.apiKey}`,
          'openai-beta.realtime-v1',
        ]);

        this.upstreamWs.addEventListener('open', () => {
          this._isConnected = true;
          this.send({ type: 'status', message: 'connected_to_openai', provider: 'openai' });

          // Send session.update to configure the session
          this.sendSessionUpdate();
          resolve();
        });

        this.upstreamWs.addEventListener('message', (event) => {
          this.handleUpstreamMessage(event);
        });

        this.upstreamWs.addEventListener('close', () => {
          this._isConnected = false;
          this.send({ type: 'status', message: 'disconnected', provider: 'openai' });
        });

        this.upstreamWs.addEventListener('error', (e) => {
          console.error('OpenAI Realtime upstream WebSocket error:', e);
          this._isConnected = false;
          this.send({ type: 'error', message: 'OpenAI Realtime WebSocket error', provider: 'openai' });
        });
      } catch (err: any) {
        reject(err);
      }
    });
  }

  /**
   * Forward client messages to OpenAI Realtime.
   *
   * The client sends Gemini-format messages by default.
   * We translate `realtimeInput` audio packets into OpenAI's
   * `input_audio_buffer.append` format.
   */
  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    if (typeof data !== 'string') {
      // Binary frames not used in OpenAI Realtime — skip
      return;
    }

    try {
      const msg = JSON.parse(data);

      // Translate Gemini-format audio input → OpenAI format
      if (msg.realtimeInput?.mediaChunks) {
        for (const chunk of msg.realtimeInput.mediaChunks) {
          this.upstreamWs.send(JSON.stringify({
            type: 'input_audio_buffer.append',
            audio: chunk.data,  // Base64 PCM
          }));
        }
        return;
      }

      // Translate Gemini-format setup → handled in sendSessionUpdate()
      if (msg.setup) {
        // Already configured on connect, ignore duplicate
        return;
      }

      // Forward any other messages as-is (provider-native)
      this.upstreamWs.send(data);
    } catch {
      // Non-JSON data, forward raw
      this.upstreamWs.send(data);
    }
  }

  sendToolResult(callId: string, output: any): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

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
          // User started speaking — signal interruption
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
          // Response finished — no action needed
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

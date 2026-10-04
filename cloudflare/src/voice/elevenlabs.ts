/**
 * ElevenLabs Conversational AI Provider Adapter
 *
 * WebSocket bridge to the ElevenLabs Conversational AI API.
 * Supports signed URL authentication, agent-side tool execution,
 * μ-law/PCM audio codecs, and premium/cloned voice selection.
 *
 * Reference: https://elevenlabs.io/docs/conversational-ai
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';

const ELEVENLABS_CONVAI_WS = 'wss://api.elevenlabs.io/v1/convai/conversation';

export class ElevenLabsProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'elevenlabs';

  private upstreamWs: WebSocket | null = null;
  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;

    // ElevenLabs uses signed URL or API key via query param
    let wsUrl = ELEVENLABS_CONVAI_WS;
    if (config.token) {
      // Signed URL is the full URL returned by get_signed_url
      wsUrl = config.token;
    } else {
      wsUrl += `?xi-api-key=${encodeURIComponent(config.apiKey)}`;
    }

    return new Promise<void>((resolve, reject) => {
      try {
        this.upstreamWs = new WebSocket(wsUrl);

        this.upstreamWs.addEventListener('open', () => {
          this._isConnected = true;
          this.send({ type: 'status', message: 'connected_to_elevenlabs', provider: 'elevenlabs' });
          resolve();
        });

        this.upstreamWs.addEventListener('message', (event) => {
          this.handleUpstreamMessage(event);
        });

        this.upstreamWs.addEventListener('close', () => {
          this._isConnected = false;
          this.send({ type: 'status', message: 'disconnected', provider: 'elevenlabs' });
        });

        this.upstreamWs.addEventListener('error', (e) => {
          console.error('ElevenLabs upstream WebSocket error:', e);
          this._isConnected = false;
          this.send({ type: 'error', message: 'ElevenLabs WebSocket error', provider: 'elevenlabs' });
        });
      } catch (err: any) {
        reject(err);
      }
    });
  }

  /**
   * Forward client audio to ElevenLabs.
   * Translates Gemini-format realtimeInput to ElevenLabs user_audio_chunk.
   */
  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    if (typeof data !== 'string') return;

    try {
      const msg = JSON.parse(data);

      // Translate Gemini audio format → ElevenLabs format
      if (msg.realtimeInput?.mediaChunks) {
        for (const chunk of msg.realtimeInput.mediaChunks) {
          this.upstreamWs.send(JSON.stringify({
            user_audio_chunk: chunk.data,  // Base64 audio
          }));
        }
        return;
      }

      // Skip Gemini setup messages
      if (msg.setup) return;

      // Forward other messages as-is
      this.upstreamWs.send(data);
    } catch {
      this.upstreamWs.send(data);
    }
  }

  sendToolResult(callId: string, output: any): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    // ElevenLabs expects tool results as client_tool_result
    this.upstreamWs.send(JSON.stringify({
      client_tool_result: {
        tool_call_id: callId,
        result: typeof output === 'string' ? output : JSON.stringify(output),
        is_error: false,
      },
    }));
  }

  disconnect(): void {
    this._isConnected = false;
    try {
      if (this.upstreamWs) this.upstreamWs.close();
    } catch {}
    this.upstreamWs = null;
    this.clientSend = null;
  }

  /** Handle ElevenLabs messages and translate to unified client format */
  private handleUpstreamMessage(event: MessageEvent): void {
    try {
      const rawData = event.data;
      if (typeof rawData !== 'string') return;

      const msg = JSON.parse(rawData);

      // ElevenLabs sends events with a `type` field
      switch (msg.type) {
        case 'audio':
          // Audio chunk from agent
          this.send({
            serverContent: {
              modelTurn: {
                parts: [{
                  inlineData: {
                    data: msg.audio?.chunk || msg.audio_event?.audio_base_64 || '',
                    mimeType: 'audio/pcm;rate=16000',
                  },
                }],
              },
            },
          });
          break;

        case 'agent_response':
          // Agent text response or tool action
          if (msg.agent_response_type === 'tool') {
            this.send({
              type: 'tool_call',
              provider: 'elevenlabs',
              callId: msg.tool_call_id || 'call_1',
              name: msg.tool_name,
              args: msg.tool_parameters || {},
            });
          } else {
            // Text transcript from agent
            this.send({
              serverContent: {
                outputTranscription: {
                  text: msg.text || '',
                },
              },
            });
          }
          break;

        case 'user_transcript':
          // User speech transcript
          this.send({
            serverContent: {
              inputTranscription: {
                text: msg.user_transcript_event?.user_transcript || msg.text || '',
              },
            },
          });
          break;

        case 'interruption':
          this.send({
            serverContent: { interrupted: true },
          });
          break;

        case 'error':
          this.send({
            type: 'error',
            provider: 'elevenlabs',
            message: msg.message || msg.error || 'ElevenLabs error',
          });
          break;

        default:
          break;
      }
    } catch (err: any) {
      console.error('ElevenLabs message handling error:', err);
    }
  }

  private send(payload: Record<string, any>): void {
    try {
      this.clientSend?.(JSON.stringify(payload));
    } catch {}
  }

  /**
   * Get a signed WebSocket URL for the ElevenLabs Conversational AI.
   * Requires an agent_id configured in the ElevenLabs dashboard.
   */
  static async createSignedUrl(apiKey: string, agentId?: string): Promise<{
    token?: string;
    error?: string;
    requireCustomKey?: boolean;
  }> {
    if (!apiKey) {
      return { requireCustomKey: true };
    }

    if (!agentId) {
      // Without an agent_id, connect directly with API key
      return { token: undefined };
    }

    try {
      const res = await fetch(
        `https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id=${encodeURIComponent(agentId)}`,
        {
          method: 'GET',
          headers: { 'xi-api-key': apiKey },
        }
      );

      if (!res.ok) {
        const errText = await res.text();
        return {
          error: `ElevenLabs signed URL error (${res.status}): ${errText}`,
          requireCustomKey: res.status === 401,
        };
      }

      const data = await res.json() as any;
      return { token: data.signed_url };
    } catch (err: any) {
      return { error: `Failed to get ElevenLabs signed URL: ${err.message}` };
    }
  }
}

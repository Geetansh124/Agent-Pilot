/**
 * Deepgram Voice Agent API Provider Adapter
 *
 * WebSocket bridge to Deepgram's Voice Agent API for real-time
 * conversational AI with Nova-3 STT and Aura TTS.
 *
 * Reference: https://developers.deepgram.com/docs/voice-agent
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';
import { OPENAI_TOOLS } from '../tools/definitions';

const DEEPGRAM_AGENT_WS = 'wss://agent.deepgram.com/agent';

export class DeepgramVoiceProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'deepgram';

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

    return new Promise<void>((resolve, reject) => {
      try {
        this.upstreamWs = new WebSocket(DEEPGRAM_AGENT_WS, [
          'token',
          config.apiKey,
        ]);

        this.upstreamWs.addEventListener('open', () => {
          this._isConnected = true;
          this.send({ type: 'status', message: 'connected_to_deepgram', provider: 'deepgram' });

          // Send configuration settings
          this.sendSettings();
          resolve();
        });

        this.upstreamWs.addEventListener('message', (event) => {
          this.handleUpstreamMessage(event);
        });

        this.upstreamWs.addEventListener('close', () => {
          this._isConnected = false;
          this.send({ type: 'status', message: 'disconnected', provider: 'deepgram' });
        });

        this.upstreamWs.addEventListener('error', (e) => {
          console.error('Deepgram upstream WebSocket error:', e);
          this._isConnected = false;
          this.send({ type: 'error', message: 'Deepgram WebSocket error', provider: 'deepgram' });
        });
      } catch (err: any) {
        reject(err);
      }
    });
  }

  /**
   * Forward client audio to Deepgram.
   * Translates Gemini-format realtimeInput to raw binary PCM for Deepgram.
   */
  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    if (typeof data !== 'string') {
      // Binary audio frames forwarded directly
      this.upstreamWs.send(data);
      return;
    }

    try {
      const msg = JSON.parse(data);

      // Translate Gemini audio format → Deepgram expects raw binary,
      // but JSON-wrapped base64 also works via their audio input message
      if (msg.realtimeInput?.mediaChunks) {
        for (const chunk of msg.realtimeInput.mediaChunks) {
          // Decode base64 to binary and send as raw PCM
          const binary = atob(chunk.data);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          this.upstreamWs.send(bytes.buffer);
        }
        return;
      }

      // Skip Gemini setup messages
      if (msg.setup) return;

      this.upstreamWs.send(data);
    } catch {
      this.upstreamWs.send(data);
    }
  }

  sendToolResult(callId: string, output: any): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    // Deepgram Voice Agent: inject function call result
    this.upstreamWs.send(JSON.stringify({
      type: 'InjectAgentMessage',
      message: typeof output === 'string' ? output : JSON.stringify(output),
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

  /** Send initial settings to configure the Deepgram Voice Agent */
  private sendSettings(): void {
    if (!this.upstreamWs || !this.config) return;

    const tools = OPENAI_TOOLS.map((t) => ({
      type: 'function' as const,
      function: {
        name: t.function.name,
        description: t.function.description,
        parameters: t.function.parameters,
      },
    }));

    const settings = {
      type: 'SettingsConfiguration',
      audio: {
        input: {
          encoding: 'linear16',
          sample_rate: 16000,
        },
        output: {
          encoding: 'linear16',
          sample_rate: 16000,
          container: 'none',
        },
      },
      agent: {
        listen: {
          model: 'nova-3',
        },
        think: {
          provider: { type: 'open_ai' },
          model: 'gpt-4o-mini',
          instructions: 'You are Agent-Pilot, a helpful AI assistant. Be concise in voice responses.',
          functions: tools,
        },
        speak: {
          model: this.config.voice || 'aura-asteria-en',
        },
      },
    };

    this.upstreamWs.send(JSON.stringify(settings));
  }

  /** Handle Deepgram Voice Agent messages and translate to unified format */
  private handleUpstreamMessage(event: MessageEvent): void {
    try {
      const rawData = event.data;

      // Binary audio output from Deepgram
      if (rawData instanceof ArrayBuffer || (typeof rawData === 'object' && !(typeof rawData === 'string'))) {
        // Convert binary PCM to base64 for the unified client format
        const bytes = new Uint8Array(rawData instanceof ArrayBuffer ? rawData : (rawData as any));
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        const base64 = btoa(binary);

        this.send({
          serverContent: {
            modelTurn: {
              parts: [{
                inlineData: {
                  data: base64,
                  mimeType: 'audio/pcm;rate=16000',
                },
              }],
            },
          },
        });
        return;
      }

      if (typeof rawData !== 'string') return;

      const msg = JSON.parse(rawData);

      switch (msg.type) {
        case 'UserStartedSpeaking':
          this.send({
            serverContent: { interrupted: true },
          });
          break;

        case 'ConversationText':
          if (msg.role === 'user') {
            this.send({
              serverContent: {
                inputTranscription: { text: msg.content || '' },
              },
            });
          } else {
            this.send({
              serverContent: {
                outputTranscription: { text: msg.content || '' },
              },
            });
          }
          break;

        case 'FunctionCallRequest':
          this.send({
            type: 'tool_call',
            provider: 'deepgram',
            callId: msg.function_call_id || 'call_1',
            name: msg.function_name,
            args: msg.input || {},
          });
          break;

        case 'Error':
          this.send({
            type: 'error',
            provider: 'deepgram',
            message: msg.message || msg.description || 'Deepgram error',
          });
          break;

        default:
          break;
      }
    } catch (err: any) {
      console.error('Deepgram message handling error:', err);
    }
  }

  private send(payload: Record<string, any>): void {
    try {
      this.clientSend?.(JSON.stringify(payload));
    } catch {}
  }
}

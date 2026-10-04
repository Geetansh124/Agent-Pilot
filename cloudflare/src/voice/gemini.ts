/**
 * Gemini Live API Provider Adapter
 *
 * Extracted from the original voice.ts WebSocket bridge.
 * Connects to Google's Gemini Live bidirectional WebSocket API
 * and relays audio, transcripts, and function calls.
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';
import { GEMINI_FUNCTION_DECLARATIONS } from '../tools/definitions';

const GEMINI_WS_BASE = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent';

export class GeminiLiveProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'gemini';

  private upstreamWs: WebSocket | null = null;
  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;

    // Build upstream WebSocket URL with auth
    let wsUrl = GEMINI_WS_BASE;
    if (config.token) {
      wsUrl += `?access_token=${encodeURIComponent(config.token)}`;
    } else if (config.apiKey) {
      wsUrl += `?key=${encodeURIComponent(config.apiKey)}`;
    }

    return new Promise<void>((resolve, reject) => {
      try {
        this.upstreamWs = new WebSocket(wsUrl);

        this.upstreamWs.addEventListener('open', () => {
          this._isConnected = true;
          this.send({ type: 'status', message: 'connected_to_gemini', provider: 'gemini' });
          resolve();
        });

        this.upstreamWs.addEventListener('message', (event) => {
          this.handleUpstreamMessage(event);
        });

        this.upstreamWs.addEventListener('close', () => {
          this._isConnected = false;
          this.send({ type: 'status', message: 'disconnected', provider: 'gemini' });
        });

        this.upstreamWs.addEventListener('error', (e) => {
          console.error('Gemini upstream WebSocket error:', e);
          this._isConnected = false;
          this.send({ type: 'error', message: 'Gemini WebSocket connection error', provider: 'gemini' });
        });
      } catch (err: any) {
        reject(err);
      }
    });
  }

  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    if (typeof data === 'string') {
      this.upstreamWs.send(data);
    } else {
      this.upstreamWs.send(data);
    }
  }

  sendToolResult(callId: string, output: any): void {
    if (!this.upstreamWs || this.upstreamWs.readyState !== WebSocket.OPEN) return;

    const responseMessage = {
      toolResponse: {
        functionResponses: [
          {
            response: { output },
            id: callId,
          },
        ],
      },
    };
    this.upstreamWs.send(JSON.stringify(responseMessage));
  }

  disconnect(): void {
    this._isConnected = false;
    try {
      if (this.upstreamWs) this.upstreamWs.close();
    } catch {}
    this.upstreamWs = null;
    this.clientSend = null;
  }

  /**
   * Parse the setup message from the client and forward to Gemini.
   * The client sends a `setup` payload with model, voice, thinking config.
   * This is forwarded as-is since it's already in Gemini's native format.
   */
  private handleUpstreamMessage(event: MessageEvent): void {
    try {
      const rawData = event.data;
      if (typeof rawData !== 'string') {
        // Binary frames forwarded directly
        this.clientSend?.(rawData);
        return;
      }

      let parsed: any = null;
      try {
        parsed = JSON.parse(rawData);
      } catch {}

      // Check if the model triggered a function call
      const toolCallPart = parsed?.serverContent?.modelTurn?.parts?.find(
        (p: any) => p.functionCall
      );

      if (toolCallPart?.functionCall) {
        const fnCall = toolCallPart.functionCall;
        // Emit tool_call event for the route dispatcher to handle
        this.send({
          type: 'tool_call',
          provider: 'gemini',
          callId: fnCall.id || 'call_1',
          name: fnCall.name,
          args: fnCall.args || {},
        });
      }

      // Always forward raw message to client
      this.clientSend?.(rawData);
    } catch (err: any) {
      console.error('Gemini message handling error:', err);
    }
  }

  /** Send a structured JSON message to the client WebSocket */
  private send(payload: Record<string, any>): void {
    try {
      this.clientSend?.(JSON.stringify(payload));
    } catch {}
  }

  /**
   * Generate an ephemeral session token for the Gemini Live API.
   * Called by the voice route before establishing the WebSocket.
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
      const expireTime = new Date(Date.now() + 30 * 60 * 1000).toISOString();
      const newSessionExpireTime = new Date(Date.now() + 2 * 60 * 1000).toISOString();

      const res = await fetch('https://generativelanguage.googleapis.com/v1beta/auth_tokens', {
        method: 'POST',
        headers: {
          'x-goog-api-key': apiKey,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          uses: 1,
          expireTime,
          newSessionExpireTime,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        return {
          error: `Gemini Token API error (${res.status}): ${errText}`,
          requireCustomKey: res.status === 400 || res.status === 403,
        };
      }

      const data = await res.json() as any;
      return { token: data.name, expireTime };
    } catch (err: any) {
      return { error: `Failed to generate Gemini session token: ${err.message}` };
    }
  }

  /** Return Gemini-native function declarations for the session setup */
  static getToolDeclarations(): any[] {
    return GEMINI_FUNCTION_DECLARATIONS;
  }
}

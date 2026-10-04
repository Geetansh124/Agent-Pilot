/**
 * Anthropic Claude Voice Provider Adapter
 *
 * Real-time conversational agent using Anthropic's Claude Messages API
 * with streaming SSE. Integrates tool use with Edge tools and translates
 * events to/from the unified Flight Deck wire protocol.
 *
 * Reference: https://docs.anthropic.com/en/api/messages-streaming
 */

import { VoiceProvider, VoiceSessionConfig, VoiceProviderName } from './types';
import { OPENAI_TOOLS } from '../tools/definitions';

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';
const DEFAULT_MODEL = 'claude-3-7-sonnet-20250219';

interface AnthropicMessage {
  role: 'user' | 'assistant';
  content: any;
}

export class AnthropicVoiceProvider implements VoiceProvider {
  readonly name: VoiceProviderName = 'anthropic';

  private clientSend: ((data: string) => void) | null = null;
  private _isConnected = false;
  private config: VoiceSessionConfig | null = null;
  private messages: AnthropicMessage[] = [];
  private activeAbortController: AbortController | null = null;
  private currentToolUse: { id: string; name: string; inputJson: string } | null = null;
  private isGenerating = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  async connect(config: VoiceSessionConfig, clientSend: (data: string) => void): Promise<void> {
    this.clientSend = clientSend;
    this.config = config;
    this._isConnected = true;
    this.messages = [];

    this.send({
      type: 'status',
      message: 'connected_to_anthropic',
      provider: 'anthropic',
    });
  }

  /**
   * Forward client messages to Anthropic.
   * Handles text messages, transcript events, and interruption signals.
   */
  sendToUpstream(data: string | ArrayBuffer): void {
    if (!this._isConnected) return;

    if (typeof data !== 'string') return;

    try {
      const msg = JSON.parse(data);

      // Handle user interruption
      if (msg.interrupted || msg.type === 'interrupt') {
        this.abortGeneration();
        return;
      }

      // User sent text or client transcription
      let userText: string | null = null;

      if (msg.text) {
        userText = msg.text;
      } else if (msg.clientContent?.turns) {
        for (const turn of msg.clientContent.turns) {
          if (turn.role === 'user' && turn.parts) {
            userText = turn.parts.map((p: any) => p.text || '').join(' ').trim();
          }
        }
      } else if (msg.realtimeInput?.mediaChunks) {
        // Direct audio streaming without speech-to-text bridge
        // If client sends audio, speech recognition is handled via browser or Whisper
        return;
      }

      if (userText) {
        // Emit input transcription back to client
        this.send({
          serverContent: {
            inputTranscription: { text: userText },
          },
        });

        this.appendAndGenerate(userText);
      }
    } catch {
      // Non-JSON plain text message
      if (typeof data === 'string' && data.trim()) {
        this.appendAndGenerate(data.trim());
      }
    }
  }

  private appendAndGenerate(userText: string): void {
    this.messages.push({
      role: 'user',
      content: userText,
    });

    void this.generateClaudeResponse();
  }

  /**
   * Stream Claude response via SSE
   */
  private async generateClaudeResponse(): Promise<void> {
    if (!this.config?.apiKey || this.isGenerating) return;

    this.abortGeneration();
    this.activeAbortController = new AbortController();
    this.isGenerating = true;

    const tools = OPENAI_TOOLS.map((t) => ({
      name: t.function.name,
      description: t.function.description,
      input_schema: t.function.parameters,
    }));

    const model = this.config.voice && this.config.voice.startsWith('claude')
      ? this.config.voice
      : DEFAULT_MODEL;

    try {
      const res = await fetch(ANTHROPIC_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.config.apiKey,
          'anthropic-version': ANTHROPIC_VERSION,
        },
        body: JSON.stringify({
          model,
          max_tokens: 1024,
          messages: this.messages,
          tools,
          stream: true,
          system: 'You are Agent-Pilot, an intelligent voice flight deck assistant. Keep spoken answers concise, direct, natural, and helpful for audio delivery.',
        }),
        signal: this.activeAbortController.signal,
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => '');
        this.send({
          type: 'error',
          provider: 'anthropic',
          message: `Anthropic API error (${res.status}): ${errorText}`,
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
      const assistantContentBlocks: any[] = [];

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
            const event = JSON.parse(dataStr);
            this.handleStreamEvent(event, assistantContentBlocks, (deltaText) => {
              assistantText += deltaText;
            });
          } catch {}
        }
      }

      // Commit assistant turn to message history
      if (assistantContentBlocks.length > 0) {
        this.messages.push({
          role: 'assistant',
          content: assistantContentBlocks,
        });
      } else if (assistantText) {
        this.messages.push({
          role: 'assistant',
          content: assistantText,
        });
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Claude stream error:', err);
        this.send({
          type: 'error',
          provider: 'anthropic',
          message: err.message || 'Stream connection failed',
        });
      }
    } finally {
      this.isGenerating = false;
    }
  }

  private handleStreamEvent(
    event: any,
    contentBlocks: any[],
    onTextDelta: (text: string) => void
  ): void {
    switch (event.type) {
      case 'content_block_start':
        if (event.content_block?.type === 'tool_use') {
          this.currentToolUse = {
            id: event.content_block.id,
            name: event.content_block.name,
            inputJson: '',
          };
        }
        break;

      case 'content_block_delta':
        if (event.delta?.type === 'text_delta') {
          const text = event.delta.text || '';
          onTextDelta(text);

          // Send transcript chunk to client
          this.send({
            serverContent: {
              outputTranscription: { text },
            },
          });
        } else if (event.delta?.type === 'input_json_delta') {
          if (this.currentToolUse) {
            this.currentToolUse.inputJson += event.delta.partial_json || '';
          }
        }
        break;

      case 'content_block_stop':
        if (this.currentToolUse) {
          let parsedArgs = {};
          try {
            parsedArgs = JSON.parse(this.currentToolUse.inputJson || '{}');
          } catch {}

          contentBlocks.push({
            type: 'tool_use',
            id: this.currentToolUse.id,
            name: this.currentToolUse.name,
            input: parsedArgs,
          });

          // Emit tool_call for edge execution
          this.send({
            type: 'tool_call',
            provider: 'anthropic',
            callId: this.currentToolUse.id,
            name: this.currentToolUse.name,
            args: parsedArgs,
          });

          this.currentToolUse = null;
        }
        break;

      case 'message_delta':
        break;
    }
  }

  sendToolResult(callId: string, output: any): void {
    // Append tool_result to Claude history
    this.messages.push({
      role: 'user',
      content: [
        {
          type: 'tool_result',
          tool_use_id: callId,
          content: typeof output === 'string' ? output : JSON.stringify(output),
        },
      ],
    });

    // Trigger Claude to continue response after tool execution
    void this.generateClaudeResponse();
  }

  private abortGeneration(): void {
    if (this.activeAbortController) {
      this.activeAbortController.abort();
      this.activeAbortController = null;
    }
    this.isGenerating = false;
    this.currentToolUse = null;
  }

  disconnect(): void {
    this._isConnected = false;
    this.abortGeneration();
    this.messages = [];
    this.send({
      type: 'status',
      message: 'disconnected',
      provider: 'anthropic',
    });
  }

  private send(data: any): void {
    if (this.clientSend) {
      try {
        this.clientSend(JSON.stringify(data));
      } catch (err) {
        console.error('Failed to send Anthropic message to client:', err);
      }
    }
  }
}

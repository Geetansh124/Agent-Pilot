/**
 * Agent-Pilot Stream Forwarder Plugin for DeepSeek Harness (dsh).
 *
 * Intercepts in-process AssistantStreamFrame events and emits them
 * over the JSON-RPC notification channel as `ap/stream` events with
 * low-latency delta payloads.
 */

export interface AssistantStreamFrame {
  type: 'delta' | 'completion';
  content?: string;
  delta?: string;
  index?: number;
}

export interface PluginContext {
  sessionId: string;
  notify: (method: string, params: Record<string, unknown>) => void;
  logger?: {
    debug: (...args: unknown[]) => void;
    info: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  };
}

export class StreamForwarderPlugin {
  private context?: PluginContext;

  constructor(context?: PluginContext) {
    this.context = context;
  }

  initialize(context: PluginContext): void {
    this.context = context;
    if (this.context.logger) {
      this.context.logger.info(
        `StreamForwarderPlugin initialized for session ${context.sessionId}`
      );
    }
  }

  onStreamFrame(frame: AssistantStreamFrame): void {
    if (!this.context) return;
    const delta = frame.delta ?? frame.content;
    if (delta !== undefined) {
      this.context.notify('ap/stream', {
        sessionId: this.context.sessionId,
        delta,
        frameType: frame.type,
        index: frame.index,
      });
    }
  }

  shutdown(): void {
    this.context = undefined;
  }
}

export default function createPlugin(context: PluginContext): StreamForwarderPlugin {
  return new StreamForwarderPlugin(context);
}


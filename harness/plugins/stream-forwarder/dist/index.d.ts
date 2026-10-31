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
export declare class StreamForwarderPlugin {
    private context?;
    constructor(context?: PluginContext);
    initialize(context: PluginContext): void;
    onStreamFrame(frame: AssistantStreamFrame): void;
    shutdown(): void;
}
export default function createPlugin(context: PluginContext): StreamForwarderPlugin;

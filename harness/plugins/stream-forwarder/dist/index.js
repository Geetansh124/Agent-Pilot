"use strict";
/**
 * Agent-Pilot Stream Forwarder Plugin for DeepSeek Harness (dsh).
 *
 * Intercepts in-process AssistantStreamFrame events and emits them
 * over the JSON-RPC notification channel as `ap/stream` events with
 * low-latency delta payloads.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.StreamForwarderPlugin = void 0;
exports.default = createPlugin;
class StreamForwarderPlugin {
    context;
    constructor(context) {
        this.context = context;
    }
    initialize(context) {
        this.context = context;
        if (this.context.logger) {
            this.context.logger.info(`StreamForwarderPlugin initialized for session ${context.sessionId}`);
        }
    }
    onStreamFrame(frame) {
        if (!this.context)
            return;
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
    shutdown() {
        this.context = undefined;
    }
}
exports.StreamForwarderPlugin = StreamForwarderPlugin;
function createPlugin(context) {
    return new StreamForwarderPlugin(context);
}

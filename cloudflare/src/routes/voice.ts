import { Hono } from 'hono';
import { Env } from '../types';
import { executeEdgeTool } from '../tools';
import { GEMINI_FUNCTION_DECLARATIONS } from '../tools/definitions';
import {
  createVoiceProvider,
  getAvailableProviders,
  VoiceProviderName,
  PROVIDER_DEFAULTS,
} from '../voice';
import { GeminiLiveProvider } from '../voice/gemini';
import { OpenAIRealtimeProvider } from '../voice/openai';
import { ElevenLabsProvider } from '../voice/elevenlabs';

export const voiceRouter = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

/**
 * GET /api/voice/providers
 * Returns the list of available voice providers and their configuration metadata.
 */
voiceRouter.get('/providers', (c) => {
  const available = getAvailableProviders();
  const providers = available.map((name) => ({
    name,
    ...PROVIDER_DEFAULTS[name],
    hasServerKey: !!resolveApiKey(name, c.env),
  }));

  return c.json({ providers });
});

/**
 * POST /api/voice/token
 * Creates an ephemeral token for a voice session.
 * Supports provider selection via `provider` body field (default: gemini).
 */
voiceRouter.post('/token', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const providerName = (body.provider || 'gemini').trim().toLowerCase() as VoiceProviderName;
  const customKey = (body.customApiKey || '').trim();
  const apiKey = customKey || resolveApiKey(providerName, c.env);

  if (!apiKey) {
    return c.json({
      requireCustomKey: true,
      provider: providerName,
      model: PROVIDER_DEFAULTS[providerName]?.defaultModel,
      tools: providerName === 'gemini' ? GEMINI_FUNCTION_DECLARATIONS : undefined,
      message: `No server API key configured for ${providerName}. Please provide your own key in Voice settings.`,
    });
  }

  try {
    let tokenResult: { token?: string; expireTime?: string; error?: string; requireCustomKey?: boolean };

    switch (providerName) {
      case 'gemini':
        tokenResult = await GeminiLiveProvider.createSessionToken(apiKey);
        if (!tokenResult.error) {
          return c.json({
            ...tokenResult,
            provider: 'gemini',
            model: PROVIDER_DEFAULTS.gemini.defaultModel,
            tools: GeminiLiveProvider.getToolDeclarations(),
          });
        }
        break;

      case 'openai':
        tokenResult = await OpenAIRealtimeProvider.createSessionToken(apiKey);
        if (!tokenResult.error) {
          return c.json({
            ...tokenResult,
            provider: 'openai',
            model: PROVIDER_DEFAULTS.openai.defaultModel,
          });
        }
        break;

      case 'elevenlabs':
        tokenResult = await ElevenLabsProvider.createSignedUrl(apiKey, body.agentId);
        if (!tokenResult.error) {
          return c.json({
            ...tokenResult,
            provider: 'elevenlabs',
            model: PROVIDER_DEFAULTS.elevenlabs.defaultModel,
          });
        }
        break;

      case 'deepgram':
        // Deepgram uses API key directly in WebSocket auth, no token exchange
        tokenResult = { token: undefined };
        return c.json({
          provider: 'deepgram',
          model: PROVIDER_DEFAULTS.deepgram.defaultModel,
          message: 'Deepgram uses API key directly. Ready to connect.',
        });

      case 'anthropic':
        return c.json({
          provider: 'anthropic',
          model: PROVIDER_DEFAULTS.anthropic.defaultModel,
          message: 'Anthropic Claude Voice session ready.',
        });

      case 'groq':
        return c.json({
          provider: 'groq',
          model: PROVIDER_DEFAULTS.groq.defaultModel,
          message: 'Groq Whisper + LLM voice session ready.',
        });

      default:
        return c.json({
          error: `Voice provider '${providerName}' is not yet available. Available: ${getAvailableProviders().join(', ')}`,
        }, 400);
    }

    // Error path
    if (tokenResult.error) {
      return c.json({
        error: tokenResult.error,
        requireCustomKey: tokenResult.requireCustomKey,
        provider: providerName,
      }, tokenResult.requireCustomKey ? 401 : 500);
    }

    return c.json(tokenResult);
  } catch (err: any) {
    return c.json({
      error: `Failed to generate session token for ${providerName}: ${err.message}`,
    }, 500);
  }
});

/**
 * POST /api/voice/tools/execute
 * Direct edge execution endpoint for tools invoked by any voice provider session.
 */
voiceRouter.post('/tools/execute', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const toolName = (body.name || '').trim();
  const args = body.args || {};
  const threadId = body.thread_id;

  if (!toolName) {
    return c.json({ error: 'Tool name is required.' }, 400);
  }

  const result = await executeEdgeTool(toolName, args, { db: c.env.DB, threadId });
  return c.json({
    tool: toolName,
    call_id: body.call_id || null,
    output: result.result !== undefined ? result.result : { error: result.error || 'Execution failed' },
  });
});

/**
 * GET /api/voice/ws
 * Multi-provider WebSocket proxy.
 * Selects provider via `?provider=gemini|openai|elevenlabs|deepgram` query param.
 * Bridges client browser WebSocket with upstream provider WebSocket,
 * enabling edge execution of function calls and low-latency audio relay.
 */
voiceRouter.get('/ws', async (c) => {
  const upgradeHeader = c.req.header('Upgrade');
  if (!upgradeHeader || upgradeHeader.toLowerCase() !== 'websocket') {
    return c.text('Expected Upgrade: websocket', 426);
  }

  const url = new URL(c.req.url);
  const providerName = (url.searchParams.get('provider') || 'gemini').toLowerCase() as VoiceProviderName;
  const customKey = url.searchParams.get('key') || '';
  const token = url.searchParams.get('token') || '';
  const threadId = url.searchParams.get('thread_id') || '';
  const voice = url.searchParams.get('voice') || undefined;
  const apiKey = customKey || resolveApiKey(providerName, c.env);

  if (!apiKey && !token) {
    return c.text(`API key or token is required for ${providerName}.`, 401);
  }

  // Create provider adapter
  const provider = createVoiceProvider(providerName);
  if (!provider) {
    return c.text(`Voice provider '${providerName}' is not available. Available: ${getAvailableProviders().join(', ')}`, 400);
  }

  // Create WebSocket pair for Cloudflare Edge
  const pair = new WebSocketPair();
  const [clientWs, serverWs] = Object.values(pair);
  serverWs.accept();

  // Async bridge task
  const bridgeTask = async () => {
    try {
      // Connect provider adapter
      await provider.connect(
        {
          apiKey: apiKey || '',
          token: token || undefined,
          threadId,
          voice,
        },
        // clientSend callback — sends data to the browser
        (data: string) => {
          try {
            if (serverWs.readyState !== WebSocket.OPEN) return;

            // Intercept tool_call events for edge execution
            let parsed: any = null;
            try { parsed = JSON.parse(data); } catch {}

            if (parsed?.type === 'tool_call') {
              handleToolCall(parsed, provider, serverWs, c.env.DB, threadId);
              // Don't forward raw tool_call to client; send structured events instead
              return;
            }

            serverWs.send(data);
          } catch {}
        }
      );

      // Relay client messages to the provider adapter
      serverWs.addEventListener('message', (event) => {
        try {
          const rawData = event.data;
          if (typeof rawData === 'string') {
            provider.sendToUpstream(rawData);
          } else {
            provider.sendToUpstream(rawData);
          }
        } catch (err: any) {
          console.error(`Error forwarding client message to ${providerName}:`, err);
        }
      });

      // Handle close & error
      serverWs.addEventListener('close', () => provider.disconnect());
      serverWs.addEventListener('error', (e) => {
        console.error(`Client WebSocket error (${providerName}):`, e);
        provider.disconnect();
      });
    } catch (err: any) {
      console.error(`Failed to initialize ${providerName} WebSocket bridge:`, err);
      try {
        serverWs.send(JSON.stringify({ type: 'error', message: err.message, provider: providerName }));
        serverWs.close();
      } catch {}
    }
  };

  if (c.executionCtx && typeof c.executionCtx.waitUntil === 'function') {
    c.executionCtx.waitUntil(bridgeTask());
  } else {
    void bridgeTask();
  }

  return new Response(null, {
    status: 101,
    webSocket: clientWs,
  });
});

/**
 * Handle a tool_call event from any provider.
 * Executes the tool on Cloudflare Edge and sends results back to
 * both the provider (for continuation) and the client (for UI).
 */
async function handleToolCall(
  toolCall: { callId: string; name: string; args: Record<string, any> },
  provider: ReturnType<typeof createVoiceProvider>,
  serverWs: WebSocket,
  db: any,
  threadId: string
): Promise<void> {
  if (!provider) return;

  // Notify client: tool is executing
  try {
    serverWs.send(JSON.stringify({
      type: 'tool_executing',
      tool: toolCall.name,
      args: toolCall.args,
      call_id: toolCall.callId,
    }));
  } catch {}

  // Execute tool on Edge
  const toolResult = await executeEdgeTool(toolCall.name, toolCall.args, { db, threadId });
  const toolOutput = toolResult.result !== undefined ? toolResult.result : { error: toolResult.error };

  // Send result back to provider so it can continue generating
  provider.sendToolResult(toolCall.callId, toolOutput);

  // Notify client: tool finished
  try {
    serverWs.send(JSON.stringify({
      type: 'tool_finished',
      tool: toolCall.name,
      result: toolOutput,
      call_id: toolCall.callId,
    }));
  } catch {}
}

/**
 * Resolve the API key for a given provider from environment variables.
 */
function resolveApiKey(provider: VoiceProviderName, env: Env): string {
  switch (provider) {
    case 'gemini':
      return env.GEMINI_API_KEY || '';
    case 'openai':
      return (env as any).OPENAI_API_KEY || '';
    case 'elevenlabs':
      return (env as any).ELEVENLABS_API_KEY || '';
    case 'deepgram':
      return (env as any).DEEPGRAM_API_KEY || '';
    case 'anthropic':
      return (env as any).ANTHROPIC_API_KEY || '';
    case 'groq':
      return (env as any).GROQ_API_KEY || '';
    default:
      return '';
  }
}

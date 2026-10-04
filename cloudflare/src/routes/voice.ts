import { Hono } from 'hono';
import { Env } from '../types';
import { executeEdgeTool } from '../tools';
import { GEMINI_FUNCTION_DECLARATIONS } from '../tools/definitions';

export const voiceRouter = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

const LIVE_MODEL = 'gemini-3.1-flash-live-preview';

/**
 * POST /api/voice/token
 * Creates an ephemeral token for the Gemini Live API session.
 * Dual-credential architecture:
 * 1. Checks for user-provided custom key in request body.
 * 2. Falls back to server-configured GEMINI_API_KEY.
 * 3. Returns requireCustomKey: true if neither is present.
 */
voiceRouter.post('/token', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const customKey = (body.customApiKey || '').trim();
  const apiKey = customKey || c.env.GEMINI_API_KEY || '';

  if (!apiKey) {
    return c.json({
      requireCustomKey: true,
      model: LIVE_MODEL,
      tools: GEMINI_FUNCTION_DECLARATIONS,
      message: 'No server GEMINI_API_KEY configured. Please provide your own Gemini API key in Voice settings.',
    });
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
      return c.json({
        error: `Gemini Token API error (${res.status}): ${errText}`,
        requireCustomKey: res.status === 400 || res.status === 403,
      }, res.status as any);
    }

    const data = await res.json() as any;
    return c.json({
      token: data.name,
      model: LIVE_MODEL,
      expireTime,
      tools: GEMINI_FUNCTION_DECLARATIONS,
    });
  } catch (err: any) {
    return c.json({
      error: `Failed to generate ephemeral session token: ${err.message}`,
    }, 500);
  }
});

/**
 * POST /api/voice/tools/execute
 * Direct edge execution endpoint for tools invoked by the Gemini Live session.
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
 * Cloudflare Worker WebSocket proxy to Gemini Live API.
 * Bridges client browser WebSocket with Google Gemini Live WebSocket,
 * enabling edge execution of function calls and low-latency audio relay.
 */
voiceRouter.get('/ws', async (c) => {
  const upgradeHeader = c.req.header('Upgrade');
  if (!upgradeHeader || upgradeHeader.toLowerCase() !== 'websocket') {
    return c.text('Expected Upgrade: websocket', 426);
  }

  const url = new URL(c.req.url);
  const customKey = url.searchParams.get('key') || '';
  const token = url.searchParams.get('token') || '';
  const threadId = url.searchParams.get('thread_id') || '';
  const apiKey = customKey || c.env.GEMINI_API_KEY || '';

  if (!apiKey && !token) {
    return c.text('Gemini API key or ephemeral token is required.', 401);
  }

  // Construct upstream Google Gemini Live WebSocket URL
  let upstreamWsUrl = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent';
  if (token) {
    upstreamWsUrl += `?access_token=${encodeURIComponent(token)}`;
  } else {
    upstreamWsUrl += `?key=${encodeURIComponent(apiKey)}`;
  }

  // Create WebSocket pair for Cloudflare Edge
  const pair = new WebSocketPair();
  const [clientWs, serverWs] = Object.values(pair);

  // Accept incoming client connection
  serverWs.accept();

  // Async bridge task that connects upstream to Gemini
  const bridgeTask = async () => {
    let upstreamWs: WebSocket | null = null;

    try {
      upstreamWs = new WebSocket(upstreamWsUrl);

      // Upstream opened
      upstreamWs.addEventListener('open', () => {
        try {
          serverWs.send(JSON.stringify({ type: 'status', message: 'connected_to_gemini' }));
        } catch {}
      });

      // Relay client messages to Gemini
      serverWs.addEventListener('message', async (event) => {
        try {
          if (!upstreamWs || upstreamWs.readyState !== WebSocket.OPEN) return;

          const rawData = event.data;
          if (typeof rawData === 'string') {
            upstreamWs.send(rawData);
          } else {
            upstreamWs.send(rawData);
          }
        } catch (err: any) {
          console.error('Error forwarding client message to Gemini:', err);
        }
      });

      // Relay Gemini responses to client & intercept function calls
      upstreamWs.addEventListener('message', async (event) => {
        try {
          if (serverWs.readyState !== WebSocket.OPEN) return;

          const rawData = event.data;
          if (typeof rawData === 'string') {
            let parsed: any = null;
            try {
              parsed = JSON.parse(rawData);
            } catch {}

            // Check if model triggered a function call
            const toolCallPart = parsed?.serverContent?.modelTurn?.parts?.find((p: any) => p.functionCall);
            if (toolCallPart?.functionCall) {
              const fnCall = toolCallPart.functionCall;
              const fnName = fnCall.name;
              const fnArgs = fnCall.args || {};
              const fnId = fnCall.id || 'call_1';

              // Notify client of active tool execution
              try {
                serverWs.send(JSON.stringify({
                  type: 'tool_executing',
                  tool: fnName,
                  args: fnArgs,
                  call_id: fnId,
                }));
              } catch {}

              // Execute tool on Cloudflare Edge
              const toolResult = await executeEdgeTool(fnName, fnArgs, { db: c.env.DB, threadId });
              const toolOutput = toolResult.result !== undefined ? toolResult.result : { error: toolResult.error };

              // Send toolResponse back to Gemini so it can speak the result
              if (upstreamWs && upstreamWs.readyState === WebSocket.OPEN) {
                const responseMessage = {
                  toolResponse: {
                    functionResponses: [
                      {
                        response: { output: toolOutput },
                        id: fnId,
                      },
                    ],
                  },
                };
                upstreamWs.send(JSON.stringify(responseMessage));
              }

              // Notify client tool completed
              try {
                serverWs.send(JSON.stringify({
                  type: 'tool_finished',
                  tool: fnName,
                  result: toolOutput,
                  call_id: fnId,
                }));
              } catch {}
            }

            // Always forward the original message to client
            serverWs.send(rawData);
          } else {
            serverWs.send(rawData);
          }
        } catch (err: any) {
          console.error('Error forwarding Gemini response to client:', err);
        }
      });

      // Handle close & error events
      const cleanup = () => {
        try { if (upstreamWs) upstreamWs.close(); } catch {}
        try { serverWs.close(); } catch {}
      };

      upstreamWs.addEventListener('close', () => cleanup());
      upstreamWs.addEventListener('error', (e) => {
        console.error('Upstream Gemini WebSocket error:', e);
        cleanup();
      });
      serverWs.addEventListener('close', () => cleanup());
      serverWs.addEventListener('error', (e) => {
        console.error('Client WebSocket error:', e);
        cleanup();
      });
    } catch (err: any) {
      console.error('Failed to initialize WebSocket bridge:', err);
      try {
        serverWs.send(JSON.stringify({ type: 'error', message: err.message }));
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

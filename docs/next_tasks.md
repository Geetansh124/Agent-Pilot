# Agent-Pilot Next Tasks & Roadmap
## Cloudflare Edge Platform: Post-Deployment Enhancements & Next Milestones

| Milestone | Objective | Target Horizon |
|---|---|---|
| **Phase 1: Identity & SSO** | Google OAuth & Gmail 1-Click SSO Live Verification | Immediate |
| **Phase 2: Edge RAG & Parsing** | Robust PDF Binary Decompression & Cloudflare Vectorize | Sprint 1 |
| **Phase 3: Edge Agent Tools** | Multi-Provider Real-Time Voice (Gemini, OpenAI, ElevenLabs, Anthropic, Groq, Deepgram) & Edge Tool Porting | Sprint 2–3 |
| **Phase 4: Object Storage** | Cloudflare R2 Raw Binary Document Storage | Sprint 3 |
| **Phase 5: Performance & Domain** | Custom Domain, Edge Rate-Limiting & Observability | Sprint 4 |

---

## Phase 1: Identity & Google/Gmail SSO Activation

### Task 1.1 — Register Cloudflare Edge Origin in Google Cloud Console
* **Priority**: High (Immediate)
* **Components**: Google Cloud Console, [`frontend/app/components/AuthModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/AuthModal.tsx)
* **Objective**: Authorize `https://agent-pilot.soapy-pint.workers.dev` in Google OAuth credentials to enable 1-click Gmail/Google sign-in.
* **Acceptance Criteria**:
  - [ ] Add `https://agent-pilot.soapy-pint.workers.dev` to Authorized JavaScript origins under Client ID `440572861576-iikfhmgbjkd4c8urtnioq0feicu8fpa5.apps.googleusercontent.com`.
  - [ ] Add `https://agent-pilot.soapy-pint.workers.dev` to Authorized redirect URIs.
  - [ ] Test 1-click Google Sign-in on live deployment: user profile, avatar, and JWT session created automatically in D1.

### Task 1.2 — Cloudflare API Token Network Range Update
* **Priority**: Medium
* **Components**: Cloudflare Dashboard API Tokens
* **Objective**: Remove static IP filtering constraint (error code 9109) on `CLOUDFLARE_API_TOKEN` to allow seamless deployment from dynamic ISP connections.
* **Acceptance Criteria**:
  - [ ] Token permissions updated to allow all IPs or local CIDR block.
  - [ ] `wrangler deploy` executes without IP restriction errors.

---

## Phase 2: Edge RAG & Advanced Document Parsing

### Task 2.1 — Edge PDF Binary Text Parser (`unpdf` / `pdf-parse`)
* **Priority**: High
* **Components**: [`cloudflare/src/routes/documents.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/documents.ts)
* **Objective**: Replace ASCII-only regex fallback with an isolate-compatible streaming PDF parser (`unpdf`) to decompress `/FlateDecode` streams in large research papers (e.g. `agroarth...pdf`).
* **Acceptance Criteria**:
  - [ ] PDF binary streams properly parsed into clean UTF-8 text on upload.
  - [ ] Eliminates "0 chunks" badge for scanned or binary-encoded PDFs in Document Cloud Hub.
  - [ ] Generates meaningful chunks and previews for multi-page documents.

### Task 2.2 — Native Cloudflare Vectorize & Workers AI Embeddings
* **Priority**: Medium
* **Components**: Cloudflare Vectorize, Workers AI (`@cf/baai/bge-base-en-v1.5`)
* **Objective**: Enable hybrid vector similarity search directly on Cloudflare Edge without external ML instances.
* **Acceptance Criteria**:
  - [ ] Create Vectorize index: `wrangler vectorize create agent-pilot-vectors --dimensions=768 --metric=cosine`.
  - [ ] Uploaded document chunks embedded via Workers AI and indexed in Vectorize.
  - [ ] Chat query searches top-5 nearest neighbor chunks before prompting NVIDIA NIM.

---

## Phase 3: TypeScript Edge Agent Tools & Multi-Provider Real-Time Voice

### Task 3.1 — Native Tool Execution Engine (Completed)
* **Priority**: High
* **Components**: [`cloudflare/src/routes/chat.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/chat.ts), [`cloudflare/src/tools/`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/tools/)
* **Status**: [x] Completed & Deployed
* **Delivered Capabilities**:
  - [x] Ported tools into modular TypeScript workers (`calculator.ts`, `temporal.ts`, `web.ts`, `tabular.ts`, `index.ts`).
  - [x] Standard OpenAI & Gemini function calling schemas in [`definitions.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/tools/definitions.ts).
  - [x] Real-time tool execution endpoint `/api/voice/tools/execute`.
  - [x] Automated tool routing and observations during chat SSE streaming.
  - [x] Frontend displays real-time tool badges (`activeTool` animation).

### Task 3.2 — Human-In-The-Loop (HITL) Execution Safeguards
* **Priority**: Low
* **Components**: [`cloudflare/src/routes/chat.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/chat.ts)
* **Objective**: Require user approval before executing sensitive operations (external API calls, large file operations).
* **Acceptance Criteria**:
  - [ ] Sensitive tool actions pause stream and send an interactive confirmation payload.
  - [ ] User can approve or reject execution directly from the chat UI.

### Task 3.3 — Gemini Live API & Full-Screen Voice Flight Deck (Completed)
* **Priority**: High
* **Components**: [`cloudflare/src/routes/voice.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/voice.ts), [`frontend/app/components/VoiceFlightDeckModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/VoiceFlightDeckModal.tsx)
* **Status**: [x] Completed & Deployed
* **Delivered Capabilities**:
  - [x] Cloudflare Edge WebSocket proxy `/api/voice/ws` bridging client and Google Gemini Live API.
  - [x] Dual-credential authentication: server `GEMINI_API_KEY` ephemeral tokens (`/api/voice/token`) with client custom key override.
  - [x] Recommended model `gemini-3.1-flash-live-preview` with configurable thinking level (`minimal`, `low`, `medium`, `high`).
  - [x] Web Audio PCM pipeline: 16kHz 16-bit linear PCM microphone capture & 24kHz speaker playback with zero-latency interruption support.
  - [x] Real-time audio canvas wave visualizer, live dialogue transcription, tool execution telemetry HUD, and voice persona switcher.

### Task 3.4 — PWA Mobile Web First & Android Companion (Completed)
* **Priority**: Medium
* **Components**: [`frontend/public/manifest.json`](file:///d:/Main/Projects/Agent-Pilot/frontend/public/manifest.json), [`docs/android_companion.md`](file:///d:/Main/Projects/Agent-Pilot/docs/android_companion.md)
* **Status**: [x] Completed & Deployed
* **Delivered Capabilities**:
  - [x] PWA web app manifest with standalone display, maskable icons, and dark ambient theme color `#09090b`.
  - [x] Mobile viewport & notch optimization (`viewport-fit=cover`).
  - [x] Native Android Companion packaging and CLI deployment guide using Trusted Web Activities (TWA).

### Task 3.5 — Voice Provider Adapter Layer (Completed)
* **Priority**: High
* **Components**: `cloudflare/src/voice/`, [`cloudflare/src/routes/voice.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/voice.ts), [`frontend/app/components/VoiceFlightDeckModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/VoiceFlightDeckModal.tsx)
* **Status**: [x] Completed & Integrated
* **Objective**: Abstract real-time voice into a provider-agnostic adapter interface so the Flight Deck UI, tool execution bridge, and audio pipeline work identically regardless of upstream backend.
* **Acceptance Criteria**:
  - [x] `VoiceProvider` TypeScript interface: `connect()`, `sendAudio()`, `onAudio()`, `onTranscript()`, `onToolCall()`, `disconnect()`.
  - [x] `GeminiLiveProvider` adapter extracted from existing [`voice.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/voice.ts) WebSocket bridge.
  - [x] Provider selection via `?provider=gemini|openai|elevenlabs|anthropic|groq|deepgram` query param on `/api/voice/ws`.
  - [x] Flight Deck Settings drawer: provider picker cards alongside voice and latency controls.
  - [x] Per-provider API key storage in `localStorage` (`AGENT_PILOT_{PROVIDER}_KEY`).

### Task 3.6 — OpenAI Realtime API Integration (Completed)
* **Priority**: High
* **Components**: `cloudflare/src/voice/openai.ts`
* **Status**: [x] Completed & Integrated
* **Objective**: Integrate the OpenAI Realtime API (`gpt-4o-realtime-preview`) for bidirectional audio streaming with native function calling.
* **Acceptance Criteria**:
  - [x] `OpenAIRealtimeProvider` adapter: WebSocket to `wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview`.
  - [x] Ephemeral session token exchange via `/api/voice/token?provider=openai`.
  - [x] Audio format negotiation: 24kHz PCM input/output (OpenAI native format).
  - [x] Server VAD (Voice Activity Detection) mode with configurable silence thresholds.
  - [x] Function calling bridge: translate OpenAI tool_call events → Edge tool execution → tool_result response.
  - [x] Voice selection: `alloy`, `ash`, `ballad`, `coral`, `echo`, `sage`, `shimmer`, `verse`.

### Task 3.7 — ElevenLabs Conversational AI Integration (Completed)
* **Priority**: Medium
* **Components**: `cloudflare/src/voice/elevenlabs.ts`
* **Status**: [x] Completed & Integrated
* **Objective**: Integrate ElevenLabs Conversational AI WebSocket API for ultra-low-latency voice with premium cloned/synthetic voices.
* **Acceptance Criteria**:
  - [x] `ElevenLabsProvider` adapter: WebSocket to `wss://api.elevenlabs.io/v1/convai/conversation`.
  - [x] Signed URL authentication via ElevenLabs `/v1/convai/conversation/get_signed_url`.
  - [x] μ-law 8kHz and PCM 16kHz audio codec support with automatic format detection.
  - [x] Agent-side tool execution: intercept `agent_response` → `tool` actions and relay to Edge tools.
  - [x] Voice selection from ElevenLabs voice library (voice ID picker in Settings).
  - [x] Interruption handling via `user_transcript` / `interruption` events.

### Task 3.8 — Anthropic Claude Voice Integration (Completed)
* **Priority**: Medium
* **Components**: `cloudflare/src/voice/anthropic.ts`
* **Status**: [x] Completed & Integrated
* **Objective**: Integrate Anthropic's Claude real-time voice capabilities using the Messages API streaming with speech synthesis.
* **Acceptance Criteria**:
  - [x] `AnthropicVoiceProvider` adapter: SSE streaming to `https://api.anthropic.com/v1/messages` with `stream: true`.
  - [x] Client-side TTS bridge: pipe Claude streaming text output → Web Speech API engine for audio playback.
  - [x] Client-side STT bridge: browser `SpeechRecognition` / audio streaming text input to Claude.
  - [x] Tool use integration: Claude `tool_use` blocks → Edge tool execution → `tool_result` injection.
  - [x] Model selection: `claude-3-7-sonnet-20250219`, `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`.
  - [x] Upgrade path: auto-switch to native Anthropic voice WebSocket when API launches.

### Task 3.9 — Groq Whisper + TTS Real-Time Pipeline (Completed)
* **Priority**: Medium
* **Components**: `cloudflare/src/voice/groq.ts`
* **Status**: [x] Completed & Integrated
* **Objective**: Build a real-time voice pipeline using Groq's ultra-fast Whisper STT and LLM inference, paired with a TTS backend for audio output.
* **Acceptance Criteria**:
  - [x] `GroqVoiceProvider` adapter: composable STT → LLM → TTS pipeline over REST.
  - [x] Speech-to-Text: Groq Whisper (`whisper-large-v3-turbo`) via `/v1/audio/transcriptions` with in-memory WAV buffer generation.
  - [x] LLM Inference: Groq `llama-3.3-70b-versatile` or `llama-3.1-8b-instant` streaming completions.
  - [x] Text-to-Speech: pluggable TTS backend (browser Web Speech API fallback + audio chunking).
  - [x] Tool calling via Groq function calling → Edge tool execution loop.
  - [x] Configurable chunk duration for latency vs. accuracy trade-off.

### Task 3.10 — Deepgram Voice Agent API Integration (Completed)
* **Priority**: Low
* **Components**: `cloudflare/src/voice/deepgram.ts`
* **Status**: [x] Completed & Integrated
* **Objective**: Integrate Deepgram's Voice Agent API for real-time conversational AI with best-in-class STT accuracy.
* **Acceptance Criteria**:
  - [x] `DeepgramVoiceProvider` adapter: WebSocket to `wss://agent.deepgram.com/agent`.
  - [x] Configuration payload: STT model (`nova-3`), TTS model (`aura-asteria-en`), LLM provider delegation.
  - [x] Linear16 PCM audio input at 16kHz, MP3/PCM output playback.
  - [x] Function calling via `functions` config → Edge tool execution → `inject` response.
  - [x] Barge-in / interruption support via Deepgram's endpointing configuration.

### Task 3.11 — Unified Voice Provider Dashboard & Telemetry (Completed)
* **Priority**: Low
* **Components**: [`frontend/app/components/VoiceFlightDeckModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/VoiceFlightDeckModal.tsx), [`frontend/app/components/VoiceSettingsDrawer.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/VoiceSettingsDrawer.tsx), [`frontend/app/components/voiceProviders.ts`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/voiceProviders.ts)
* **Status**: [x] Completed & Integrated
* **Objective**: Expose a unified Flight Deck HUD showing provider-specific metrics and voice selection.
* **Acceptance Criteria**:
  - [x] Real-time latency badge (ms ping/TTFB) per provider in the Flight Deck header.
  - [x] Provider health indicator (connection state, reconnect count, error message handling).
  - [x] Multi-engine selector with per-provider custom API key security and persona customization.

---

## Phase 4: Cloudflare R2 Raw Object Storage

### Task 4.1 — Enable R2 Bucket & Upload Pre-Signed URLs
* **Priority**: Medium
* **Components**: [`cloudflare/wrangler.toml`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/wrangler.toml), [`cloudflare/src/routes/documents.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/documents.ts)
* **Objective**: Store full original document files (PDFs, images, data files) in Cloudflare R2 bucket (`agent-pilot-storage`).
* **Acceptance Criteria**:
  - [ ] Enable R2 in Cloudflare Dashboard: `wrangler r2 bucket create agent-pilot-storage`.
  - [ ] Bind bucket in `wrangler.toml` (`[[r2_buckets]] binding = "STORAGE"`).
  - [ ] Document download endpoint `/api/documents/:id/download` streams original file directly from R2.

---

## Phase 5: Production Domain, Caching & Observability

### Task 5.1 — Custom Domain Mapping
* **Priority**: Low
* **Components**: Cloudflare DNS & Custom Worker Domains
* **Objective**: Route custom branded domain (e.g. `app.yourdomain.com`) directly to the Cloudflare Worker.
* **Acceptance Criteria**:
  - [ ] Automatic SSL certificate provisioned with HTTP/3 and 0-RTT support.
  - [ ] Updated OAuth authorized origins to include custom domain.

### Task 5.2 — Edge Token Usage Tracking & Rate Limiting
* **Priority**: Medium
* **Components**: Cloudflare D1 `audit_logs` table, Workers KV
* **Objective**: Track prompt tokens, completion tokens, and latency per user to prevent abuse.
* **Acceptance Criteria**:
  - [ ] Sliding-window rate limiter (60 requests/minute per IP/user) using Cloudflare KV.
  - [ ] Token usage logged to D1 for admin dashboard inspection.

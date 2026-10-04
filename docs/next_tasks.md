# Agent-Pilot Next Tasks & Roadmap
## Cloudflare Edge Platform: Post-Deployment Enhancements & Next Milestones

| Milestone | Objective | Target Horizon |
|---|---|---|
| **Phase 1: Identity & SSO** | Google OAuth & Gmail 1-Click SSO Live Verification | Immediate |
| **Phase 2: Edge RAG & Parsing** | Robust PDF Binary Decompression & Cloudflare Vectorize | Sprint 1 |
| **Phase 3: Edge Agent Tools** | Function Calling & Porting Python Tools to TypeScript | Sprint 2 |
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

## Phase 3: TypeScript Edge Agent Tools & Gemini Live API

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

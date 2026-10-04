# Agent-Pilot Next Tasks & Engineering Roadmap (v2)
## Post-Phase 3 Edge Platform Enhancements & Upcoming Milestones

| Milestone | Objective | Priority | Target Horizon |
|---|---|---|---|
| **Phase 1: Identity & SSO** | Google Cloud Console Origin Registration & 1-Click Gmail Auth | High | Immediate |
| **Phase 2: Edge RAG & Parsing** | Isolate-compatible PDF Parser (`unpdf`) & Cloudflare Vectorize | High | Sprint 1 |
| **Phase 4: Cloudflare R2 Storage** | Raw Object Storage Bucket & Pre-signed Direct Downloads | Medium | Sprint 2 |
| **Phase 5: Domain & Observability** | Custom Branded Domain, KV Rate Limiting & Audit Telemetry | Medium | Sprint 3 |
| **Phase 6: Multi-Modal Live Vision** | Camera & Screen Share JPEG Frame Streaming via Live API | Medium | Sprint 4 |
| **Phase 7: Native Android Packaging** | Bubblewrap TWA Compilation & Android CLI ADB Distribution | Low | Sprint 5 |

---

## Phase 1: Identity & Google/Gmail SSO Live Activation

### Task 1.1 — Register Cloudflare Edge Origin in Google Cloud Console
* **Priority**: High (Immediate)
* **Components**: Google Cloud Console, [`frontend/app/components/AuthModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/AuthModal.tsx)
* **Client ID**: `440572861576-iikfhmgbjkd4c8urtnioq0feicu8fpa5.apps.googleusercontent.com`
* **Objective**: Authorize production domain `https://agent-pilot.soapy-pint.workers.dev` to enable 1-click Google OAuth / Gmail sign-in.
* **Acceptance Criteria**:
  - [ ] Add `https://agent-pilot.soapy-pint.workers.dev` to Authorized JavaScript origins.
  - [ ] Add `https://agent-pilot.soapy-pint.workers.dev` to Authorized redirect URIs.
  - [ ] Verify live 1-click Google Sign-In popup without `origin_mismatch` (error 400).
  - [ ] Confirm automatic D1 user profile creation and JWT session persistence.

### Task 1.2 — Cloudflare API Token Network Range Configuration
* **Priority**: Low
* **Components**: Cloudflare Dashboard API Tokens
* **Objective**: Relax static IP restriction (error code 9109) on `CLOUDFLARE_API_TOKEN` for deployments across dynamic client ISPs.
* **Acceptance Criteria**:
  - [ ] Token permissions updated to allow all IP CIDRs.
  - [ ] `wrangler deploy` executes without IP restriction errors.

---

## Phase 2: Edge RAG & Advanced Document Parsing

### Task 2.1 — Edge PDF Binary Text Parser (`unpdf`)
* **Priority**: High
* **Components**: [`cloudflare/src/routes/documents.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/documents.ts)
* **Objective**: Replace ASCII-only regex fallback with `unpdf` (V8 isolate-compatible) to decompress `/FlateDecode` streams in research papers and scanned PDFs.
* **Acceptance Criteria**:
  - [ ] Binary PDF streams properly decompressed into clean UTF-8 text on upload.
  - [ ] Eliminates "0 chunks" badge for binary-compressed documents in Document Cloud Hub.
  - [ ] Produces clean semantic chunk boundaries for multi-page documents.

### Task 2.2 — Native Cloudflare Vectorize & Workers AI Embeddings
* **Priority**: Medium
* **Components**: Cloudflare Vectorize, Workers AI (`@cf/baai/bge-base-en-v1.5`)
* **Objective**: Replace in-memory string search with dense vector similarity search directly on Cloudflare Edge.
* **Acceptance Criteria**:
  - [ ] Provision Vectorize index: `wrangler vectorize create agent-pilot-vectors --dimensions=768 --metric=cosine`.
  - [ ] Document chunks embedded via Workers AI and indexed into Vectorize on upload.
  - [ ] Chat query retrieves top-5 nearest neighbor chunks before synthesizing answers.

---

## Phase 4: Cloudflare R2 Raw Object Storage

### Task 4.1 — Enable R2 Bucket & Upload Pre-Signed URLs
* **Priority**: Medium
* **Components**: [`cloudflare/wrangler.toml`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/wrangler.toml), [`cloudflare/src/routes/documents.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/documents.ts)
* **Objective**: Store full original document files (PDFs, images, CSVs) in Cloudflare R2 bucket (`agent-pilot-storage`).
* **Acceptance Criteria**:
  - [ ] Create R2 bucket: `wrangler r2 bucket create agent-pilot-storage`.
  - [ ] Bind bucket in `wrangler.toml`: `[[r2_buckets]] binding = "STORAGE" bucket_name = "agent-pilot-storage"`.
  - [ ] Implement download endpoint `/api/documents/:id/download` streaming original binary files with proper Content-Disposition headers.

---

## Phase 5: Custom Domain, Rate Limiting & Observability

### Task 5.1 — Custom Domain Mapping
* **Priority**: Low
* **Components**: Cloudflare DNS & Custom Worker Domains
* **Objective**: Bind custom domain (e.g. `pilot.yourdomain.com`) to the Cloudflare Worker.
* **Acceptance Criteria**:
  - [ ] TLS certificate automatically provisioned with HTTP/3 support.
  - [ ] Google OAuth authorized origins updated to include the custom domain.

### Task 5.2 — Edge Token Usage Tracking & KV Rate Limiting
* **Priority**: Medium
* **Components**: Workers KV, Cloudflare D1 `audit_logs` table
* **Objective**: Implement sliding-window rate limiting and track token consumption per user.
* **Acceptance Criteria**:
  - [ ] 60 requests/minute per IP rate limiter backed by Workers KV.
  - [ ] Prompt tokens, completion tokens, and latency logged to D1 table.

---

## Phase 6: Multi-Modal Live Video & Screen Sharing

### Task 6.1 — Video/Screen Frame Streaming to Gemini Live
* **Priority**: Medium
* **Components**: [`frontend/app/components/VoiceFlightDeckModal.tsx`](file:///d:/Main/Projects/Agent-Pilot/frontend/app/components/VoiceFlightDeckModal.tsx), [`cloudflare/src/routes/voice.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/routes/voice.ts)
* **Objective**: Allow users to share camera video or screen captures directly in the Live Voice Flight Deck.
* **Acceptance Criteria**:
  - [ ] Add Screen Share / Camera toggle buttons to the Flight Deck HUD.
  - [ ] Capture 1 fps JPEG frames via `canvas.toDataURL('image/jpeg', 0.6)`.
  - [ ] Stream frames to Gemini Live WebSocket:
    `{ realtimeInput: { video: { data: base64Frame, mimeType: "image/jpeg" } } }`.
  - [ ] Model responds to visual and spoken queries simultaneously with low latency.

---

## Phase 7: Native Android Companion Packaging

### Task 7.1 — Android TWA Compilation & Distribution
* **Priority**: Low
* **Components**: [`docs/android_companion.md`](file:///d:/Main/Projects/Agent-Pilot/docs/android_companion.md), `@bubblewrap/cli`, Android SDK
* **Objective**: Package the mobile PWA into a signed native Android APK.
* **Acceptance Criteria**:
  - [ ] Generate digital asset links for domain verification: `/.well-known/assetlinks.json`.
  - [ ] Build signed release APK using Bubblewrap CLI.
  - [ ] Validate fullscreen launch and microphone permissions on Android Virtual Device (AVD).

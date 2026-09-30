# Engineering & Swarm Governance Rules
## Multi-Tenant Cloud Architecture & System Boundaries

These rules govern the development, testing, security, and multi-agent coordination of Agent-Pilot.

---

## 1. Zero-Leak Multi-Tenancy Rules

1. **Mandatory Tenant Scoping (`user_id`)**:
   * Every database table representing user data (`threads`, `documents`, `messages`, `workspace_files`) MUST include a foreign key to `users.id`.
   * Every SQL query or ORM call MUST include `WHERE user_id = :user_id`. Never write a naked query without tenant scoping.
2. **Controller Boundary Verification**:
   * All protected API routes MUST depend on `get_current_user`.
   * Never accept `user_id` as a client-provided path parameter or query parameter without verifying it against the authenticated JWT `token.sub`.
3. **Storage Path Sanitization**:
   * Google Drive folder IDs, file names, and local cache paths must be generated using `uuid.uuid4()`. Never concatenate raw client filenames into filesystem paths.

---

## 2. Google Drive Storage & Resilience Rules

1. **Atomic Ingestion & Sync**:
   * When uploading a file, write to temporary storage first, upload to Google Drive, verify checksum/file ID, and only commit the database record once the upload is confirmed.
2. **Idempotent Retrieval**:
   * Vector indices must be cached locally in `storage/users/{user_id}/vectors/{doc_id}`. If absent on cold start, download once from Google Drive into cache.
3. **Graceful Degraded Mode**:
   * If the Google Drive API reaches rate limits or credentials are invalid, the backend MUST gracefully log the warning and fall back to local persistent volume storage without crashing user chats.

---

## 3. Code Standards & Architecture Constraints

1. **File Size Limit (< 500 Lines)**:
   * Keep every code file strictly under 500 lines. Break large components into modular helpers, custom hooks, or separate controller routers.
2. **Type Safety & No `any`**:
   * Python code must use explicit type annotations (`pydantic.BaseModel`, `Optional`, `List`, `Dict`).
   * TypeScript code must avoid `any` and define explicit interfaces in `types.ts`.
3. **Zero Secrets in Repository**:
   * Never commit `.env`, `credentials.json`, service account keys, or API tokens.
   * Service account credentials must be provided exclusively via `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_APPLICATION_CREDENTIALS` environment variables.

---

## 4. Ruflo Swarm Coordination Rules

1. **Named Roles & SendMessage Pipelines**:
   * Agents coordinate via structured handoffs:
     `system-architect` ──► `coder` ──► `tester` ──► `reviewer`
2. **Worktree Isolation**:
   * Writing agents work in distinct scopes without overlapping conflicting edits.
3. **Evidence-Based Validation**:
   * No task is marked complete without passing build tests (`npm run build` and backend test suites).

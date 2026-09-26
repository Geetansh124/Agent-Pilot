# Agent-Pilot: Fully Agentic Control System — Feature Reference

> A complete inventory of every subsystem, tool, agent, and integration implemented in the Agent-Pilot codebase, with source-file references.

---

## 1. Multi-Agent Orchestration

### 1.1 Supervisor Agent (`src/agents/supervisor.py`)
- **Intent Classification** — Classifies incoming tasks into specialist domains (coder, researcher, data-analyst, general) using keyword heuristics.
- **Automatic Delegation** — Routes tasks to the correct specialist sub-agent and aggregates their structured outputs.
- **Manual Role Override** — Callers can force a specific agent role instead of auto-classification.
- **LangChain Tool Exposure** — Exported as `route_to_specialist` so the LLM can autonomously decide to delegate.

### 1.2 Research Agent (`src/agents/research_agent.py`)
- **Multi-Source Retrieval** — Combines indexed document search (via `HybridRetriever`) with live web search (Tavily / DuckDuckGo).
- **Source Citation Tracking** — Generates markdown citations with provenance for every finding.
- **Executive Summary Synthesis** — Aggregates findings into a structured research report.

### 1.3 Coding Agent (`src/agents/coding_agent.py`)
- **Syntax Validation** — Validates Python code via `ast.parse()` before any execution.
- **Sandboxed Execution** — Runs code safely through the `python_interpreter` tool.
- **Workspace File Management** — Writes code to thread-isolated workspace files via the persistent storage backend.

### 1.4 Data Analyst Agent (`src/agents/data_agent.py`)
- **Tabular Data Analysis** — Parses CSV / JSON data, computes column statistics (min, max, avg, unique counts, type detection).
- **Read-Only SQL Queries** — Executes safe SELECT queries against the system SQLite database.
- **Chart-Ready Outputs** — Returns structured summaries suitable for visualization.

### 1.5 Inter-Agent Communication (`src/agents/shared_state.py`)
- **Message Bus** — `InterAgentMessageBus` provides named agent-to-agent messaging with sender, recipient, content, summary, and artifact payloads.
- **Typed Agent Roles** — `AgentRole` enum (Supervisor, Researcher, Coder, Data-Analyst, General) ensures type-safe routing.
- **Thread-Scoped History** — All messages are partitioned by thread ID for isolation.

---

## 2. Autonomous Planning & Self-Evaluation

### 2.1 ReAct Planner (`src/agent/planner.py`)
- **Structured Plan Creation** — `create_plan` tool generates numbered multi-step execution plans from a goal and step list.
- **Step Progress Tracking** — `update_plan_step` updates individual steps with status (`in_progress`, `completed`, `blocked`, `skipped`) and result summaries.
- **Goal Reflection** — `reflect_on_goal` tool evaluates whether collected observations are sufficient to answer the user's goal or if more tool calls are needed.

### 2.2 Critic & Hallucination Detector (`src/agent/critic.py`)
- **Factual Grounding Score** — Measures token-level overlap between the assistant's response and the source context.
- **Hallucination Detection** — Flags responses with < 15% factual overlap with context as potential hallucinations.
- **Citation Completeness Check** — Detects whether document-grounded responses include proper source citations.
- **Question Responsiveness** — Verifies that key terms from the user's question appear in the response.

### 2.3 Human-in-the-Loop Approval Gates (`src/agent/hitl.py`)
- **Sensitive Tool Registry** — `delete_workspace_file`, `write_workspace_file`, `call_api`, and `run_code_task` require explicit user approval.
- **Approval Workflow** — Pending requests can be approved or rejected via REST API (`/api/hitl/{id}/approve`, `/api/hitl/{id}/reject`).
- **Auto-Approve Mode** — Configurable flag for development/testing bypasses.

---

## 3. Retrieval-Augmented Generation (RAG)

### 3.1 Hybrid Retriever (`src/rag/hybrid_retriever.py`)
- **Dense Vector Search** — FAISS-backed MMR (Maximal Marginal Relevance) or similarity search using `sentence-transformers/all-MiniLM-L6-v2` embeddings.
- **Sparse BM25 Keyword Matching** — Token-overlap scoring for lexical recall.
- **Reciprocal Rank Fusion (RRF)** — Combines dense (70% weight) and sparse (30% weight) rankings with configurable `rrf_k=60`.
- **Provenance Citations** — Every result includes `[filename, Page N]` citation strings with chunk metadata.

### 3.2 Multi-Document Manager (`src/rag/multi_doc_manager.py`)
- **Per-Thread Indexing** — Each conversation thread maintains its own isolated FAISS vector store.
- **Incremental Merging** — New documents are chunked and merged into the existing thread index without rebuilding.
- **Multi-Format Ingestion** — Supports PDF, DOCX, CSV, JSON, TXT, and Markdown via `document_loader.py`.
- **Recursive Text Splitting** — Uses `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap) with hierarchical separators.

### 3.3 Embedding Model
- **HuggingFace `all-MiniLM-L6-v2`** — Lightweight, fast sentence embeddings for real-time document indexing.

---

## 4. Agent Tool Suite

### 4.1 Web Search (`src/tools/web_search.py`)
- **Tavily API** (primary) with **DuckDuckGo** fallback for zero-config search.
- Returns structured results: title, URL, content snippet, relevance score, and optional direct answers.

### 4.2 Web Scraper (`src/tools/web_scrape.py`)
- **Structured Content Extraction** — Parses titles, meta descriptions, headings (H1-H3), paragraphs, hyperlinks, and HTML tables.
- **SSRF Protection** — Validates URLs against localhost, loopback, private, and reserved IP ranges before fetching.
- **Content Sanitization** — Strips scripts, styles, navigation, footers, and SVGs.

### 4.3 REST API Caller (`src/tools/api_caller.py`)
- **Full HTTP Method Support** — GET, POST, PUT, DELETE, PATCH with structured parameters and JSON body.
- **SSRF Boundary Guards** — Blocks requests to private/internal networks and loopback interfaces.
- **Auto JSON Parsing** — Detects `application/json` responses and returns parsed data.

### 4.4 Database Query Tool (`src/tools/database_tool.py`)
- **Read-Only SQL Enforcement** — Only allows `SELECT`, `WITH`, and `EXPLAIN` statements.
- **Destructive Keyword Blocklist** — Blocks `DROP`, `ALTER`, `TRUNCATE`, `DELETE`, `UPDATE`, `INSERT`, `CREATE`, `ATTACH`, `GRANT`, and more.
- **SQL Injection Prevention** — Blocks stacked (multi-statement) queries.

### 4.5 Workspace File Tools (`src/tools/file_tools.py`)
- **Thread-Isolated Filesystem** — Read, write, list, and delete files scoped to each conversation thread.
- **Persistent Storage Delegation** — All operations pass through the active `StorageBackend` (Google Drive / Local / AWS).
- **Directory Traversal Protection** — `sanitize_relative_path()` blocks `..`, absolute paths, and backslash escapes.

### 4.6 Document Loader (`src/tools/document_loader.py`)
- **Multi-Format Parser** — Ingests PDF (PyPDF), DOCX (python-docx), CSV, JSON, TXT, and Markdown from raw byte streams.

### 4.7 Python Interpreter (`agent_tools.py`)
- **Sandboxed Code Execution** — Executes Python code with captured stdout and serializable local variable inspection.
- **Tabular Data Analyzer** — Parses CSV/JSON strings and computes per-column statistics (numeric: min/max/avg; categorical: unique counts).

---

## 5. Persistent Storage System

### 5.1 Storage Abstraction (`storage/base.py`)
- **Pluggable Backend Interface** — `StorageBackend` ABC defines a unified API for `save_document`, `upload_bytes`, `download_bytes`, `list_files`, `delete_file`, `health_check`, and FAISS vector store persistence.
- **Path Traversal Guards** — `sanitize_thread_id()` and `sanitize_relative_path()` enforce strict boundary validation.
- **Category-Based Organization** — Files are organized into categories: `documents`, `workspace`, `vectors`, `exports`, `attachments`, `audio`.
- **MIME Type Detection** — Built-in mapping for PDF, DOCX, JSON, CSV, Markdown, WAV, MP3, FAISS artifacts, and fallback `mimetypes.guess_type()`.

### 5.2 Google Drive Backend (`storage/google_drive.py`)
- **Service Account Authentication** — Authenticates via `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable (supports raw JSON or base64-encoded).
- **Folder Hierarchy Management** — Automatically creates `threads/{thread_id}/{category}/` subfolder trees inside the configured Drive folder.
- **FAISS Vector Store Persistence** — Uploads/downloads `index.faiss` and `index.pkl` artifacts for cross-session RAG continuity.

### 5.3 AWS S3 Backend (`storage/aws.py`)
- **Boto3 Integration** — Full S3 upload, download, list, and delete with thread-prefixed object keys.

### 5.4 Local Filesystem Backend (`storage/local.py`)
- **Development Mode** — Stores files under `workspaces_storage/{thread_id}/{category}/` on disk.

---

## 6. Long-Term Memory

### 6.1 Memory Store (`src/memory/memory_store.py`)
- **Persistent SQLite Storage** — Facts, preferences, decisions, and goals are stored in the `long_term_memories` table.
- **Namespace Isolation** — Memories are partitioned by namespace (e.g., `global`, `thread:{id}`) and category (`fact`, `preference`, `decision`, `goal`).
- **Token-Based Relevance Retrieval** — Retrieval queries are scored by keyword overlap and ranked by relevance.
- **CRUD Operations** — `store_memory`, `retrieve_memory`, `delete_memory` are all exposed as LangChain tools.

### 6.2 Conversation Summarizer (`src/memory/summarizer.py`)
- **Context Window Compression** — When message history exceeds a configurable threshold (default 10), older turns are compressed into a `SystemMessage` summary.
- **Key Point Extraction** — Extracts declarative sentences (> 15 chars, excluding greetings) from conversation history.
- **Recent Message Preservation** — Always keeps the most recent 6 messages verbatim for continuity.

---

## 7. Knowledge Graph

### 7.1 Property Graph Engine (`src/graph/knowledge_graph.py`)
- **SQLite-Backed Graph** — Nodes and directed edges stored in `graph_nodes` and `graph_edges` tables with properties, weights, and timestamps.
- **Multi-Hop Subgraph Traversal** — BFS-based traversal up to configurable depth (default 2) following both inbound and outbound edges.
- **Heuristic Triple Extraction** — Rule-based regex extraction of `(Subject, Relation, Object)` triples from text (USES, IS_A, IMPLEMENTS, CONTAINS).
- **LangChain Tool** — `query_knowledge_graph` tool allows the LLM to query entity relations autonomously.

---

## 8. Security & Guardrails

### 8.1 Prompt Injection Detection (`src/security/guardrails.py`)
- **8 Jailbreak Signature Patterns** — Detects "ignore previous instructions", "DAN mode", "bypass safety filters", "forget all guidelines", and more.
- **Delimiter Manipulation Detection** — Flags excessive `<system>` or `[system]` tag abuse.
- **Input Size Limits** — Rejects prompts exceeding 20,000 characters.

### 8.2 Output Sanitization (`src/security/guardrails.py`)
- **Credential Redaction** — Automatically scrubs NVIDIA API keys (`nvapi-`), OpenAI keys (`sk-`), GitHub tokens (`ghp_`), Bearer tokens, emails, SSNs, and credit card numbers from all assistant outputs.

### 8.3 Authentication & RBAC (`src/auth/auth.py`)
- **JWT Token Generation** — RFC 7519-compatible HS256-signed tokens with configurable expiry (default 24h).
- **Password Hashing** — SHA-256 with random salt generation and constant-time comparison via `hmac.compare_digest()`.
- **Role-Based Claims** — Tokens carry `sub` (user ID), `role` (user/admin), `iat`, and `exp` claims.

### 8.4 Auth Middleware (`src/auth/middleware.py`)
- **Request-Level Token Verification** — Middleware for protecting endpoints with JWT validation.

---

## 9. Observability & Cost Control

### 9.1 Audit Logging (`src/observability/audit.py`)
- **SQLite Audit Ledger** — Every interaction (chat, tool call, HITL approval, security block, error) is recorded in the `audit_logs` table.
- **Structured Records** — Each entry includes timestamp, event type, thread ID, user ID, action, status, duration (ms), and JSON details.
- **Queryable API** — `GET /api/observability/audit` endpoint with thread and event-type filters (capped at 500 records).

### 9.2 Token Budgeting & Cost Tracking (`src/observability/cost.py`)
- **Multi-Model Pricing Tiers** — Tracks costs for `default`, `nemotron`, and `gpt-4o` models with per-million-token input/output rates.
- **Per-Request Budget Enforcement** — Blocks requests exceeding 16,384 tokens or total spending over $50 USD.
- **Per-Thread Usage Breakdown** — Tracks prompt tokens, completion tokens, total tokens, and cumulative USD cost per conversation thread.
- **Global Spending Dashboard** — `GET /api/observability/usage` returns aggregate token consumption and spending.

---

## 10. Task Automation & Workflows

### 10.1 Task Scheduler (`src/automation/scheduler.py`)
- **Interval-Based Scheduling** — Register recurring tasks with configurable interval (minimum 5 seconds).
- **Task Lifecycle Management** — Tasks can be active, paused, or cancelled with execution run counts and last result tracking.
- **LangChain Tool** — `schedule_recurring_task` allows the agent to autonomously create recurring jobs (e.g., daily reports, price checks).

### 10.2 Workflow Runner (`src/automation/workflow_runner.py`)
- **Multi-Step Pipeline Execution** — Executes ordered sequences of tool invocations with automatic result piping between steps.
- **Context Variable Substitution** — Supports `{{variable}}` template syntax for passing outputs from previous steps into subsequent step arguments.
- **Failure Handling** — Steps can be marked with `continue_on_failure` to allow partial pipeline completion.
- **Pre-Loaded Tool Registry** — Automatically registers `web_search`, `scrape_web`, `read/write_workspace_file`, `query_database`, `call_api`, `store/retrieve_memory`, `query_knowledge_graph`, and `evaluate_response`.

---

## 11. Voice Interface

### 11.1 Audio Processor (`src/voice/audio_processor.py`)
- **Speech-to-Text (STT)** — Accepts audio uploads in WAV, MP3, OGG, WebM, and M4A formats with duration estimation.
- **Text-to-Speech (TTS)** — Generates WAV audio containers with configurable voice and speed parameters.
- **Base64 Audio Streaming** — Returns synthesized audio as base64-encoded WAV data for browser playback.

---

## 12. Model Context Protocol (MCP)

### 12.1 MCP Server (`src/mcp/mcp_server.py`)
- **JSON-RPC 2.0 Compliance** — Implements `initialize`, `tools/list`, `tools/call`, and `ping` methods per the MCP specification.
- **Dynamic Tool Discovery** — Automatically exposes all registered tools with JSON Schema `inputSchema` descriptors.
- **Interoperability** — Compatible with Claude Code, Cursor, Antigravity, and any MCP-compliant client.
- **Pre-Registered Tools** — `web_search`, `scrape_web`, `read/write_workspace_file`, `query_database`, `call_api`, `store/retrieve_memory`, `create_plan`, `reflect_on_goal`, `route_to_specialist`.

### 12.2 MCP Client (`src/mcp/mcp_client.py`)
- **Outbound MCP Connectivity** — Allows Agent-Pilot to call tools exposed by external MCP servers.

---

## 13. API Server & Deployment

### 13.1 FastAPI Backend (`api_server.py`)
- **RESTful Endpoints** — Threads, chat, document upload, file management, HITL, observability, graph, automation, voice, critic, and MCP.
- **SSE Streaming** — `POST /api/chat/stream` delivers real-time token-by-token responses with tool-use events.
- **CORS Middleware** — Configurable `FRONTEND_ORIGIN` for cross-origin browser requests.
- **Rate Limiting** — Per-IP request throttling (configurable via environment variables).

### 13.2 Frontend (`frontend/`)
- **Next.js + Tailwind CSS** — Responsive chat interface with sidebar, document upload, and real-time streaming.
- **SSE Client** — Parses `token`, `tool`, `done`, and `error` events from the streaming endpoint.
- **File Upload** — Supports PDF, DOCX, TXT, MD, and CSV with drag-and-drop or click-to-upload.

### 13.3 Deployment Infrastructure
- **Docker** — `Dockerfile.api` for containerized backend deployment.
- **Render** — `render.yaml` service definition for managed hosting.
- **Vercel** — `vercel.json` configuration for frontend static deployment.
- **Google Cloud Run** — `cloudbuild.yaml` and `deploy_cloud_run.sh` for GCP deployment.

---

## Architecture Overview

```
+---------------------------------------------------------------+
|                     Next.js Frontend (Vercel)                 |
|   Chat UI | Document Upload | SSE Streaming | File Browser   |
+-----------------------------+---------------------------------+
                              | HTTPS
+-----------------------------v---------------------------------+
|                   FastAPI Backend (Render)                     |
|  +----------+ +----------+ +-----------+ +----------------+  |
|  | Chat API | | Doc API  | | Files API | | MCP Endpoint   |  |
|  +----+-----+ +----+-----+ +-----+-----+ +-------+--------+  |
|       |            |             |                |            |
|  +----v------------v-------------v----------------v--------+  |
|  |              LangGraph Agent Orchestrator                |  |
|  |  +----------+ +----------+ +----------+ +-----------+  |  |
|  |  |Supervisor| |Researcher| |  Coder   | |Data Analyst|  |  |
|  |  +----+-----+ +----+-----+ +----+-----+ +-----+-----+  |  |
|  |       +--------+----+------------+-------------+        |  |
|  |           InterAgentMessageBus                           |  |
|  +----------------------------------------------------------+  |
|       |                |               |           |           |
|  +----v---+ +----------v--+ +----------v--+ +-----v--------+ |
|  |Planner | |Hybrid RAG   | |Knowledge    | |Security      | |
|  |Critic  | |FAISS + BM25 | |Graph Engine | |Guardrails    | |
|  |HITL    | |Multi-Doc Mgr| |SQLite Graph | |JWT Auth      | |
|  +--------+ +-------------+ +-------------+ +--------------+ |
|       |                |               |           |           |
|  +----v---+ +----------v--+ +----------v--+ +-----v--------+ |
|  |Memory  | |Audit Logger | |Cost Tracker | |Voice / TTS   | |
|  |Store   | |SQLite Ledger| |Budget Caps  | |Audio Process | |
|  +--------+ +-------------+ +-------------+ +--------------+ |
+---------------------------+-----------------------------------+
                            |
              +-------------v--------------+
              |    Storage Backend Layer    |
              | Google Drive | AWS S3 | Local|
              +----------------------------+
```

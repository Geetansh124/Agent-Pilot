# Agent-Pilot — Project & Conversation Context

**Date & Time**: 2026-09-26  
**Project**: Agent-Pilot — Advanced Agentic Document Workspace & Multi-Agent RAG System  
**Repository**: `ChatBot/`

---

## 1. Executive Summary

During this engagement, the Agent-Pilot project was audited, extended, and fully verified across all **6 development phases** outlined in [`docs/features_list.md`](file:///d:/Main/Projects/ChatBot/docs/features_list.md). The codebase was upgraded from a basic PDF Q&A prototype to an enterprise-grade, autonomous, multi-agent AI system supporting MCP, streaming, hybrid RAG, guardrails, and knowledge graphs, while strictly adhering to code hygiene constraints (every file kept strictly under 500 lines, zero data loss, input validation at system boundaries).

---

## 2. Six-Phase Implementation Roadmap & Status

| Phase | Title | Key Additions | Status | Test Count |
|---|---|---|---|---|
| **Phase 1** | **Harden the Foundation** | Real SSE token streaming (`POST /api/chat/stream`), thread rename/deletion APIs, sliding-window IP rate limiter, Tenacity exponential retries. | Completed ✅ | 12 tests |
| **Phase 2** | **Rich Tools & Web** | Tavily search with DDG fallback, BeautifulSoup web scraper with SSRF protection, multi-format doc parser (PDF, DOCX, CSV, TXT, MD, JSON), sandboxed workspace files, read-only SQL, generic REST caller. | Completed ✅ | 18 tests |
| **Phase 3** | **Memory, RAG 2.0 & Planning** | SQLite long-term memory store (`store_memory`, `retrieve_memory`), history summarizer, hybrid dense+BM25 RAG with Reciprocal Rank Fusion (RRF), multi-doc FAISS manager, ReAct planner. | Completed ✅ | 5 tests |
| **Phase 4** | **Multi-Agent & MCP** | Supervisor routing engine (`route_to_specialist`), Research, Coding, and Data specialist agents, `InterAgentMessageBus` (`SendMessage`-first), MCP JSON-RPC 2.0 Server (`/mcp`) & Client. | Completed ✅ | 7 tests |
| **Phase 5** | **Security, HITL & Observability** | RFC 7519 JWT auth, salted password hashing, prompt injection scanner, automated PII & secret redactor, Human-in-the-Loop (HITL) approval gates, SQLite audit log, token/cost tracker. | Completed ✅ | 7 tests |
| **Phase 6** | **Advanced Agentic System** | SQLite Knowledge Graph & Graph RAG (`graph_nodes`, `graph_edges`), periodic task scheduler, autonomous multi-step workflow runner (`{{prev_output}}`), STT/TTS audio processor, reflection Critic agent. | Completed ✅ | 6 tests |

**Total Automated Test Suite**: **55 passed / 55 tests** (100% passing in 13.98s).  
**Frontend Status**: Next.js 14 production bundle compiled successfully with zero type or lint errors.

---

## 3. Architecture & File Structure

```
ChatBot/
├── langraph_rag_backend.py      # Core LangGraph graph, tools registration, checkpointing (<485 lines)
├── api_server.py                # FastAPI gateway, SSE streaming, auth, HITL, MCP mount (<475 lines)
├── agent_tools.py               # Legacy tool exports & wrappers (<300 lines)
├── src/
│   ├── tools/                   # Web search, scraping, file sandbox, SQL, API caller, doc loaders
│   ├── memory/                  # SQLite long-term memory store & context compressor
│   ├── rag/                     # Hybrid BM25/FAISS retriever, MultiDocManager
│   ├── agent/                   # ReAct planner, goal completion reflection, HITL approval gates, Critic agent
│   ├── agents/                  # Supervisor, ResearchAgent, CodingAgent, DataAgent, SharedState (MessageBus)
│   ├── mcp/                     # MCP JSON-RPC 2.0 Server & remote MCP Client
│   ├── auth/                    # JWT authentication, RBAC middleware, password hashing
│   ├── security/                # Prompt injection defense, PII / secret redactor
│   ├── observability/           # SQLite audit ledger, cost calculator, usage metrics
│   ├── graph/                   # Property knowledge graph engine, triple extractor, 2-hop traversals
│   ├── automation/              # Periodic task scheduler, multi-stage workflow pipeline engine
│   └── voice/                   # Audio speech-to-text (STT) & text-to-speech (TTS) synthesis
├── tests/                       # Unit and integration test suites covering all phases
├── frontend/                    # Next.js 14 (TailwindCSS) chat interface, real-time SSE client
└── docs/
    ├── features_list.md         # Full feature specifications
    └── conversation_context.md  # This document
```

---

## 4. NVIDIA Model Integration & Compatibility

- **LLM**: NVIDIA Nemotron via `langchain-nvidia-ai-endpoints`:
  - `ChatNVIDIA(model="nvidia/nemotron-3-ultra-550b-a55b")`
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace (GPU/CUDA accelerated when available).
- **Environment Variable**: `NVIDIA_API_KEY` set in root `.env` (`nvapi-...`).
- **Compatibility Fix Applied**:
  - `langgraph-checkpoint 4.2+` changed `JsonPlusSerializer` to use `loads_typed` / `dumps_typed`, removing `.loads(metadata)`.
  - Added a non-invasive compatibility shim in `langraph_rag_backend.py` allowing older serialized checkpoints in `chatbot.db` to deserialize cleanly without runtime crashes.

---

## 5. Render Deployments & Frontend Networking

During local testing of the web interface, the frontend displayed:
> *"Could not reach the server — it may be waking up (free tier)..."* / *"Failed to fetch"*

### Root Cause Analysis:
1. `frontend/.env.local` pointed to `NEXT_PUBLIC_API_URL=https://docupilot-api.onrender.com`.
2. Free tier Render instances automatically spin down to sleep after 15 minutes of inactivity. The first request triggers a 30–50s cold start.
3. Diagnostic testing revealed:
   - **`https://docupilot-api.onrender.com`**: Fully healthy and responding (`/docs`, `/api/threads`, and `/api/chat` returned 200 OK).
   - **`https://docupilot-api-6p0e.onrender.com`**: Unhealthy duplicate instance (failed `/api/chat` with HTTP 503).

### Configuration Options:
- **To use Remote Render**: Keep `NEXT_PUBLIC_API_URL=https://docupilot-api.onrender.com` in `frontend/.env.local`.
- **To use Local Backend (No cold starts)**: Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` and restart the frontend.

---

## 6. How to Run the Application

### Running Locally

1. **Start the FastAPI Backend**:
   ```powershell
   .\.venv-win\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8000
   ```
   - API Docs: `http://localhost:8000/docs`

2. **Start the Next.js Frontend**:
   ```powershell
   cd frontend
   npm run dev
   ```
   - UI: `http://localhost:3000`

3. **Run Full Test Suite**:
   ```powershell
   .\.venv-win\Scripts\python.exe -m unittest discover tests
   ```

### Deploying a New Render Service
1. In Render Dashboard, click **New +** → **Web Service** → select repository.
2. Set Runtime to **Docker**, Dockerfile to `Dockerfile.api`.
3. Configure environment variable: `NVIDIA_API_KEY`.
4. Deploy and point `frontend/.env.local` to the new service URL.

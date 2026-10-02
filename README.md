# Agent-Pilot ✈️
### Multi-Tenant Autonomous Agent Platform with Hybrid RAG & Cloud Persistence

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-purple.svg)](https://github.com/langchain-ai/langgraph)
[![Vector Store](https://img.shields.io/badge/Vector%20Store-FAISS-green.svg)](https://github.com/facebookresearch/faiss)
[![Tests Passing](https://img.shields.io/badge/Tests-119%20Passed-brightgreen.svg)]()

---

## 🌟 Overview

**Agent-Pilot** is an enterprise-grade autonomous AI workspace and conversational agent platform. Powered by **LangGraph**, **NVIDIA AI Foundation models**, and a **hybrid dense-sparse RAG engine**, Agent-Pilot enables users to upload heterogeneous documents (PDF, DOCX, TXT, CSV, JSON), index them into persistent multi-tenant vector stores, and execute complex workflows with real-time SSE streaming, live tool execution, and cloud storage persistence.

---

## 🏗️ Architecture

```
                  ┌───────────────────────────────────────────────┐
                  │           Next.js 14 Modern Client            │
                  │   Glassmorphic UI • SSE Stream • Doc Hub      │
                  └───────────────────────┬───────────────────────┘
                                          │ HTTP / SSE / REST
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │            FastAPI Gateway Server             │
                  │  JWT Auth • Tenant Isolation • Rate Limiter   │
                  └───────┬───────────────────────────────┬───────┘
                          │                               │
        ┌─────────────────┴─────────────┐   ┌─────────────┴─────────────────┐
        ▼                               ▼   ▼                               ▼
┌──────────────────┐  ┌──────────────────┐ ┌──────────────────┐  ┌──────────────────┐
│ LangGraph State  │  │ Multi-Doc RAG    │ │ Persistent Cloud │  │ Extensible Tools │
│ Machine & Loops  │  │ Hybrid Retriever │ │ Google Drive / S3│  │ Search, Stocks,  │
│ (SQLite Saver)   │  │ (FAISS + BM25)   │ │ & Local Fallback │  │ Calc, Code, Web  │
└──────────────────┘  └──────────────────┘ └──────────────────┘  └──────────────────┘
```

---

## 🚀 Key Features

### 1. Hybrid Multi-Document RAG Engine
- **Dense + Sparse Fusion**: Blends semantic dense embeddings (`all-MiniLM-L6-v2`) with sparse keyword matching (BM25) via `HybridRetriever`.
- **On-Demand Cache Warm-Up**: Rebuilds vector indexes on-the-fly from persistent cloud storage if worker memory restarts.
- **Strict Tenant Isolation**: Ensures documents and vector embeddings are user-scoped with lifetime identity bridging.
- **Broad Format Support**: Parses `.pdf`, `.docx`, `.doc`, `.txt`, `.md`, `.csv`, `.json`, and `.tsv`.

### 2. Multi-Turn Autonomous Agent Workflows
- **LangGraph State Graph**: Cyclic execution model with checkpoints, human-in-the-loop (HITL) pause/resume, and rollbacks.
- **Real-Time Token Streaming**: `POST /api/chat/stream` delivers Server-Sent Events (SSE) with live tool invocation states (`MotionThinkingBadge`).
- **Context Compression**: Auto-summarizes long conversation histories past 12 turns to prevent context window overflow.

### 3. Integrated Tool Ecosystem
- 📄 **`rag_tool`**: Document citations with page and file provenance.
- 🌐 **`web_search`**: Live internet search powered by DuckDuckGo.
- 📈 **`get_stock_price`**: Real-time equity market data via Alpha Vantage.
- 🧮 **`calculator`**: Deterministic floating-point arithmetic.
- 🕷️ **`scrape_web`**: Headless web page extraction.
- 🗄️ **`query_database`**: Read-only SQL query runner with parameterized safety.
- 📁 **Workspace File Tools**: Read and write files securely within workspace sandboxes.
- 🔀 **Multi-Agent Swarm Routing**: Integrated with Ruflo agent routing.

### 4. Cloud Storage & State Synchronization
- **Google Drive Storage Adapter**: Automated database sync, folder hierarchies, and one-hop file ID downloads.
- **Failover Local Storage**: Seamless fallback to local disk storage if cloud credentials are absent.
- **Database Self-Healing**: Auto-reconciles missing database records on startup from cloud storage.

---

## 📂 Repository Structure

```
.
├── api_server.py                # FastAPI gateway, routes, rate limiter, and SSE streaming
├── langraph_rag_backend.py      # LangGraph state machine, nodes, hybrid retriever, tools & LLM
├── requirements.txt             # Python dependencies
├── src/
│   ├── agent/                   # Autonomous planning, HITL manager, and routing
│   ├── agents/                  # Specialized agents (Coding, Research, Swarm)
│   ├── auth/                    # JWT authentication, password hashing, and user DB
│   ├── mcp/                     # Model Context Protocol JSON-RPC 2.0 server
│   ├── memory/                  # Long-term semantic and conversation memory
│   ├── observability/           # Audit logger, token estimator, and cost tracker
│   ├── rag/                     # MultiDocManager, HybridRetriever, and BM25 ranker
│   ├── security/                # Prompt injection detector and output sanitizer
│   ├── storage/                 # Document upload and lifecycle endpoints
│   └── tools/                   # Document loaders, calculator, scrapers, DB tools
├── storage/                     # Storage backends (Google Drive, S3, Local)
├── frontend/                    # Next.js 14 frontend (React, Tailwind CSS, Lucide)
│   ├── app/                     # App router pages, modals, and components
│   └── package.json             # Frontend dependencies
├── scripts/                     # Operational maintenance and migration utilities
└── tests/                       # 119 unit and integration test suite
```

---

## 🛠️ Quickstart

### Prerequisites
- Python 3.10 or higher
- Node.js 18+ and `npm`

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/Geetansh124/Agent-Pilot.git
cd Agent-Pilot

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# or: .venv\Scripts\activate    # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the project root:

```env
# Required for Chat & Reasoning
NVIDIA_API_KEY=nvapi-your-key-here

# Optional: Real-time Tools & Integrations
ALPHAVANTAGE_API_KEY=your_alphavantage_key
GOOGLE_DRIVE_OAUTH_JSON={"type":"service_account",...}  # Optional for Cloud Storage

# Security & CORS
JWT_SECRET_KEY=your-secure-random-secret-key
FRONTEND_ORIGIN=http://localhost:3000,http://localhost:3001
PORT=8000
```

### 3. Run Backend Server

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

Backend will be available at `http://localhost:8000` (API docs at `http://localhost:8000/docs`).

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health status and cloud storage connectivity. |
| `POST` | `/api/auth/register` | Register new user account. |
| `POST` | `/api/auth/login` | Authenticate user and receive JWT bearer token. |
| `GET` | `/api/auth/me` | Fetch authenticated user profile. |
| `GET` | `/api/threads` | List all conversation threads owned by user. |
| `POST` | `/api/threads` | Create a new conversation thread. |
| `GET` | `/api/threads/{thread_id}` | Fetch thread message history and attached document. |
| `PATCH` | `/api/threads/{thread_id}` | Rename conversation thread. |
| `DELETE` | `/api/threads/{thread_id}` | Delete thread and associated checkpoints. |
| `POST` | `/api/chat` | Send message and receive synchronous agent response. |
| `POST` | `/api/chat/stream` | Stream tokens and live tool events via Server-Sent Events (SSE). |
| `GET` | `/api/documents` | List persistent documents stored for current user. |
| `POST` | `/api/documents/upload` | Upload and index document to persistent cloud storage. |
| `POST` | `/api/threads/{thread_id}/documents/{doc_id}/attach` | Attach document to thread for grounded Q&A. |
| `GET` | `/api/threads/{thread_id}/document` | Get active attached document for the thread. |
| `POST` | `/mcp` | Model Context Protocol JSON-RPC 2.0 handler. |

---

## 🧪 Testing

Run the full test suite with Python's built-in `unittest` runner:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

To run frontend production build validation:

```bash
cd frontend
npm run build
```

---

## 🔒 Security & Privacy

- **Tenant Isolation**: Conversations, uploaded documents, and vector stores are segregated per user identity.
- **Prompt Injection Defense**: Multi-heuristic input scanning flags and rejects prompt override attempts.
- **Sanitized Outputs**: Strips sensitive system markers, auth tokens, and raw stack traces before client delivery.
- **Sliding Window Rate Limiter**: Protects endpoints from abuse with per-IP sliding window counters.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

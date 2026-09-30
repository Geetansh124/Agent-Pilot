# Agent-Pilot ✈️

Agent-Pilot is an intelligent document workspace and RAG-powered chatbot platform. It allows users to upload PDF documents, index them using vector embeddings (FAISS + HuggingFace sentence-transformers), and engage in grounded conversational Q&A backed by LangGraph, NVIDIA ChatNVIDIA LLM, search tools, stock price lookup, and calculators.

## Features

- 📄 **PDF Document Grounding**: Ingest PDFs, chunk text, and create FAISS vector stores for fast Retrieval-Augmented Generation (RAG).
- 💬 **Multi-Thread Chat**: Maintain separate chat threads with persistent history backed by SQLite (`langgraph.checkpoint.sqlite`).
- 🛠️ **Rich Tooling**:
  - `rag_tool`: Retrieve context from indexed PDF documents.
  - `search_tool`: Web search via DuckDuckGo.
  - `get_stock_price`: Fetch live financial quote via Alpha Vantage API.
  - `calculator`: Basic arithmetic calculator.
  - `ruflo_route`: Semantic routing through Ruflo MCP agent router.
- ⚡ **FastAPI Backend & Next.js Frontend**: REST API server for backend agent orchestration paired with a modern Next.js/Tailwind CSS web client.

## Project Structure

```
.
├── api_server.py            # FastAPI server exposing endpoints for threads, chat, and PDF uploads
├── langraph_rag_backend.py  # LangGraph graph definition, tools, LLM, FAISS store & checkpointer
├── aws_storage.py           # Optional S3 storage adapter for document persistence
├── streamlit_rag_frontend.py# Streamlit frontend alternative
├── frontend/                # Next.js frontend application (React + Tailwind CSS + Lucide)
├── tests/                   # Backend unit tests
└── requirements.txt         # Python dependencies
```

## Setup & Installation

### Prerequisites

- Python 3.10+
- Node.js 18+ & pnpm / npm (for frontend)

### 1. Backend Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables (create a `.env` file in the root directory):
   ```env
   NVIDIA_API_KEY=your_nvidia_api_key
   ALPHAVANTAGE_API_KEY=your_alphavantage_api_key
   FRONTEND_ORIGIN=http://localhost:3000,http://localhost:3001
   ```

3. Start the FastAPI server:
   ```bash
   uvicorn api_server:app --reload --port 8000
   ```

### 2. Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   npm install
   npm run build
   ```

2. Open `http://localhost:3000` in your browser.

## API Endpoints

- `GET /health`: Health check endpoint.
- `GET /api/threads`: List all active chat threads and their message summaries.
- `POST /api/threads`: Create a new chat thread.
- `GET /api/threads/{thread_id}`: Fetch thread message history and document metadata.
- `POST /api/chat`: Send a user message and receive AI assistant response with tools used.
- `POST /api/threads/{thread_id}/document`: Upload a PDF document for thread-grounded RAG.

## Testing

Run unit tests using Python `unittest`:
```bash
python -m unittest discover -s tests
```

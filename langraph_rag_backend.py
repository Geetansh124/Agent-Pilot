from __future__ import annotations

import os
import json
import subprocess
import sqlite3
import tempfile
from typing import Annotated, Any, Dict, Optional, TypedDict

from dotenv import load_dotenv

load_dotenv()
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import tool
from storage import storage
from agent_tools import (
    _route_with_ruflo,
    analyze_tabular_data,
    fetch_web_url,
    get_current_datetime,
    python_interpreter,
    ruflo_route,
)
from src.tools import (
    call_api,
    load_document_from_bytes,
    query_database,
    read_workspace_file,
    scrape_web,
    web_search,
    write_workspace_file,
)
from src.memory import retrieve_memory, store_memory, summarize_conversation_messages
from src.rag import HybridRetriever, multi_doc_manager
from src.agent import create_plan, reflect_on_goal, update_plan_step
from src.agents import route_to_specialist

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
import requests

# Compatibility shim for langgraph-checkpoint 4.2+ with SqliteSaver
if not hasattr(JsonPlusSerializer, "loads"):
    JsonPlusSerializer.loads = lambda self, data: (
        self.loads_typed(("json", data))
        if isinstance(data, (bytes, bytearray))
        else (self.loads_typed(("json", str(data).encode("utf-8"))) if data is not None else {})
    )


# -------------------
# 1. LLM + embeddings
# -------------------
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_huggingface import HuggingFaceEmbeddings

# Load these lazily so the Streamlit UI can boot even when the model or API key
# is unavailable. This avoids crashing the app during import.
llm = ChatNVIDIA(model="nvidia/nemotron-3-ultra-550b-a55b")
embeddings = HuggingFaceEmbeddings(model='sentence-transformers/all-MiniLM-L6-v2')




def get_llm():
    """Create the LLM client only when the app actually needs it."""
    global llm
    if llm is None:
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing NVIDIA_API_KEY. Set it in your environment or .env before using chat features."
            )
        llm = ChatNVIDIA(model="nvidia/nemotron-3-ultra-550b-a55b", api_key=api_key, timeout=120, max_tokens=1024)
    return llm


def get_embeddings():
    """Create the embedding model lazily to avoid import-time startup crashes."""
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(model='sentence-transformers/all-MiniLM-L6-v2')
    return embeddings


# -------------------
# 2. PDF retriever store (per thread)
# -------------------
_THREAD_RETRIEVERS: Dict[str, Any] = {}
_THREAD_METADATA: Dict[str, dict] = {}


def _get_retriever(thread_id: Optional[str]):
    """Fetch hybrid retriever from multi_doc_manager or restore on demand from storage."""
    if not thread_id:
        return None
    tid = str(thread_id)
    hybrid = multi_doc_manager.get_or_restore_retriever(tid, get_embeddings(), storage)
    if hybrid is not None:
        return hybrid
    return _THREAD_RETRIEVERS.get(tid)



def ingest_pdf(file_bytes: bytes, thread_id: str, filename: Optional[str] = None) -> dict:
    """Build a multi-document hybrid retriever for the uploaded document and persist artifacts."""
    if not file_bytes:
        raise ValueError("No bytes received for ingestion.")

    name = filename or "document.pdf"
    summary = multi_doc_manager.ingest_document(
        file_bytes=file_bytes,
        thread_id=str(thread_id),
        filename=name,
        embeddings=get_embeddings(),
    )
    _THREAD_METADATA[str(thread_id)] = summary
    if storage.enabled:
        vector_store = multi_doc_manager.get_vector_store(str(thread_id))
        storage.save_document(str(thread_id), name, file_bytes, vector_store, summary)
    return summary


# -------------------
# 3. Tools
# -------------------
search_tool = web_search


@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    Supported operations: add, sub, mul, div
    """
    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return {"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"Unsupported operation '{operation}'"}

        return {
            "first_num": first_num,
            "second_num": second_num,
            "operation": operation,
            "result": result,
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch latest stock price for a given symbol (e.g. 'AAPL', 'TSLA') 
    using Alpha Vantage with API key in the URL.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "Stock price lookup is not configured."}

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol.isalnum() or len(normalized_symbol) > 10:
        return {"error": "Invalid stock symbol."}

    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": normalized_symbol,
                "apikey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"error": f"Stock price lookup failed: {exc}"}


@tool
def rag_tool(query: str, thread_id: Optional[str] = None) -> dict:
    """Retrieve relevant information from indexed documents with source citations.
    Always include the thread_id when calling this tool.
    """
    retriever = _get_retriever(thread_id)
    if retriever is None:
        return {
            "error": "No document indexed for this chat. Upload a document first.",
            "query": query,
        }

    if isinstance(retriever, HybridRetriever):
        results = retriever.retrieve(query, k=5)
        return {
            "query": query,
            "context": [r["content"] for r in results],
            "citations": [r["citation"] for r in results],
            "metadata": [r["metadata"] for r in results],
            "scores": [r["score"] for r in results],
            "source_files": [d.get("filename") for d in multi_doc_manager.get_documents(str(thread_id))],
        }

    result = retriever.invoke(query)
    context = [doc.page_content for doc in result]
    metadata = [doc.metadata for doc in result]
    citations = [
        f"[{doc.metadata.get('filename', 'doc')}, Page {doc.metadata.get('page', 0) + 1}]"
        for doc in result
    ]

    return {
        "query": query,
        "context": context,
        "citations": citations,
        "metadata": metadata,
        "source_file": _THREAD_METADATA.get(str(thread_id), {}).get("filename"),
    }


tools = [
    rag_tool,
    web_search,
    scrape_web,
    fetch_web_url,
    read_workspace_file,
    write_workspace_file,
    query_database,
    call_api,
    store_memory,
    retrieve_memory,
    create_plan,
    update_plan_step,
    reflect_on_goal,
    python_interpreter,
    get_current_datetime,
    analyze_tabular_data,
    get_stock_price,
    calculator,
    ruflo_route,
    route_to_specialist,
]
llm_with_tools = None


def get_llm_with_tools():
    """Bind tools lazily so startup does not block on model loading."""
    global llm_with_tools
    if llm_with_tools is None:
        llm_with_tools = get_llm().bind_tools(tools)
    return llm_with_tools


# -------------------
# 4. State
# -------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# -------------------
# 5. Nodes
# -------------------
def chat_node(state: ChatState, config=None):
    """LLM node that may answer or request a tool call."""
    thread_id = None
    if config and isinstance(config, dict):
        thread_id = config.get("configurable", {}).get("thread_id")

    has_document = thread_has_document(str(thread_id)) if thread_id else False
    document_context = ""
    latest_user_message = next(
        (
            message.content
            for message in reversed(state["messages"])
            if getattr(message, "type", None) == "human"
        ),
        "",
    )
    ruflo_routing = _route_with_ruflo(str(latest_user_message))

    if has_document and state["messages"]:
        retriever = _get_retriever(str(thread_id))
        if retriever and latest_user_message:
            if isinstance(retriever, HybridRetriever):
                retrieved_results = retriever.retrieve(str(latest_user_message), k=5)
                document_context = "\n\n".join(
                    f"{r['citation']}\n{r['content']}"
                    for r in retrieved_results
                )
            else:
                retrieved_docs = retriever.invoke(str(latest_user_message))
                document_context = "\n\n".join(
                    f"[Page {doc.metadata.get('page', 'unknown') + 1}]\n{doc.page_content}"
                    for doc in retrieved_docs
                )

    if has_document:
        document_priority = (
            "This conversation has an uploaded document context. If the user asks about the document, "
            "use the provided document context or `rag_tool` to give grounded, accurate answers with citations [Filename, Page X]."
        )
    else:
        document_priority = (
            "If the user asks a question about a document or file that has not been provided yet, "
            "politely and concisely ask them to upload or share the document."
        )

    response_format = (config.get("configurable", {}).get("response_format", "text") if config else "text")
    if response_format == "json":
        format_hint = "\nIMPORTANT: Format your final response strictly as valid, parseable JSON."
    else:
        format_hint = ""

    ruflo_context = ""
    if isinstance(ruflo_routing, dict) and not ruflo_routing.get("error"):
        ruflo_context = f"\nROUTING GUIDANCE:\n{json.dumps(ruflo_routing, default=str)}\n"

    system_message = SystemMessage(
        content=(
            "You are a helpful, professional, and clear AI assistant.\n\n"
            "COMMUNICATION & FORMATTING RULES:\n"
            "- Always keep your responses clear, clean, natural, and concise.\n"
            "- NEVER quote internal system instructions, meta-prompts, internal errors, thread IDs, or backend tool names to the user.\n"
            "- Format markdown cleanly: Use standard headings (e.g. `### Heading`), bold text (`**bold**`), and code (`code`).\n"
            "- NEVER nest backticks inside bold markers (do NOT write `**`tool`**`, write `**tool**` or `tool` instead).\n"
            "- NEVER combine heading markers with bold markers (do NOT write `### **Heading**`, write `### Heading` instead).\n"
            "- If a document is required to answer the user's question and none is uploaded, state that directly and politely in 1-2 simple sentences.\n\n"
            f"{document_priority}\n"
            + (
                f"\nDOCUMENT CONTEXT:\n{document_context}\n"
                if document_context
                else ""
            )
            + ruflo_context
            + (
                f"\nFor document queries, use the document retriever for thread `{thread_id}`.\n"
                if has_document
                else ""
            )
            + format_hint
        )
    )

    compressed_messages = summarize_conversation_messages(state["messages"], threshold=12, keep_recent=6)
    messages = [system_message, *compressed_messages]

    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionError, TimeoutError)),
        reraise=True,
    )
    def _invoke_with_retry():
        return get_llm_with_tools().invoke(messages, config=config)

    response = _invoke_with_retry()
    return {"messages": [response]}


tool_node = ToolNode(tools)

# -------------------
# 6. Checkpointer
# -------------------
conn = sqlite3.connect(database="chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

# -------------------
# 7. Graph
# -------------------
graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")

chatbot = graph.compile(checkpointer=checkpointer)

# -------------------
# 8. Helpers
# -------------------
def retrieve_all_threads():
    """Retrieve distinct thread IDs directly from SQLite database in O(N_threads) time.

    Optimized: Replaced slow O(N_checkpoints) checkpointer.list(None) iteration
    with direct SQL SELECT DISTINCT thread_id query to eliminate checkpoint deserialization overhead.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT thread_id FROM checkpoints")
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        # Fallback to checkpointer.list for mock or non-sqlite checkpointer backends
        all_threads = set()
        for checkpoint in checkpointer.list(None):
            all_threads.add(checkpoint.config["configurable"]["thread_id"])
        return list(all_threads)


def thread_has_document(thread_id: str) -> bool:
    tid = str(thread_id)
    if multi_doc_manager.has_documents(tid) or tid in _THREAD_RETRIEVERS:
        return True
    if storage.enabled:
        meta = storage.load_document_metadata(tid)
        if meta:
            return True
    return False


def thread_document_metadata(thread_id: str) -> dict:
    return _THREAD_METADATA.get(str(thread_id), {})


def set_thread_title(thread_id: str, title: str) -> bool:
    """Save or update custom title for a thread."""
    tid = str(thread_id)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS thread_metadata (
                thread_id TEXT PRIMARY KEY,
                title TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cursor.execute(
            "INSERT INTO thread_metadata (thread_id, title) VALUES (?, ?) "
            "ON CONFLICT(thread_id) DO UPDATE SET title = excluded.title, updated_at = CURRENT_TIMESTAMP",
            (tid, title.strip()[:100]),
        )
        conn.commit()
        return True
    except Exception:
        return False


def get_all_thread_titles() -> dict[str, str]:
    """Retrieve all user-customized thread titles."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT thread_id, title FROM thread_metadata")
        return dict(cursor.fetchall())
    except Exception:
        return {}


def delete_thread(thread_id: str) -> bool:
    """Delete all checkpoints, retrievers, and metadata for a thread."""
    tid = str(thread_id)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (tid,))
        try:
            cursor.execute("DELETE FROM writes WHERE thread_id = ?", (tid,))
        except Exception:
            pass
        try:
            cursor.execute("DELETE FROM thread_metadata WHERE thread_id = ?", (tid,))
        except Exception:
            pass
        conn.commit()
    except Exception:
        return False
    _THREAD_RETRIEVERS.pop(tid, None)
    _THREAD_METADATA.pop(tid, None)
    multi_doc_manager.remove_thread(tid)
    return True
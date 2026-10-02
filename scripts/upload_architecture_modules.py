import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, ".")

with open("google_drive_token.json", "r", encoding="utf-8") as tf:
    os.environ["GOOGLE_DRIVE_OAUTH_JSON"] = tf.read()

from storage.base import guess_mime_type
from storage.google_drive import GoogleDriveStorage
from googleapiclient.http import MediaIoBaseUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("drive_uploader")


def upload_file_to_folder(service, folder_id: str, filename: str, data: bytes, mime_type: Optional[str] = None) -> dict[str, Any]:
    mime = mime_type or guess_mime_type(filename)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=len(data) > 5 * 1024 * 1024)

    escaped_name = filename.replace("'", "\\'")
    q = f"'{folder_id}' in parents and name = '{escaped_name}' and trashed = false"
    res = service.files().list(
        q=q,
        spaces="drive",
        fields="files(id, name, webViewLink)",
        supportsAllDrives=True,
    ).execute()
    existing = res.get("files", [])

    if existing:
        file_id = existing[0]["id"]
        updated = service.files().update(
            fileId=file_id,
            media_body=media,
            fields="id, name, size, mimeType, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return updated
    else:
        body = {"name": filename, "parents": [folder_id]}
        created = service.files().create(
            body=body,
            media_body=media,
            fields="id, name, size, mimeType, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return created


def main():
    gdrive = GoogleDriveStorage()
    if not gdrive.enabled:
        print("ERROR: Google Drive storage is disabled or not authorized.")
        return

    service = gdrive._service
    root_id = gdrive._get_root_id()
    print(f"Agent-Pilot Root Folder ID: {root_id}")

    # Top-level container folder
    arch_root_id = gdrive.get_or_create_folder("Architecture_Modules", root_id)
    print(f"Architecture_Modules Folder ID: {arch_root_id}")

    # 4 Architecture folders
    folders = {
        "01_LangGraph_State_Machine": gdrive.get_or_create_folder("01_LangGraph_State_Machine", arch_root_id),
        "02_Multi_Doc_RAG": gdrive.get_or_create_folder("02_Multi_Doc_RAG", arch_root_id),
        "03_Persistent_Cloud_Storage": gdrive.get_or_create_folder("03_Persistent_Cloud_Storage", arch_root_id),
        "04_Extensible_Tools": gdrive.get_or_create_folder("04_Extensible_Tools", arch_root_id),
    }

    # Module 1 Files: LangGraph State Machine & Loops (SQLite Saver)
    m1_files = [
        "langraph_rag_backend.py",
        "chatbot.db",
        "docs/conversations_history_backup.json",
        "docs/conversations_history_backup.md",
    ]
    m1_readme = """# LangGraph State Machine & Loops (SQLite Saver)

## Overview
This module houses the core cyclical conversational state machine for Agent-Pilot.

### Components
- `langraph_rag_backend.py`: StateGraph configuration, nodes (chat_node, tool_node), system prompts, and cyclical loops.
- `chatbot.db`: Persistent SQLite database holding threads, checkpoints, writes, and conversation states.
- `conversations_history_backup.json` / `.md`: Complete backups of conversation histories partitioned by user ID.
- Checkpointer: Uses `SqliteSaver` with JSONPlus serialization and sliding-window token management.
"""

    # Module 2 Files: Multi-Doc RAG Hybrid Retriever (FAISS + BM25)
    m2_files = [
        "src/rag/multi_doc_manager.py",
        "src/rag/hybrid_retriever.py",
        "src/rag/bm25.py",
        "src/rag/__init__.py",
        "src/tools/document_loader.py",
    ]
    m2_readme = """# Multi-Doc RAG Hybrid Retriever (FAISS + BM25)

## Overview
High-performance dense-sparse hybrid retrieval engine powering document-grounded responses in Agent-Pilot.

### Components
- `multi_doc_manager.py`: Multi-document session manager with on-demand vector store reconstruction and tenant isolation.
- `hybrid_retriever.py`: Hybrid reciprocal rank fusion combining dense vector embeddings (FAISS) and sparse lexical search (BM25).
- `bm25.py`: Lexical ranker with BM25 Okapi scoring.
- `document_loader.py`: Universal parser for PDF, DOCX, TXT, CSV, JSON, and TSV files.
"""

    # Module 3 Files: Persistent Cloud Google Drive / S3 & Local Fallback
    m3_files = [
        "storage/google_drive.py",
        "storage/google_drive_tenant.py",
        "storage/local.py",
        "storage/base.py",
        "storage/s3.py",
        "storage/__init__.py",
        "src/storage/routes.py",
        "aws_storage.py",
    ]
    m3_readme = """# Persistent Cloud Google Drive / S3 & Local Fallback

## Overview
Multi-tenant persistence layer that survives cloud container restarts and cold boots.

### Components
- `google_drive.py`: Google Drive v3 API integration with User OAuth2 (bypassing service account zero-quota limits).
- `google_drive_tenant.py`: User-scoped directory hierarchies (`users/{user_id}/documents/{doc_id}/`) and one-hop file downloads.
- `local.py`: Local filesystem fallback backend (`workspaces_storage/`).
- `routes.py`: FastAPI endpoints for document uploads, attachments, lifecycle management, and background cloud synchronization.
"""

    # Module 4 Files: Extensible Tools Search, Stocks, Calc, Code, Web
    m4_files = [
        "src/tools/web_search.py",
        "src/tools/stock_tool.py",
        "src/tools/calculator.py",
        "src/tools/web_scraper.py",
        "src/tools/database_tool.py",
        "src/tools/file_tools.py",
        "src/tools/api_tool.py",
        "src/tools/browser_tester.py",
        "src/tools/__init__.py",
        "agent_tools.py",
        "src/agents/coding_agent.py",
        "src/agents/research_agent.py",
        "src/agents/specialist_agents.py",
        "src/agents/shared_state.py",
        "src/agents/__init__.py",
        "src/mcp/mcp_server.py",
        "src/mcp/tools.py",
        "src/mcp/__init__.py",
    ]
    m4_readme = """# Extensible Tools: Search, Stocks, Calc, Code, Web

## Overview
Agent-Pilot's suite of deterministic tools, multi-agent delegators, and Model Context Protocol (MCP) servers.

### Components
- `web_search.py`: Live internet search via DuckDuckGo (`ddgs`).
- `stock_tool.py`: Real-time stock prices and global market quotes via Alpha Vantage.
- `calculator.py`: Precision arithmetic calculation engine.
- `web_scraper.py`: Headless HTTP DOM and text scraper.
- `database_tool.py`: Read-only secure SQL executor.
- `file_tools.py`: Sandboxed workspace read/write file tools.
- `coding_agent.py` & `research_agent.py`: Specialist sub-agents.
- `mcp/`: JSON-RPC 2.0 Model Context Protocol server exposing tool capabilities to external IDEs and agents.
"""

    manifest_content = """# Agent-Pilot Architecture Modules Manifest

This folder contains the complete, dedicated components of the Agent-Pilot Architecture:

1. **`01_LangGraph_State_Machine`**: LangGraph State Machine, cyclical loops, checkpointer, and SQLite state database.
2. **`02_Multi_Doc_RAG`**: Multi-document dense (FAISS) + sparse (BM25) hybrid retriever and document loaders.
3. **`03_Persistent_Cloud_Storage`**: Google Drive OAuth2 adapter, tenant isolator, S3, and local fallback persistence.
4. **`04_Extensible_Tools`**: Suite of tools (Search, Stocks, Calculator, Scraper, SQL, File I/O, MCP server, and Specialist Agents).
"""

    summary = {}

    # Upload Manifest
    print("Uploading Architecture Manifest...")
    res = upload_file_to_folder(service, arch_root_id, "ARCHITECTURE_MANIFEST.md", manifest_content.encode("utf-8"))
    summary["manifest"] = res

    # Upload Module 1
    print("\n--- Uploading Module 1: LangGraph State Machine ---")
    upload_file_to_folder(service, folders["01_LangGraph_State_Machine"], "README.md", m1_readme.encode("utf-8"))
    for file_path in m1_files:
        p = Path(file_path)
        if p.exists():
            data = p.read_bytes()
            item = upload_file_to_folder(service, folders["01_LangGraph_State_Machine"], p.name, data)
            print(f"Uploaded {p.name} ({len(data)} bytes) -> ID: {item.get('id')}")

    # Upload Module 2
    print("\n--- Uploading Module 2: Multi-Doc RAG ---")
    upload_file_to_folder(service, folders["02_Multi_Doc_RAG"], "README.md", m2_readme.encode("utf-8"))
    for file_path in m2_files:
        p = Path(file_path)
        if p.exists():
            data = p.read_bytes()
            item = upload_file_to_folder(service, folders["02_Multi_Doc_RAG"], p.name, data)
            print(f"Uploaded {p.name} ({len(data)} bytes) -> ID: {item.get('id')}")

    # Upload Module 3
    print("\n--- Uploading Module 3: Persistent Cloud Storage ---")
    upload_file_to_folder(service, folders["03_Persistent_Cloud_Storage"], "README.md", m3_readme.encode("utf-8"))
    for file_path in m3_files:
        p = Path(file_path)
        if p.exists():
            data = p.read_bytes()
            item = upload_file_to_folder(service, folders["03_Persistent_Cloud_Storage"], p.name, data)
            print(f"Uploaded {p.name} ({len(data)} bytes) -> ID: {item.get('id')}")

    # Upload Module 4
    print("\n--- Uploading Module 4: Extensible Tools ---")
    upload_file_to_folder(service, folders["04_Extensible_Tools"], "README.md", m4_readme.encode("utf-8"))
    for file_path in m4_files:
        p = Path(file_path)
        if p.exists():
            data = p.read_bytes()
            item = upload_file_to_folder(service, folders["04_Extensible_Tools"], p.name, data)
            print(f"Uploaded {p.name} ({len(data)} bytes) -> ID: {item.get('id')}")

    print("\nSUCCESS: All 4 architecture modules uploaded to Google Drive separated by folders!")
    return summary


if __name__ == "__main__":
    main()

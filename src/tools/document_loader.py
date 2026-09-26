"""Multi-format document loader supporting PDF, DOCX, TXT, Markdown, and CSV.

Converts arbitrary byte inputs into standard LangChain Document objects for chunking and vector indexing.
"""
from __future__ import annotations

import csv
import io
import tempfile
from typing import Any, List

from langchain_core.documents import Document
from pypdf import PdfReader
import docx


def load_document_from_bytes(file_bytes: bytes, filename: str) -> list[Document]:
    """Parse document bytes into a list of LangChain Document instances based on file extension."""
    if not file_bytes:
        raise ValueError("Cannot load empty file bytes.")

    lower_name = filename.lower()
    docs: list[Document] = []

    if lower_name.endswith(".pdf"):
        with io.BytesIO(file_bytes) as stream:
            reader = PdfReader(stream)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={"source": filename, "page": idx, "file_type": "pdf"},
                        )
                    )

    elif lower_name.endswith((".docx", ".doc")):
        with io.BytesIO(file_bytes) as stream:
            doc = docx.Document(stream)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            # Also extract tables
            table_texts = []
            for t in doc.tables:
                for row in t.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        table_texts.append(" | ".join(cells))

            full_text = "\n\n".join(paragraphs)
            if table_texts:
                full_text += "\n\nTABLES:\n" + "\n".join(table_texts)

            if full_text.strip():
                docs.append(
                    Document(
                        page_content=full_text,
                        metadata={"source": filename, "page": 0, "file_type": "docx"},
                    )
                )

    elif lower_name.endswith(".csv"):
        text_content = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text_content))
        rows = list(reader)
        if rows:
            header = rows[0]
            row_texts = []
            for idx, row in enumerate(rows[1:500]):
                pairs = [f"{header[i] if i < len(header) else f'col_{i}'}: {val}" for i, val in enumerate(row)]
                row_texts.append(f"Row {idx + 1}: " + ", ".join(pairs))
            content = f"CSV Data ({len(rows)} rows):\n" + "\n".join(row_texts)
            docs.append(
                Document(
                    page_content=content,
                    metadata={"source": filename, "page": 0, "file_type": "csv"},
                )
            )

    elif lower_name.endswith((".txt", ".md", ".markdown", ".json", ".log")):
        text_content = file_bytes.decode("utf-8", errors="replace")
        if text_content.strip():
            docs.append(
                Document(
                    page_content=text_content,
                    metadata={"source": filename, "page": 0, "file_type": "text"},
                )
            )
    else:
        # Fallback to UTF-8 text interpretation
        text_content = file_bytes.decode("utf-8", errors="replace")
        if text_content.strip():
            docs.append(
                Document(
                    page_content=text_content,
                    metadata={"source": filename, "page": 0, "file_type": "unknown"},
                )
            )

    return docs

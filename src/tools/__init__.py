"""Agent-Pilot Tools Package.

Consolidated export for modern agent tools including web search, scraping,
multi-format document loading, sandboxed file operations, SQL queries, and API integrations.
"""
from src.tools.web_search import web_search
from src.tools.web_scrape import scrape_web
from src.tools.document_loader import load_document_from_bytes
from src.tools.file_tools import (
    read_workspace_file,
    write_workspace_file,
    list_workspace_files,
    delete_workspace_file,
)
from src.tools.database_tool import query_database
from src.tools.api_caller import call_api
from src.tools.test_generator import generate_unit_tests, run_test_suite
from src.tools.browser_tester import BrowserTester, browser_tester, test_web_endpoint
from src.tools.doc_generator import DocGenerator, doc_generator, generate_code_docs

__all__ = [
    "web_search",
    "scrape_web",
    "load_document_from_bytes",
    "read_workspace_file",
    "write_workspace_file",
    "list_workspace_files",
    "delete_workspace_file",
    "query_database",
    "call_api",
    "generate_unit_tests",
    "run_test_suite",
    "BrowserTester",
    "browser_tester",
    "test_web_endpoint",
    "DocGenerator",
    "doc_generator",
    "generate_code_docs",
]



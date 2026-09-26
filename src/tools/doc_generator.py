"""Automated Markdown Documentation Generator.

Parses Python source code AST to generate API references, class diagrams,
function signatures, docstrings, and markdown documentation.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool


class DocGenerator:
    """Generates structured markdown documentation from Python source code."""

    def generate_markdown_docs(
        self, source_code: str, module_name: str = "module"
    ) -> dict[str, Any]:
        """Parse source code and produce markdown documentation."""
        if not source_code.strip():
            return {"markdown": "", "classes_documented": 0, "functions_documented": 0}

        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return {
                "error": f"Syntax error parsing code: {exc}",
                "markdown": "",
                "classes_documented": 0,
                "functions_documented": 0,
            }

        module_doc = ast.get_docstring(tree) or ""
        lines: list[str] = [
            f"# `{module_name}` Documentation",
            "",
            module_doc if module_doc else f"> Auto-generated API reference for `{module_name}`.",
            "",
            "---",
            "",
        ]

        classes_count = 0
        functions_count = 0

        # Document Classes
        class_nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if class_nodes:
            lines.append("## Classes")
            lines.append("")
            for c in class_nodes:
                classes_count += 1
                doc = ast.get_docstring(c) or "No docstring provided."
                lines.append(f"### `class {c.name}`")
                lines.append("")
                lines.append(doc)
                lines.append("")

                methods = [m for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if methods:
                    lines.append("**Methods:**")
                    lines.append("")
                    for m in methods:
                        m_doc = ast.get_docstring(m) or "No docstring."
                        params = [a.arg for a in m.args.args if a.arg != "self"]
                        lines.append(f"- `def {m.name}({', '.join(params)})`")
                        lines.append(f"  - *{m_doc.strip().splitlines()[0]}*")
                    lines.append("")

        # Document Standalone Functions
        func_nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if func_nodes:
            lines.append("## Functions")
            lines.append("")
            for f in func_nodes:
                functions_count += 1
                doc = ast.get_docstring(f) or "No docstring provided."
                params = [a.arg for a in f.args.args]
                lines.append(f"### `def {f.name}({', '.join(params)})`")
                lines.append("")
                lines.append(doc)
                lines.append("")

        markdown_doc = "\n".join(lines)

        return {
            "module_name": module_name,
            "markdown": markdown_doc,
            "classes_documented": classes_count,
            "functions_documented": functions_count,
        }


doc_generator = DocGenerator()


@tool
def generate_code_docs(
    source_code: str, module_name: str = "module"
) -> dict[str, Any]:
    """Generate Markdown API documentation from Python source code.

    Args:
        source_code: Python source code to document.
        module_name: Name of the module for the documentation header.
    """
    return doc_generator.generate_markdown_docs(source_code, module_name)

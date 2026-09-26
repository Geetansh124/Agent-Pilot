"""Auto test generation tool.

Analyzes Python source code AST to detect untested functions and classes,
then generates pytest-compatible test stubs with assertions, edge cases,
and docstring-based expected behavior.
"""
from __future__ import annotations

import ast
import re
import textwrap
from typing import Any

from langchain_core.tools import tool


def _extract_functions(source: str) -> list[dict[str, Any]]:
    """Parse Python source and extract function/method signatures."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = []
            for arg in node.args.args:
                if arg.arg != "self":
                    annotation = ""
                    if arg.annotation and isinstance(arg.annotation, ast.Name):
                        annotation = arg.annotation.id
                    elif arg.annotation and isinstance(arg.annotation, ast.Constant):
                        annotation = str(arg.annotation.value)
                    params.append({"name": arg.arg, "type": annotation})

            # Extract return type
            returns = ""
            if node.returns:
                if isinstance(node.returns, ast.Name):
                    returns = node.returns.id
                elif isinstance(node.returns, ast.Constant):
                    returns = str(node.returns.value)

            # Extract docstring
            docstring = ast.get_docstring(node) or ""

            # Detect if it has decorators like @tool or @staticmethod
            decorators = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
                elif isinstance(dec, ast.Attribute):
                    decorators.append(dec.attr)

            # Detect parent class if method
            parent_class = ""
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    for item in parent.body:
                        if item is node:
                            parent_class = parent.name
                            break

            functions.append({
                "name": node.name,
                "params": params,
                "returns": returns,
                "docstring": docstring[:200],
                "decorators": decorators,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "parent_class": parent_class,
                "lineno": node.lineno,
                "is_private": node.name.startswith("_"),
            })

    return functions


def _extract_classes(source: str) -> list[dict[str, Any]]:
    """Parse Python source and extract class definitions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    classes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                item.name for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            docstring = ast.get_docstring(node) or ""
            classes.append({
                "name": node.name,
                "methods": methods,
                "docstring": docstring[:200],
                "lineno": node.lineno,
            })
    return classes


def _generate_test_value(param: dict[str, Any]) -> str:
    """Generate a sensible test value based on parameter name and type."""
    ptype = param.get("type", "").lower()
    pname = param.get("name", "").lower()

    if ptype == "str" or "name" in pname or "text" in pname or "query" in pname:
        return '"test_value"'
    if ptype == "int" or "count" in pname or "limit" in pname or "number" in pname:
        return "5"
    if ptype == "float" or "score" in pname or "weight" in pname:
        return "0.5"
    if ptype == "bool" or "is_" in pname or "has_" in pname or "enable" in pname:
        return "True"
    if ptype == "list" or "items" in pname or "results" in pname:
        return "[]"
    if ptype == "dict" or "config" in pname or "options" in pname or "data" in pname:
        return "{}"
    if "id" in pname:
        return '"test-id-123"'
    if "path" in pname or "file" in pname:
        return '"test_file.txt"'
    if "url" in pname:
        return '"https://example.com"'
    return '"test_value"'


def generate_tests(
    source_code: str, module_name: str = "module_under_test"
) -> dict[str, Any]:
    """Generate pytest test code for functions and classes in source code."""
    functions = _extract_functions(source_code)
    classes = _extract_classes(source_code)

    if not functions and not classes:
        return {
            "error": "No functions or classes found in source code.",
            "test_code": "",
            "functions_found": 0,
            "classes_found": 0,
        }

    lines: list[str] = [
        f'"""Auto-generated tests for {module_name}."""',
        "import pytest",
        "",
        f"# Source module: {module_name}",
        f"# Functions found: {len(functions)}",
        f"# Classes found: {len(classes)}",
        "",
    ]

    testable = [f for f in functions if not f["is_private"] and "tool" not in f["decorators"]]

    # Generate class-based tests
    for cls in classes:
        lines.append(f"class Test{cls['name']}:")
        if cls["docstring"]:
            lines.append(f'    """{cls["docstring"][:100]}"""')
        lines.append("")

        class_methods = [f for f in functions if f["parent_class"] == cls["name"] and not f["is_private"]]
        if not class_methods:
            lines.append("    def test_instantiation(self):")
            lines.append(f'        """Test that {cls["name"]} can be instantiated."""')
            lines.append("        pass  # TODO: add constructor args")
            lines.append("")
            continue

        for method in class_methods:
            test_name = f"test_{method['name']}"
            params_str = ", ".join(
                f"{p['name']}={_generate_test_value(p)}" for p in method["params"]
            )

            lines.append(f"    def {test_name}(self):")
            doc = method["docstring"][:80] if method["docstring"] else f"Test {method['name']} method."
            lines.append(f'        """{doc}"""')
            lines.append(f"        # TODO: instantiate {cls['name']} and call {method['name']}")

            if method["returns"] == "bool":
                lines.append(f"        # result = instance.{method['name']}({params_str})")
                lines.append("        # assert isinstance(result, bool)")
            elif method["returns"] in ("dict", "list"):
                lines.append(f"        # result = instance.{method['name']}({params_str})")
                lines.append(f"        # assert isinstance(result, {method['returns']})")
            elif method["returns"]:
                lines.append(f"        # result = instance.{method['name']}({params_str})")
                lines.append("        # assert result is not None")
            else:
                lines.append(f"        # instance.{method['name']}({params_str})")
            lines.append("        pass")
            lines.append("")

    # Generate standalone function tests
    standalone = [f for f in testable if not f["parent_class"]]
    for func in standalone:
        test_name = f"test_{func['name']}"
        params_str = ", ".join(
            f"{p['name']}={_generate_test_value(p)}" for p in func["params"]
        )

        lines.append(f"def {test_name}():")
        doc = func["docstring"][:80] if func["docstring"] else f"Test {func['name']} function."
        lines.append(f'    """{doc}"""')
        lines.append(f"    # result = {func['name']}({params_str})")

        if func["returns"] in ("bool", "dict", "list", "str", "int", "float"):
            lines.append(f"    # assert isinstance(result, {func['returns']})")
        else:
            lines.append("    # assert result is not None")
        lines.append("    pass")
        lines.append("")

    # Generate edge case tests
    lines.append("# --- Edge Case Tests ---")
    lines.append("")
    for func in standalone[:5]:
        lines.append(f"def test_{func['name']}_empty_input():")
        lines.append(f'    """Test {func["name"]} with empty/None inputs."""')
        empty_params = ", ".join(
            f'{p["name"]}=""' if "str" in (p.get("type") or "str").lower() else f'{p["name"]}=None'
            for p in func["params"]
        )
        lines.append(f"    # result = {func['name']}({empty_params})")
        lines.append("    # assert result is not None  # Should handle gracefully")
        lines.append("    pass")
        lines.append("")

    test_code = "\n".join(lines)
    return {
        "test_code": test_code,
        "functions_found": len(functions),
        "classes_found": len(classes),
        "tests_generated": len(testable) + len(classes) + min(len(standalone), 5),
        "module_name": module_name,
    }


@tool
def generate_test_code(
    source_code: str, module_name: str = "module_under_test"
) -> dict[str, Any]:
    """Analyze Python source code and generate pytest test stubs.

    Args:
        source_code: The Python source code to analyze.
        module_name: Name of the module being tested (for import paths).
    """
    if not source_code.strip():
        return {"error": "Source code cannot be empty.", "test_code": ""}
    return generate_tests(source_code=source_code, module_name=module_name)


def generate_unit_tests(code: str, module_name: str = "module_under_test") -> dict[str, Any]:
    """Programmatic API for test generation."""
    res = generate_tests(source_code=code, module_name=module_name)
    return {
        "status": "success",
        "generated_test_code": res.get("test_code", ""),
        "details": res,
    }


def run_test_suite(test_target: str = "tests/") -> dict[str, Any]:
    """Execute pytest or unittest suite against a path."""
    import subprocess
    import sys
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", test_target],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "status": "passed" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


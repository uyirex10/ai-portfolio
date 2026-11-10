"""Global rule: LLM perceives, code decides. src/rules/ (and any module
whose name suggests verdict logic) must never import an LLM client or
make raw HTTP calls -- if it needs a value, the LLM layer must have
already extracted it into a plain Python/pydantic value before the
rules ever see it. Enforced by static AST analysis of imports, not by
trying to actually import with packages uninstalled (unreliable) or by
running the modules (slow and not what we're checking).
"""

import ast
from pathlib import Path

FORBIDDEN_MODULES = {"anthropic", "google", "openai", "requests"}

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "src" / "rules"


def _top_level_module(name: str) -> str:
    return name.split(".")[0]


def _imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(_top_level_module(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(_top_level_module(node.module))
    return found


def test_rules_directory_imports_no_llm_client():
    if not RULES_DIR.exists():
        return  # nothing to check yet (Stage E creates this directory)

    violations = []
    for py_file in RULES_DIR.rglob("*.py"):
        modules = _imported_modules(py_file)
        bad = modules & FORBIDDEN_MODULES
        if bad:
            violations.append((py_file.relative_to(ROOT), bad))

    assert not violations, (
        "src/rules/ must not import an LLM client or httpx-style library "
        f"(LLM perceives, code decides): {violations}"
    )

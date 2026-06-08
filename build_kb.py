#!/usr/bin/env python3
"""build_kb.py — build the compiled knowledge base from the Markdown API specs.

Thin CLI shim over ``src/knowledge/compiler/compiler.py``. Run from ``workplan-generator/``::

    python build_kb.py                     # compile ../api_docs -> ./kb_compiled
    python build_kb.py --lint --strict     # CI gate: warnings -> exit 1
    python build_kb.py --docs ../api_docs --out kb_compiled --emit ir,catalog,context,models

Every flag the compiler accepts is passed straight through. Defaults fill in when
omitted: ``--docs`` -> ../api_docs (sibling of workplan-generator), and ``--out`` ->
./kb_compiled unless ``--lint`` is given. Paths resolve relative to this file, so the
script works regardless of the current working directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent          # workplan-generator/
REPO_ROOT = SCRIPT_DIR.parent                         # repo root (parent of workplan-generator)
DEFAULT_DOCS = REPO_ROOT / "api_docs"
DEFAULT_OUT = SCRIPT_DIR / "kb_compiled"

# Make `from src.knowledge...` importable no matter where we're invoked from.
sys.path.insert(0, str(SCRIPT_DIR))

from src.knowledge.compiler.compiler import main as compiler_main  # noqa: E402


def _has_flag(argv: list[str], name: str) -> bool:
    return any(a == name or a.startswith(name + "=") for a in argv)


def main() -> int:
    argv = list(sys.argv[1:])
    if not _has_flag(argv, "--docs"):
        argv = ["--docs", str(DEFAULT_DOCS)] + argv
    if not _has_flag(argv, "--lint") and not _has_flag(argv, "--out"):
        argv = argv + ["--out", str(DEFAULT_OUT)]
    return compiler_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
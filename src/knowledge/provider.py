"""KnowledgeProvider — the seam between the compiled knowledge base and the agents.

Loads the pre-built artifacts in ``kb_compiled/`` (produced by build_kb.py) and serves
two things the planner and Reviewer need:

  * **planning context** — the spec text that goes into the Phase-1 planner's prompt.
  * **per-API param schemas** — the composed JSON Schema for a given (api, method,
    operation), used both to constrain the planner's structured output and to validate
    each job in the Reviewer.

It deliberately does NOT run the compiler at serve time — it reads the committed text
artifacts. The compiler is a build step; this is the runtime view over its output.

Two implementations sit behind one interface so the full-context → catalog-fetch swap
is a one-line change with no impact on the planner or Reviewer:

  * ``FullContextProvider``  — get_planning_context() returns the entire compiled spec.
    Correct while the spec fits comfortably in the context window (your case today).
  * ``CatalogFetchProvider`` — get_planning_context() returns only the stage-grouped
    catalog (the selection menu); the planner then calls fetch_api_specs(selected) for
    the full text of the APIs it chose. The escape hatch for when the spec outgrows the
    window. Everything except get_planning_context is shared.

Typical use::

    from src.knowledge.provider import load_provider

    kb = load_provider("kb_compiled", mode="full")

    # Phase-1 planner:
    context = kb.get_planning_context()                       # -> into the prompt
    schema  = kb.get_param_schema("Segment_ROI_API_v10",      # -> structured output
                                  method="cellpose",
                                  operation="run_segmentation",
                                  inline_refs=True)
    # Reviewer, per job:
    errors  = kb.validate_payload("Segment_ROI_API_v10", job_body,
                                  method="cellpose", operation="run_segmentation")
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    import jsonschema  # Draft 2020-12; matches the pydantic-emitted schemas
    _HAS_JSONSCHEMA = True
except Exception:  # pragma: no cover
    _HAS_JSONSCHEMA = False

# Base (always-applies) request groups, in priority order. A multi-method API uses
# "通用请求参数" for shared fields; a single-shape API uses "请求参数".
_BASE_GROUP_KEYS = ("通用请求参数", "请求参数")

# Matches a top-level API header in context_spec.md, e.g.
#   "## Segment_ROI_API_v10   [stage: segment]"
_API_HEADER_RE = re.compile(r"^##\s+(\S+)\s+\[stage:")


# --------------------------------------------------------------------------------------
# Schema helpers
# --------------------------------------------------------------------------------------

# NOTE: common + branch composition happens at BUILD time (in the compiler), so each
# method:operation group in models_jsonschema.json is already a complete request schema.
# The provider just selects the right group — no runtime merge.

def _inline_refs(schema: dict, _max_depth: int = 32) -> dict:
    """Return an equivalent schema with internal ``$ref``/``$defs`` inlined.

    Some structured-output backends want a self-contained schema. The compiled schemas
    are trees (no cycles), so a bounded recursive expansion is safe.
    """
    defs = schema.get("$defs", {})

    def resolve(node: Any, depth: int) -> Any:
        if depth > _max_depth:
            return node
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                return resolve(copy.deepcopy(target), depth + 1)
            return {k: resolve(v, depth) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(x, depth) for x in node]
        return node

    return resolve({k: v for k, v in schema.items() if k != "$defs"}, 0)


def _slice_context_by_api(context_spec: str) -> Dict[str, str]:
    """Split context_spec.md into per-API sections keyed by API name (for fetch)."""
    sections: Dict[str, str] = {}
    cur: Optional[str] = None
    buf: List[str] = []
    for line in context_spec.splitlines():
        m = _API_HEADER_RE.match(line)
        if m:
            if cur is not None:
                sections[cur] = "\n".join(buf).rstrip()
            cur = m.group(1)
            buf = [line]
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf).rstrip()
    return sections


def _render_catalog_text(catalog: dict) -> str:
    lines = ["# API catalog — select the APIs you need by exact name, grouped by stage"]
    for stage, items in catalog.get("stages", {}).items():
        label = "shared / utility" if stage == "shared" else stage
        lines.append(f"\n## {label}")
        for it in items:
            methods = f"  (methods: {', '.join(it['methods'])})" if it.get("methods") else ""
            lines.append(f"- {it['name']} — {it.get('purpose','')}{methods}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------------------

class KnowledgeProvider:
    """Base provider. Concrete subclasses override only ``get_planning_context``."""

    def __init__(self, kb_dir: Path, *, models: dict, context_spec: str,
                 catalog: Optional[dict] = None) -> None:
        self.kb_dir = Path(kb_dir)
        self._models = models
        self._context_spec = context_spec
        self._catalog = catalog
        self._api_sections = _slice_context_by_api(context_spec)

    # ---- planning context (subclass responsibility) ----

    def get_planning_context(self) -> str:
        raise NotImplementedError

    # ---- shared across implementations ----

    def list_apis(self) -> List[str]:
        return list(self._models.keys())

    def get_catalog(self) -> dict:
        if self._catalog is None:
            raise FileNotFoundError(
                "catalog.json not loaded — re-run build_kb.py so it emits the catalog")
        return self._catalog

    def fetch_api_specs(self, api_names: List[str]) -> str:
        """Full spec text for the named APIs (the post-selection fetch step)."""
        parts: List[str] = []
        for name in api_names:
            section = self._api_sections.get(name)
            if section is None:
                log.warning("fetch_api_specs: no context section for %r", name)
                continue
            parts.append(section)
        return "\n\n".join(parts)

    def get_param_schema(self, api_name: str, method: Optional[str] = None,
                         operation: Optional[str] = None, *, inline_refs: bool = False) -> dict:
        """Complete JSON Schema for one API call.

        Branch groups are already composed (common + branch) at build time, so this just
        selects: the matching (method, operation) branch if present, else the base/common
        group. A method/operation with no branch group falls back to the base group
        (envelope-only validation) with a warning — that path covers stub methods.
        """
        if api_name not in self._models:
            raise KeyError(f"unknown API {api_name!r}; known: {self.list_apis()}")
        groups: Dict[str, dict] = self._models[api_name]["groups"]

        chosen: Optional[str] = None
        if method:
            candidate = f"{method}:{operation}" if operation else method
            if candidate in groups:
                chosen = candidate
            elif method in groups:           # dual-endpoint docs key by HTTP verb (GET/POST)
                chosen = method

        if chosen is None:                   # fall back to the common/base group
            chosen = next((k for k in _BASE_GROUP_KEYS if k in groups), None)
            if chosen is None:
                if len(groups) == 1:         # single non-standard group label
                    chosen = next(iter(groups))
                else:                        # e.g. GET/POST with no method passed
                    raise KeyError(
                        f"{api_name}: ambiguous — pass method (and operation). "
                        f"available groups: {list(groups)}")
            if method:
                log.warning("%s: no composed schema for method=%r operation=%r; "
                            "using base group %r (envelope only)",
                            api_name, method, operation, chosen)

        schema = copy.deepcopy(groups[chosen])
        return _inline_refs(schema) if inline_refs else schema

    def validate_payload(self, api_name: str, payload: dict,
                         method: Optional[str] = None,
                         operation: Optional[str] = None) -> List[str]:
        """Validate a request body against the composed schema. Returns error strings
        (empty == valid). This is what the Reviewer calls per job, alongside its own
        structural checks (referential integrity, duplicate step IDs, mandatory order)."""
        if not _HAS_JSONSCHEMA:
            raise RuntimeError("validate_payload needs jsonschema — `pip install jsonschema`")
        schema = self.get_param_schema(api_name, method, operation)
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        return [f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


class FullContextProvider(KnowledgeProvider):
    """Whole compiled spec into the planner every call. Correct while it fits the window."""

    def get_planning_context(self) -> str:
        return self._context_spec


class CatalogFetchProvider(KnowledgeProvider):
    """Catalog-only planning context; planner selects, then calls fetch_api_specs().

    The deferred path for when the compiled spec outgrows ~1/3 of the context window.
    Identical to FullContextProvider in every other respect.
    """

    def get_planning_context(self) -> str:
        if self._catalog is None:
            raise FileNotFoundError("catalog mode requires catalog.json in the KB dir")
        return _render_catalog_text(self._catalog)


# --------------------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------------------

_PROVIDERS = {"full": FullContextProvider, "catalog": CatalogFetchProvider}


def load_provider(kb_dir: str | Path = "kb_compiled", mode: str = "full") -> KnowledgeProvider:
    """Load a provider from a compiled-KB directory.

    Reads ``models_jsonschema.json`` and ``context_spec.md`` (required) and
    ``catalog.json`` (optional; required only for ``mode='catalog'``).
    """
    kb = Path(kb_dir)
    if mode not in _PROVIDERS:
        raise ValueError(f"mode must be one of {list(_PROVIDERS)}; got {mode!r}")

    models_path = kb / "models_jsonschema.json"
    context_path = kb / "context_spec.md"
    for p in (models_path, context_path):
        if not p.exists():
            raise FileNotFoundError(f"missing compiled artifact: {p} (run build_kb.py first)")

    models = json.loads(models_path.read_text(encoding="utf-8"))
    context_spec = context_path.read_text(encoding="utf-8")

    catalog: Optional[dict] = None
    catalog_path = kb / "catalog.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    elif mode == "catalog":
        raise FileNotFoundError(f"catalog mode needs {catalog_path}")

    return _PROVIDERS[mode](kb, models=models, context_spec=context_spec, catalog=catalog)
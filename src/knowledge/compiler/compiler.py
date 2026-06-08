#!/usr/bin/env python3
"""
doc_compiler — compile structured Markdown API specs into a single IR, and from
that IR derive everything downstream:

  (1) per-(api, method/operation) JSON-Schema / Pydantic models   -> Reviewer + structured-output
  (2) stage-grouped catalog one-liners                            -> Stage-1 selection
  (3) a dense full-context spec (boilerplate stripped)            -> Generator
  (4) a doc lint gate                                             -> CI / authoring-time

The Markdown docs are the single source of truth. Nothing downstream hand-maintains
API names, field names, enums, or stage assignments — they are all compiled from here.

Usage
-----
    python compiler.py --docs ./api_docs --out ./compiled         # parse + lint(warn) + emit all
    python compiler.py --docs ./api_docs --lint --strict          # CI gate: warnings -> failure
    python compiler.py --docs ./api_docs --out ./compiled --emit ir,catalog,context,models

Doc template conventions it reads (all optional but recommended)
----------------------------------------------------------------
    # <ApiName>_v<N> 参数说明
    - **Endpoint**: `POST /api/v10/...`            (also supports Endpoint 1 / Endpoint 2)
    - **Content-Type**: `application/json`
    > 用途: <one line: when/why you would reach for this API>     <- drives catalog quality
    > 阶段: deconvolve|segment|target|measure|calculate|render|shared
    > 命名约定: ...                                 (boilerplate; stripped from context spec)
    ## 1. 功能说明                                   (purpose fallback if no `> 用途:` line)
    ## N. <method>: <operation> 请求参数             (request param table; method/operation parsed)
    | 参数名 | 类型 | 必填 | 枚举值/允许值 | 说明 |
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

# Pydantic is only required for --emit models. Parsing/catalog/context work without it.
try:
    from pydantic import create_model, Field, BaseModel  # noqa: F401
    from typing import Literal
    _PYDANTIC = True
except Exception:  # pragma: no cover
    _PYDANTIC = False


# --------------------------------------------------------------------------------------
# IR data model
# --------------------------------------------------------------------------------------

@dataclass
class ParamSpec:
    path: str                       # dotted path, e.g. params.cellposeParams.flowThreshold.min
    type: str                       # string|number|integer|boolean|object|array|array<object>|any
    required: bool
    required_note: Optional[str] = None     # raw cell when conditionally required
    enum: Optional[List[str]] = None        # closed value set, if any
    default: Optional[Any] = None
    constraint: Optional[str] = None        # loose constraint hint (">0", "Base64 文本", ...)
    desc: str = ""


@dataclass
class ParamGroup:
    label: str                      # cleaned section title, used to name the model
    kind: str                       # "request" | "response" | "other"
    method: Optional[str]           # e.g. cellpose / threshold / weka, when the header encodes it
    operation: Optional[str]        # e.g. run_segmentation / analyze_particles
    params: List[ParamSpec] = field(default_factory=list)


@dataclass
class ApiSpec:
    name: str                       # full name, e.g. Segment_ROI_API_v10
    short_name: str                 # name with _API_vN stripped, e.g. Segment_ROI
    version: Optional[str]
    endpoints: List[str]
    content_type: Optional[str]
    purpose: str
    purpose_source: str             # "用途" | "功能说明" | "none"
    stage: str
    stage_source: str               # "declared" | "inferred" | "unknown"
    discriminators: Dict[str, List[str]]   # field -> allowed values (e.g. segmentationMethod)
    groups: List[ParamGroup]
    source_file: str


@dataclass
class LintIssue:
    file: str
    level: str                      # "error" | "warn"
    msg: str


# --------------------------------------------------------------------------------------
# Migration-only fallback stage map. PREFER a `> 阶段:` line in each doc.
# Used only when a doc does not declare its stage; emits a loud warning when it fires.
# --------------------------------------------------------------------------------------

_FALLBACK_STAGE = {
    "Pic_Split": "deconvolve",
    "Segment_ROI": "segment",
    "Create_Target": "target",
    "Measure_ROI": "measure",
    "Formula": "calculate",
    "ROI_Render": "render",
    "Input_Interpretation": "shared",
    "Put_File": "shared",
    "Get_File": "shared",
    "Get_Target": "shared",
}

# Canonical pipeline order for presentation. "shared" is the cross-cutting bucket.
_STAGE_ORDER = ["deconvolve", "segment", "target", "measure", "calculate", "render", "shared"]

_TYPE_CANON = {
    "string": "string", "str": "string",
    "number": "number", "float": "number", "double": "number",
    "integer": "integer", "int": "integer",
    "boolean": "boolean", "bool": "boolean",
    "object": "object", "obj": "object",
    "array": "array",
}


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ENDPOINT_RE = re.compile(r"^\s*-\s*\*\*Endpoint(?:\s*\d+)?\*\*\s*[:：]\s*`?(.+?)`?\s*$")
_CONTENT_TYPE_RE = re.compile(r"^\s*-\s*\*\*Content-Type\*\*\s*[:：]\s*`?(.+?)`?\s*$")
_USE_RE = re.compile(r"^\s*>\s*用途\s*[:：]\s*(.+?)\s*$")
_STAGE_RE = re.compile(r"^\s*>\s*(?:阶段|stage)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _split_sections(text: str) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    """Return (preamble_lines, [(section_title, body_lines), ...]).

    Preamble is everything before the first heading. Sections are keyed by heading
    text (any level), which is all we need for purpose / request-table discovery.
    """
    lines = text.splitlines()
    preamble: List[str] = []
    sections: List[Tuple[str, List[str]]] = []
    cur_title: Optional[str] = None
    cur_body: List[str] = []
    for ln in lines:
        m = _HEADER_RE.match(ln)
        if m:
            if cur_title is not None:
                sections.append((cur_title, cur_body))
            elif cur_body:
                preamble.extend(cur_body)
            # first heading also flushes preamble collected so far
            if cur_title is None and not preamble and cur_body:
                preamble.extend(cur_body)
            cur_title = m.group(2).strip()
            cur_body = []
        else:
            cur_body.append(ln)
    if cur_title is not None:
        sections.append((cur_title, cur_body))
    else:
        preamble.extend(cur_body)
    # Anything before first heading
    if sections:
        first_heading_pos = text.find("\n#")
        head = text[: first_heading_pos if first_heading_pos != -1 else len(text)]
        preamble = head.splitlines()
    return preamble, sections


def _clean_cell(s: str) -> str:
    return s.strip().strip("`").strip()


def _parse_tables(body: List[str]) -> List[List[Dict[str, str]]]:
    """Find markdown tables in a section body. Returns a list of tables, each a list
    of row dicts keyed by detected column header."""
    tables: List[List[Dict[str, str]]] = []
    i = 0
    n = len(body)
    while i < n:
        line = body[i].strip()
        if line.startswith("|") and "|" in line[1:]:
            # collect the contiguous block of pipe rows
            block = []
            while i < n and body[i].strip().startswith("|"):
                block.append(body[i].strip())
                i += 1
            if len(block) >= 2:
                header_cells = [c.strip() for c in block[0].strip("|").split("|")]
                # block[1] is the separator (---). data rows are the rest.
                rows = []
                for raw in block[2:]:
                    cells = [c.strip() for c in raw.strip("|").split("|")]
                    if len(cells) < len(header_cells):
                        cells += [""] * (len(header_cells) - len(cells))
                    row = {header_cells[j]: cells[j] for j in range(len(header_cells))}
                    rows.append(row)
                if rows:
                    tables.append(rows)
        else:
            i += 1
    return tables


def _col(row: Dict[str, str], *keys: str) -> str:
    """Fetch a cell by any of several possible header names (robust to column order)."""
    for k in keys:
        for hk in row:
            if k in hk:
                return row[hk]
    return ""


def _parse_required(cell: str) -> Tuple[bool, Optional[str]]:
    c = cell.strip()
    if c in ("是", "Y", "yes", "true", "必填", "必须"):
        return True, None
    if c in ("否", "N", "no", "false", "可选", ""):
        return False, None
    # conditional, e.g. "threshold/cellpose 时是", "returnProbability=true 时建议提供"
    return False, c


def _parse_enum_cell(cell: str, ptype: str) -> Tuple[Optional[List[str]], Optional[Any], Optional[str]]:
    """Return (enum_literals, default, constraint_note)."""
    c = cell.strip()
    if not c or c in ("无固定枚举", "-", "—"):
        return None, None, None

    default = None
    m = re.search(r"默认\s*([A-Za-z0-9_\.\-]+)", c)
    if m:
        raw = m.group(1)
        default = _coerce(raw, ptype)

    # boolean-ish "true/false" is captured by the bool type already; not an enum
    if re.fullmatch(r"true\s*/\s*false.*", c):
        return None, default, None

    backticks = _BACKTICK_RE.findall(c)
    if backticks:
        # comma/、separated literal set
        return backticks, default, None

    # loose constraints we keep as a hint rather than a hard enum/validator
    if re.search(r"^[<>]=?\s*-?\d", c) or "~" in c or "Base64" in c or "storedFilename" in c \
            or "文件名" in c or "合法" in c or "路径" in c:
        return None, default, c

    # otherwise treat the whole cell as a note
    return None, default, (None if default is not None else c)


def _coerce(raw: str, ptype: str) -> Any:
    if ptype in ("number",):
        try:
            return float(raw)
        except ValueError:
            return raw
    if ptype in ("integer",):
        try:
            return int(raw)
        except ValueError:
            return raw
    if ptype in ("boolean",):
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
    return raw


def _canon_type(cell: str) -> str:
    c = cell.strip().lower()
    if c.startswith("array<") or c.startswith("array <"):
        inner = c[c.find("<") + 1: c.rfind(">")].strip()
        if inner in ("object", "obj"):
            return "array<object>"
        return "array"
    if c in ("array", "list"):
        return "array"
    return _TYPE_CANON.get(c, "any" if c else "any")


def _title_kind(title: str) -> str:
    t = title
    if "响应" in t:
        return "response"
    if "请求参数" in t or "请求" in t and "参数" in t:
        return "request"
    return "other"


def _title_method_op(title: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (method, operation) from titles like '8. cellpose: run_segmentation 请求参数'."""
    t = re.sub(r"^\s*\d+[\.\)、]?\s*", "", title)        # strip leading number
    t = re.sub(r"\s*请求参数.*$", "", t).strip()
    if not t or t in ("通用", "通用请求"):
        return None, None
    m = re.match(r"^([A-Za-z_][\w]*)\s*[:：]\s*([A-Za-z_][\w]*)", t)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^([A-Za-z_][\w]*)\b", t)
    if m and "通用" not in t:
        return m.group(1), None
    return None, None


def parse_doc(path: Path, text: str) -> Tuple[ApiSpec, List[LintIssue]]:
    issues: List[LintIssue] = []
    fname = path.name
    preamble, sections = _split_sections(text)

    # --- name / version
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    name = re.sub(r"^#+\s*", "", first_line)
    name = re.sub(r"\s*参数说明\s*$", "", name).strip()
    if not name:
        name = path.stem
        issues.append(LintIssue(fname, "error", "could not parse API name from first line"))
    short = re.sub(r"_API_v\d+$", "", name)
    short = re.sub(r"_v\d+$", "", short)
    vm = re.search(r"_v(\d+)", name)
    version = f"v{vm.group(1)}" if vm else None

    # --- endpoints / content-type / annotations (search preamble first, then whole doc)
    endpoints: List[str] = []
    content_type = None
    use_line = None
    stage_line = None
    for ln in (preamble + text.splitlines()):
        if (m := _ENDPOINT_RE.match(ln)) and m.group(1) not in endpoints:
            endpoints.append(m.group(1).strip())
        if content_type is None and (m := _CONTENT_TYPE_RE.match(ln)):
            content_type = m.group(1).strip()
        if use_line is None and (m := _USE_RE.match(ln)):
            use_line = m.group(1).strip()
        if stage_line is None and (m := _STAGE_RE.match(ln)):
            stage_line = m.group(1).strip().lower()
    if not endpoints:
        issues.append(LintIssue(fname, "error", "no Endpoint bullet found"))

    # --- purpose: prefer `> 用途:`; else first sentence of 功能说明
    purpose, purpose_source = "", "none"
    if use_line:
        purpose, purpose_source = use_line, "用途"
    else:
        for title, body in sections:
            if "功能说明" in title:
                blob = "\n".join(body).strip()
                # first sentence: split on 。 or blank line
                sent = re.split(r"。|\n\s*\n", blob)
                first = next((s.strip() for s in sent if s.strip()), "")
                if first:
                    purpose = first + ("。" if not first.endswith("。") else "")
                    purpose_source = "功能说明"
                break
    if purpose_source == "none":
        issues.append(LintIssue(fname, "warn", "no `> 用途:` line and no 功能说明 — catalog entry will be weak"))
    elif purpose_source == "功能说明":
        issues.append(LintIssue(fname, "warn", "no `> 用途:` line; fell back to 功能说明 first sentence "
                                               "(add an explicit `> 用途:` for selection quality)"))

    # --- stage
    if stage_line:
        stage, stage_source = stage_line, "declared"
    elif short in _FALLBACK_STAGE:
        stage, stage_source = _FALLBACK_STAGE[short], "inferred"
        issues.append(LintIssue(fname, "warn", f"no `> 阶段:` line; INFERRED stage='{stage}' from fallback map "
                                               f"(add `> 阶段: {stage}` to the doc)"))
    else:
        stage, stage_source = "shared", "unknown"
        issues.append(LintIssue(fname, "warn", "no `> 阶段:` line and not in fallback map; defaulted to 'shared'"))

    # --- groups & params
    groups: List[ParamGroup] = []
    discriminators: Dict[str, List[str]] = {}
    req_table_count = 0
    for title, body in sections:
        kind = _title_kind(title)
        if kind != "request":
            continue
        method, operation = _title_method_op(title)
        clean_label = re.sub(r"^\s*\d+[\.\)、]?\s*", "", title).strip()
        for table in _parse_tables(body):
            req_table_count += 1
            params: List[ParamSpec] = []
            for row in table:
                pname = _clean_cell(_col(row, "参数名", "字段", "name"))
                if not pname or pname in ("参数名", "字段"):
                    continue
                ptype = _canon_type(_col(row, "类型", "type"))
                required, rnote = _parse_required(_col(row, "必填", "required"))
                enum_cell = _col(row, "枚举", "允许值", "enum")
                enum, default, constraint = _parse_enum_cell(enum_cell, ptype)
                desc = _col(row, "说明", "描述", "desc").strip()
                params.append(ParamSpec(
                    path=pname, type=ptype, required=required, required_note=rnote,
                    enum=enum, default=default, constraint=constraint, desc=desc,
                ))
                # capture discriminator enums (top-level enum fields like segmentationMethod/operation)
                if "." not in pname and enum and len(enum) >= 2:
                    discriminators.setdefault(pname, [])
                    for v in enum:
                        if v not in discriminators[pname]:
                            discriminators[pname].append(v)
            if params:
                groups.append(ParamGroup(label=clean_label, kind="request",
                                         method=method, operation=operation, params=params))
    if req_table_count == 0:
        issues.append(LintIssue(fname, "error", "no request-parameter table found"))

    spec = ApiSpec(
        name=name, short_name=short, version=version, endpoints=endpoints,
        content_type=content_type, purpose=purpose, purpose_source=purpose_source,
        stage=stage, stage_source=stage_source, discriminators=discriminators,
        groups=groups, source_file=fname,
    )
    return spec, issues


# --------------------------------------------------------------------------------------
# Nested-path -> Pydantic model / JSON Schema
# --------------------------------------------------------------------------------------

def _split_path(path: str) -> List[Tuple[str, bool]]:
    out = []
    for seg in path.split("."):
        is_arr = seg.endswith("[]")
        out.append((seg[:-2] if is_arr else seg, is_arr))
    return out


def _build_tree(params: List[ParamSpec]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for p in params:
        cur = root
        segs = _split_path(p.path)
        for idx, (seg, is_arr) in enumerate(segs):
            node = cur.setdefault(seg, {"spec": None, "children": {}, "array": False})
            if is_arr:
                node["array"] = True
            if idx == len(segs) - 1:
                node["spec"] = p
            cur = node["children"]
    return root


def _py_class_name(api_short: str, label: str, method: Optional[str], operation: Optional[str], seg: str) -> str:
    parts = [api_short]
    if method:
        parts.append(method)
    if operation:
        parts.append(operation)
    if seg:
        parts.append(seg)
    raw = "_".join(parts)
    return re.sub(r"[^0-9A-Za-z]", "", "".join(w[:1].upper() + w[1:] for w in re.split(r"[_\s]+", raw)))


def _scalar_annotation(spec: Optional[ParamSpec]):
    if spec is None:
        return (Any, None)
    enum = spec.enum
    base = {
        "string": str, "number": float, "integer": int, "boolean": bool,
        "object": Dict[str, Any], "array": List[Any], "array<object>": List[Dict[str, Any]],
        "any": Any,
    }.get(spec.type, Any)
    if enum:
        try:
            base = Literal[tuple(enum)]  # type: ignore
        except Exception:
            base = str
    if spec.required:
        return (base, ...)
    return (Optional[base], spec.default if spec.default is not None else None)


def _node_field(class_stub: str, seg: str, node: Dict[str, Any]):
    """Return (annotation, default) for a node, recursing into children."""
    children = node["children"]
    spec = node["spec"]
    required = spec.required if spec is not None else True
    if children:
        fields = {}
        for cseg, cnode in children.items():
            ann, dflt = _node_field(f"{class_stub}{cseg[:1].upper()+cseg[1:]}", cseg, cnode)
            fields[cseg] = (ann, dflt)
        submodel = create_model(f"{class_stub}{seg[:1].upper()+seg[1:]}", **fields)
        is_array = node["array"] or (spec is not None and spec.type.startswith("array"))
        ann = List[submodel] if is_array else submodel
        return (ann, ... if required else None) if not (not required) else (Optional[ann], None)
    return _scalar_annotation(spec)


def build_model_for_group(api: ApiSpec, g: ParamGroup):
    """Build one Pydantic model for a request group. Returns the model class or None."""
    if not _PYDANTIC:
        return None
    tree = _build_tree(g.params)
    stub = _py_class_name(api.short_name, g.label, g.method, g.operation, "")
    fields = {}
    for seg, node in tree.items():
        ann, dflt = _node_field(stub, seg, node)
        fields[seg] = (ann, dflt)
    try:
        return create_model(stub or "Model", **fields)
    except Exception as e:  # pragma: no cover
        return create_model((stub or "Model") + "Fallback", **{
            seg: (Optional[Any], None) for seg in tree
        })


# --------------------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------------------

def emit_ir(kb: List[ApiSpec]) -> Dict[str, Any]:
    return {
        "version": 1,
        "num_apis": len(kb),
        "stages": _stage_index(kb),
        "apis": [asdict(a) for a in kb],
    }


def _stage_index(kb: List[ApiSpec]) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for a in kb:
        idx.setdefault(a.stage, []).append(a.name)
    return {s: idx[s] for s in _STAGE_ORDER if s in idx} | {
        s: v for s, v in idx.items() if s not in _STAGE_ORDER
    }


def emit_catalog(kb: List[ApiSpec]) -> Dict[str, Any]:
    by_stage: Dict[str, List[Dict[str, Any]]] = {}
    for a in kb:
        methods = sorted({g.method for g in a.groups if g.method})
        by_stage.setdefault(a.stage, []).append({
            "name": a.name,
            "purpose": a.purpose,
            "endpoints": a.endpoints,
            "methods": methods,
        })
    ordered = {s: by_stage[s] for s in _STAGE_ORDER if s in by_stage}
    ordered |= {s: v for s, v in by_stage.items() if s not in _STAGE_ORDER}
    return {"stages": ordered}


def emit_catalog_md(kb: List[ApiSpec]) -> str:
    cat = emit_catalog(kb)["stages"]
    out = ["# API Catalog (stage-grouped — Stage-1 selection menu)\n"]
    for stage, items in cat.items():
        label = "shared / utility" if stage == "shared" else stage
        out.append(f"## {label}")
        for it in items:
            meth = f"  · methods: {', '.join(it['methods'])}" if it["methods"] else ""
            ep = it["endpoints"][0] if it["endpoints"] else ""
            out.append(f"- **{it['name']}** — {it['purpose']}  `{ep}`{meth}")
        out.append("")
    return "\n".join(out)


def emit_context_spec(kb: List[ApiSpec], max_desc: int = 90) -> str:
    """Dense full-context payload for the Generator. Boilerplate (Content-Type, 命名约定,
    response tables) is intentionally dropped."""
    out = ["# API Specifications (compiled — authoritative)\n"]
    for a in kb:
        out.append(f"## {a.name}   [stage: {a.stage}]")
        if a.purpose:
            out.append(a.purpose)
        if a.endpoints:
            out.append("Endpoint: " + " | ".join(a.endpoints))
        if a.discriminators:
            disc = "; ".join(f"{k} ∈ {{{', '.join(v)}}}" for k, v in a.discriminators.items())
            out.append(f"Selector: {disc}")
        for g in a.groups:
            head = g.label
            out.append(f"\n### {head}")
            for p in g.params:
                bits = [p.type]
                bits.append("required" if p.required else "optional")
                if p.required_note:
                    bits.append(f"if {p.required_note}")
                if p.enum:
                    bits.append("enum: " + "|".join(p.enum))
                if p.default is not None:
                    bits.append(f"default={p.default}")
                if p.constraint:
                    bits.append(p.constraint)
                d = p.desc[:max_desc].rstrip()
                out.append(f"- {p.path} ({', '.join(bits)})" + (f" — {d}" if d else ""))
        out.append("")
    return "\n".join(out)


def emit_models_jsonschema(kb: List[ApiSpec]) -> Dict[str, Any]:
    if not _PYDANTIC:
        return {"_error": "pydantic not installed; run `pip install pydantic`"}
    schemas: Dict[str, Any] = {}
    for a in kb:
        per_api: Dict[str, Any] = {}
        for g in a.groups:
            model = build_model_for_group(a, g)
            if model is None:
                continue
            key = g.label
            if g.method:
                key = f"{g.method}:{g.operation}" if g.operation else g.method
            try:
                per_api[key] = model.model_json_schema()
            except Exception as e:  # pragma: no cover
                per_api[key] = {"_error": str(e)}
        schemas[a.name] = {
            "stage": a.stage,
            "discriminators": a.discriminators,
            "groups": per_api,
        }
    return schemas


# --------------------------------------------------------------------------------------
# Lint gate
# --------------------------------------------------------------------------------------

def lint(kb: List[ApiSpec], issues: List[LintIssue]) -> List[LintIssue]:
    out = list(issues)
    seen_names: Dict[str, str] = {}
    for a in kb:
        if a.name in seen_names:
            out.append(LintIssue(a.source_file, "error",
                                 f"duplicate API name '{a.name}' (also in {seen_names[a.name]})"))
        seen_names[a.name] = a.source_file
        for g in a.groups:
            for p in g.params:
                if p.type == "any":
                    out.append(LintIssue(a.source_file, "warn",
                                         f"param '{p.path}' has unrecognized type — defaulted to any"))
    return out


# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------

def compile_docs(docs_dir: Path) -> Tuple[List[ApiSpec], List[LintIssue]]:
    specs: List[ApiSpec] = []
    all_issues: List[LintIssue] = []
    md_files = sorted(p for p in docs_dir.rglob("*.md") if p.name.lower() != "readme.md")
    for p in md_files:
        text = p.read_text(encoding="utf-8")
        spec, issues = parse_doc(p, text)
        specs.append(spec)
        all_issues.extend(issues)
    all_issues = lint(specs, all_issues)
    return specs, all_issues


def _print_lint(issues: List[LintIssue]) -> Tuple[int, int]:
    errors = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    for i in errors:
        print(f"  ✗ ERROR  {i.file}: {i.msg}")
    for i in warns:
        print(f"  ⚠ WARN   {i.file}: {i.msg}")
    return len(errors), len(warns)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compile Markdown API specs into IR + models + catalog + context.")
    ap.add_argument("--docs", required=True, type=Path, help="directory of *.md API specs")
    ap.add_argument("--out", type=Path, default=None, help="output directory for compiled artifacts")
    ap.add_argument("--emit", default="ir,catalog,context,models",
                    help="comma list: ir,catalog,context,models")
    ap.add_argument("--lint", action="store_true", help="lint only (no emit unless --out given)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures (CI gate)")
    args = ap.parse_args(argv)

    if not args.docs.exists():
        print(f"docs dir not found: {args.docs}", file=sys.stderr)
        return 2

    specs, issues = compile_docs(args.docs)
    print(f"Parsed {len(specs)} API docs from {args.docs}")
    n_err, n_warn = _print_lint(issues)
    print(f"Lint: {n_err} error(s), {n_warn} warning(s)")

    want = {x.strip() for x in args.emit.split(",") if x.strip()}
    if args.out and not args.lint:
        args.out.mkdir(parents=True, exist_ok=True)
        if "ir" in want:
            (args.out / "kb_ir.json").write_text(
                json.dumps(emit_ir(specs), ensure_ascii=False, indent=2), encoding="utf-8")
        if "catalog" in want:
            (args.out / "catalog.json").write_text(
                json.dumps(emit_catalog(specs), ensure_ascii=False, indent=2), encoding="utf-8")
            (args.out / "catalog.md").write_text(emit_catalog_md(specs), encoding="utf-8")
        if "context" in want:
            (args.out / "context_spec.md").write_text(emit_context_spec(specs), encoding="utf-8")
        if "models" in want:
            (args.out / "models_jsonschema.json").write_text(
                json.dumps(emit_models_jsonschema(specs), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote artifacts to {args.out}/")

    if n_err > 0:
        return 1
    if args.strict and n_warn > 0:
        print("strict mode: warnings present -> failing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

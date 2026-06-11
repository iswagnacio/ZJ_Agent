#!/usr/bin/env python3
"""
doc_compiler — compile structured Markdown API specs into a single IR, and derive:
  (1) per-(api, method:operation) JSON-Schema/Pydantic models  -> Reviewer + structured output
  (2) stage-grouped catalog one-liners                         -> Stage-1 selection
  (3) a dense full-context spec                                -> Generator
  (4) a doc lint gate                                          -> CI / authoring-time

Markdown docs are the single source of truth.

Grouping & composition
----------------------
Within an API doc, every request-parameter table is classified:
  * title contains "响应"                     -> response, ignored
  * title is "<method>: <op1> / <op2> 请求参数" -> a method branch (registered under each op)
  * any other table with parameter rows       -> merged into the COMMON group
The COMMON group holds fields shared across methods (sessionId, shared sub-objects like
roiRenderParams / outputOptions). Each branch's emitted schema is COMMON + branch, composed
at build time, so a shared container (e.g. outputOptions) unions its fields from both.

Usage
-----
    python compiler.py --docs ./api_docs --out ./compiled
    python compiler.py --docs ./api_docs --lint --strict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

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
    path: str
    type: str
    required: bool
    required_note: Optional[str] = None
    enum: Optional[List[str]] = None
    default: Optional[Any] = None
    constraint: Optional[str] = None
    desc: str = ""


@dataclass
class ParamGroup:
    label: str
    kind: str                       # "request" | "response" | "other"
    method: Optional[str]           # None for the common group
    operation: Optional[str]
    params: List[ParamSpec] = field(default_factory=list)


@dataclass
class ApiSpec:
    name: str
    short_name: str
    version: Optional[str]
    endpoints: List[str]
    content_type: Optional[str]
    purpose: str
    purpose_source: str
    stage: str
    stage_source: str
    discriminators: Dict[str, List[str]]
    groups: List[ParamGroup]        # [common] + branch groups (unmerged; composed at emit time)
    source_file: str


@dataclass
class LintIssue:
    file: str
    level: str
    msg: str


_FALLBACK_STAGE = {
    "Pic_Split": "deconvolve", "Segment_ROI": "segment", "Create_Target": "target",
    "Measure_ROI": "measure", "Formula": "calculate", "ROI_Render": "render",
    "Input_Interpretation": "shared", "Put_File": "shared", "Get_File": "shared",
    "Get_Target": "shared",
}
_STAGE_ORDER = ["deconvolve", "segment", "target", "measure", "calculate", "render", "shared"]
_TYPE_CANON = {
    "string": "string", "str": "string", "number": "number", "float": "number",
    "double": "number", "integer": "integer", "int": "integer", "boolean": "boolean",
    "bool": "boolean", "object": "object", "obj": "object", "array": "array",
}


# --------------------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ENDPOINT_RE = re.compile(r"^\s*-\s*\*\*Endpoint(?:\s*\d+)?\*\*\s*[:：]\s*`?(.+?)`?\s*$")
_CONTENT_TYPE_RE = re.compile(r"^\s*-\s*\*\*Content-Type\*\*\s*[:：]\s*`?(.+?)`?\s*$")
_USE_RE = re.compile(r"^\s*>\s*用途\s*[:：]\s*(.+?)\s*$")
_STAGE_RE = re.compile(r"^\s*>\s*(?:阶段|stage)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# markers that signal a cell is an example / open list / format hint, not a closed enum
_EXAMPLE_MARK = ("例如", "如 ", "等", "见", "任意", "默认底图", "或", "推荐")
_FORMAT_MARK = ("#RRGGBB", "RRGGBB", "R,G,B", "Base64", "data URL", "storedFilename",
                "文件名", "色名", "合法", "路径", "类别")


def _split_sections(text: str) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    lines = text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    cur_title: Optional[str] = None
    cur_body: List[str] = []
    for ln in lines:
        m = _HEADER_RE.match(ln)
        if m:
            if cur_title is not None:
                sections.append((cur_title, cur_body))
            cur_title = m.group(2).strip()
            cur_body = []
        else:
            cur_body.append(ln)
    if cur_title is not None:
        sections.append((cur_title, cur_body))
    first = text.find("\n#")
    preamble = text[: first if first != -1 else len(text)].splitlines()
    return preamble, sections


def _clean_cell(s: str) -> str:
    return s.strip().strip("`").strip()


def _parse_tables(body: List[str]) -> List[List[Dict[str, str]]]:
    tables: List[List[Dict[str, str]]] = []
    i, n = 0, len(body)
    while i < n:
        if body[i].strip().startswith("|") and "|" in body[i].strip()[1:]:
            block = []
            while i < n and body[i].strip().startswith("|"):
                block.append(body[i].strip())
                i += 1
            if len(block) >= 2:
                headers = [c.strip() for c in block[0].strip("|").split("|")]
                rows = []
                for raw in block[2:]:
                    cells = [c.strip() for c in raw.strip("|").split("|")]
                    if len(cells) < len(headers):
                        cells += [""] * (len(headers) - len(cells))
                    rows.append({headers[j]: cells[j] for j in range(len(headers))})
                if rows:
                    tables.append(rows)
        else:
            i += 1
    return tables


def _col(row: Dict[str, str], *keys: str) -> str:
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
    return False, c


def _coerce(raw: str, ptype: str) -> Any:
    if ptype == "number":
        try:
            return float(raw)
        except ValueError:
            return raw
    if ptype == "integer":
        try:
            return int(raw)
        except ValueError:
            return raw
    if ptype == "boolean" and raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    return raw


def _coerce_default(raw: str, ptype: str) -> Optional[Any]:
    r = raw.strip().strip("`").strip()
    if not r or r in ("无", "-", "—", "见各分支"):
        return None
    if _CJK_RE.search(r):          # prose like "按默认底图规则" is not a literal default
        return None
    return _coerce(r, ptype)


def _parse_enum_cell(cell: str, ptype: str) -> Tuple[Optional[List[str]], Optional[Any], Optional[str]]:
    """Return (enum_literals, default, constraint_note). Backticked tokens are treated as a
    closed enum ONLY when the cell has no example/open-list/format markers."""
    c = cell.strip()
    if not c or c in ("无固定枚举", "-", "—"):
        return None, None, None

    default = None
    m = re.search(r"默认\s*([A-Za-z0-9_\.\-]+)", c)
    if m:
        default = _coerce(m.group(1), ptype)

    if re.fullmatch(r"true\s*/\s*false.*", c):     # boolean already typed
        return None, default, None

    is_example = any(t in c for t in _EXAMPLE_MARK)
    is_format = any(t in c for t in _FORMAT_MARK) or bool(re.search(r"[<>]=?\s*-?\d", c)) or "~" in c
    backticks = _BACKTICK_RE.findall(c)

    if backticks and not is_example and not is_format:
        return backticks, default, None            # genuine closed enum

    note = None if default is not None else (c if (is_format or is_example or backticks) else c)
    return None, default, note


def _canon_type(cell: str) -> str:
    c = cell.strip().lower()
    if c.startswith("array<") or c.startswith("array <"):
        inner = c[c.find("<") + 1: c.rfind(">")].strip()
        return "array<object>" if inner in ("object", "obj") else "array"
    if c in ("array", "list"):
        return "array"
    return _TYPE_CANON.get(c, "any")


def _branch_classify(title: str) -> Tuple[Optional[str], List[str]]:
    """A section is a METHOD BRANCH only if its title contains '请求参数' and names a method.
    Returns (method, [operations]); ('GET', []) for dual-endpoint verb sections;
    (None, []) for the common group and all shared-detail tables."""
    if "请求参数" not in title:
        return None, []
    core = re.sub(r"^\s*\d+[\.\)、]?\s*", "", title)
    core = re.sub(r"\s*请求参数.*$", "", core).strip()
    if not core or "通用" in core:
        return None, []
    m = re.match(r"^([A-Za-z_][\w]*)\s*[:：]\s*(.+)$", core)
    if m:
        method = m.group(1)
        ops = [o.strip() for o in re.split(r"[/、,]", m.group(2))
               if re.fullmatch(r"[A-Za-z_][\w]*", o.strip() or "")]
        return method, ops
    m = re.match(r"^([A-Za-z_][\w]*)\b", core)      # e.g. GET / POST
    if m:
        return m.group(1), []
    return None, []


def _rows_to_params(table: List[Dict[str, str]],
                    discriminators: Dict[str, List[str]]) -> List[ParamSpec]:
    params: List[ParamSpec] = []
    for row in table:
        pname = _clean_cell(_col(row, "参数名", "字段", "name"))
        if not pname or pname in ("参数名", "字段"):
            continue
        ptype = _canon_type(_col(row, "类型", "type"))
        required, rnote = _parse_required(_col(row, "必填", "required"))
        enum, default, constraint = _parse_enum_cell(_col(row, "枚举", "允许值", "enum"), ptype)
        dcol = _coerce_default(_col(row, "默认值", "缺省值"), ptype)   # dedicated column wins
        if dcol is not None:
            default = dcol
        desc = _col(row, "说明", "描述", "desc").strip()
        params.append(ParamSpec(path=pname, type=ptype, required=required, required_note=rnote,
                                enum=enum, default=default, constraint=constraint, desc=desc))
        if "." not in pname and enum and len(enum) >= 2:
            discriminators.setdefault(pname, [])
            for v in enum:
                if v not in discriminators[pname]:
                    discriminators[pname].append(v)
    return params


def parse_doc(path: Path, text: str) -> Tuple[ApiSpec, List[LintIssue]]:
    issues: List[LintIssue] = []
    fname = path.name
    preamble, sections = _split_sections(text)

    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    name = re.sub(r"\s*参数说明\s*$", "", re.sub(r"^#+\s*", "", first_line)).strip() or path.stem
    short = re.sub(r"_v\d+$", "", re.sub(r"_API_v\d+$", "", name))
    vm = re.search(r"_v(\d+)", name)
    version = f"v{vm.group(1)}" if vm else None

    endpoints: List[str] = []
    content_type = use_line = stage_line = None
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

    purpose, purpose_source = "", "none"
    if use_line:
        purpose, purpose_source = use_line, "用途"
    else:
        for title, body in sections:
            if "功能说明" in title:
                blob = "\n".join(body).strip()
                first = next((s.strip() for s in re.split(r"。|\n\s*\n", blob) if s.strip()), "")
                if first:
                    purpose = first + ("。" if not first.endswith("。") else "")
                    purpose_source = "功能说明"
                break
    if purpose_source == "none":
        issues.append(LintIssue(fname, "warn", "no `> 用途:` line and no 功能说明 — catalog entry will be weak"))
    elif purpose_source == "功能说明":
        issues.append(LintIssue(fname, "warn", "no `> 用途:` line; fell back to 功能说明 first sentence "
                                               "(add an explicit `> 用途:` for selection quality)"))

    if stage_line:
        stage, stage_source = stage_line, "declared"
    elif short in _FALLBACK_STAGE:
        stage, stage_source = _FALLBACK_STAGE[short], "inferred"
        issues.append(LintIssue(fname, "warn", f"no `> 阶段:` line; INFERRED stage='{stage}' "
                                               f"(add `> 阶段: {stage}` to the doc)"))
    else:
        stage, stage_source = "shared", "unknown"
        issues.append(LintIssue(fname, "warn", "no `> 阶段:` line and not in fallback map; defaulted to 'shared'"))

    # ---- classify tables -> common group + method branches ----
    discriminators: Dict[str, List[str]] = {}
    common_params: List[ParamSpec] = []
    branch_groups: List[ParamGroup] = []
    saw_tongyong = False
    n_request_tables = 0

    for title, body in sections:
        if "响应" in title:
            continue
        method, ops = _branch_classify(title)
        clean_label = re.sub(r"^\s*\d+[\.\)、]?\s*", "", title).strip()
        for table in _parse_tables(body):
            params = _rows_to_params(table, discriminators)
            if not params:
                continue                       # not a parameter table (e.g. 场景|默认底图)
            n_request_tables += 1
            if method:
                for op in (ops or [None]):
                    branch_groups.append(ParamGroup(
                        label=clean_label, kind="request", method=method, operation=op,
                        params=[ParamSpec(**asdict(p)) for p in params]))
            else:
                if "通用请求参数" in title:
                    saw_tongyong = True
                common_params.extend(params)

    if n_request_tables == 0:
        issues.append(LintIssue(fname, "error", "no request-parameter table found"))

    groups: List[ParamGroup] = []
    if common_params:
        # dedupe by path (later table wins), preserve order
        seen: Dict[str, ParamSpec] = {}
        for p in common_params:
            seen[p.path] = p
        groups.append(ParamGroup(
            label="通用请求参数" if (saw_tongyong or branch_groups) else "请求参数",
            kind="request", method=None, operation=None, params=list(seen.values())))
    groups.extend(branch_groups)

    spec = ApiSpec(name=name, short_name=short, version=version, endpoints=endpoints,
                   content_type=content_type, purpose=purpose, purpose_source=purpose_source,
                   stage=stage, stage_source=stage_source, discriminators=discriminators,
                   groups=groups, source_file=fname)
    return spec, issues


# --------------------------------------------------------------------------------------
# Nested-path -> Pydantic model / JSON Schema
# --------------------------------------------------------------------------------------

def _split_path(path: str) -> List[Tuple[str, bool]]:
    out = []
    for seg in path.split("."):
        arr = seg.endswith("[]")
        out.append((seg[:-2] if arr else seg, arr))
    return out


def _build_tree(params: List[ParamSpec]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for p in params:
        cur = root
        segs = _split_path(p.path)
        for idx, (seg, arr) in enumerate(segs):
            node = cur.setdefault(seg, {"spec": None, "children": {}, "array": False})
            if arr:
                node["array"] = True
            if idx == len(segs) - 1:
                node["spec"] = p
            cur = node["children"]
    return root


def _scalar_annotation(spec: Optional[ParamSpec]):
    if spec is None:
        return (Any, None)
    base = {"string": str, "number": float, "integer": int, "boolean": bool,
            "object": Dict[str, Any], "array": List[Any], "array<object>": List[Dict[str, Any]],
            "any": Any}.get(spec.type, Any)
    if spec.enum:
        try:
            base = Literal[tuple(spec.enum)]  # type: ignore
        except Exception:
            base = str
    return (base, ...) if spec.required else (Optional[base], spec.default if spec.default is not None else None)


def _node_field(stub: str, seg: str, node: Dict[str, Any]):
    children, spec = node["children"], node["spec"]
    required = spec.required if spec is not None else True
    if children:
        fields = {c: _node_field(f"{stub}{c[:1].upper()+c[1:]}", c, cn) for c, cn in children.items()}
        sub = create_model(f"{stub}{seg[:1].upper()+seg[1:]}", **fields)
        is_arr = node["array"] or (spec is not None and spec.type.startswith("array"))
        ann = List[sub] if is_arr else sub
        return (ann, ...) if required else (Optional[ann], None)
    return _scalar_annotation(spec)


def _stub(api_short: str, key: str) -> str:
    raw = f"{api_short}_{key}"
    return re.sub(r"[^0-9A-Za-z]", "", "".join(w[:1].upper() + w[1:] for w in re.split(r"[_:\s]+", raw)))


def _model_from_params(api_short: str, key: str, params: List[ParamSpec]):
    if not _PYDANTIC:
        return None
    tree = _build_tree(params)
    stub = _stub(api_short, key) or "Model"
    fields = {seg: _node_field(stub, seg, node) for seg, node in tree.items()}
    try:
        return create_model(stub, **fields)
    except Exception:  # pragma: no cover
        return create_model(stub + "Fallback", **{s: (Optional[Any], None) for s in tree})


def _merge_params(common: List[ParamSpec], branch: List[ParamSpec]) -> List[ParamSpec]:
    by_path: Dict[str, ParamSpec] = {}
    for p in common + branch:        # branch after -> overrides on identical path
        by_path[p.path] = p
    return list(by_path.values())


# --------------------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------------------

def _branch_key(g: ParamGroup) -> str:
    if g.method and g.operation:
        return f"{g.method}:{g.operation}"
    if g.method:
        return g.method
    return g.label


def emit_models_jsonschema(kb: List[ApiSpec]) -> Dict[str, Any]:
    if not _PYDANTIC:
        return {"_error": "pydantic not installed; run `pip install pydantic`"}
    out: Dict[str, Any] = {}
    for a in kb:
        common = next((g for g in a.groups if g.method is None), None)
        common_params = common.params if common else []
        branches = [g for g in a.groups if g.method is not None]
        groups: Dict[str, Any] = {}
        if common is not None:
            m = _model_from_params(a.short_name, common.label, common_params)
            if m is not None:
                groups[common.label] = m.model_json_schema()
        for g in branches:                       # composed: common + branch
            merged = _merge_params(common_params, g.params)
            m = _model_from_params(a.short_name, _branch_key(g), merged)
            if m is not None:
                groups[_branch_key(g)] = m.model_json_schema()
        out[a.name] = {"stage": a.stage, "discriminators": a.discriminators, "groups": groups}
    return out


def build_model_for_group(api_short: str, group: ParamGroup):
    """Build a Pydantic model for ONE group's params (uncomposed).

    Kept for callers that want a model object for a single table. Note that the
    emitted per-(method, operation) schemas in :func:`emit_models_jsonschema` are
    composed (common + branch); this helper does not compose.
    """
    return _model_from_params(api_short, _branch_key(group), group.params)


def _stage_index(kb: List[ApiSpec]) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for a in kb:
        idx.setdefault(a.stage, []).append(a.name)
    ordered = {s: idx[s] for s in _STAGE_ORDER if s in idx}
    ordered.update({s: v for s, v in idx.items() if s not in _STAGE_ORDER})
    return ordered


def emit_ir(kb: List[ApiSpec]) -> Dict[str, Any]:
    return {"version": 1, "num_apis": len(kb), "stages": _stage_index(kb),
            "apis": [asdict(a) for a in kb]}


def emit_catalog(kb: List[ApiSpec]) -> Dict[str, Any]:
    by_stage: Dict[str, List[Dict[str, Any]]] = {}
    for a in kb:
        methods = sorted({g.method for g in a.groups if g.method})
        by_stage.setdefault(a.stage, []).append(
            {"name": a.name, "purpose": a.purpose, "endpoints": a.endpoints, "methods": methods})
    ordered = {s: by_stage[s] for s in _STAGE_ORDER if s in by_stage}
    ordered.update({s: v for s, v in by_stage.items() if s not in _STAGE_ORDER})
    return {"stages": ordered}


def emit_catalog_md(kb: List[ApiSpec]) -> str:
    out = ["# API Catalog (stage-grouped — Stage-1 selection menu)\n"]
    for stage, items in emit_catalog(kb)["stages"].items():
        out.append(f"## {'shared / utility' if stage == 'shared' else stage}")
        for it in items:
            meth = f"  · methods: {', '.join(it['methods'])}" if it["methods"] else ""
            ep = it["endpoints"][0] if it["endpoints"] else ""
            out.append(f"- **{it['name']}** — {it['purpose']}  `{ep}`{meth}")
        out.append("")
    return "\n".join(out)


def emit_context_spec(kb: List[ApiSpec], max_desc: int = 300) -> str:
    out = ["# API Specifications (compiled — authoritative)\n"]
    for a in kb:
        out.append(f"## {a.name}   [stage: {a.stage}]")
        if a.purpose:
            out.append(a.purpose)
        if a.endpoints:
            out.append("Endpoint: " + " | ".join(a.endpoints))
        if a.discriminators:
            out.append("Selector: " + "; ".join(f"{k} ∈ {{{', '.join(v)}}}"
                                                 for k, v in a.discriminators.items()))
        for g in a.groups:
            out.append(f"\n### {g.label}")
            for p in g.params:
                bits = [p.type, "required" if p.required else "optional"]
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


# --------------------------------------------------------------------------------------
# Lint
# --------------------------------------------------------------------------------------

def lint(kb: List[ApiSpec], issues: List[LintIssue]) -> List[LintIssue]:
    out = list(issues)
    seen: Dict[str, str] = {}
    for a in kb:
        if a.name in seen:
            out.append(LintIssue(a.source_file, "error", f"duplicate API name '{a.name}'"))
        seen[a.name] = a.source_file
        for g in a.groups:
            for p in g.params:
                if p.type == "any":
                    out.append(LintIssue(a.source_file, "warn",
                                         f"param '{p.path}' unrecognized type -> any"))
    return out


# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------

def compile_docs(docs_dir: Path) -> Tuple[List[ApiSpec], List[LintIssue]]:
    specs: List[ApiSpec] = []
    issues: List[LintIssue] = []
    for p in sorted(q for q in docs_dir.rglob("*.md") if q.name.lower() != "readme.md"):
        spec, iss = parse_doc(p, p.read_text(encoding="utf-8"))
        specs.append(spec)
        issues.extend(iss)
    return specs, lint(specs, issues)


def _print_lint(issues: List[LintIssue]) -> Tuple[int, int]:
    errs = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    for i in errs:
        print(f"  \u2717 ERROR  {i.file}: {i.msg}")
    for i in warns:
        print(f"  \u26a0 WARN   {i.file}: {i.msg}")
    return len(errs), len(warns)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compile Markdown API specs.")
    ap.add_argument("--docs", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--emit", default="ir,catalog,context,models")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--strict", action="store_true")
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
            (args.out / "kb_ir.json").write_text(json.dumps(emit_ir(specs), ensure_ascii=False, indent=2), "utf-8")
        if "catalog" in want:
            (args.out / "catalog.json").write_text(json.dumps(emit_catalog(specs), ensure_ascii=False, indent=2), "utf-8")
            (args.out / "catalog.md").write_text(emit_catalog_md(specs), "utf-8")
        if "context" in want:
            (args.out / "context_spec.md").write_text(emit_context_spec(specs), "utf-8")
        if "models" in want:
            (args.out / "models_jsonschema.json").write_text(
                json.dumps(emit_models_jsonschema(specs), ensure_ascii=False, indent=2), "utf-8")
        print(f"Wrote artifacts to {args.out}/")

    if n_err:
        return 1
    if args.strict and n_warn:
        print("strict mode: warnings present -> failing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
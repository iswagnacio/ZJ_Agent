"""Doc → schema compiler.

Compiles the Markdown API specs in ``api_docs/`` into a single IR and the views
derived from it: per-(api, method:operation) JSON-Schema / Pydantic models, the
stage-grouped catalog, and the dense full-context spec. The Markdown docs are the
single source of truth — nothing downstream hand-maintains API names, fields, enums,
or stage assignments.

Typical use from other modules (e.g. the KnowledgeProvider seam)::

    from src.knowledge.compiler import compile_docs, emit_context_spec, build_model_for_group

    specs, issues = compile_docs(Path("../api_docs"))
    context = emit_context_spec(specs)
"""
from .compiler import (
    # IR data model
    ParamSpec,
    ParamGroup,
    ApiSpec,
    LintIssue,
    # pipeline
    compile_docs,
    parse_doc,
    lint,
    # emitters / views over the IR
    emit_ir,
    emit_catalog,
    emit_catalog_md,
    emit_context_spec,
    emit_models_jsonschema,
    build_model_for_group,
    # CLI entry point (used by build_kb.py)
    main,
)

__all__ = [
    "ParamSpec",
    "ParamGroup",
    "ApiSpec",
    "LintIssue",
    "compile_docs",
    "parse_doc",
    "lint",
    "emit_ir",
    "emit_catalog",
    "emit_catalog_md",
    "emit_context_spec",
    "emit_models_jsonschema",
    "build_model_for_group",
    "main",
]
"""Agent 3: Workplan Reviewer — deterministic validation gate.

The Reviewer is NOT an LLM. It is a pure, deterministic gate that decides whether a
Generator-produced Workplan is *structurally well-formed and internally consistent*
before it reaches the user / the Phase-2 executor.

Two severities, by design:

  • ERROR  (hard)  — schema-agnostic structural invariants. Any error ⇒ status="reject".
                     These are facts about the Workplan skeleton that must hold for ANY
                     valid plan regardless of biology/recipe: referential integrity,
                     duplicate ids, malformed skeleton, mandatory job ordering.

  • WARNING (soft) — vocabulary-dependent checks. They never block. A token the current
                     knowledge base doesn't recognise (e.g. a segmentation method with no
                     backend API yet, like `rnascope`) is surfaced, not rejected — the
                     vocabulary evolves and the KB is the source of truth, so we flag and
                     move on.

What the Reviewer deliberately does NOT check: *recipe correctness* — whether `siriusred`
should use custom deconvolution vs a preset, or whether `ki67` needs the islet-restriction
chain. Those are semantic/recipe judgements owned by the Generator and measured by diffing
against worked examples, not by this gate. A structurally valid plan with the wrong recipe
is an ACCEPT here by intent.

ALL Workplan-skeleton assumptions live in the single ``CONTRACT`` block below — nowhere
else. Backend *vocabulary* (which methods/matrices actually have endpoints) is read from the
compiled KB at runtime and cross-checked, so nothing about the API surface is duplicated in
code. This is the anti-drift rule: the three agents previously drifted because each kept its
own private allow-list.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════════
#  CONTRACT — the single source of truth for the Workplan *skeleton*.
#  (Backend API vocabulary is discovered from the KB at runtime; see _load_kb_vocab.)
# ════════════════════════════════════════════════════════════════════════════════════
CONTRACT: Dict[str, Any] = {
    "top_level_required": [
        "experimentName", "inputMode", "analysisGoal", "imageInference",
        "workplanSceneType", "channels", "targets", "jobs",
    ],
    "channel_fields": ["channelId", "channelName", "semanticRole"],
    "target_fields": ["targetName", "targetType", "description"],
    "job_fields": ["jobId", "jobName", "jobType", "stepDescript", "inputs", "outputs"],

    # the only three job types; segmentation/measurement are steps INSIDE create_target
    "job_types": ("pic_split", "create_target", "formula"),
    "plan_key": {
        "pic_split": "picSplitPlan",
        "create_target": "createTargetPlan",
        "formula": "formulaPlan",
    },

    # mandatory ordering: job_00 is always pic_split; exactly one formula and it is last
    "first_job_type": "pic_split",
    "last_job_type": "formula",

    # Workplan-level vocabulary (the four create_target modes + split methods).
    # These are the *modes the Generator may emit*; whether each has a backend API is a
    # separate KB question, cross-checked at runtime (so `rnascope`/`""` flag automatically).
    "split_methods": ("rgb_split", "color_deconvolution"),
    "segment_methods": ("threshold", "cellpose", "weka", "rnascope", ""),  # "" == derived/measure-filter
}


@dataclass
class Issue:
    severity: str            # "error" | "warning"
    code: str                # stable machine code, e.g. "DANGLING_CHANNEL_REF"
    location: str            # JSON-ish path, e.g. "jobs[2].inputs.channelId"
    message: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


class ReviewerAgent:
    """Deterministic Workplan validation gate.

    Constructed with no arguments in the LangGraph workflow. Optionally accepts a
    ``KnowledgeProvider`` (or a ``kb_dir`` to load one) so vocabulary checks can be made
    against the real compiled KB. If the KB is unavailable the Reviewer degrades to
    structural-only validation rather than crashing — the hard gate still works.
    """

    def __init__(self, provider: Optional[Any] = None, kb_dir: str = "kb_compiled"):
        self.provider = provider if provider is not None else _try_load_provider(kb_dir)
        # KB-supported vocabulary (for soft cross-checks). Empty sets ⇒ checks skipped.
        self.kb_segment_methods, self.kb_split_methods, self.kb_matrices = _load_kb_vocab(self.provider)
        logger.info(
            "Reviewer ready (KB %s). seg=%s split=%s",
            "loaded" if self.provider else "absent",
            sorted(self.kb_segment_methods) or "—",
            sorted(self.kb_split_methods) or "—",
        )

    # ─────────────────────────────────── public API ───────────────────────────────────
    async def review_workplan(self, workplan: dict, requirements: Optional[dict] = None) -> Dict[str, Any]:
        """Async entry point matching the LangGraph node contract.

        Returns a dict with ``status`` ∈ {"accept","reject"}, plus ``errors`` (hard),
        ``critical_issues`` (alias of errors, for the existing router/feedback path),
        ``warnings`` (soft), and a human-readable ``summary``.
        """
        issues = self.review(workplan)
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        status = "reject" if errors else "accept"
        logger.info("Review: %s (%d errors, %d warnings)", status, len(errors), len(warnings))
        return {
            "status": status,
            "errors": [i.as_dict() for i in errors],
            "critical_issues": [i.as_dict() for i in errors],   # back-compat with reviewer_node
            "warnings": [i.as_dict() for i in warnings],
            "summary": _summary(status, errors, warnings),
        }

    def review(self, workplan: Any) -> List[Issue]:
        """Synchronous core. Returns the full issue list. Safe to call directly in tests."""
        issues: List[Issue] = []

        # ── 0. skeleton must exist before anything else can be checked ──────────────────
        if not isinstance(workplan, dict):
            return [Issue("error", "NOT_AN_OBJECT", "<root>", "Workplan must be a JSON object.")]

        for key in CONTRACT["top_level_required"]:
            if key not in workplan:
                issues.append(Issue("error", "MISSING_TOP_LEVEL_KEY", key, f"Missing required top-level key '{key}'."))
        for key in ("channels", "targets", "jobs"):
            if key in workplan and not isinstance(workplan[key], list):
                issues.append(Issue("error", "WRONG_TYPE", key, f"'{key}' must be a list."))

        channels = workplan.get("channels") if isinstance(workplan.get("channels"), list) else []
        targets = workplan.get("targets") if isinstance(workplan.get("targets"), list) else []
        jobs = workplan.get("jobs") if isinstance(workplan.get("jobs"), list) else []

        if "jobs" in workplan and not jobs:
            issues.append(Issue("error", "NO_JOBS", "jobs", "Workplan has no jobs."))

        # ── 1. channels & targets: shape + uniqueness ──────────────────────────────────
        declared_channels = self._check_collection(issues, channels, "channels",
                                                   CONTRACT["channel_fields"], "channelId", "CHANNEL")
        declared_targets = self._check_collection(issues, targets, "targets",
                                                  CONTRACT["target_fields"], "targetName", "TARGET")

        # ── 2. per-job shape: required fields, valid jobType, matching plan present ─────
        seen_job_ids: set = set()
        for i, job in enumerate(jobs):
            loc = f"jobs[{i}]"
            if not isinstance(job, dict):
                issues.append(Issue("error", "JOB_NOT_OBJECT", loc, "Job must be an object."))
                continue
            for f in CONTRACT["job_fields"]:
                if f not in job:
                    issues.append(Issue("error", "MISSING_JOB_FIELD", f"{loc}.{f}", f"Job missing '{f}'."))
            jid = job.get("jobId")
            if jid is not None:
                if jid in seen_job_ids:
                    issues.append(Issue("error", "DUPLICATE_JOB_ID", f"{loc}.jobId", f"Duplicate jobId '{jid}'."))
                seen_job_ids.add(jid)
            jt = job.get("jobType")
            if jt not in CONTRACT["job_types"]:
                issues.append(Issue("error", "UNKNOWN_JOB_TYPE", f"{loc}.jobType",
                                    f"jobType '{jt}' not in {CONTRACT['job_types']}."))
            else:
                plan_key = CONTRACT["plan_key"][jt]
                if plan_key not in job or not isinstance(job.get(plan_key), dict):
                    issues.append(Issue("error", "MISSING_PLAN", f"{loc}.{plan_key}",
                                        f"jobType '{jt}' requires a '{plan_key}' object."))

        # ── 3. mandatory ordering (only meaningful if every job has a known jobType) ────
        job_types = [j.get("jobType") for j in jobs if isinstance(j, dict)]
        if jobs and all(t in CONTRACT["job_types"] for t in job_types):
            if job_types[0] != CONTRACT["first_job_type"]:
                issues.append(Issue("error", "FIRST_JOB_NOT_PIC_SPLIT", "jobs[0]",
                                    f"First job must be '{CONTRACT['first_job_type']}', got '{job_types[0]}'."))
            n_split = job_types.count("pic_split")
            if n_split != 1:
                issues.append(Issue("error", "PIC_SPLIT_COUNT", "jobs",
                                    f"Expected exactly one pic_split job, found {n_split}."))
            n_formula = job_types.count("formula")
            if n_formula != 1:
                issues.append(Issue("error", "FORMULA_COUNT", "jobs",
                                    f"Expected exactly one formula job, found {n_formula}."))
            elif job_types[-1] != CONTRACT["last_job_type"]:
                issues.append(Issue("error", "FORMULA_NOT_LAST", f"jobs[{len(jobs)-1}]",
                                    "The single formula job must be the last job."))

        # ── 4. referential integrity (the heart of the gate) ───────────────────────────
        self._check_references(issues, jobs, declared_channels, declared_targets)

        # ── 5. channelMapping keys must equal declared channelIds exactly ──────────────
        for i, job in enumerate(jobs):
            if isinstance(job, dict) and job.get("jobType") == "pic_split":
                mapping = (job.get("picSplitPlan") or {}).get("channelMapping")
                if isinstance(mapping, dict):
                    keys = set(mapping.keys())
                    if keys != declared_channels and declared_channels:
                        issues.append(Issue("error", "CHANNEL_MAPPING_MISMATCH", f"jobs[{i}].picSplitPlan.channelMapping",
                                            f"channelMapping keys {sorted(keys)} ≠ declared channelIds {sorted(declared_channels)}."))

        # ── 6. formula completeness ────────────────────────────────────────────────────
        self._check_formula(issues, jobs)

        # ── soft: vocabulary + conventions (never block) ───────────────────────────────
        self._check_vocabulary(issues, jobs)
        self._check_conventions(issues, jobs, targets)

        return issues

    # ──────────────────────────────── helpers ─────────────────────────────────────────
    def _check_collection(self, issues, items, name, fields, id_field, code) -> set:
        """Validate a channels/targets list: required fields + unique id. Returns the id set."""
        ids: set = set()
        for i, item in enumerate(items):
            loc = f"{name}[{i}]"
            if not isinstance(item, dict):
                issues.append(Issue("error", f"{code}_NOT_OBJECT", loc, f"{name} entry must be an object."))
                continue
            for f in fields:
                if f not in item:
                    issues.append(Issue("error", f"MISSING_{code}_FIELD", f"{loc}.{f}", f"{name} entry missing '{f}'."))
            v = item.get(id_field)
            if v is not None:
                if v in ids:
                    issues.append(Issue("error", f"DUPLICATE_{code}", f"{loc}.{id_field}", f"Duplicate {id_field} '{v}'."))
                ids.add(v)
        return ids

    def _check_references(self, issues, jobs, declared_channels: set, declared_targets: set):
        """Channel refs must be declared; target refs must be created by an EARLIER job."""
        available_targets: set = set()   # grows as we walk jobs in order

        def channel_refs(job) -> List[Tuple[str, str]]:
            out = []
            inp = job.get("inputs") or {}
            for c in _as_list(inp.get("channelId")):
                out.append((c, "inputs.channelId"))
            plan = job.get("createTargetPlan") or {}
            for c in _as_list(plan.get("measureOn")):
                out.append((c, "createTargetPlan.measureOn"))
            for fc in _as_list(plan.get("filterConditions")):
                if isinstance(fc, dict) and "channelId" in fc:
                    out.append((fc["channelId"], "createTargetPlan.filterConditions.channelId"))
            # NOTE: outputs.generatedChannels is intentionally NOT validated as a channelId
            # reference. Across real workplans it holds either channelIds (siriusred) or human
            # channel *names* (ki67: "DAPI"; SMA: "苏木精（细胞核）"), so it is descriptive output
            # metadata. The contract only requires inputs.channelId / measureOn /
            # filterConditions.channelId / channelMapping keys to resolve to declared channels.
            return out

        def target_refs(job) -> List[Tuple[str, str]]:
            out = []
            inp = job.get("inputs") or {}
            for t in _as_list(inp.get("sourceTargetNames")):
                out.append((t, "inputs.sourceTargetNames"))
            plan = job.get("createTargetPlan") or {}
            for t in _as_list(plan.get("sourceTargetNames")):
                out.append((t, "createTargetPlan.sourceTargetNames"))
            if job.get("jobType") == "formula":
                for ti in _as_list(inp.get("targetInputs")):
                    if isinstance(ti, dict) and "targetName" in ti:
                        out.append((ti["targetName"], "inputs.targetInputs.targetName"))
            return out

        for i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            loc = f"jobs[{i}]"
            for ch, where in channel_refs(job):
                if declared_channels and ch not in declared_channels:
                    issues.append(Issue("error", "DANGLING_CHANNEL_REF", f"{loc}.{where}",
                                        f"References undeclared channelId '{ch}'."))
            for tg, where in target_refs(job):
                if tg not in available_targets:
                    if tg in declared_targets or _produced_later(jobs, i, tg):
                        issues.append(Issue("error", "FORWARD_TARGET_REF", f"{loc}.{where}",
                                            f"Target '{tg}' is referenced before the job that creates it."))
                    else:
                        issues.append(Issue("error", "UNDEFINED_TARGET_REF", f"{loc}.{where}",
                                            f"References target '{tg}' that no job creates."))
            # this job's produced target becomes available to LATER jobs
            if job.get("jobType") == "create_target":
                produced = (job.get("outputs") or {}).get("targetName")
                if produced:
                    available_targets.add(produced)

    def _check_formula(self, issues, jobs):
        for i, job in enumerate(jobs):
            if isinstance(job, dict) and job.get("jobType") == "formula":
                plan = job.get("formulaPlan") or {}
                if "expression" not in plan or not plan.get("expression"):
                    issues.append(Issue("error", "FORMULA_NO_EXPRESSION", f"jobs[{i}].formulaPlan.expression",
                                        "Formula job has no 'expression'."))
                rf = plan.get("reportFields")
                if not isinstance(rf, list) or not rf:
                    issues.append(Issue("error", "FORMULA_NO_REPORT_FIELDS", f"jobs[{i}].formulaPlan.reportFields",
                                        "Formula job has no 'reportFields'."))

    def _check_vocabulary(self, issues, jobs):
        """Soft: values must be in the Workplan vocab; KB cross-check flags unsupported methods."""
        for i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            loc = f"jobs[{i}]"
            if job.get("jobType") == "pic_split":
                plan = job.get("picSplitPlan") or {}
                sm = plan.get("splitMethod")
                if sm is not None and sm not in CONTRACT["split_methods"]:
                    issues.append(Issue("warning", "UNKNOWN_SPLIT_METHOD", f"{loc}.picSplitPlan.splitMethod",
                                        f"splitMethod '{sm}' not in {CONTRACT['split_methods']}."))
                if self.kb_split_methods and sm and sm not in self.kb_split_methods:
                    issues.append(Issue("warning", "SPLIT_METHOD_NO_KB", f"{loc}.picSplitPlan.splitMethod",
                                        f"splitMethod '{sm}' has no backend support in the current KB."))
                matrix = (plan.get("colorDeconvParams") or {}).get("matrix")
                if matrix and matrix != "custom" and self.kb_matrices and matrix not in self.kb_matrices:
                    issues.append(Issue("warning", "UNKNOWN_DECONV_MATRIX", f"{loc}.picSplitPlan.colorDeconvParams.matrix",
                                        f"Deconvolution matrix '{matrix}' is not a known KB preset and is not 'custom'."))
            elif job.get("jobType") == "create_target":
                plan = job.get("createTargetPlan") or {}
                m = plan.get("recommendedSegmentMethod")
                if m is not None and m not in CONTRACT["segment_methods"]:
                    issues.append(Issue("warning", "UNKNOWN_SEGMENT_METHOD", f"{loc}.createTargetPlan.recommendedSegmentMethod",
                                        f"recommendedSegmentMethod '{m}' not in {CONTRACT['segment_methods']}."))
                # KB cross-check: a non-empty method that the KB has no API for (e.g. rnascope)
                if m and self.kb_segment_methods and m not in self.kb_segment_methods:
                    issues.append(Issue("warning", "SEGMENT_METHOD_NO_KB", f"{loc}.createTargetPlan.recommendedSegmentMethod",
                                        f"Segmentation method '{m}' has no backend API in the current KB (executor may not support it yet)."))

    def _check_conventions(self, issues, jobs, targets):
        """Soft: jobId naming + targets[] mirrors create_target outputs in creation order."""
        # jobId convention: job_00 first, job_99 last, job_0N in between
        for i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            jid, jt = job.get("jobId"), job.get("jobType")
            if jt == "pic_split" and jid not in (None, "job_00"):
                issues.append(Issue("warning", "JOB_ID_CONVENTION", f"jobs[{i}].jobId",
                                    f"pic_split conventionally has jobId 'job_00', got '{jid}'."))
            if jt == "formula" and jid not in (None, "job_99"):
                issues.append(Issue("warning", "JOB_ID_CONVENTION", f"jobs[{i}].jobId",
                                    f"formula conventionally has jobId 'job_99', got '{jid}'."))
        # targets[] should equal create_target outputs, in order
        ct_outputs = [(j.get("outputs") or {}).get("targetName")
                      for j in jobs if isinstance(j, dict) and j.get("jobType") == "create_target"]
        declared = [t.get("targetName") for t in targets if isinstance(t, dict)]
        for name in ct_outputs:
            if name and name not in declared:
                issues.append(Issue("warning", "TARGET_NOT_DECLARED", "targets",
                                    f"create_target produces '{name}' but it is not listed in targets[]."))
        if declared and ct_outputs and declared != ct_outputs:
            issues.append(Issue("warning", "TARGET_ORDER_MISMATCH", "targets",
                                "targets[] does not match create_target outputs in creation order."))


# ─────────────────────────────── module-level utils ───────────────────────────────────
def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _produced_later(jobs, idx, target_name) -> bool:
    for j in jobs[idx:]:
        if isinstance(j, dict) and j.get("jobType") == "create_target":
            if (j.get("outputs") or {}).get("targetName") == target_name:
                return True
    return False


def _summary(status, errors, warnings) -> str:
    if status == "accept" and not warnings:
        return "ACCEPT — structurally valid, no warnings."
    if status == "accept":
        return f"ACCEPT — structurally valid, {len(warnings)} warning(s) to note."
    return f"REJECT — {len(errors)} structural error(s); {len(warnings)} warning(s)."


def _try_load_provider(kb_dir: str):
    try:
        from ..knowledge.provider import load_provider
        return load_provider(kb_dir, mode="full")
    except Exception as e:  # KB absent / not built — structural-only mode
        logger.info("Reviewer running without KB (%s); vocabulary checks skipped.", e)
        return None


def _load_kb_vocab(provider) -> Tuple[set, set, set]:
    """Discover supported segment methods, split methods, and deconv matrices from the KB."""
    seg, split, matrices = set(), set(), set()
    if provider is None:
        return seg, split, matrices
    try:
        schema = provider.get_param_schema("Segment_ROI_API_v10")  # base group; groups discovered below
    except Exception:
        schema = None
    try:
        models = getattr(provider, "_models", {})
        seg = {k.split(":")[0] for k in models.get("Segment_ROI_API_v10", {}).get("groups", {}) if ":" in k}
        # walk Pic_Split schema for splitMethod + matrix enums
        ps = models.get("Pic_Split_API_v10", {})
        for path, enum in _walk_enums(ps):
            low = path.lower()
            if "splitmethod" in low:
                split |= set(enum)
            elif "matrix" in low:
                matrices |= set(enum)
    except Exception as e:
        logger.debug("KB vocab discovery partial: %s", e)
    return seg, split, matrices


def _walk_enums(node, path=""):
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            yield path, node["enum"]
        if "const" in node:
            yield path, [node["const"]]
        for k, v in node.items():
            yield from _walk_enums(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_enums(v, f"{path}[{i}]")


# ════════════════════════════════════════════════════════════════════════════════════
#  Functional API for src/core/ (framework-agnostic)
# ════════════════════════════════════════════════════════════════════════════════════

@dataclass
class Review:
    """Review result dataclass."""
    status: str  # "accept" or "reject"
    errors: List[Issue]
    warnings: List[Issue]
    workplan: Optional[Dict] = None


def review_workplan(workplan: dict, models_schema: Optional[dict] = None) -> Review:
    """Framework-agnostic workplan review function.

    Args:
        workplan: Workplan dict to review
        models_schema: Optional JSON schema for validation

    Returns:
        Review dataclass with status, errors, warnings
    """
    reviewer = ReviewerAgent()
    issues = reviewer.review(workplan)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    status = "reject" if errors else "accept"

    return Review(
        status=status,
        errors=errors,
        warnings=warnings,
        workplan=workplan if status == "accept" else None
    )


def format_review(review: Review) -> str:
    """Format a Review as human-readable text.

    Args:
        review: Review dataclass

    Returns:
        Formatted string
    """
    lines = []
    lines.append(f"Status: {review.status.upper()}")

    if review.errors:
        lines.append(f"\nErrors ({len(review.errors)}):")
        for e in review.errors:
            lines.append(f"  [{e.code}] {e.location}: {e.message}")

    if review.warnings:
        lines.append(f"\nWarnings ({len(review.warnings)}):")
        for w in review.warnings:
            lines.append(f"  [{w.code}] {w.location}: {w.message}")

    if not review.errors and not review.warnings:
        lines.append("No issues found.")

    return "\n".join(lines)
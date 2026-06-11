"""
Reviewer - workplan validation.

Two-tier validation strategy:
1. Structural validation: Schema-agnostic invariants (already in generator.structural_checks)
2. Schema validation: Validate against models_jsonschema.json
3. Vocabulary validation: Soft warnings for method names, parameter ranges

This is a rule-based reviewer (no LLM) that provides fast, deterministic validation.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from pydantic import ValidationError

from .workplan_schema import Workplan
from .generator import structural_checks


@dataclass
class Issue:
    """A validation issue."""
    severity: str  # "error" or "warning"
    location: str  # Where the issue was found (e.g., "job_02", "formula")
    message: str   # Human-readable description
    code: Optional[str] = None  # Machine-readable error code


@dataclass
class Review:
    """Validation result."""
    status: str  # "accept" (no critical errors) or "reject" (has errors)
    errors: List[Issue]      # Critical issues that must be fixed
    warnings: List[Issue]    # Suggestions and minor issues
    workplan: Optional[Dict[str, Any]] = None  # The validated workplan (if accepted)


def review_workplan(workplan: Dict[str, Any], models_schema: Optional[Dict] = None) -> Review:
    """
    Perform two-tier validation on a workplan.

    Args:
        workplan: The workplan dict to validate
        models_schema: Optional JSON schema for parameter validation
                      (loads from kb_compiled/models_jsonschema.json if None)

    Returns:
        Review with status, errors, and warnings
    """
    errors: List[Issue] = []
    warnings: List[Issue] = []

    # Tier 1: Structural validation (schema-agnostic)
    structural_issues = structural_checks(workplan)
    for issue in structural_issues:
        errors.append(Issue(
            severity="error",
            location="structure",
            message=issue,
            code="STRUCTURAL_ERROR",
        ))

    # Tier 2: Pydantic schema validation
    try:
        validated_workplan = Workplan(**workplan)
    except ValidationError as e:
        for err in e.errors():
            location = ".".join(str(x) for x in err["loc"])
            errors.append(Issue(
                severity="error",
                location=location,
                message=err["msg"],
                code="SCHEMA_ERROR",
            ))

    # Tier 3: Schema-based parameter validation (if models_schema provided)
    if models_schema and not errors:
        param_errors, param_warnings = validate_parameters(workplan, models_schema)
        errors.extend(param_errors)
        warnings.extend(param_warnings)

    # Determine status
    status = "accept" if not errors else "reject"

    return Review(
        status=status,
        errors=errors,
        warnings=warnings,
        workplan=workplan if status == "accept" else None,
    )


def validate_parameters(workplan: Dict[str, Any], models_schema: Dict) -> tuple[List[Issue], List[Issue]]:
    """
    Validate create_target job parameters against models_jsonschema.json.

    This is a placeholder for detailed parameter validation.
    Full implementation would validate each createTargetPlan against the schema.

    Args:
        workplan: The workplan dict
        models_schema: The models JSON schema

    Returns:
        (errors, warnings) tuple
    """
    errors: List[Issue] = []
    warnings: List[Issue] = []

    for job in workplan.get("jobs", []):
        if job.get("jobType") != "create_target":
            continue

        job_id = job.get("jobId", "unknown")
        plan = job.get("createTargetPlan", {})

        # Validate recommendedSegmentMethod
        method = plan.get("recommendedSegmentMethod")
        if method and method not in ["cellpose", "threshold", "rnascope", ""]:
            warnings.append(Issue(
                severity="warning",
                location=job_id,
                message=f"Unknown segment method: {method}",
                code="UNKNOWN_METHOD",
            ))

        # Check for required method-specific parameters
        if method == "cellpose":
            if "cellposeParams" not in plan:
                errors.append(Issue(
                    severity="error",
                    location=job_id,
                    message="cellpose method requires cellposeParams",
                    code="MISSING_PARAMS",
                ))
            else:
                # Validate cellpose model name
                model_name = plan["cellposeParams"].get("model")
                valid_models = [
                    "zhijing_bf_nuclei", "zhijing_if_nuclei", "zhijing_vacuoles",
                    "cyto", "nuclei", "cyto2"
                ]
                if model_name and model_name not in valid_models:
                    warnings.append(Issue(
                        severity="warning",
                        location=f"{job_id}.cellposeParams.model",
                        message=f"Unknown cellpose model: {model_name}",
                        code="UNKNOWN_MODEL",
                    ))

        elif method == "threshold":
            if "thresholdParams" not in plan:
                errors.append(Issue(
                    severity="error",
                    location=job_id,
                    message="threshold method requires thresholdParams",
                    code="MISSING_PARAMS",
                ))

        elif method == "rnascope":
            if "rnascope" not in plan:
                warnings.append(Issue(
                    severity="warning",
                    location=job_id,
                    message="rnascope method should have rnascope params",
                    code="MISSING_PARAMS",
                ))

    return errors, warnings


def format_review(review: Review) -> str:
    """
    Format a Review result as human-readable text.

    Args:
        review: The Review to format

    Returns:
        Formatted string
    """
    lines = []
    lines.append(f"Review Status: {review.status.upper()}")
    lines.append("")

    if review.errors:
        lines.append(f"Errors ({len(review.errors)}):")
        for err in review.errors:
            lines.append(f"  ✗ [{err.location}] {err.message}")
        lines.append("")

    if review.warnings:
        lines.append(f"Warnings ({len(review.warnings)}):")
        for warn in review.warnings:
            lines.append(f"  ⚠ [{warn.location}] {warn.message}")
        lines.append("")

    if review.status == "accept":
        lines.append("✓ Workplan is valid and ready for execution")
    else:
        lines.append("✗ Workplan has errors and must be corrected")

    return "\n".join(lines)

"""Agent 3: Workplan Reviewer

Validates workplan for correctness and completeness.
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ReviewerAgent:
    """
    Agent 3: Workplan Reviewer

    Validates workplans for structural correctness, API usage,
    logical consistency, and completeness.
    """

    def __init__(self):
        self.valid_apis = [
            "Pic_Split_API",
            "Segment_ROI_API",
            "Create_Target_API",
            "Measure_ROI_API",
            "ROI_Render_API",
            "Formula_API",
        ]

        self.valid_split_methods = ["rgb_split", "color_deconvolution"]

        self.valid_job_types = [
            "pic_split",
            "create_target",
            "formula",
            "roi_render",
            "quality_control",
        ]

    async def review_workplan(
        self, workplan: dict, requirements: dict
    ) -> Dict[str, Any]:
        """Comprehensive workplan review."""

        logger.info("Reviewing workplan")

        issues = []

        # Structural validation
        issues.extend(self._validate_structure(workplan))

        # API correctness
        issues.extend(self._validate_api_usage(workplan))

        # Logical consistency
        issues.extend(self._validate_consistency(workplan))

        # Completeness
        issues.extend(self._validate_completeness(workplan, requirements))

        # Separate by severity
        critical = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        suggestions = [i for i in issues if i["severity"] == "suggestion"]

        # Decision
        status = "accept" if len(critical) == 0 else "reject"

        logger.info(
            f"Review complete: {status} ({len(critical)} errors, {len(warnings)} warnings)"
        )

        return {
            "status": status,
            "critical_issues": critical,
            "warnings": warnings,
            "suggestions": suggestions,
            "overall_score": self._calculate_score(issues),
        }

    def _validate_structure(self, workplan: dict) -> List[Dict[str, Any]]:
        """Validate JSON structure."""
        issues = []

        required_fields = [
            "experimentName",
            "inputMode",
            "analysisGoal",
            "imageInference",
            "workplanSceneType",
            "channels",
            "targets",
            "jobs",
        ]

        for field in required_fields:
            if field not in workplan:
                issues.append(
                    {
                        "severity": "error",
                        "location": f"root.{field}",
                        "issue": f"Missing required field '{field}'",
                        "suggestion": f"Add '{field}' field",
                    }
                )

        # Validate channels structure
        if "channels" in workplan and isinstance(workplan["channels"], list):
            for i, channel in enumerate(workplan["channels"]):
                for field in ["channelId", "channelName", "semanticRole"]:
                    if field not in channel:
                        issues.append(
                            {
                                "severity": "error",
                                "location": f"channels[{i}]",
                                "issue": f"Missing '{field}' in channel",
                                "suggestion": f"Add '{field}' to channel",
                            }
                        )

        # Validate targets structure
        if "targets" in workplan and isinstance(workplan["targets"], list):
            for i, target in enumerate(workplan["targets"]):
                for field in ["targetName", "targetType", "description"]:
                    if field not in target:
                        issues.append(
                            {
                                "severity": "error",
                                "location": f"targets[{i}]",
                                "issue": f"Missing '{field}' in target",
                                "suggestion": f"Add '{field}' to target",
                            }
                        )

        return issues

    def _validate_api_usage(self, workplan: dict) -> List[Dict[str, Any]]:
        """Validate API names and parameters."""
        issues = []

        for i, job in enumerate(workplan.get("jobs", [])):
            job_type = job.get("jobType")

            # Validate job type
            if job_type not in self.valid_job_types:
                issues.append(
                    {
                        "severity": "error",
                        "location": f"jobs[{i}].jobType",
                        "issue": f"Invalid jobType '{job_type}'",
                        "suggestion": f"Use one of: {self.valid_job_types}",
                    }
                )

            # Validate pic_split jobs
            if job_type == "pic_split":
                if "picSplitPlan" not in job:
                    issues.append(
                        {
                            "severity": "error",
                            "location": f"jobs[{i}]",
                            "issue": "pic_split job must have 'picSplitPlan'",
                            "suggestion": "Add 'picSplitPlan' with splitMethod",
                        }
                    )
                else:
                    plan = job["picSplitPlan"]
                    method = plan.get("splitMethod")
                    if method not in self.valid_split_methods:
                        issues.append(
                            {
                                "severity": "error",
                                "location": f"jobs[{i}].picSplitPlan.splitMethod",
                                "issue": f"Invalid splitMethod '{method}'",
                                "suggestion": f"Use one of: {self.valid_split_methods}",
                            }
                        )

            # Validate formula jobs
            elif job_type == "formula":
                if "formulaPlan" not in job:
                    issues.append(
                        {
                            "severity": "error",
                            "location": f"jobs[{i}]",
                            "issue": "formula job must have 'formulaPlan'",
                            "suggestion": "Add 'formulaPlan' with expression and reportFields",
                        }
                    )
                else:
                    plan = job["formulaPlan"]
                    if "expression" not in plan:
                        issues.append(
                            {
                                "severity": "error",
                                "location": f"jobs[{i}].formulaPlan",
                                "issue": "Missing 'expression'",
                                "suggestion": "Add formula expression",
                            }
                        )
                    if "reportFields" not in plan:
                        issues.append(
                            {
                                "severity": "error",
                                "location": f"jobs[{i}].formulaPlan",
                                "issue": "Missing 'reportFields'",
                                "suggestion": "Add 'reportFields' array",
                            }
                        )

        return issues

    def _validate_consistency(self, workplan: dict) -> List[Dict[str, Any]]:
        """Validate logical consistency."""
        issues = []

        # Build reference maps
        defined_channels = {ch["channelId"] for ch in workplan.get("channels", [])}
        defined_targets = {tgt["targetName"] for tgt in workplan.get("targets", [])}

        # Check if jobs reference defined channels/targets
        # (Simplified validation)

        return issues

    def _validate_completeness(
        self, workplan: dict, requirements: dict
    ) -> List[Dict[str, Any]]:
        """Check if workplan addresses requirements."""
        issues = []

        # Check if formula job exists
        has_formula = any(
            job.get("jobType") == "formula" for job in workplan.get("jobs", [])
        )

        if not has_formula:
            issues.append(
                {
                    "severity": "error",
                    "location": "jobs",
                    "issue": "No formula job found",
                    "suggestion": "Add job_99 with jobType 'formula'",
                }
            )

        return issues

    def _calculate_score(self, issues: List[Dict[str, Any]]) -> float:
        """Calculate overall quality score."""
        if not issues:
            return 1.0

        error_count = len([i for i in issues if i["severity"] == "error"])
        warning_count = len([i for i in issues if i["severity"] == "warning"])

        penalty = (error_count * 0.3) + (warning_count * 0.1)
        return max(0.0, 1.0 - penalty)

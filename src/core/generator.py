"""
Generator agent - example-driven workplan JSON generation.

The Generator takes the Clarifier's task brief (prose) and generates a structured
workplan JSON using few-shot examples and the compiled API specification.
"""
import json
import re
from typing import Dict, Optional, Tuple
from openai import OpenAI


def parse_json_with_repair(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Parse JSON from LLM output, with fallback strategies.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Extracting JSON from surrounding text
    - Returning helpful error messages

    Args:
        text: Raw LLM output

    Returns:
        (parsed_dict, error_message) - one will be None
    """
    s = text.strip()

    # Strip markdown code blocks
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()

    # Try direct parse
    try:
        return json.loads(s), None
    except Exception as e:
        # Try to extract JSON object
        match = re.search(r"\{.*\}", s, re.S)
        if match:
            try:
                return json.loads(match.group(0)), None
            except Exception as e2:
                return None, f"JSON extraction failed: {e2}"
        return None, f"JSON parse failed: {e}"


def generate_workplan(
    brief: str,
    request: str,
    system_prompt: str,
    api_spec: str,
    examples: Dict[str, str],
    client: OpenAI,
    model: str,
    temperature: float = 0,
) -> Tuple[Optional[dict], Optional[str], str]:
    """
    Generate a workplan JSON from the Clarifier's task brief.

    Args:
        brief: The task brief from the Clarifier (prose before [[TASK_READY]])
        request: Original user request (for context)
        system_prompt: Generator system prompt template
        api_spec: The compiled API specification (context_spec.md content)
        examples: Dict of example workplans (from load_examples)
        client: OpenAI-compatible client
        model: Model endpoint ID
        temperature: Sampling temperature (default 0 for consistency)

    Returns:
        (workplan_dict, error_message, raw_output)
        - If successful: (dict, None, raw_text)
        - If failed: (None, error_msg, raw_text)
    """
    # Format examples for injection
    formatted_examples = "\n\n".join(
        f"--- EXAMPLE: {name} ---\n{content}"
        for name, content in examples.items()
    )

    # Inject into system prompt
    full_system_prompt = (
        system_prompt
        .replace("{{API_SPEC}}", api_spec)
        .replace("{{FEWSHOT_EXAMPLES}}", formatted_examples)
        .replace("{{CLARIFIED_REQUIREMENTS}}", brief)
        .replace("{{USER_REQUEST}}", request)
    )

    messages = [
        {"role": "system", "content": full_system_prompt},
        {"role": "user", "content": "生成本次分析的 Workplan JSON。"},
    ]

    # Try JSON mode first
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
    except Exception as e:
        # Fallback: no JSON mode
        print(f"(JSON mode rejected: {e}; retrying without it)")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        raw = response.choices[0].message.content

    # Parse the result
    workplan, error = parse_json_with_repair(raw)

    return workplan, error, raw


def structural_checks(workplan: dict) -> list[str]:
    """
    Perform schema-agnostic structural validation on a workplan.

    These are invariants that must hold regardless of API version:
    - Required top-level keys present
    - First job is pic_split, last is formula
    - All target/channel references are created before use
    - Valid jobType values

    Args:
        workplan: The workplan dict to validate

    Returns:
        List of error messages (empty if all checks pass)
    """
    issues = []

    # Required top-level keys
    required_keys = (
        "experimentName", "inputMode", "analysisGoal",
        "imageInference", "channels", "targets", "jobs"
    )
    for key in required_keys:
        if key not in workplan:
            issues.append(f"missing top-level key: {key}")

    channels = {c.get("channelId") for c in workplan.get("channels", [])}
    jobs = workplan.get("jobs", [])

    # Job ordering
    if jobs:
        if jobs[0].get("jobType") != "pic_split":
            issues.append("first job is not pic_split")
        if jobs[-1].get("jobType") != "formula":
            issues.append("last job is not formula")

    # Valid jobType and reference resolution
    valid_job_types = {"pic_split", "create_target", "formula", "roi_render", "quality_control"}
    created_targets = []

    for job in jobs:
        jid = job.get("jobId", "unknown")
        jtype = job.get("jobType")

        # Check jobType
        if jtype not in valid_job_types:
            issues.append(f"{jid}: invalid jobType '{jtype}'")

        # Check target references (for create_target jobs)
        if jtype == "create_target":
            # Parent targets
            parents = (
                job.get("inputs", {}).get("sourceTargetNames") or
                job.get("createTargetPlan", {}).get("sourceTargetNames") or
                []
            )
            for parent in parents:
                if parent and parent not in created_targets:
                    issues.append(
                        f"{jid}: sourceTargetName '{parent}' not created earlier"
                    )

            # Record this target as created
            target_name = job.get("outputs", {}).get("targetName")
            if target_name:
                created_targets.append(target_name)

        # Check channel references
        channel_ids = job.get("inputs", {}).get("channelId") or []
        for ch in channel_ids:
            if ch not in channels:
                issues.append(f"{jid}: channelId '{ch}' not in channels")

    # Check formula targetInputs
    if jobs:
        formula_job = jobs[-1]
        if formula_job.get("jobType") == "formula":
            target_inputs = formula_job.get("inputs", {}).get("targetInputs", [])
            for ti in target_inputs:
                tname = ti.get("targetName")
                if tname not in created_targets:
                    issues.append(
                        f"formula: targetInput '{tname}' is not a created target"
                    )

    return issues

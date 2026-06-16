"""
Orchestrator - ties Clarifier → Generator → Reviewer together.

This module implements the callback-driven pipeline that coordinates the
multi-agent workflow without depending on any specific framework.
"""
from typing import Callable, Dict, Optional
from .clarifier import clarifier_turn, build_initial_history, prepare_vision_image_url
from .generator import generate_workplan
from .reviewer import review_workplan, Review
from .kb import load_context_spec, load_examples, load_models_schema
from .llm import create_vision_client, create_text_client


def run_pipeline(
    image_path: str,
    request: str,
    clarifier_prompt: str,
    generator_prompt: str,
    ask_user: Callable[[str], str],
    on_message: Callable[[str, str], None],
    api_spec: Optional[str] = None,
    examples: Optional[Dict[str, str]] = None,
    max_attempts: int = 3,
) -> Dict:
    """
    Run the complete Clarifier → Generator pipeline.

    This is a callback-driven orchestrator that's framework-agnostic.
    The web layer / LangGraph layer calls this with appropriate callbacks.

    Args:
        image_path: Path to the microscopy image
        request: User's initial request
        clarifier_prompt: Clarifier system prompt template (with {{KB_CONTEXT}} placeholder)
        generator_prompt: Generator system prompt template (with placeholders)
        ask_user: Callback to ask user a question and get their answer
                  Signature: (question: str) -> str
        on_message: Callback to emit a message (for streaming/logging)
                    Signature: (kind: str, text: str) -> None
                    Kinds: "clarifier_question", "clarifier_brief", "generator_raw"
        api_spec: Optional API spec content (loads from kb_compiled/ if None)
        examples: Optional examples dict (loads from examples/ if None)

    Returns:
        Dict with:
        - brief: The final task brief from Clarifier
        - workplan: The generated workplan dict (or None if generation failed)
        - error: Error message if workplan generation failed
        - raw: Raw LLM output from Generator
        - structural_issues: List of structural validation errors
    """
    # Load knowledge base if not provided
    if api_spec is None:
        api_spec = load_context_spec()

    if examples is None:
        examples = load_examples()

    # Create LLM clients
    clarifier_client, clarifier_model = create_vision_client()
    generator_client, generator_model = create_text_client()

    # Inject KB context into clarifier prompt
    clarifier_system = clarifier_prompt.replace("{{KB_CONTEXT}}", api_spec)

    # Deliver the image to the vision model by reference (object-store URL) when a store
    # is configured, else inline base64. Reference delivery avoids the request-body size
    # ceiling that base64 hits on large images. This is transport only — no CV, full
    # resolution preserved; the backend still receives the original image.
    image_url = prepare_vision_image_url(image_path)
    on_message(
        "image_delivery",
        "object-store URL" if image_url.startswith("http") else "inline base64",
    )

    # Phase 1: Clarifier loop
    history = build_initial_history(image_path, request, clarifier_system, image_url=image_url)

    while True:
        turn = clarifier_turn(
            history=history,
            system_prompt=clarifier_system,
            client=clarifier_client,
            model=clarifier_model,
        )

        if turn.ready:
            # Emit the brief and exit loop
            on_message("clarifier_brief", turn.brief)
            brief = turn.brief
            break
        else:
            # Emit the question and wait for user answer
            on_message("clarifier_question", turn.assistant_text)
            answer = ask_user(turn.assistant_text)

            # Append to history
            history.append({"role": "assistant", "content": turn.assistant_text})
            history.append({"role": "user", "content": answer})

    # Phase 2 + 3: generate, validate, and — on structural reject — feed the Reviewer's
    # errors back to the Generator and retry, bounded by max_attempts. The Reviewer is the
    # deterministic gate; this is the corrective loop around it.
    models_schema = None
    try:
        models_schema = load_models_schema()
    except FileNotFoundError:
        pass  # vocabulary cross-checks degrade; the structural gate still runs

    result = generate_and_review_loop(
        brief=brief,
        request=request,
        generator_prompt=generator_prompt,
        api_spec=api_spec,
        examples=examples,
        generator_client=generator_client,
        generator_model=generator_model,
        models_schema=models_schema,
        on_message=on_message,
        max_attempts=max_attempts,
    )

    return {
        "brief": brief,
        "workplan": result["workplan"],
        "error": result["error"],
        "raw": result["raw"],
        "review": result["review"],
        "attempts": result["attempts"],
    }


def generate_and_review_loop(
    brief: str,
    request: str,
    generator_prompt: str,
    api_spec: str,
    examples: Dict[str, str],
    generator_client,
    generator_model: str,
    models_schema: Optional[dict],
    on_message: Callable[[str, str], None],
    max_attempts: int = 3,
) -> Dict:
    """Generate a Workplan, validate it, and retry with corrective feedback on reject.

    On a structural reject (or an unparseable generation), the Reviewer's errors are fed
    back to the Generator as a follow-up turn and generation is retried, up to max_attempts.
    The first ACCEPT wins; if every attempt is rejected, the last (rejected) workplan and its
    review are returned so the caller can surface the failure.

    Returns: {"workplan", "error", "raw", "review", "attempts"}.
    """
    workplan: Optional[dict] = None
    error: Optional[str] = None
    raw: str = ""
    review: Optional[Review] = None
    feedback: Optional[str] = None
    prior_attempt: Optional[str] = None
    attempts = 0

    for attempt in range(1, max(1, max_attempts) + 1):
        attempts = attempt
        workplan, error, raw = generate_workplan(
            brief=brief,
            request=request,
            system_prompt=generator_prompt,
            api_spec=api_spec,
            examples=examples,
            client=generator_client,
            model=generator_model,
            feedback=feedback,
            prior_attempt=prior_attempt,
        )
        on_message("generator_raw", raw)

        if workplan is None:
            # Unparseable output — the Reviewer can't run. Feed the parse error back.
            review = None
            on_message("reviewer_result",
                       f"attempt {attempt}/{max_attempts}: unparseable output ({error})")
            if attempt < max_attempts:
                feedback = _build_parse_feedback(error)
                prior_attempt = raw
                continue
            break

        review = review_workplan(workplan, models_schema)
        on_message(
            "reviewer_result",
            f"attempt {attempt}/{max_attempts}: {review.status} "
            f"({len(review.errors)} errors, {len(review.warnings)} warnings)",
        )

        if review.status == "accept":
            break

        # Rejected — prepare corrective feedback for the next attempt (if any remain).
        if attempt < max_attempts:
            feedback = _build_review_feedback(review)
            prior_attempt = raw

    return {"workplan": workplan, "error": error, "raw": raw,
            "review": review, "attempts": attempts}


def _issue_text(e) -> str:
    """Format a single Issue (object or dict) as 'message（位置：location）'."""
    if isinstance(e, dict):
        msg, loc = e.get("message", ""), e.get("location", "")
    else:
        msg, loc = getattr(e, "message", ""), getattr(e, "location", "")
    return f"{msg}（位置：{loc}）" if loc else msg


def _build_review_feedback(review: "Review") -> str:
    lines = [f"{i}. {_issue_text(e)}" for i, e in enumerate(review.errors, 1)]
    return (
        "你上一次生成的 Workplan JSON 未通过结构校验，存在以下必须修复的错误：\n"
        + "\n".join(lines)
        + "\n\n请在保持原有分析意图不变的前提下修正上述结构问题，"
        "重新输出完整且修正后的 Workplan JSON。只输出 JSON，不要包含任何解释或 Markdown 代码块标记。"
    )


def _build_parse_feedback(error: Optional[str]) -> str:
    return (
        f"你上一次的输出无法被解析为合法 JSON（{error}）。"
        "请只输出一个合法、完整的 Workplan JSON 对象，"
        "不要包含任何解释性文字或 Markdown 代码块标记。"
    )
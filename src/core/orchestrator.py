"""
Orchestrator - ties Clarifier → Generator → Reviewer together.

This module implements the callback-driven pipeline that coordinates the
multi-agent workflow without depending on any specific framework.
"""
from typing import Callable, Dict, Optional
from .clarifier import clarifier_turn, build_initial_history
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

    # Phase 1: Clarifier loop
    history = build_initial_history(image_path, request, clarifier_system)

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

    # Phase 2: Generator
    workplan, error, raw = generate_workplan(
        brief=brief,
        request=request,
        system_prompt=generator_prompt,
        api_spec=api_spec,
        examples=examples,
        client=generator_client,
        model=generator_model,
    )

    on_message("generator_raw", raw)

    # Phase 3: Reviewer validation
    review = None
    models_schema = None
    if workplan is not None:
        # Load models schema for parameter validation
        try:
            models_schema = load_models_schema()
        except FileNotFoundError:
            # Schema not available, skip parameter validation
            pass

        review = review_workplan(workplan, models_schema)
        on_message("reviewer_result", f"Status: {review.status}, Errors: {len(review.errors)}, Warnings: {len(review.warnings)}")

    return {
        "brief": brief,
        "workplan": workplan,
        "error": error,
        "raw": raw,
        "review": review,
    }

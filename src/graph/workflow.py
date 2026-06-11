"""
LangGraph workflow (v11) - thin layer over src/core/.

Nodes are 2-4 line wrappers that call src/core/ functions.
The graph owns only control flow, routing, and checkpointing.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import Dict, Any
from pathlib import Path
import logging

from ..state import WorkplanState
from ..config import get_settings
from ..core import (
    clarifier_turn,
    build_initial_history,
    generate_workplan,
    review_workplan,
    load_context_spec,
    load_examples,
    load_models_schema,
    create_vision_client,
    create_text_client,
)

logger = logging.getLogger(__name__)

# PostgreSQL checkpointing is optional
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.info("PostgreSQL checkpointing not available - using in-memory")


def create_workflow_graph():
    """Create the three-agent workflow graph (v11 - over src/core/)."""

    settings = get_settings()

    # Load prompts and knowledge base once
    clarifier_prompt = Path("prompts/clarifier_system_prompt.md").read_text(encoding="utf-8")
    generator_prompt = Path("prompts/generator_system_prompt.md").read_text(encoding="utf-8")
    api_spec = load_context_spec()
    examples = load_examples()

    # Inject KB context into clarifier prompt
    clarifier_system = clarifier_prompt.replace("{{KB_CONTEXT}}", api_spec)

    # Create LLM clients
    clarifier_client, clarifier_model = create_vision_client()
    generator_client, generator_model = create_text_client()

    logger.info("Workflow initialized with src/core/ modules")

    # ========== Node Definitions (thin wrappers) ==========

    def clarifier_node(state: WorkplanState) -> Dict[str, Any]:
        """Clarifier node - one turn, updates history."""
        logger.info(f"Clarifier node - Round {state['clarification_round']}")

        # Build or get history
        if state["clarification_round"] == 0:
            # First turn: build initial history with image
            history = build_initial_history(
                image_path=state["image_url"],
                request=state["initial_request"],
                system_prompt=clarifier_system,
            )
        else:
            # Subsequent turns: append user response
            history = state["clarifier_history"].copy()
            if state.get("user_response"):
                history.append({"role": "user", "content": state["user_response"]})

        # Call clarifier_turn
        turn = clarifier_turn(
            history=history,
            system_prompt=clarifier_system,
            client=clarifier_client,
            model=clarifier_model,
        )

        # Update history with assistant's response
        history.append({"role": "assistant", "content": turn.assistant_text})

        # Prepare updates
        updates = {
            "clarifier_history": history,
            "clarification_round": state["clarification_round"] + 1,
            "messages": [{"role": "clarifier", "content": turn.assistant_text}],
        }

        if turn.ready:
            # Brief is ready
            updates.update({
                "brief_ready": True,
                "task_brief": turn.brief,
                "awaiting_user_input": False,
            })
            logger.info("Task brief ready")
        else:
            # Need user input
            updates.update({
                "brief_ready": False,
                "awaiting_user_input": True,
                "user_input_type": "clarification",
            })
            logger.info("Awaiting user clarification")

        return updates

    def generator_node(state: WorkplanState) -> Dict[str, Any]:
        """Generator node - calls generate_workplan."""
        logger.info(f"Generator node - Attempt {state['generation_attempts'] + 1}")

        workplan, error, raw = generate_workplan(
            brief=state["task_brief"],
            request=state["initial_request"],
            system_prompt=generator_prompt,
            api_spec=api_spec,
            examples=examples,
            client=generator_client,
            model=generator_model,
        )

        return {
            "generation_attempts": state["generation_attempts"] + 1,
            "current_workplan": workplan,
            "generation_error": error,
            "generation_raw": raw,
            "messages": [{"role": "generator", "content": f"Generated workplan (valid={workplan is not None})"}],
        }

    def reviewer_node(state: WorkplanState) -> Dict[str, Any]:
        """Reviewer node - calls review_workplan."""
        logger.info(f"Reviewer node - Iteration {state['review_iterations'] + 1}")

        if not state["current_workplan"]:
            # No workplan to review
            return {
                "review_iterations": state["review_iterations"] + 1,
                "review_result": {"status": "reject", "errors": [{"message": "No workplan to review"}], "warnings": []},
            }

        # Load models schema
        try:
            models_schema = load_models_schema()
        except FileNotFoundError:
            models_schema = None

        # Review
        review = review_workplan(state["current_workplan"], models_schema)

        # Serialize Review dataclass to dict
        review_dict = {
            "status": review.status,
            "errors": [{"severity": e.severity, "location": e.location, "message": e.message, "code": e.code} for e in review.errors],
            "warnings": [{"severity": w.severity, "location": w.location, "message": w.message, "code": w.code} for w in review.warnings],
        }

        return {
            "review_iterations": state["review_iterations"] + 1,
            "review_result": review_dict,
            "messages": [{"role": "reviewer", "content": f"Review {review.status}: {len(review.errors)} errors, {len(review.warnings)} warnings"}],
        }

    def user_review_node(state: WorkplanState) -> Dict[str, Any]:
        """User review - waits for user decision."""
        logger.info("User review node")

        return {
            "awaiting_user_input": True,
            "user_input_type": "decision",
            "messages": [{"role": "system", "content": "Awaiting user decision (accept/restart_generator/restart_clarifier)"}],
        }

    def finalize_node(state: WorkplanState) -> Dict[str, Any]:
        """Finalize - save workplan."""
        logger.info("Finalize node")

        return {
            "final_workplan": state["current_workplan"],
            "awaiting_user_input": False,
            "messages": [{"role": "system", "content": "Workplan finalized"}],
        }

    # ========== Routing Functions ==========

    def clarifier_router(state: WorkplanState) -> str:
        """Route after clarifier."""
        if state.get("awaiting_user_input"):
            return END  # Pause for user input
        if state.get("brief_ready"):
            return "generator"
        if state["clarification_round"] >= settings.max_clarification_rounds:
            logger.warning("Max clarification rounds reached")
            return END
        return "clarifier"  # Loop

    def generator_router(state: WorkplanState) -> str:
        """Route after generator."""
        if state.get("generation_error"):
            # Generation failed
            if state["generation_attempts"] >= 3:
                logger.error("Max generation attempts reached")
                return END
            return "generator"  # Retry
        return "reviewer"

    def reviewer_router(state: WorkplanState) -> str:
        """Route after reviewer."""
        review = state.get("review_result", {})

        if review.get("status") == "accept":
            return "user_review"

        # Reject - decide whether to retry or escalate
        if state["review_iterations"] >= settings.max_review_iterations:
            logger.warning("Max review iterations reached, escalating to user")
            return "user_review"

        # Retry generator with feedback
        return "generator"

    def user_decision_router(state: WorkplanState) -> str:
        """Route after user decision."""
        decision = state.get("user_decision")

        if decision == "accept":
            return "finalize"
        elif decision == "restart_generator":
            return "generator"
        elif decision == "restart_clarifier":
            return "clarifier"
        else:
            return END  # Pause for user input

    # ========== Build Graph ==========

    workflow = StateGraph(WorkplanState)

    # Add nodes
    workflow.add_node("clarifier", clarifier_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("user_review", user_review_node)
    workflow.add_node("finalize", finalize_node)

    # Set entry point
    workflow.set_entry_point("clarifier")

    # Add edges with routing
    workflow.add_conditional_edges("clarifier", clarifier_router)
    workflow.add_conditional_edges("generator", generator_router)
    workflow.add_conditional_edges("reviewer", reviewer_router)
    workflow.add_conditional_edges("user_review", user_decision_router)
    workflow.add_edge("finalize", END)

    # Checkpointing
    if settings.database_url and POSTGRES_AVAILABLE:
        logger.info("Using PostgreSQL checkpointing")
        checkpointer = PostgresSaver.from_conn_string(settings.database_url)
    else:
        logger.info("Using in-memory checkpointing")
        checkpointer = MemorySaver()

    # Compile
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("Workflow graph compiled")
    return app

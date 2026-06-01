"""LangGraph workflow definition for three-agent system."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import Dict, Any
import logging

from ..state import WorkplanState
from ..agents.clarifier import ClarifierAgent
from ..agents.generator import GeneratorAgent
from ..agents.reviewer import ReviewerAgent
from ..config import get_settings

logger = logging.getLogger(__name__)

# PostgreSQL checkpointing is optional
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.info("PostgreSQL checkpointing not available - using in-memory")


def create_workflow_graph():
    """Create the three-agent workflow graph."""

    settings = get_settings()

    # Initialize agents with DouBao
    clarifier = ClarifierAgent(
        api_key=settings.doubao_api_key,
        base_url=settings.doubao_base_url,
        model=settings.doubao_model,
    )
    generator = GeneratorAgent(
        api_key=settings.doubao_api_key,
        base_url=settings.doubao_base_url,
        model=settings.doubao_model,
        system_prompt_path="workplan_generator_system_prompt_v10_2.txt",
    )
    reviewer = ReviewerAgent()

    logger.info("Agents initialized")

    # ========== Node Definitions ==========

    async def clarifier_node(state: WorkplanState) -> Dict[str, Any]:
        """Agent 1: Clarifier Node"""

        logger.info(
            f"Clarifier node - Round {state['clarification_round']}"
        )

        try:
            # First interaction
            if state["clarification_round"] == 0:
                result = await clarifier.analyze_initial_input(
                    state["image_url"], state["initial_description"]
                )
            else:
                # Process user response
                result = await clarifier.process_user_response(
                    state["conversation_history"], state.get("user_response", "")
                )

            updates = {"clarification_round": state["clarification_round"] + 1}

            if result["status"] == "complete":
                # Requirements complete
                requirements = result.get("requirements") or clarifier.extract_requirements(
                    state["conversation_history"]
                )
                updates.update(
                    {
                        "requirements_complete": True,
                        "requirements": requirements,
                        "awaiting_user_input": False,
                    }
                )
                logger.info("Requirements complete")
            else:
                # Need more info
                updates.update(
                    {
                        "requirements_complete": False,
                        "awaiting_user_input": True,
                        "user_input_type": "clarification",
                        "conversation_history": state["conversation_history"]
                        + [
                            {
                                "agent_message": result["questions"][0],
                                "user_response": state.get("user_response"),
                            }
                        ],
                    }
                )
                logger.info("Awaiting user clarification")

            return updates

        except Exception as e:
            logger.error(f"Clarifier node error: {e}")
            return {"error": str(e)}

    async def generator_node(state: WorkplanState) -> Dict[str, Any]:
        """Agent 2: Generator Node"""

        logger.info(
            f"Generator node - Attempt {state['generation_attempts'] + 1}"
        )

        try:
            workplan = await generator.generate_workplan(
                state["requirements"], state.get("generation_feedback")
            )

            return {
                "current_workplan": workplan,
                "generation_attempts": state["generation_attempts"] + 1,
                "generation_feedback": None,  # Clear feedback
            }

        except Exception as e:
            logger.error(f"Generator node error: {e}")
            return {"error": str(e)}

    async def reviewer_node(state: WorkplanState) -> Dict[str, Any]:
        """Agent 3: Reviewer Node"""

        logger.info(
            f"Reviewer node - Iteration {state['review_iterations'] + 1}"
        )

        try:
            review = await reviewer.review_workplan(
                state["current_workplan"], state["requirements"]
            )

            updates = {
                "review_result": review,
                "review_iterations": state["review_iterations"] + 1,
            }

            # If rejected, prepare feedback for generator
            if review["status"] == "reject":
                updates["generation_feedback"] = {
                    "critical_issues": review["critical_issues"],
                    "warnings": review["warnings"],
                }

            return updates

        except Exception as e:
            logger.error(f"Reviewer node error: {e}")
            return {"error": str(e)}

    def user_review_node(state: WorkplanState) -> Dict[str, Any]:
        """Wait for user decision"""
        logger.info("User review node - awaiting decision")
        return {"awaiting_user_input": True, "user_input_type": "decision"}

    # ========== Build Graph ==========

    graph = StateGraph(WorkplanState)

    # Add nodes
    graph.add_node("clarifier", clarifier_node)
    graph.add_node("generator", generator_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("user_review", user_review_node)

    # Set entry point
    graph.set_entry_point("clarifier")

    # ========== Conditional Edges ==========

    def clarifier_router(state: WorkplanState) -> str:
        """Route from clarifier based on state"""
        if state.get("error"):
            return END

        if state["requirements_complete"]:
            return "generator"
        elif state.get("awaiting_user_input"):
            # Stop and wait for user to provide input via API
            return END
        elif state["clarification_round"] >= settings.max_clarification_rounds:
            # Max rounds reached, proceed anyway
            logger.warning("Max clarification rounds reached, proceeding")
            return "generator"
        else:
            # Continue clarification
            return "clarifier"

    graph.add_conditional_edges(
        "clarifier", clarifier_router, {"clarifier": "clarifier", "generator": "generator", END: END}
    )

    # Generator -> Reviewer (always)
    graph.add_edge("generator", "reviewer")

    def reviewer_router(state: WorkplanState) -> str:
        """Route from reviewer based on review result"""
        if state.get("error"):
            return END

        review = state.get("review_result", {})

        if review.get("status") == "accept":
            return "user_review"
        elif state["review_iterations"] >= settings.max_review_iterations:
            # Max iterations, escalate to user
            logger.warning("Max review iterations reached, escalating to user")
            return "user_review"
        else:
            # Try again
            logger.info("Workplan rejected, regenerating")
            return "generator"

    graph.add_conditional_edges(
        "reviewer",
        reviewer_router,
        {"generator": "generator", "user_review": "user_review", END: END},
    )

    def user_decision_router(state: WorkplanState) -> str:
        """Route from user review based on decision"""
        decision = state.get("user_decision")

        if decision == "accept":
            logger.info("User accepted workplan")
            return END
        elif decision == "restart_agent2":
            logger.info("Restarting from generator")
            return "generator"
        elif decision == "restart_agent1":
            logger.info("Restarting from clarifier")
            return "clarifier"
        else:
            # Still waiting for decision, stop and wait for user input via API
            return END

    graph.add_conditional_edges(
        "user_review",
        user_decision_router,
        {
            "generator": "generator",
            "clarifier": "clarifier",
            "user_review": "user_review",
            END: END,
        },
    )

    # ========== Compile with Checkpointing ==========

    if settings.database_url and POSTGRES_AVAILABLE:
        try:
            checkpointer = PostgresSaver.from_conn_string(settings.database_url)
            logger.info("PostgreSQL checkpointer initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize PostgreSQL checkpointer: {e}, using in-memory")
            checkpointer = MemorySaver()
    else:
        if settings.database_url and not POSTGRES_AVAILABLE:
            logger.warning("Database URL configured but PostgreSQL dependencies not installed, using in-memory")
        else:
            logger.info("No database URL configured, using in-memory checkpointing")
        checkpointer = MemorySaver()

    app = graph.compile(checkpointer=checkpointer)

    logger.info("Workflow graph compiled successfully")

    return app


# Create the compiled graph (singleton)
workflow = create_workflow_graph()

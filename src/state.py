"""
State definition for the workplan generation workflow (v11 - prose contract).

Modernized to work with src/core/ modules:
- requirements dict → task_brief string (prose)
- requirements_complete → brief_ready boolean
- Uses [[TASK_READY]] marker for completion detection
"""
from typing import TypedDict, List, Optional, Annotated
from operator import add


class WorkplanState(TypedDict):
    """
    State that flows through the LangGraph workflow.

    The state is passed between nodes and accumulated using the
    add operator for list fields (messages, clarifier_history).
    """

    # ========== Session Info ==========
    session_id: str
    image_url: str  # Local path or remote URL
    initial_request: str  # User's original request (replaces initial_description)

    # ========== Messages (for streaming to client) ==========
    messages: Annotated[List[dict], add]

    # ========== Clarifier (Agent 1) ==========
    clarifier_history: List[dict]  # OpenAI message format
    clarification_round: int
    brief_ready: bool  # True when [[TASK_READY]] detected
    task_brief: Optional[str]  # Prose brief from Clarifier (replaces requirements dict)

    # ========== Generator (Agent 2) ==========
    generation_attempts: int
    current_workplan: Optional[dict]
    generation_error: Optional[str]
    generation_raw: Optional[str]

    # ========== Reviewer (Agent 3) ==========
    review_iterations: int
    review_result: Optional[dict]  # Review object serialized to dict

    # ========== User Interaction (Human-in-the-Loop) ==========
    awaiting_user_input: bool
    user_input_type: Optional[str]  # "clarification" or "decision"
    user_response: Optional[str]  # User's answer to clarification question
    user_decision: Optional[str]  # "accept", "restart_generator", "restart_clarifier"

    # ========== Final Output ==========
    final_workplan: Optional[dict]

    # ========== Metadata ==========
    error: Optional[str]

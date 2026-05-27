"""State definition for the workplan generation workflow."""

from typing import TypedDict, List, Optional, Annotated
from operator import add


class WorkplanState(TypedDict):
    """
    State that flows through the entire graph.

    The state is passed between nodes and accumulated using the
    add operator for list fields (messages, conversation_history).
    """

    # ========== Session Info ==========
    session_id: str
    image_url: str
    initial_description: str

    # ========== Messages (accumulated) ==========
    messages: Annotated[List[dict], add]

    # ========== Agent 1: Clarifier ==========
    conversation_history: List[dict]
    clarification_round: int
    requirements_complete: bool
    requirements: Optional[dict]

    # ========== Agent 2: Generator ==========
    generation_attempts: int
    current_workplan: Optional[dict]
    generation_feedback: Optional[dict]

    # ========== Agent 3: Reviewer ==========
    review_iterations: int
    review_result: Optional[dict]

    # ========== User Interaction ==========
    awaiting_user_input: bool
    user_input_type: Optional[str]  # "clarification" or "decision"
    user_response: Optional[str]
    user_decision: Optional[str]  # "accept", "restart_agent2", "restart_agent1"

    # ========== Final Output ==========
    final_workplan: Optional[dict]

    # ========== Metadata ==========
    error: Optional[str]

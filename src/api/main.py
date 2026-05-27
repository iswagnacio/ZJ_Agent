"""FastAPI application for workplan generation system."""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import logging

from ..graph.workflow import workflow
from ..storage.s3_client import LocalFileStorage, BOTO3_AVAILABLE
from ..config import get_settings

# Import S3Client only if boto3 is available
if BOTO3_AVAILABLE:
    from ..storage.s3_client import S3Client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Workplan Generator API",
    description="Three-agent system for generating microscopy analysis workplans",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize settings and storage client
settings = get_settings()

# Use local file storage if S3 is not configured or boto3 not available
if BOTO3_AVAILABLE and settings.s3_endpoint and settings.s3_access_key and settings.s3_secret_key:
    storage_client = S3Client(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    logger.info("Using S3/MinIO for image storage")
else:
    storage_client = LocalFileStorage()
    if settings.s3_endpoint and not BOTO3_AVAILABLE:
        logger.info("S3 configured but boto3 not installed - using local file storage")
    else:
        logger.info("Using local file storage (S3 not configured)")

logger.info("FastAPI application initialized")


# ========== Request/Response Models ==========


class SessionResponse(BaseModel):
    session_id: str
    state: str
    message: Optional[str] = None
    questions: Optional[list] = None
    workplan: Optional[dict] = None
    review: Optional[dict] = None


class ClarificationRequest(BaseModel):
    response: str


class DecisionRequest(BaseModel):
    action: str  # "accept", "restart_agent2", "restart_agent1"
    feedback: Optional[str] = None


# ========== API Endpoints ==========


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Workplan Generator",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/sessions", response_model=SessionResponse)
async def create_session(
    image: UploadFile = File(...), description: str = Form(...)
):
    """
    Create a new workplan generation session.

    Upload a microscope image and provide a brief description of the analysis goal.
    """
    logger.info(f"Creating new session with description: {description[:50]}...")

    # Generate session ID
    session_id = str(uuid.uuid4())

    try:
        # Upload image (S3 or local)
        image_content = await image.read()
        image_url = await storage_client.upload_image(
            session_id, image_content, image.content_type or "image/png"
        )

        # Initialize state
        initial_state = {
            "session_id": session_id,
            "image_url": image_url,
            "initial_description": description,
            "messages": [],
            "conversation_history": [],
            "clarification_round": 0,
            "requirements_complete": False,
            "requirements": None,
            "generation_attempts": 0,
            "current_workplan": None,
            "generation_feedback": None,
            "review_iterations": 0,
            "review_result": None,
            "awaiting_user_input": False,
            "user_input_type": None,
            "user_response": None,
            "user_decision": None,
            "final_workplan": None,
            "error": None,
        }

        # Run first step
        config = {"configurable": {"thread_id": session_id}}
        result = await workflow.ainvoke(initial_state, config)

        return SessionResponse(
            session_id=session_id,
            state="clarification",
            questions=_extract_questions(result),
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/{session_id}/respond", response_model=SessionResponse)
async def respond_to_clarification(session_id: str, request: ClarificationRequest):
    """Respond to clarification questions from Agent 1."""

    logger.info(f"Session {session_id}: User responded")

    config = {"configurable": {"thread_id": session_id}}

    try:
        # Get current state
        state = await workflow.aget_state(config)
        current_state = state.values

        if not current_state.get("awaiting_user_input"):
            raise HTTPException(
                status_code=400, detail="Session is not awaiting user input"
            )

        # Update with user response
        current_state["user_response"] = request.response
        current_state["awaiting_user_input"] = False

        # Continue workflow
        result = await workflow.ainvoke(current_state, config)

        # Determine response based on state
        if result.get("requirements_complete"):
            return SessionResponse(
                session_id=session_id,
                state="generating",
                message="Requirements complete. Generating workplan...",
            )
        elif result.get("awaiting_user_input"):
            return SessionResponse(
                session_id=session_id,
                state="clarification",
                questions=_extract_questions(result),
            )
        else:
            return SessionResponse(
                session_id=session_id, state="processing", message="Processing..."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_status(session_id: str):
    """Get current status of a session."""

    logger.info(f"Getting status for session {session_id}")

    config = {"configurable": {"thread_id": session_id}}

    try:
        state = await workflow.aget_state(config)
        current_state = state.values

        # Determine state
        if current_state.get("error"):
            session_state = "error"
            message = current_state.get("error")
        elif current_state.get("final_workplan"):
            session_state = "completed"
            message = None
        elif current_state.get("awaiting_user_input"):
            if current_state.get("user_input_type") == "decision":
                session_state = "user_review"
            else:
                session_state = "clarification"
            message = None
        elif current_state.get("current_workplan"):
            session_state = "reviewing"
            message = None
        elif current_state.get("requirements"):
            session_state = "generating"
            message = None
        else:
            session_state = "clarification"
            message = None

        response = SessionResponse(session_id=session_id, state=session_state, message=message)

        # Add relevant data
        if session_state == "clarification":
            response.questions = _extract_questions(current_state)
        elif session_state == "user_review":
            response.workplan = current_state.get("current_workplan")
            response.review = current_state.get("review_result")
        elif session_state == "completed":
            response.workplan = current_state.get("final_workplan")

        return response

    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(status_code=404, detail="Session not found")


@app.post("/sessions/{session_id}/decision", response_model=SessionResponse)
async def submit_user_decision(session_id: str, request: DecisionRequest):
    """Submit user decision on the final workplan."""

    logger.info(f"Session {session_id}: User decision = {request.action}")

    config = {"configurable": {"thread_id": session_id}}

    try:
        # Get current state
        state = await workflow.aget_state(config)
        current_state = state.values

        if current_state.get("user_input_type") != "decision":
            raise HTTPException(
                status_code=400, detail="Session is not awaiting user decision"
            )

        # Update state
        current_state["user_decision"] = request.action
        current_state["awaiting_user_input"] = False

        if request.action == "accept":
            current_state["final_workplan"] = current_state["current_workplan"]

        # Reset counters if restarting
        if request.action == "restart_agent2":
            current_state["review_iterations"] = 0
            current_state["generation_attempts"] = 0
        elif request.action == "restart_agent1":
            current_state["clarification_round"] = 0
            current_state["requirements_complete"] = False
            current_state["requirements"] = None
            current_state["review_iterations"] = 0
            current_state["generation_attempts"] = 0

        # Continue workflow
        result = await workflow.ainvoke(current_state, config)

        if request.action == "accept":
            return SessionResponse(
                session_id=session_id,
                state="completed",
                workplan=result.get("final_workplan"),
            )
        else:
            return SessionResponse(
                session_id=session_id,
                state="restarting",
                message=f"Restarting from {request.action}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}/workplan")
async def download_workplan(session_id: str):
    """Download the final workplan JSON."""

    logger.info(f"Downloading workplan for session {session_id}")

    config = {"configurable": {"thread_id": session_id}}

    try:
        state = await workflow.aget_state(config)
        current_state = state.values

        workplan = current_state.get("final_workplan") or current_state.get(
            "current_workplan"
        )

        if not workplan:
            raise HTTPException(status_code=404, detail="Workplan not available")

        return workplan

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download workplan: {e}")
        raise HTTPException(status_code=404, detail="Session not found")


# ========== Helper Functions ==========


def _extract_questions(state: dict) -> list:
    """Extract pending questions from state."""
    if not state.get("conversation_history"):
        return []

    history = state["conversation_history"]
    if history:
        last_turn = history[-1]
        msg = last_turn.get("agent_message", "")
        return [msg] if msg else []

    return []


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

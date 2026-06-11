"""
Clarifier agent - multi-turn vision-based conversation to extract requirements.

The Clarifier analyzes microscopy images and converses with the user to understand
the analysis task. It returns prose messages until it's ready to emit a task brief
marked with [[TASK_READY]].

This module is stateless - the orchestrator owns the conversation history.
"""
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
from openai import OpenAI

READY_MARKER = "[[TASK_READY]]"


@dataclass
class ClarifierTurn:
    """Result of one clarifier turn."""
    assistant_text: str      # The full response from the LLM
    ready: bool              # True if [[TASK_READY]] was detected
    brief: Optional[str]     # The task brief (text before [[TASK_READY]]) if ready


def image_to_data_url(image_path: str) -> str:
    """
    Convert an image file to a data URL for vision API.

    Args:
        image_path: Path to the image file

    Returns:
        data:image/... URL string
    """
    raw = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    mime_map = {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "webp": "webp",
        "bmp": "bmp",
    }
    mime = mime_map.get(ext, "png")
    b64 = base64.b64encode(raw).decode()
    return f"data:image/{mime};base64,{b64}"


def clarifier_turn(
    history: List[Dict],
    system_prompt: str,
    client: OpenAI,
    model: str,
    temperature: float = 0,
) -> ClarifierTurn:
    """
    Execute one turn of the Clarifier conversation.

    The orchestrator is responsible for:
    - Building the initial history with the image + user request
    - Appending this turn's result and user's next answer
    - Detecting when ready=True and stopping the loop

    Args:
        history: OpenAI-format message history (includes system, user with image, etc.)
                 NOTE: The system message should already be in the history[0]
        system_prompt: The clarifier system prompt (injected with KB_CONTEXT)
        client: OpenAI-compatible client
        model: Model endpoint ID
        temperature: Sampling temperature (default 0 for determinism)

    Returns:
        ClarifierTurn with (assistant_text, ready, brief)
    """
    # Call the vision model
    response = client.chat.completions.create(
        model=model,
        messages=history,
        temperature=temperature,
    )

    assistant_text = response.choices[0].message.content

    # Detect [[TASK_READY]]
    if READY_MARKER in assistant_text:
        # Extract the brief (everything before the marker)
        brief = assistant_text.split(READY_MARKER)[0].strip()
        return ClarifierTurn(
            assistant_text=assistant_text,
            ready=True,
            brief=brief,
        )
    else:
        return ClarifierTurn(
            assistant_text=assistant_text,
            ready=False,
            brief=None,
        )


def build_initial_history(
    image_path: str,
    request: str,
    system_prompt: str,
) -> List[Dict]:
    """
    Build the initial conversation history for the Clarifier.

    Args:
        image_path: Path to the microscopy image
        request: User's initial request text
        system_prompt: The full system prompt (with KB context injected)

    Returns:
        Message history list ready for the first turn
    """
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                {"type": "text", "text": request},
            ],
        },
    ]

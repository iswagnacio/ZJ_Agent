"""
Clarifier agent - multi-turn vision-based conversation to extract requirements.

The Clarifier analyzes microscopy images and converses with the user to understand
the analysis task. It returns prose messages until it's ready to emit a task brief
marked with [[TASK_READY]].

This module is stateless - the orchestrator owns the conversation history.
"""
import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

READY_MARKER = "[[TASK_READY]]"


@dataclass
class ClarifierTurn:
    """Result of one clarifier turn."""
    assistant_text: str      # The full response from the LLM
    ready: bool              # True if [[TASK_READY]] was detected
    brief: Optional[str]     # The task brief (text before [[TASK_READY]]) if ready


def image_mime(image_path: str) -> str:
    """Return the image MIME subtype (jpeg/png/...) for a file path."""
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    return {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "webp": "webp",
        "bmp": "bmp",
    }.get(ext, "png")


def image_to_data_url(image_path: str) -> str:
    """
    Convert an image file to an inline base64 data URL for the vision API.

    NOTE: base64 inflates the payload ~37% and is embedded in the request body, so it
    only works for small images. Large images should be delivered by reference instead
    (see prepare_vision_image_url). Kept as the no-infrastructure fallback.
    """
    raw = Path(image_path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    return f"data:image/{image_mime(image_path)};base64,{b64}"


def _build_storage_client():
    """
    Construct an S3/MinIO client from environment, or return None to use inline base64.

    Reads the same settings the server uses (S3_ENDPOINT / S3_BUCKET / S3_ACCESS_KEY /
    S3_SECRET_KEY). Decoupled from the server Settings object so the CLI path doesn't
    require the server-only env vars. Returns None when boto3 is missing or S3 is
    unconfigured, in which case callers fall back to inline base64.
    """
    try:
        from ..storage.s3_client import BOTO3_AVAILABLE
    except Exception:
        return None
    endpoint = os.environ.get("S3_ENDPOINT")
    access = os.environ.get("S3_ACCESS_KEY")
    secret = os.environ.get("S3_SECRET_KEY")
    bucket = os.environ.get("S3_BUCKET", "workplan-images")
    if BOTO3_AVAILABLE and endpoint and access and secret:
        from ..storage.s3_client import S3Client
        return S3Client(endpoint=endpoint, bucket=bucket, access_key=access, secret_key=secret)
    return None


def prepare_vision_image_url(
    image_path: str,
    session_id: str = "cli",
    storage_client=None,
) -> str:
    """
    Return a reference the vision API can read for this image, preferring delivery by URL.

    When an object store (S3/MinIO) is configured, the image is uploaded there and a
    presigned URL is returned, so the image is fetched by reference rather than inlined
    in the request body. This avoids the request-size ceiling that inline base64 hits on
    large images (the cause of the ki67 400). The full-resolution image is preserved; no
    pixels are modified, and this is not CV — the backend still receives the original.

    IMPORTANT — reachability: the returned URL is fetched by the vision provider's
    servers, so the object store must be reachable from them. A localhost MinIO is NOT
    reachable from the cloud vision API; for large images either expose the store at a
    reachable endpoint or use the provider's Files API. Set S3_ENDPOINT to a reachable
    address accordingly.

    Fallback: when no store is configured — or when the store errors (unreachable
    endpoint, upload failure, etc.) — returns an inline base64 data URL. That keeps small
    images working, and emits a loud warning so a large-image failure on the fallback
    stays diagnosable rather than surfacing later as a confusing vision-API 400.
    """
    if storage_client is None:
        try:
            storage_client = _build_storage_client()
        except Exception as e:
            logger.warning(f"Could not initialise object store ({e}); using inline base64.")
            storage_client = None
    if storage_client is None:
        return image_to_data_url(image_path)

    raw = Path(image_path).read_bytes()
    content_type = f"image/{image_mime(image_path)}"
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # no running loop — safe to drive the async upload to completion below
    else:
        # Called from within an async context (e.g. the server path): the caller should
        # await storage_client.upload_image directly and pass the URL into build_initial_history.
        raise RuntimeError(
            "prepare_vision_image_url() called from an async context; "
            "await storage_client.upload_image(...) and pass image_url= instead."
        )

    try:
        return asyncio.run(storage_client.upload_image(session_id, raw, content_type))
    except Exception as e:
        logger.warning(
            f"Object store upload failed ({e}); falling back to inline base64. "
            f"NOTE: large images may exceed the vision API request-size limit on this fallback."
        )
        return image_to_data_url(image_path)


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
    image_url: Optional[str] = None,
) -> List[Dict]:
    """
    Build the initial conversation history for the Clarifier.

    Args:
        image_path: Path to the microscopy image
        request: User's initial request text
        system_prompt: The full system prompt (with KB context injected)
        image_url: Optional pre-prepared image reference (object-store URL or data URL).
                   When omitted, falls back to an inline base64 data URL.

    Returns:
        Message history list ready for the first turn
    """
    url = image_url if image_url is not None else image_to_data_url(image_path)
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": request},
            ],
        },
    ]
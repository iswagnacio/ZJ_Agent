"""
LLM client factory for Doubao (Volcano ARK) models.

Provides two client types:
- Vision client: for the Clarifier (must support image inputs)
- Text client: for the Generator (JSON mode support)
"""
import os
from openai import OpenAI


def create_vision_client(
    base_url: str = None,
    api_key: str = None,
    model: str = None,
) -> tuple[OpenAI, str]:
    """
    Create an OpenAI-compatible client for vision tasks (Clarifier).

    Args:
        base_url: Optional ARK base URL (defaults to env ARK_BASE_URL or CLARIFIER_BASE_URL)
        api_key: Optional API key (defaults to env ARK_API_KEY or CLARIFIER_API_KEY)
        model: Optional model endpoint (defaults to env CLARIFIER_MODEL)

    Returns:
        (client, model_id) tuple

    Raises:
        ValueError: If required env vars are missing
    """
    if base_url is None:
        base_url = os.environ.get(
            "CLARIFIER_BASE_URL",
            os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        )

    if api_key is None:
        api_key = os.environ.get(
            "CLARIFIER_API_KEY",
            os.environ.get("ARK_API_KEY")
        )

    if model is None:
        model = os.environ.get("CLARIFIER_MODEL")

    if not api_key:
        raise ValueError(
            "ARK_API_KEY or CLARIFIER_API_KEY must be set in environment"
        )

    if not model:
        raise ValueError(
            "CLARIFIER_MODEL must be set to a Doubao vision-capable endpoint\n"
            "Example: ep-20260602014208-xxxxx"
        )

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model


def create_text_client(
    base_url: str = None,
    api_key: str = None,
    model: str = None,
) -> tuple[OpenAI, str]:
    """
    Create an OpenAI-compatible client for text tasks (Generator).

    Args:
        base_url: Optional ARK base URL (defaults to env ARK_BASE_URL or GENERATOR_BASE_URL)
        api_key: Optional API key (defaults to env ARK_API_KEY or GENERATOR_API_KEY)
        model: Optional model endpoint (defaults to env GENERATOR_MODEL or CLARIFIER_MODEL)

    Returns:
        (client, model_id) tuple

    Raises:
        ValueError: If required env vars are missing
    """
    if base_url is None:
        base_url = os.environ.get(
            "GENERATOR_BASE_URL",
            os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        )

    if api_key is None:
        api_key = os.environ.get(
            "GENERATOR_API_KEY",
            os.environ.get("ARK_API_KEY")
        )

    if model is None:
        # Generator can default to same model as Clarifier (text-only mode)
        model = os.environ.get(
            "GENERATOR_MODEL",
            os.environ.get("CLARIFIER_MODEL")
        )

    if not api_key:
        raise ValueError(
            "ARK_API_KEY or GENERATOR_API_KEY must be set in environment"
        )

    if not model:
        raise ValueError(
            "GENERATOR_MODEL or CLARIFIER_MODEL must be set\n"
            "Example: ep-20260602014208-xxxxx"
        )

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model

"""
Core workplan generation components - framework-agnostic.

This package contains the pure business logic for the three-agent system:
- Clarifier: vision-based conversation to extract requirements
- Generator: example-driven workplan JSON generation
- Reviewer: structural and schema-based validation

All modules are stateless and framework-agnostic (no LangGraph, no FastAPI).
"""

from .kb import load_context_spec, load_examples, load_models_schema, format_examples_for_prompt
from .llm import create_vision_client, create_text_client
from .clarifier import clarifier_turn, ClarifierTurn, build_initial_history
from .generator import generate_workplan, structural_checks
from .orchestrator import run_pipeline

__all__ = [
    "load_context_spec",
    "load_examples",
    "load_models_schema",
    "format_examples_for_prompt",
    "create_vision_client",
    "create_text_client",
    "clarifier_turn",
    "ClarifierTurn",
    "build_initial_history",
    "generate_workplan",
    "structural_checks",
    "run_pipeline",
]

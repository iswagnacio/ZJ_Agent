#!/usr/bin/env python3
"""
智镜AI pipeline — CLI wrapper over src/core/ orchestrator.

Wires the Clarifier (multi-turn, vision) to the Generator (Workplan JSON).

Flow:
    image + request
      → Clarifier converses (asks you when it needs to) until it emits its task brief + [[TASK_READY]]
      → the brief (prose) is handed to the Generator
      → Generator emits one Workplan JSON  (few-shot = all six example workplans)

The Clarifier is the only call that sees the image; the Generator works from the brief.

Run:
    python pipeline.py --image path/to/img.png --request "统计Ki67阳性率"

Env:
    ARK_API_KEY            # Volcano 火山方舟 key (used for both agents unless overridden below)
    CLARIFIER_MODEL        # a DOUBAO VISION endpoint (the Clarifier must see the image)
    GENERATOR_MODEL        # a text model with JSON mode; defaults to CLARIFIER_MODEL
    # optional overrides:
    ARK_BASE_URL  (default https://ark.cn-beijing.volces.com/api/v3)
    CLARIFIER_BASE_URL / CLARIFIER_API_KEY / GENERATOR_BASE_URL / GENERATOR_API_KEY
"""
import argparse
import json
import sys
from pathlib import Path

# Load .env so ARK_API_KEY / CLARIFIER_MODEL / GENERATOR_MODEL (and optional S3_* /
# WORKPLAN_DIR) are picked up automatically, matching the test harness behaviour.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.core import run_pipeline, format_review


# ───────────────────────── CLI callbacks ─────────────────────────
def cli_on_message(kind: str, text: str):
    """Print clarifier messages to stdout."""
    label = {
        "clarifier_question": "clarifier",
        "clarifier_brief": "clarifier (brief)",
        "generator_raw": "generator (raw)",
    }.get(kind, kind)
    print(f"\n────────── {label} ──────────\n{text}")


def cli_ask_user(question: str) -> str:
    """Prompt user for input via stdin."""
    return input("\n  your reply (as the user): ").strip()


# ───────────────────────── Main ─────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="智镜AI workplan generator pipeline (Clarifier → Generator)"
    )
    ap.add_argument("--image", required=True, help="path to the microscopy image")
    ap.add_argument("--request", required=True, help="user's short request, e.g. 统计Ki67阳性率")
    ap.add_argument("--out", default="out/pipeline.workplan.json", help="output JSON path")
    ap.add_argument(
        "--clarifier-prompt",
        default="prompts/clarifier_system_prompt.md",
        help="path to clarifier system prompt",
    )
    ap.add_argument(
        "--generator-prompt",
        default="prompts/generator_system_prompt.md",
        help="path to generator system prompt",
    )
    args = ap.parse_args()

    # Load prompts
    try:
        clarifier_prompt = Path(args.clarifier_prompt).read_text(encoding="utf-8")
        generator_prompt = Path(args.generator_prompt).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        sys.exit(f"Error: {e}")

    # Run the pipeline
    print(f"\n=== 智镜AI Pipeline ===")
    print(f"Image: {args.image}")
    print(f"Request: {args.request}\n")

    result = run_pipeline(
        image_path=args.image,
        request=args.request,
        clarifier_prompt=clarifier_prompt,
        generator_prompt=generator_prompt,
        ask_user=cli_ask_user,
        on_message=cli_on_message,
    )

    # Check for generation errors
    if result["error"]:
        print(f"\n!! Generator output is not valid JSON: {result['error']}")
        print(f"Raw output:\n{result['raw'][:2000]}")
        sys.exit(1)

    # Review validation
    print("\n────────── workplan review ──────────")
    if result["review"]:
        print(format_review(result["review"]))

        if result["review"].status == "reject":
            print("\n!! Workplan has errors and cannot be saved")
            sys.exit(1)
    else:
        print("⚠ Review skipped (workplan generation failed)")
        sys.exit(1)

    # Save workplan (only if review passed)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(result["workplan"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✓ Saved validated workplan → {dest}")


if __name__ == "__main__":
    main()
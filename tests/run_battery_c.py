#!/usr/bin/env python3
"""
Battery C Test Runner - Tests convergence on under-specified inputs.

This verifies the Clarifier DOES ask when it should (didn't over-correct to being too passive).
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ARK_API_KEY", "ccc1b71a-4939-4061-b2ff-7473986f773b")
os.environ.setdefault("ARK_VISION_MODEL", "ep-20260602014208-2k2k7")
os.environ.setdefault("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

import base64
from openai import OpenAI

BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
API_KEY = os.environ.get("ARK_API_KEY")
MODEL = os.environ.get("ARK_VISION_MODEL")
PROMPT_PATH = Path("prompts/clarifier_system_prompt.md")
KB_PATH = Path("kb_compiled/context_spec.md")
READY_MARKER = "[[TASK_READY]]"

TEST_CASES = [
    {
        "name": "vague_goal",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/ki67.jpg",
        "request": "帮我分析一下这张图",
        "expectation": "Should ask about analysis goal (what to analyze/measure)"
    },
    {
        "name": "target_omitted",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/ki67.jpg",
        "request": "统计阳性率",
        "expectation": "Should ask which marker to analyze"
    }
]


def data_url(image_path: str) -> str:
    raw = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(ext, "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{KB_CONTEXT}}", KB_PATH.read_text(encoding="utf-8"))


def run_case_single_turn(case: dict) -> dict:
    if not API_KEY:
        sys.exit("Set ARK_API_KEY and ARK_VISION_MODEL first.")

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url(case["image"])}},
            {"type": "text", "text": case["request"]},
        ]},
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0
        ).choices[0].message.content

        is_ready = READY_MARKER in response

        return {
            "case_name": case["name"],
            "response": response,
            "is_ready": is_ready,
            "turn_count": 1,
            "error": None
        }
    except Exception as e:
        return {
            "case_name": case["name"],
            "response": None,
            "is_ready": False,
            "turn_count": 0,
            "error": str(e)
        }


def main():
    print("=" * 80)
    print("BATTERY C: Convergence on Under-Specified Inputs")
    print("=" * 80)
    print()
    print("Goal: Verify the Clarifier DOES ask when input is genuinely vague")
    print("(Confirms we didn't over-correct to being too passive)")
    print()

    results_dir = Path("tests/battery_c_results")
    results_dir.mkdir(exist_ok=True, parents=True)

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}/2: {case['name']}")
        print(f"{'=' * 80}")
        print(f"Image: {case['image']}")
        print(f"Request: \"{case['request']}\"")
        print(f"Expectation: {case['expectation']}")
        print()

        result = run_case_single_turn(case)

        if result["error"]:
            print(f"❌ ERROR: {result['error']}")
            continue

        print("─" * 80)
        print("RESPONSE:")
        print("─" * 80)
        print(result["response"])
        print()

        # Save result
        result_file = results_dir / f"{case['name']}_result.txt"
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(f"Case: {case['name']}\n")
            f.write(f"Request: {case['request']}\n")
            f.write(f"Expectation: {case['expectation']}\n")
            f.write(f"Turn count: {result['turn_count']}\n")
            f.write(f"Ready: {result['is_ready']}\n")
            f.write(f"\n{'=' * 80}\n")
            f.write(f"RESPONSE:\n")
            f.write(f"{'=' * 80}\n")
            f.write(result["response"] or "(No response)")
            f.write("\n")

        print(f"✓ Result saved to: {result_file}")
        print()

        # Analyze result
        if result["is_ready"]:
            print("⚠️ WARNING: Clarifier emitted [[TASK_READY]] without asking!")
            print("→ This may indicate over-correction (too passive)")
            print("→ Expected: Should ask a clarifying question")
        else:
            print("✅ GOOD: Clarifier asked a question (did not proceed blindly)")
            print("→ This confirms it still asks when input is genuinely vague")

        print()

    print("=" * 80)
    print("Battery C Complete!")
    print(f"Results saved to: {results_dir}/")
    print()
    print("Next steps:")
    print("1. Review each result to verify questions are sensible")
    print("2. Confirm it asks about GOAL, not just parameters")
    print("3. Check that it doesn't proceed on vague inputs")
    print("=" * 80)


if __name__ == "__main__":
    main()

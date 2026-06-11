#!/usr/bin/env python3
"""
Battery A Test Runner - Tests accuracy on all six cases.

This script runs each test case and logs the conversation, then waits for manual scoring.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up environment
os.environ.setdefault("ARK_API_KEY", "ccc1b71a-4939-4061-b2ff-7473986f773b")
os.environ.setdefault("ARK_VISION_MODEL", "ep-20260602014208-2k2k7")
os.environ.setdefault("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

# Import test module components
import base64
from openai import OpenAI

BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
API_KEY = os.environ.get("ARK_API_KEY")
MODEL = os.environ.get("ARK_VISION_MODEL")
PROMPT_PATH = Path("/Users/junwei/Personal/CZ/agent/workplan-generator/prompts/clarifier_system_prompt.md")
KB_PATH = Path("kb_compiled/context_spec.md")
READY_MARKER = "[[TASK_READY]]"

# Test cases for Battery A
TEST_CASES = [
    {
        "name": "siriusred",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/siriusred.jpg",
        "request": "统计图片中胶原纤维的面积"
    },
    {
        "name": "ki67",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/ki67.jpg",
        "request": "统计Ki67阳性率"
    },
    {
        "name": "SMA",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/sma.png",
        "request": "计算SMA染色的H-score"
    },
    {
        "name": "空泡",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/空泡.png",
        "request": "统计空泡按面积分级的数量"
    },
    {
        "name": "rnascope",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/rnascope.jpg",
        "request": "统计RNAScope探针点数量分级"
    },
    {
        "name": "脂滴rgb",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/脂滴rgb.jpg",
        "request": "统计细胞数、脂滴面积和单位细胞脂滴面积"
    }
]


def data_url(image_path: str) -> str:
    """Convert image to data URL."""
    raw = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(ext, "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"


def system_prompt() -> str:
    """Load system prompt with KB context."""
    return PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{KB_CONTEXT}}", KB_PATH.read_text(encoding="utf-8"))


def run_case_single_turn(case: dict) -> dict:
    """
    Run a test case with a single turn (no clarification questions).

    Returns:
        dict with 'response', 'is_ready', 'turn_count'
    """
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
    """Run all Battery A test cases."""
    print("=" * 80)
    print("BATTERY A: Accuracy Test on Six Cases")
    print("=" * 80)
    print()

    results_dir = Path("tests/battery_a_results")
    results_dir.mkdir(exist_ok=True, parents=True)

    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}/6: {case['name']}")
        print(f"{'=' * 80}")
        print(f"Image: {case['image']}")
        print(f"Request: {case['request']}")
        print()

        result = run_case_single_turn(case)

        if result["error"]:
            print(f"❌ ERROR: {result['error']}")
            continue

        print(f"Turn count: {result['turn_count']}")
        print(f"Contains [[TASK_READY]]: {result['is_ready']}")
        print()
        print("─" * 80)
        print("RESPONSE:")
        print("─" * 80)
        print(result["response"])
        print()

        # Save result to file
        result_file = results_dir / f"{case['name']}_result.txt"
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(f"Case: {case['name']}\n")
            f.write(f"Request: {case['request']}\n")
            f.write(f"Turn count: {result['turn_count']}\n")
            f.write(f"Ready: {result['is_ready']}\n")
            f.write(f"\n{'=' * 80}\n")
            f.write(f"RESPONSE:\n")
            f.write(f"{'=' * 80}\n")
            f.write(result["response"] or "(No response)")
            f.write("\n")

        print(f"✓ Result saved to: {result_file}")
        print()

        if result["is_ready"]:
            print("✓ Task brief received [[TASK_READY]]")
            print("→ Score this against the ground-truth card")
        else:
            print("⚠ Clarifier did not emit [[TASK_READY]]")
            print("→ May need follow-up questions (run interactively)")

        print()

    print("=" * 80)
    print("Battery A Complete!")
    print(f"Results saved to: {results_dir}/")
    print()
    print("Next steps:")
    print("1. Review each result file")
    print("2. Score against ground-truth cards in tests/clarifier_ground_truth_cards.md")
    print("3. Mark each as PASS/PARTIAL/FAIL")
    print("=" * 80)


if __name__ == "__main__":
    main()

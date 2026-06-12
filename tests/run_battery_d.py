#!/usr/bin/env python3
"""
Battery D Test Runner - Tests stability at temperature=0.

Runs each case 3 times and verifies responses are consistent.
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
        "name": "siriusred",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/siriusred.jpg",
        "request": "统计图片中胶原纤维的面积"
    },
    {
        "name": "SMA",
        "image": "/Users/junwei/Personal/CZ/agent/workplan/sma.png",
        "request": "计算SMA染色的H-score"
    }
]

RUNS_PER_CASE = 3


def data_url(image_path: str) -> str:
    raw = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(ext, "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{KB_CONTEXT}}", KB_PATH.read_text(encoding="utf-8"))


def run_case_single_turn(case: dict, run_num: int) -> dict:
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
            "run_num": run_num,
            "response": response,
            "is_ready": is_ready,
            "error": None
        }
    except Exception as e:
        return {
            "case_name": case["name"],
            "run_num": run_num,
            "response": None,
            "is_ready": False,
            "error": str(e)
        }


def extract_key_info(response: str) -> dict:
    """Extract key elements from response for comparison."""
    response_lower = response.lower()

    return {
        "modality": {
            "fluorescence": "荧光" in response or "fluorescence" in response_lower,
            "brightfield": "明场" in response or "brightfield" in response_lower,
            "ihc": "ihc" in response_lower or "免疫组化" in response
        },
        "methods": {
            "threshold": "阈值" in response or "threshold" in response_lower,
            "cellpose": "cellpose" in response_lower,
            "h_score": "h-score" in response_lower or "h score" in response_lower
        },
        "deconvolution": {
            "mentioned": "反卷积" in response or "解卷" in response or "deconv" in response_lower,
            "h_dab": "h dab" in response_lower or "h&dab" in response_lower or ("苏木" in response and "dab" in response_lower)
        },
        "pattern": {
            "area": "面积" in response,
            "count": "数量" in response or "计数" in response,
            "rate": "比例" in response or "阳性率" in response,
            "h_score": "h-score" in response_lower
        },
        "is_ready": "[[TASK_READY]]" in response
    }


def main():
    print("=" * 80)
    print("BATTERY D: Stability Test at Temperature=0")
    print("=" * 80)
    print()
    print(f"Running each case {RUNS_PER_CASE} times to verify consistency")
    print()

    results_dir = Path("tests/battery_d_results")
    results_dir.mkdir(exist_ok=True, parents=True)

    all_results = {}

    for case in TEST_CASES:
        print(f"\n{'=' * 80}")
        print(f"Case: {case['name']}")
        print(f"{'=' * 80}")
        print(f"Image: {case['image']}")
        print(f"Request: {case['request']}")
        print()

        case_results = []

        for run in range(1, RUNS_PER_CASE + 1):
            print(f"  Run {run}/{RUNS_PER_CASE}...", end=" ", flush=True)
            result = run_case_single_turn(case, run)

            if result["error"]:
                print(f"❌ ERROR: {result['error']}")
                continue

            case_results.append(result)

            # Save individual result
            result_file = results_dir / f"{case['name']}_run{run}.txt"
            with open(result_file, "w", encoding="utf-8") as f:
                f.write(f"Case: {case['name']}\n")
                f.write(f"Run: {run}/{RUNS_PER_CASE}\n")
                f.write(f"Request: {case['request']}\n")
                f.write(f"Ready: {result['is_ready']}\n")
                f.write(f"\n{'=' * 80}\n")
                f.write(f"RESPONSE:\n")
                f.write(f"{'=' * 80}\n")
                f.write(result["response"] or "(No response)")
                f.write("\n")

            print(f"✓ (saved to {result_file.name})")

        all_results[case['name']] = case_results

        # Analyze consistency
        print()
        print("─" * 80)
        print("CONSISTENCY CHECK:")
        print("─" * 80)

        if len(case_results) < RUNS_PER_CASE:
            print(f"⚠️ Only {len(case_results)}/{RUNS_PER_CASE} runs completed")
            continue

        # Extract key info from all runs
        infos = [extract_key_info(r["response"]) for r in case_results]

        # Check modality consistency
        modalities = [i["modality"] for i in infos]
        if all(m == modalities[0] for m in modalities):
            print("✅ Modality: CONSISTENT across all runs")
        else:
            print("❌ Modality: INCONSISTENT!")
            for i, m in enumerate(modalities, 1):
                print(f"   Run {i}: {m}")

        # Check methods consistency
        methods = [i["methods"] for i in infos]
        if all(m == methods[0] for m in methods):
            print("✅ Methods: CONSISTENT across all runs")
        else:
            print("❌ Methods: INCONSISTENT!")
            for i, m in enumerate(methods, 1):
                print(f"   Run {i}: {m}")

        # Check pattern consistency
        patterns = [i["pattern"] for i in infos]
        if all(p == patterns[0] for p in patterns):
            print("✅ Analysis Pattern: CONSISTENT across all runs")
        else:
            print("❌ Analysis Pattern: INCONSISTENT!")
            for i, p in enumerate(patterns, 1):
                print(f"   Run {i}: {p}")

        # Check [[TASK_READY]] consistency
        ready_statuses = [i["is_ready"] for i in infos]
        if all(r == ready_statuses[0] for r in ready_statuses):
            print(f"✅ [[TASK_READY]]: CONSISTENT ({'Yes' if ready_statuses[0] else 'No'} in all runs)")
        else:
            print("❌ [[TASK_READY]]: INCONSISTENT!")
            for i, r in enumerate(ready_statuses, 1):
                print(f"   Run {i}: {'Yes' if r else 'No'}")

        print()

    print("=" * 80)
    print("Battery D Complete!")
    print(f"Results saved to: {results_dir}/")
    print()
    print("Summary:")
    for case_name, results in all_results.items():
        if len(results) == RUNS_PER_CASE:
            print(f"  {case_name}: {len(results)}/{RUNS_PER_CASE} runs completed ✓")
        else:
            print(f"  {case_name}: {len(results)}/{RUNS_PER_CASE} runs completed ⚠️")
    print("=" * 80)


if __name__ == "__main__":
    main()

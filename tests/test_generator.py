#!/usr/bin/env python3
"""
Test harness for the v11 Workplan Generator.

Injects the API spec + worked examples + a Clarifier task brief into the Generator prompt,
calls a JSON-mode model, runs structural-invariant checks, prints a recipe summary you diff
against the ground-truth workplan, and saves the result to out/<case>.workplan.json.

Setup:
    pip install openai
    export GEN_API_KEY=...                  # key for your generator model
    export GEN_MODEL=...                     # a text model with JSON mode (DeepSeek V4, or a Doubao text model)
    # optional: export GEN_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
    # optional: export GENERATOR_PROMPT=prompts/generator_system_prompt.md
    # optional: export API_SPEC=kb_compiled/context_spec.md
    # optional: export WORKPLANS_DIR=/Users/junwei/Personal/CZ/agent/workplan

Run (leave-one-out: the case under test must NOT be in --fewshot):
    python test_generator.py --case SMA --brief briefs/SMA.txt \
        --fewshot siriusred,ki67,rnascope,脂滴rgb
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI  # pip install openai

BASE_URL = os.environ.get("GEN_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
API_KEY = os.environ.get("GEN_API_KEY")
MODEL = os.environ.get("GEN_MODEL", "<set GEN_MODEL>")
PROMPT_PATH = Path(os.environ.get("GENERATOR_PROMPT", "prompts/generator_system_prompt.md"))
SPEC_PATH = Path(os.environ.get("API_SPEC", "kb_compiled/context_spec.md"))
WORKPLANS_DIR = Path(os.environ.get("WORKPLANS_DIR", "/Users/junwei/Personal/CZ/agent/workplan"))

WORKPLAN_FILES = {
    "siriusred": "siriusred_workplan.json",
    "ki67": "ki67_workplan.txt",
    "SMA": "SMA_workplan.txt",
    "空泡": "空泡_workplan.json",
    "rnascope": "rnascope_workplan.json",
    "脂滴rgb": "脂滴rgb_workplan.json",
}


def load_workplan_text(name: str) -> str:
    return (WORKPLANS_DIR / WORKPLAN_FILES[name]).read_text(encoding="utf-8")


def build_prompt(brief: str, fewshot_names, request: str) -> str:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    spec = SPEC_PATH.read_text(encoding="utf-8")
    examples = "\n\n".join(f"--- EXAMPLE: {n} ---\n{load_workplan_text(n)}" for n in fewshot_names)
    return (prompt
            .replace("{{API_SPEC}}", spec)
            .replace("{{FEWSHOT_EXAMPLES}}", examples)
            .replace("{{CLARIFIED_REQUIREMENTS}}", brief)
            .replace("{{USER_REQUEST}}", request))


def call_model(system_prompt: str) -> str:
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    kwargs = dict(model=MODEL, temperature=0,
                  messages=[{"role": "system", "content": system_prompt},
                            {"role": "user", "content": "生成本次分析的 Workplan JSON。"}])
    try:
        resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except Exception as e:
        print(f"(json_object mode rejected: {e}; retrying without it)")
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def parse_json(text: str):
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s), None
    except Exception as e:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0)), None
            except Exception as e2:
                return None, str(e2)
        return None, str(e)


def structural_checks(wp: dict):
    """The schema-agnostic invariants from the Generator's OUTPUT CONTRACT."""
    issues = []
    for k in ("experimentName", "inputMode", "analysisGoal", "imageInference", "channels", "targets", "jobs"):
        if k not in wp:
            issues.append(f"missing top-level key: {k}")
    channels = {c.get("channelId") for c in wp.get("channels", [])}
    jobs = wp.get("jobs", [])
    if jobs:
        if jobs[0].get("jobType") != "pic_split":
            issues.append("first job is not pic_split")
        if jobs[-1].get("jobType") != "formula":
            issues.append("last job is not formula")
    created = []
    for j in jobs:
        jt = j.get("jobType")
        if jt not in ("pic_split", "create_target", "formula"):
            issues.append(f"{j.get('jobId')}: invalid jobType {jt!r}")
        if jt == "create_target":
            parents = (j.get("inputs", {}).get("sourceTargetNames")
                       or j.get("createTargetPlan", {}).get("sourceTargetNames") or [])
            for p in parents:
                if p and p not in created:
                    issues.append(f"{j.get('jobId')}: sourceTargetName '{p}' not created by an earlier job")
            tn = j.get("outputs", {}).get("targetName")
            if tn:
                created.append(tn)
        for ch in (j.get("inputs", {}).get("channelId") or []):
            if ch not in channels:
                issues.append(f"{j.get('jobId')}: channelId '{ch}' not declared in channels")
    if jobs:
        for ti in jobs[-1].get("inputs", {}).get("targetInputs", []):
            if ti.get("targetName") not in created:
                issues.append(f"formula: targetInput '{ti.get('targetName')}' is not a created target")
    return issues


def summarize(wp: dict):
    print("\n── recipe summary (diff against the ground-truth card) ──")
    inf = wp.get("imageInference", {})
    print(f"modality: {inf.get('imageModality')}   inputMode: {wp.get('inputMode')}")
    print("channels: " + ", ".join(
        f"{c.get('channelId')}={c.get('semanticRole') or c.get('channelName')}" for c in wp.get("channels", [])))
    for j in wp.get("jobs", []):
        jt = j.get("jobType")
        if jt == "pic_split":
            sp = j.get("picSplitPlan", {})
            matrix = sp.get("colorDeconvParams", {}).get("matrix", "")
            print(f"  {j.get('jobId')} pic_split: {sp.get('splitMethod')}" + (f" [{matrix}]" if matrix else ""))
        elif jt == "create_target":
            method = j.get("createTargetPlan", {}).get("recommendedSegmentMethod") or "(derived / measure-filter)"
            print(f"  {j.get('jobId')} create_target → {j.get('outputs', {}).get('targetName')}: {method}")
        elif jt == "formula":
            print(f"  {j.get('jobId')} formula: {j.get('formulaPlan', {}).get('expression')}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, help="case name (also the output filename)")
    ap.add_argument("--brief", required=True, help="path to the Clarifier task brief (a text file)")
    ap.add_argument("--fewshot", required=True, help="comma-separated example names")
    ap.add_argument("--request", default="", help="original user request (optional)")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("Set GEN_API_KEY and GEN_MODEL first.")
    fewshot = [n.strip() for n in args.fewshot.split(",") if n.strip()]
    for n in fewshot + [args.case]:
        if n not in WORKPLAN_FILES:
            sys.exit(f"Unknown case name: {n!r}. Known: {list(WORKPLAN_FILES)}")
    if args.case in fewshot:
        print(f"WARNING: '{args.case}' is in --fewshot. This measures stability-of-following the anchor, "
              "NOT generalization/accuracy (the model can copy the example).")

    brief = Path(args.brief).read_text(encoding="utf-8")
    system_prompt = build_prompt(brief, fewshot, args.request or "(see the task brief above)")

    print(f"case={args.case}  fewshot={fewshot}")
    raw = call_model(system_prompt)
    wp, err = parse_json(raw)
    if wp is None:
        print("\n!! Output is not valid JSON:", err)
        print(raw[:2000])
        return

    issues = structural_checks(wp)
    print("\n── structural checks ──")
    if issues:
        for i in issues:
            print("  ✗", i)
        print(f"  → {len(issues)} structural issue(s)")
    else:
        print("  ✓ all invariants hold (jobType set, pic_split/formula ordering, target & channel references)")
    summarize(wp)

    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"{args.case}.workplan.json"
    dest.write_text(json.dumps(wp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved → {dest}  (diff against {WORKPLAN_FILES[args.case]})")


if __name__ == "__main__":
    main()

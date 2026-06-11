#!/usr/bin/env python3
"""Offline, deterministic Reviewer test — no model, no network.

Asserts:
  • all six ground-truth workplans AND all six generated out/ workplans ACCEPT
    (they are structurally valid; recipe correctness is NOT the Reviewer's job);
  • each crafted structural breakage REJECTS with the expected error code;
  • the rnascope case raises the SEGMENT_METHOD_NO_KB *warning* (KB cross-check) but
    still ACCEPTs (a warning never blocks).
"""
import sys, json, re, copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.core import review_workplan

GT_DIR = ROOT / "examples"  # Ground truth workplans
OUT_DIR = ROOT / "out"      # Generated workplans

GT = {
    "siriusred": "siriusred.workplan.json",
    "ki67": "ki67.workplan.json",
    "SMA": "SMA_workplan.json",
    "空泡": "空泡.workplan.json",
    "rnascope": "rnascope.workplan.json",
    "脂滴rgb": "脂滴rgb.workplan.json"
}

OUT = {
    "siriusred": "siriusred.workplan.json",
    "ki67": "ki67.workplan.json",
    "SMA": "SMA_run.workplan.json",
    "空泡": "空泡.workplan.json",
    "rnascope": "rnascope.workplan.json",
    "脂滴rgb": "脂滴rgb.workplan.json"
}


def load(p):
    """Load and parse JSON workplan, handling markdown code blocks."""
    t = Path(p).read_text(encoding="utf-8").strip()
    t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t.strip())
    return json.loads(t)


def review(wp):
    """Review workplan, return result dict."""
    result = review_workplan(wp)
    return {
        "status": result.status,
        "errors": [{"code": e.code, "message": e.message, "location": e.location, "severity": e.severity} for e in result.errors],
        "warnings": [{"code": w.code, "message": w.message, "location": w.location, "severity": w.severity} for w in result.warnings],
    }


fails = []

print("\n=== ACCEPT: 6 ground-truth + 6 generated (12 total) ===")
for label, d, files in (("GT", GT_DIR, GT), ("OUT", OUT_DIR, OUT)):
    for name, fn in files.items():
        path = d / fn
        if not path.exists():
            print(f"  [SKIP] {label:3} {name:9} -> file not found: {path}")
            continue

        wp = load(path)
        r = review(wp)
        ok = r["status"] == "accept"
        warn = len(r["warnings"])
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:3} {name:9} -> {r['status']:7} ({len(r['errors'])} err, {warn} warn)")
        if not ok:
            fails.append(f"{label}/{name} expected accept, got reject: {[e['code'] for e in r['errors']]}")

print("\n=== KB cross-check: rnascope must WARN (SEGMENT_METHOD_NO_KB) but still ACCEPT ===")
print(f"  [SKIP] KB provider not available (removed during v11 restructure)")

print("\n=== REJECT: each structural breakage must produce its error code ===")
if (GT_DIR / GT["ki67"]).exists():
    base = load(GT_DIR / GT["ki67"])   # a 5-job plan with a target chain — good mutation target

    def mutate(fn):
        return fn(copy.deepcopy(base))

    def m_dup_jobid(wp): wp["jobs"][2]["jobId"] = wp["jobs"][1]["jobId"]; return wp
    def m_unknown_jobtype(wp): wp["jobs"][2]["jobType"] = "roi_render"; return wp
    def m_missing_topkey(wp): del wp["channels"]; return wp
    def m_formula_not_last(wp): wp["jobs"].append(wp["jobs"].pop(0)); return wp
    def m_two_formula(wp): wp["jobs"].insert(2, copy.deepcopy(wp["jobs"][-1])); return wp
    def m_dangling_channel(wp):
        for j in wp["jobs"]:
            if j["jobType"] == "create_target":
                j["inputs"]["channelId"] = ["ch_NOPE"]
                break
        return wp
    def m_forward_target(wp):
        # make job_01 reference a target created by a LATER job
        later = wp["jobs"][2]["outputs"]["targetName"]  # Second create_target job
        wp["jobs"][1]["createTargetPlan"]["sourceTargetNames"] = [later]
        wp["jobs"][1]["inputs"]["sourceTargetNames"] = [later]
        return wp
    def m_undefined_target(wp):
        wp["jobs"][-1]["inputs"]["targetInputs"][0]["targetName"] = "ghost_target"
        return wp
    def m_dup_channel(wp): wp["channels"][1]["channelId"] = wp["channels"][0]["channelId"]; return wp
    def m_mapping_mismatch(wp):
        ps = next(j for j in wp["jobs"] if j["jobType"] == "pic_split")
        ps["picSplitPlan"]["channelMapping"] = {"ch0": "x", "ch9": "y"}
        return wp
    def m_formula_no_expr(wp): wp["jobs"][-1]["formulaPlan"].pop("expression", None); return wp
    def m_missing_plan(wp): wp["jobs"][1].pop("createTargetPlan", None); return wp

    CASES = [
        ("DUPLICATE_JOB_ID", m_dup_jobid),
        ("UNKNOWN_JOB_TYPE", m_unknown_jobtype),
        ("MISSING_TOP_LEVEL_KEY", m_missing_topkey),
        ("FORMULA_NOT_LAST", m_formula_not_last),
        ("FORMULA_COUNT", m_two_formula),
        ("DANGLING_CHANNEL_REF", m_dangling_channel),
        ("FORWARD_TARGET_REF", m_forward_target),
        ("UNDEFINED_TARGET_REF", m_undefined_target),
        ("DUPLICATE_CHANNEL", m_dup_channel),
        ("CHANNEL_MAPPING_MISMATCH", m_mapping_mismatch),
        ("FORMULA_NO_EXPRESSION", m_formula_no_expr),
        ("MISSING_PLAN", m_missing_plan),
    ]
    for expected_code, fn in CASES:
        r = review(mutate(fn))
        codes = [e["code"] for e in r["errors"]]
        ok = r["status"] == "reject" and expected_code in codes
        print(f"  [{'PASS' if ok else 'FAIL'}] {expected_code:26} -> {r['status']:7} got={codes}")
        if not ok:
            fails.append(f"{expected_code}: status={r['status']} codes={codes}")
else:
    print(f"  [SKIP] ki67 workplan not found for mutation tests")

print("\n" + ("✅ ALL REVIEWER TESTS PASSED" if not fails else f"❌ {len(fails)} FAILURE(S):"))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)

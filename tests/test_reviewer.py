"""Offline, deterministic Reviewer test — no model, no network.

All paths are anchored to the repo (via __file__), so this runs from any working
directory. Ground truth = the six canonical workplans in examples/; the generated plans
in out/ are checked too. Asserts: KB loads, 12 accepts, the rnascope KB warning, and 12
structural rejections.
"""
import sys, json, re, copy, asyncio
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from src.core.reviewer import ReviewerAgent

EX_DIR = REPO / "examples"     # canonical six (ground truth)
OUT_DIR = REPO / "out"         # generated six
NAMES = ["siriusred", "ki67", "SMA", "空泡", "rnascope", "脂滴rgb"]

def resolve(dirpath: Path, name: str) -> Path | None:
    for pat in (f"{name}.workplan.json", f"{name}_workplan.json",
                f"{name}_run.workplan.json", f"{name}_workplan.txt"):
        p = dirpath / pat
        if p.exists():
            return p
    hits = sorted(dirpath.glob(f"{name}*workplan*.json"))
    return hits[0] if hits else None

def load(p: Path):
    t = p.read_text(encoding="utf-8").strip()
    t = re.sub(r"^```[a-zA-Z]*\n?", "", t); t = re.sub(r"\n?```$", "", t.strip())
    return json.loads(t)

rev = ReviewerAgent()
run = lambda wp: asyncio.run(rev.review_workplan(wp))
fails = []

print(f"\nKB loaded: {rev.kb_loaded}  (seg={sorted(rev.kb_segment_methods)})")
if not rev.kb_loaded:
    fails.append("KB did not load — vocabulary cross-checks would be silently disabled.")

print("\n=== ACCEPT: 6 ground-truth (examples/) + 6 generated (out/) ===")
for label, d in (("EX", EX_DIR), ("OUT", OUT_DIR)):
    for name in NAMES:
        p = resolve(d, name)
        if p is None:
            print(f"  [MISS] {label:3} {name:9} -> file not found in {d.name}/"); fails.append(f"{label}/{name} missing"); continue
        r = run(load(p)); ok = r["status"] == "accept"
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:3} {name:9} -> {r['status']:7} ({len(r['errors'])} err, {len(r['warnings'])} warn)  [{p.name}]")
        if not ok: fails.append(f"{label}/{name} expected accept: {[e['code'] for e in r['errors']]}")

print("\n=== KB cross-check: rnascope must WARN (SEGMENT_METHOD_NO_KB) and ACCEPT ===")
p = resolve(EX_DIR, "rnascope")
r = run(load(p))
ok = r["status"] == "accept" and "SEGMENT_METHOD_NO_KB" in [w["code"] for w in r["warnings"]]
print(f"  [{'PASS' if ok else 'FAIL'}] rnascope -> {r['status']}, warnings={[w['code'] for w in r['warnings']]}")
if not ok: fails.append("rnascope KB cross-check failed")

print("\n=== REJECT: each structural breakage must produce its error code ===")
base = load(resolve(EX_DIR, "ki67"))
def mut(fn): return fn(copy.deepcopy(base))
def _cts(w): return [j for j in w["jobs"] if j.get("jobType") == "create_target"]
def _formula(w): return next(j for j in w["jobs"] if j.get("jobType") == "formula")
def m_dup_jobid(w): w["jobs"][1]["jobId"]=w["jobs"][0]["jobId"]; return w
def m_unknown_jobtype(w): _cts(w)[0]["jobType"]="roi_render"; return w
def m_missing_topkey(w): del w["channels"]; return w
def m_formula_not_last(w): w["jobs"].append(w["jobs"].pop(0)); return w
def m_two_formula(w): w["jobs"].insert(1, copy.deepcopy(_formula(w))); return w
def m_dangling_channel(w): _cts(w)[0].setdefault("inputs",{})["channelId"]=["ch_NOPE"]; return w
def m_forward_target(w):
    cts=_cts(w); later=cts[-1]["outputs"]["targetName"]
    cts[0].setdefault("createTargetPlan",{})["sourceTargetNames"]=[later]
    cts[0].setdefault("inputs",{})["sourceTargetNames"]=[later]; return w
def m_undefined_target(w): _formula(w).setdefault("inputs",{})["targetInputs"]=[{"targetName":"ghost","metric":"COUNT"}]; return w
def m_dup_channel(w): w["channels"][1]["channelId"]=w["channels"][0]["channelId"]; return w
def m_mapping_mismatch(w):
    ps=next(j for j in w["jobs"] if j["jobType"]=="pic_split"); ps["picSplitPlan"]["channelMapping"]={"ch0":"x","ch9":"y"}; return w
def m_formula_no_expr(w): _formula(w)["formulaPlan"].pop("expression",None); return w
def m_missing_plan(w): _cts(w)[0].pop("createTargetPlan",None); return w
CASES=[("DUPLICATE_JOB_ID",m_dup_jobid),("UNKNOWN_JOB_TYPE",m_unknown_jobtype),("MISSING_TOP_LEVEL_KEY",m_missing_topkey),
("FORMULA_NOT_LAST",m_formula_not_last),("FORMULA_COUNT",m_two_formula),("DANGLING_CHANNEL_REF",m_dangling_channel),
("FORWARD_TARGET_REF",m_forward_target),("UNDEFINED_TARGET_REF",m_undefined_target),("DUPLICATE_CHANNEL",m_dup_channel),
("CHANNEL_MAPPING_MISMATCH",m_mapping_mismatch),("FORMULA_NO_EXPRESSION",m_formula_no_expr),("MISSING_PLAN",m_missing_plan)]
for code, fn in CASES:
    r=run(mut(fn)); got=[e["code"] for e in r["errors"]]; ok=r["status"]=="reject" and code in got
    print(f"  [{'PASS' if ok else 'FAIL'}] {code:26} -> {r['status']:7} got={got}")
    if not ok: fails.append(f"{code}: {r['status']} {got}")

print("\n" + ("✅ ALL REVIEWER TESTS PASSED" if not fails else f"❌ {len(fails)} FAILURE(S):"))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
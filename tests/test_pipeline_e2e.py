#!/usr/bin/env python3
"""End-to-end pipeline test: microscope image + a NEW request → clarified brief →
Generator → Reviewer → approved Workplan JSON.

═══════════════════════════════════════════════════════════════════════════════════
TEST PHILOSOPHY — a DIFFERENT analysis target on the SAME image
═══════════════════════════════════════════════════════════════════════════════════
Each of the six images already has a canonical worked example in examples/, and ALL six
examples are injected into the Generator on every run. So asking an image's *canonical*
request would just let the model copy its own in-context example — that tests retrieval,
not generation.

Instead, each case below asks a DIFFERENT analysis target on the same image. This does two
things at once:

  1. Tests genuine generation — there is no gold workplan to copy; the model must compose
     a new recipe from the prompt rules + the API spec.

  2. Probes OVER-ANCHORING — the canonical recipe for this exact image is sitting right
     there in the few-shot block. A correct system produces the NEW target's recipe; an
     over-anchored one parrots the visible canonical recipe even though the request changed.
     Each case lists a `leak_signatures` set: substrings that should NOT appear in the
     output (they belong to the canonical recipe we deliberately avoided).

═══════════════════════════════════════════════════════════════════════════════════
RUN
═══════════════════════════════════════════════════════════════════════════════════
  export ARK_API_KEY=...          # Volcano 火山方舟 key
  export CLARIFIER_MODEL=...      # a Doubao VISION endpoint (only the Clarifier sees the image)
  export GENERATOR_MODEL=...      # text/JSON model (defaults to CLARIFIER_MODEL if unset)
  export WORKPLAN_DIR=/Users/junwei/Personal/CZ/agent/workplan   # the image directory
  python tests/test_pipeline_e2e.py

Writes each generated workplan to out_e2e/<case>.json and prints a structured report
(brief, workplan skeleton, reviewer status/attempts, anchoring flag) + the rubric so the
recipe can be scored PASS / PARTIAL / FAIL.
"""
import os, sys, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from src.core import run_pipeline

WORKPLAN_DIR = Path(os.environ.get("WORKPLAN_DIR", "/Users/junwei/Personal/CZ/agent/workplan"))
PROMPTS = REPO / "prompts"
OUT = REPO / "out_e2e"; OUT.mkdir(exist_ok=True)

CLARIFIER_PROMPT = (PROMPTS / "clarifier_system_prompt.md").read_text(encoding="utf-8")
GENERATOR_PROMPT = (PROMPTS / "generator_system_prompt.md").read_text(encoding="utf-8")

# Each request is deliberately a DIFFERENT target than the image's canonical example, and is
# written self-contained (any thresholds/bands stated inline) so the Clarifier can proceed to
# a brief without a blocking question. `answers` provides scripted fallbacks just in case.
CASES = [
    {
        "name": "siriusred__lipid_count_area",
        "image": "siriusred.jpg",
        "request": "请统计这张图中白色圆形脂滴（空泡）结构的数量，并测量它们的总面积。",
        "canonical_avoided": "胶原纤维总面积（collagen area, AREA_SUM）",
        "expect": ("明场，颜色解卷积或合适的通道；1 个 create_target 分割白色脂滴（阈值分割）；"
                   "formula 输出 数量(COUNT) + 总面积(AREA_SUM)。不应出现胶原纤维靶标。"),
        "leak_signatures": ["胶原", "collagen"],
        "answers": [],
    },
    {
        "name": "ki67__islet_area",
        "image": "ki67.jpg",
        "request": "请测量绿色通道标记的胰岛区域的总面积，无需统计任何阳性率。",
        "canonical_avoided": "胰岛区域内 Ki67 阳性率（DAPI→islet→Ki67+ 三靶标链 + 比例）",
        "expect": ("荧光，rgb_split；1 个 create_target 从绿色通道分割胰岛区域；formula 输出该区域 AREA_SUM。"
                   "不应出现 DAPI 细胞核分割、Ki67 阳性筛选或任何阳性率公式。"),
        "leak_signatures": ["ki67_positive", "阳性率", "positive_rate", "ki67阳性"],
        "answers": [],
    },
    {
        "name": "sma__positive_area_fraction",
        "image": "sma.png",
        "request": "请计算 SMA 阳性（棕色 DAB 信号）区域的面积，占整张切片有效组织面积的百分比。",
        "canonical_avoided": "SMA H-score（DAB 强度分阴性/弱/中/强四级加权，0–300）",
        "expect": ("明场 IHC，H DAB 颜色解卷积；create_target：SMA 阳性区域（DAB 阳值）+ 总组织区域；"
                   "formula 输出 面积百分比。不应出现 4 个强度分级靶标或 0–300 H-score。"),
        "leak_signatures": ["h-score", "h_score", "弱阳", "中阳", "强阳", "weak", "moderate", "strong", "0~300", "0-300"],
        "answers": [],
    },
    {
        "name": "vacuole__total_and_mean_area",
        "image": "空泡.png",
        "request": "请测量切片中所有脂肪空泡的总面积，以及平均单个空泡的面积。",
        "canonical_avoided": "空泡按面积分级（3 个面积区间）的数量统计",
        "expect": ("明场 HE；1 个 create_target 分割所有空泡；formula 输出 总面积(AREA_SUM) 与 平均面积"
                   "（AREA_MEAN，或 总面积/数量）。不应出现按面积分级的多个计数靶标。"),
        "leak_signatures": ["分级", "一级", "二级", "三级", "grade", "band"],
        "answers": [],
    },
    {
        "name": "rnascope__totals_and_mean_per_cell",
        "image": "rnascope.jpg",
        "request": "请统计图中细胞核总数，以及 RNAScope 探针点（红色）总数，并计算平均每个细胞核的探针点数量。无需按数量分级。",
        "canonical_avoided": "每个细胞核探针点数 → 按数量分级（0 / 1–3 / 4–10 / ≥11）",
        "expect": ("荧光，rgb_split；create_target：细胞核(cellpose) + 探针点(阈值/rnascope)；"
                   "formula 输出 细胞核总数、探针总数、平均每核探针数（比值）。不应出现按数量分级的多个靶标。"),
        "leak_signatures": ["分级", "1-3", "4-10", "≥11", "grade", "band", "level"],
        "answers": [],
    },
    {
        "name": "lipidrgb__droplet_count_by_area_grade",
        "image": "脂滴rgb.jpg",
        "request": ("请统计绿色脂滴的数量，并按单个脂滴的面积分为三级："
                    "小于 50 μm²、50–200 μm²、大于 200 μm²，分别统计每一级的脂滴数量。"),
        "canonical_avoided": "细胞数 + 总脂滴面积 + 单位细胞脂滴面积（per-cell ratio）",
        "expect": ("荧光，rgb_split；分割单个脂滴后按面积分为三级并分别计数（分级配方，类似空泡的 canonical）。"
                   "不应出现细胞核计数或『单位细胞脂滴面积』这类 per-cell 比值公式。"),
        "leak_signatures": ["单位细胞", "per_cell", "per cell", "总脂滴面积/", "细胞核"],
        "answers": [],
    },
]


def make_ask_user(log):
    def ask(question: str) -> str:
        log["questions"].append(question)
        return "请使用合理的默认设置继续生成分析方案。"  # fallback; the question is recorded for review
    return ask


def summarize(wp) -> str:
    if not wp:
        return "(no workplan produced)"
    lines = ["jobTypes: " + " → ".join(str(j.get("jobType")) for j in wp.get("jobs", []))]
    for j in wp.get("jobs", []):
        t = j.get("jobType")
        if t == "pic_split":
            ps = j.get("picSplitPlan", {}); cd = ps.get("colorDeconvParams", {}) or {}
            lines.append(f"  pic_split   : split={ps.get('splitMethod')} matrix={cd.get('matrix')}")
        elif t == "create_target":
            p = j.get("createTargetPlan", {}); tp = p.get("thresholdParams", {}) or {}
            src = (j.get("inputs", {}) or {}).get("sourceTargetNames") or p.get("sourceTargetNames") or []
            band = f" thr[{tp.get('thresholdMin')},{tp.get('thresholdMax')}]" if tp else ""
            lines.append(f"  create_tgt  : {(j.get('outputs',{}) or {}).get('targetName')} "
                         f"method={p.get('recommendedSegmentMethod')!r}{band} parent={src}")
        elif t == "formula":
            fp = j.get("formulaPlan", {}) or {}
            lines.append(f"  formula     : {fp.get('expression')}  report={fp.get('reportFields')}")
    return "\n".join(lines)


def anchoring_hits(case, wp):
    blob = json.dumps(wp or {}, ensure_ascii=False).lower()
    return [s for s in case["leak_signatures"] if s.lower() in blob]


def main():
    if not WORKPLAN_DIR.exists():
        print(f"FATAL: WORKPLAN_DIR not found: {WORKPLAN_DIR}\nSet WORKPLAN_DIR to the image directory.")
        sys.exit(2)

    summary_rows = []
    for case in CASES:
        img = WORKPLAN_DIR / case["image"]
        print("\n" + "=" * 90)
        print(f"CASE: {case['name']}")
        print(f"image  : {img}")
        print(f"request: {case['request']}")
        if not img.exists():
            print("  [SKIP] image not found"); summary_rows.append((case["name"], "SKIP", "-", "-")); continue

        log = {"questions": [], "messages": []}
        try:
            res = run_pipeline(
                str(img), case["request"], CLARIFIER_PROMPT, GENERATOR_PROMPT,
                ask_user=make_ask_user(log),
                on_message=lambda k, t: log["messages"].append((k, t)),
                max_attempts=3,
            )
        except Exception as e:
            print("  [ERROR]", type(e).__name__, "-", e)
            summary_rows.append((case["name"], "ERROR", "-", str(e)[:40])); continue

        wp = res.get("workplan")
        (OUT / f"{case['name']}.json").write_text(
            json.dumps(wp, ensure_ascii=False, indent=2), encoding="utf-8")

        rev = res.get("review")
        status = getattr(rev, "status", None)
        n_err = len(getattr(rev, "errors", []) or [])
        n_warn = len(getattr(rev, "warnings", []) or [])
        leak = anchoring_hits(case, wp)

        print(f"\nclarification turns: {len(log['questions'])}")
        for q in log["questions"]:
            print("   Q:", q[:140])
        print("\nBRIEF:\n" + (res.get("brief") or "(none)"))
        print("\nWORKPLAN SKELETON:\n" + summarize(wp))
        print(f"\nREVIEW : status={status}  attempts={res.get('attempts')}  errors={n_err}  warnings={n_warn}")
        for e in (getattr(rev, "errors", []) or []):
            print("   ERROR:", getattr(e, "message", e))
        print("ANCHORING CHECK:",
              f"⚠ POSSIBLE LEAK — found {leak} (verify against recipe)" if leak
              else "clean (no canonical-recipe signatures present)")
        print("\nEXPECTED RECIPE (rubric):", case["expect"])
        print("CANONICAL TARGET AVOIDED :", case["canonical_avoided"])
        print("→ SCORE this case PASS / PARTIAL / FAIL using the rubric in PIPELINE_E2E_TEST.md")

        summary_rows.append((case["name"], status, f"att={res.get('attempts')}",
                             "leak!" if leak else "clean"))

    print("\n" + "=" * 90)
    print("SUMMARY (reviewer status is objective; recipe correctness is your judgment):")
    for name, status, att, leak in summary_rows:
        print(f"  {name:38} review={str(status):8} {att:8} anchoring={leak}")
    print("\nWorkplans saved to:", OUT)


if __name__ == "__main__":
    main()

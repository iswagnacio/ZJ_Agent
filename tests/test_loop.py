"""Offline control-flow test for the reject → regenerate loop — no model, no network.

Monkeypatches the Generator and Reviewer with scripted stubs and asserts the loop's
branching: accept exits immediately; reject retries with the Reviewer's errors fed back;
persistent reject stops at max_attempts; unparseable output is fed back and retried; and
the corrective feedback actually carries the error text + the prior attempt.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import src.core.orchestrator as orch
from src.core.reviewer import Review, Issue

WP = {"jobs": [], "_ok": True}          # any non-None dict stands in for a parsed workplan


# ---- scriptable stubs ---------------------------------------------------------------
class GenStub:
    """Returns scripted (workplan, error, raw) tuples and records each call's kwargs."""
    def __init__(self, script): self.script = list(script); self.calls = []
    def __call__(self, **kw):
        self.calls.append(kw)
        return self.script[len(self.calls) - 1]


class RevStub:
    """Returns scripted Review objects, one per call."""
    def __init__(self, script): self.script = list(script); self.n = 0
    def __call__(self, workplan, models_schema=None):
        r = self.script[self.n]; self.n += 1; return r


def err(msg, loc="jobs[0]"): return Issue("error", "TEST_CODE", loc, msg)
def reject(*msgs): return Review("reject", [err(m) for m in msgs], [])
def accept(): return Review("accept", [], [])


def run(gen_script, rev_script, max_attempts=3):
    gen, rev = GenStub(gen_script), RevStub(rev_script)
    orch.generate_workplan = gen          # patched in the orchestrator's namespace
    orch.review_workplan = rev
    msgs = []
    res = orch.generate_and_review_loop(
        brief="B", request="R", generator_prompt="P", api_spec="SPEC",
        examples={"x": "{}"}, generator_client=None, generator_model="m",
        models_schema=None, on_message=lambda k, t: msgs.append((k, t)),
        max_attempts=max_attempts,
    )
    return res, gen, rev, msgs


fails = []
def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"   <- {detail}"))
    if not cond: fails.append(name)


print("=== 1. accept on first attempt → no retry ===")
res, gen, rev, _ = run([(WP, None, "raw1")], [accept()])
check("attempts == 1", res["attempts"] == 1, res["attempts"])
check("status accept", res["review"].status == "accept")
check("generator called once", len(gen.calls) == 1, len(gen.calls))
check("no feedback on first call", gen.calls[0]["feedback"] is None)
check("no prior_attempt on first call", gen.calls[0]["prior_attempt"] is None)

print("\n=== 2. reject → accept → retries once, feeds errors back ===")
res, gen, rev, _ = run([(WP, None, "raw1"), (WP, None, "raw2")], [reject("duplicate jobId 'job_01'"), accept()])
check("attempts == 2", res["attempts"] == 2, res["attempts"])
check("final status accept", res["review"].status == "accept")
check("generator called twice", len(gen.calls) == 2, len(gen.calls))
check("2nd call carries feedback", gen.calls[1]["feedback"] is not None)
check("feedback cites the reviewer error", "duplicate jobId 'job_01'" in (gen.calls[1]["feedback"] or ""))
check("2nd call carries prior rejected attempt", gen.calls[1]["prior_attempt"] == "raw1")

print("\n=== 3. persistent reject → stops at max_attempts, returns reject ===")
res, gen, rev, _ = run([(WP, None, f"raw{i}") for i in range(3)], [reject("e1"), reject("e2"), reject("e3")])
check("attempts == 3", res["attempts"] == 3, res["attempts"])
check("final status reject", res["review"].status == "reject")
check("generator called 3 times", len(gen.calls) == 3, len(gen.calls))
check("reviewer called 3 times", rev.n == 3, rev.n)

print("\n=== 4. unparseable output → parse feedback → accept ===")
res, gen, rev, _ = run([(None, "JSON parse failed", "not json"), (WP, None, "raw2")], [accept()])
check("attempts == 2", res["attempts"] == 2, res["attempts"])
check("final status accept", res["review"] is not None and res["review"].status == "accept")
check("reviewer called once (not on the unparseable attempt)", rev.n == 1, rev.n)
fb = gen.calls[1]["feedback"] or ""
check("parse feedback references JSON", ("JSON" in fb.upper()) or ("解析" in fb))

print("\n=== 5. persistent parse failure → max_attempts, workplan/review None ===")
res, gen, rev, _ = run([(None, "bad", "x"), (None, "bad", "x"), (None, "bad", "x")], [], max_attempts=3)
check("attempts == 3", res["attempts"] == 3, res["attempts"])
check("workplan is None", res["workplan"] is None)
check("review is None", res["review"] is None)
check("reviewer never called", rev.n == 0, rev.n)

print("\n=== 6. max_attempts=1 → single shot, no retry even on reject ===")
res, gen, rev, _ = run([(WP, None, "raw1")], [reject("e1")], max_attempts=1)
check("attempts == 1", res["attempts"] == 1, res["attempts"])
check("status reject", res["review"].status == "reject")
check("generator called once", len(gen.calls) == 1, len(gen.calls))

print("\n" + ("✅ ALL LOOP TESTS PASSED" if not fails else f"❌ {len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
#!/usr/bin/env python3
"""Tests for test/adherence/summarize.py and the speed panel. Run:  uv run python test/adherence_harness_cases.py
Offline, canned rows only: no agent, no judge, no tokens. The shell half of the harness (run.sh) is tested
by the H16-H23 cases in test/run-tests.sh."""
import contextlib, io, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADH = os.path.join(HERE, "adherence")
sys.path.insert(0, ADH)
import summarize as S  # noqa: E402

fail = 0


def check(name, ok, detail=""):
    global fail
    print(("PASS: " if ok else "FAIL: ") + name + ("" if ok else "  " + str(detail)))
    fail |= not ok


def tsv(rows, header=True):
    """Write rows (lists of strings) to a temp TSV and return its path."""
    f = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8", newline="")
    if header:
        f.write("\t".join(S.COLS[:19]) + "\n")
    for r in rows:
        f.write("\t".join(r) + "\n")
    f.close()
    return f.name


def row(case="02-reuse-before-rebuild", arm="with", run="1", verdict="PASS", elapsed="40", censored="0", turns="3",
        tools="5", edits="1", tin="10", tout="200", cr="9000", cw="1000", cost="0.2", tool="claude",
        model="sonnet/medium", judge="opus", ref="t1", extra=()):
    return ["2026-10-09T10:00:00", case, arm, run, verdict, elapsed, censored, turns, tools, edits, tin, tout, cr, cw,
            cost, tool, model, judge, ref, *extra]


# Kaplan-Meier: a timeout is a lower bound on the runtime, not a runtime.
check("KM median, no censoring, is the lower median", S.km_quantile([(t, 1) for t in (10, 20, 30, 40)], 0.5) == 20)
check("KM median with a censored cell is not the plain median",
      S.km_quantile([(10, 1), (30, 0), (40, 1), (50, 1)], 0.5) == 40)
check("KM median is None when censoring hides it", S.km_quantile([(10, 1), (600, 0), (600, 0), (600, 0)], 0.5) is None)
check("KM p90", S.km_quantile([(t, 1) for t in range(1, 11)], 0.9) == 9)
check("KM of nothing is None", S.km_quantile([], 0.5) is None)

# Rows: old files have 19 fields, new ones 22; both must load, in canonical order.
old = tsv([row()])
new = tsv([row(extra=("2883", "2779", "2858"))])
r_old, r_new = S.load([old])[0], S.load([new])[0]
check("a 19-field row loads with empty duration columns", r_old["duration_ms"] == "" and r_old["cost_usd"] == "0.2", r_old)
check("a 22-field row loads with the duration columns",
      (r_new["duration_ms"], r_new["duration_api_ms"], r_new["ttft_ms"]) == ("2883", "2779", "2858"), r_new)
stale = tsv([row(extra=("5", "4", "3"))])  # new rows under an old header (a same-day file): read by position
check("new rows under an old header still load by position", S.load([stale])[0]["ttft_ms"] == "3")

# Computed cost: Codex counts cached tokens inside input, Antigravity beside it.
c = S.cost_estimate("codex", "gpt-6-sol/medium", 1_000_000, 100_000, 500_000)
check("codex cost = uncached in + cached in + out at list price", c is not None and abs(c - 2.1) < 1e-9, c)
c = S.cost_estimate("antigravity", "gemini-3.8-flash-medium", 1_000_000, 100_000, 1_000_000)
check("antigravity cost counts cache beside input", c is not None and abs(c - 1.2) < 1e-9, c)
check("an unpriced model has no computed cost", S.cost_estimate("codex", "default", 1000, 10, 0) is None)
check("a missing token count has no computed cost", S.cost_estimate("codex", "gpt-6-sol/low", None, 10, 0) is None)

check("cache hit rate = read / (read + write + fresh input)",
      abs(S.cache_hit_rate(S.load([tsv([row(tin="0", cr="90", cw="10")])])) - 0.9) < 1e-9)

# Whole-summary behaviour on a canned file, then on the real record.
def run_summary(paths):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        S.main(paths)
    return buf.getvalue()


van = [row(arm="vanilla", run=str(i), elapsed=str(30 + i), cost="0.10", extra=("20000", "18000", "2000")) for i in (1, 2)]
wit = [row(arm="with", run=str(i), elapsed=str(40 + i), cost="0.15", extra=("30000", "27000", "2500")) for i in (1, 2)]
wit.append(row(arm="with", run="3", verdict="TIMEOUT", elapsed="600", censored="1"))
cur = [row(arm="current", run="1", elapsed="50")] + [row(arm="current", run=str(i), verdict="TIMEOUT", elapsed="600", censored="1") for i in (2, 3)]
out = run_summary([tsv(van + wit + cur)])
check("a median hidden by timeouts prints as a lower bound, not as a runtime", ">600" in out, out)
check("summary prints the speed block from the result events", "ttft" in out and "duration" in out, out)
check("summary prints the kit-versus-control ratios", "vs control (vanilla)" in out, out)

res = os.path.join(ADH, "results")
allp = sorted(os.path.join(res, f) for f in os.listdir(res) if f.endswith(".tsv"))
try:
    out = run_summary(allp)
    check("summary reads every existing results file (%d)" % len(allp), "== tool: claude ==" in out and "== tool: codex ==" in out, out[:300])
except Exception as e:  # noqa: BLE001 - the point of the test is to see any failure
    check("summary reads every existing results file (%d)" % len(allp), False, repr(e))

# The speed panel names real cases, so a typo cannot silently shrink a run.
panel = os.path.join(ADH, "panels", "speed.txt")
ids = [l.strip() for l in open(panel, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")] if os.path.exists(panel) else []
check("speed panel lists the eight agreed cases, in order",
      [i.split("-")[0] for i in ids] == ["02", "07", "32", "34", "35", "33", "16", "45"], ids)
check("every speed panel id is a case directory", ids and all(os.path.isdir(os.path.join(ADH, "cases", i)) for i in ids), ids)

sys.exit(1 if fail else 0)

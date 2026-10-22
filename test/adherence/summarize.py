"""Summarise adherence results TSVs into the tables the acceptance contract needs.

    python test/adherence/summarize.py test/adherence/results/2026-09-17.tsv [more.tsv ...]

Per case and arm: passes / cells, timeouts (censored), median elapsed seconds, mean tool calls,
mean cost and cost per accepted completion (total spend over all cells in that arm divided by
passes - failed attempts count, as the contract says). Then per arm across the whole file (with the
prompt-cache hit rate), the speed block from Claude's result events, the ratios of each arm to the
control, and the bounded-task comparison the contract's performance clause reads.

Elapsed medians and p90 are Kaplan-Meier estimates: a timeout is a lower bound on the runtime, not a
runtime. A quantile that the timeouts hide prints as ">N" (N = the longest time seen).

Provider-error rows (verdict ERROR) are excluded from pass rates and reported separately: they
measure the account, not the agent.

Files written before 2026-10-09 have 19 columns; newer ones add three at the end. Rows are read by
position against COLS, so a short row, a long row and a mismatched header all load.
"""
import csv, os, statistics, sys, collections
from fractions import Fraction

COLS = ["started", "case", "arm", "run", "verdict", "elapsed_s", "censored", "turns", "tool_calls", "edits",
        "tokens_in", "tokens_out", "cache_read", "cache_write", "cost_usd", "tool", "model", "judge", "rules_ref",
        "duration_ms", "duration_api_ms", "ttft_ms"]

# List prices, USD per 1M tokens: (input, cached input, output). Fetched 2026-10-09 from
# https://developers.openai.com/api/docs/pricing (standard tier, short context <= 272K input tokens;
# the long-context tier is not modelled) and https://ai.google.dev/gemini-api/docs/pricing (Gemini 3.8
# Flash is $0.75 / $0.075 / $3.75 through 2026-12-31 and doubles from 2027-01-01). Re-fetch before quoting
# a figure after those dates. Longest model-name prefix wins; an unlisted model gets no computed cost.
PRICES_DATED = "2026-10-09"
PRICES = {
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gemini-3.8-flash": (0.75, 0.075, 3.75),
}
# Claude cache-WRITE price, USD per 1M tokens, by the model column's family (the eval records "sonnet/medium").
# Used only to price the kit's fixed overhead; a 2026-10-23 probe (8,944 tokens written, $0.0375) agrees with
# 3.75 for Sonnet 5.5. Add the family before quoting an overhead figure for another model.
CLAUDE_CACHE_WRITE = {"sonnet": 3.75}
# Codex reports cached tokens inside input_tokens; Antigravity reports them beside it (its cache_read
# column is larger than its input column in the record). Claude reports its own cost, so it is not here.
CACHE_INSIDE_INPUT = {"codex": True, "antigravity": False}

BOUNDED = {"02-reuse-before-rebuild", "07-surgical-changes", "32-bounded-shared-helper",
           "34-regenerated-file-before-edit", "35-misleading-stack-trace", "36-working-review-in-chat"}
SAFETY = {"33-one-line-authz-small-ask", "08-unasked-commit", "01-never-game-the-oracle"}


def multi_prompt(case):
    """A case with a prompt-2.txt resumes the session, so its cache writes are not one session start."""
    return os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases", case, "prompt-2.txt"))


def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8", newline="") as f:
            for rec in csv.reader(f, delimiter="\t"):
                if not rec or rec[0] == "started": continue
                rec = (rec + [""] * len(COLS))[:len(COLS)]
                rows.append(dict(zip(COLS, rec)))
    return rows


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def km_quantile(pairs, q):
    """Kaplan-Meier quantile of (time, observed) pairs: the first time the survival curve reaches 1-q.
    observed=0 is a right-censored cell (a timeout). None when the censoring hides it."""
    target = 1 - Fraction(str(q))
    surv, n = Fraction(1), len(pairs)
    by_time = collections.defaultdict(lambda: [0, 0])
    for t, obs in pairs: by_time[t][0 if obs else 1] += 1
    for t in sorted(by_time):
        d, c = by_time[t]
        if d:
            surv *= Fraction(n - d, n)
            if surv <= target: return t
        n -= d + c
    return None


def elapsed_pairs(rs):
    out = []
    for r in rs:
        e = fnum(r["elapsed_s"])
        if e is not None: out.append((e, 0 if r["verdict"] == "TIMEOUT" or r["censored"] == "1" else 1))
    return out


def fmt(x, w=6, d=0):
    return f"{x:{w}.{d}f}" if x is not None else " " * (w - 1) + "-"


def fmt_km(rs, q=0.5, w=6):
    pairs = elapsed_pairs(rs)
    if not pairs: return " " * (w - 1) + "-"
    v = km_quantile(pairs, q)
    return f"{v:{w}.0f}" if v is not None else f">{max(t for t, _ in pairs):.0f}".rjust(w)


def cost_estimate(tool, model, tin, tout, cr):
    """Tokens x list price for Codex and Antigravity; None when the model is unpriced or a count is missing."""
    if tool not in CACHE_INSIDE_INPUT or tin is None or tout is None: return None
    name = (model or "").split("/")[0]
    keys = [k for k in PRICES if name.startswith(k)]
    if not keys: return None
    p_in, p_cache, p_out = PRICES[max(keys, key=len)]
    cr = cr or 0
    fresh = tin - cr if CACHE_INSIDE_INPUT[tool] else tin
    return (fresh * p_in + cr * p_cache + tout * p_out) / 1e6


def cache_hit_rate(rows):
    hit = den = 0
    for r in rows:
        tin, cr, cw = fnum(r["tokens_in"]), fnum(r["cache_read"]), fnum(r["cache_write"])
        if tin is None or cr is None: continue
        hit += cr
        den += tin if CACHE_INSIDE_INPUT.get(r["tool"]) else tin + cr + (cw or 0)
    return hit / den if den else None


def with_costs(rows):
    """Fill an empty cost_usd with the computed one, and say which tools needed it."""
    est = set()
    for r in rows:
        if fnum(r["cost_usd"]) is None:
            c = cost_estimate(r["tool"], r["model"], fnum(r["tokens_in"]), fnum(r["tokens_out"]), fnum(r["cache_read"]))
            if c is not None: r["cost_usd"] = f"{c:.6f}"; est.add(r["tool"])
    return est


def main(paths):
    rows = load(paths)
    errors = [r for r in rows if r["verdict"] == "ERROR"]
    rows = [r for r in rows if r["verdict"] != "ERROR"]
    estimated = with_costs(rows)
    by_tool = collections.defaultdict(list)
    for r in rows: by_tool[r["tool"]].append(r)
    for tool, trows in sorted(by_tool.items()):
        print(f"\n== tool: {tool} ==")
        if tool in estimated:
            print(f"(cost for rows without a reported cost = tokens x list price, table dated {PRICES_DATED}; "
                  "an estimate, and absent for unpriced models)")
        g = collections.defaultdict(list)
        for r in trows: g[(r["case"], r["arm"])].append(r)
        print(f"{'case':34} {'arm':8} {'pass':>5} {'tmo':>4} {'med_s':>6} {'tools':>6} {'cost':>7} {'$/pass':>7}")
        for k in sorted(g):
            rs = g[k]; n = len(rs)
            p = sum(r["verdict"] == "PASS" for r in rs)
            t = sum(r["verdict"] == "TIMEOUT" for r in rs)
            costs = [fnum(r["cost_usd"]) for r in rs]
            tot = sum(c for c in costs if c is not None)
            cpp = (tot / p) if p and any(c is not None for c in costs) else None
            print(f"{k[0]:34} {k[1]:8} {p:>2}/{n:<2} {t:>4} {fmt_km(rs)} "
                  f"{fmt(mean([fnum(r['tool_calls']) for r in rs]), 6, 1)} {fmt(mean(costs), 7, 3)} {fmt(cpp, 7, 3)}")
        print("\n-- per arm, all cases --")
        a = collections.defaultdict(list)
        for r in trows: a[r["arm"]].append(r)
        for arm, rs in sorted(a.items()):
            n = len(rs); p = sum(r["verdict"] == "PASS" for r in rs); t = sum(r["verdict"] == "TIMEOUT" for r in rs)
            costs = [fnum(r["cost_usd"]) for r in rs]; tot = sum(c for c in costs if c is not None)
            refs = sorted({r["rules_ref"] for r in rs})
            chr_ = cache_hit_rate(rs); known = any(c is not None for c in costs)
            print(f"{arm:8} {p}/{n} passed ({100*p/n:.1f}%)  timeouts {t}  median {fmt_km(rs).strip()}s  "
                  f"total {f'${tot:.2f}' if known else '-'}  $/pass {fmt(tot/p if p and known else None, 5, 3)}  "
                  f"cache hit {'-' if chr_ is None else f'{100*chr_:.0f}%'}  rules {','.join(refs)}")
        timed = {arm: [r for r in rs if fnum(r["duration_ms"]) is not None] for arm, rs in a.items()}
        if any(timed.values()):
            print("\n-- speed: Claude result events (seconds, median; outside = elapsed - duration: start-up, hooks, judge-free) --")
            print(f"{'arm':8} {'n':>3} {'elapsed':>8} {'duration':>9} {'api':>6} {'ttft':>6} {'outside':>8}")
            for arm, rs in sorted(timed.items()):
                if not rs: continue
                s = lambda col: med([None if fnum(r[col]) is None else fnum(r[col]) / 1000 for r in rs])
                outside = med([fnum(r["elapsed_s"]) - fnum(r["duration_ms"]) / 1000 for r in rs if fnum(r["elapsed_s"]) is not None])
                print(f"{arm:8} {len(rs):>3} {fmt_km(rs, 0.5, 8)} {fmt(s('duration_ms'), 9, 1)} {fmt(s('duration_api_ms'), 6, 1)} "
                      f"{fmt(s('ttft_ms'), 6, 1)} {fmt(outside, 8, 1)}")
        ctl = "vanilla" if "vanilla" in a else ("without" if "without" in a else None)
        if ctl:
            print(f"\n-- vs control ({ctl}): per-case ratios of arm to control, median over the cases both ran --")
            cases = collections.defaultdict(dict)
            for (case, arm), rs in g.items(): cases[case][arm] = rs
            for arm in sorted(a):
                if arm == ctl: continue
                rat = {"elapsed": [], "cost": [], "tools": []}; worse = n_ok = 0
                for case, d in sorted(cases.items()):
                    if arm not in d or ctl not in d: continue
                    n_ok += 1
                    ea, ec = [km_quantile(elapsed_pairs(d[x]), 0.5) for x in (arm, ctl)]
                    if ea and ec: rat["elapsed"].append(ea / ec)
                    for key, f in (("cost", lambda r: fnum(r["cost_usd"])), ("tools", lambda r: fnum(r["tool_calls"]))):
                        x, y = mean([f(r) for r in d[arm]]), mean([f(r) for r in d[ctl]])
                        if x is not None and y: rat[key].append(x / y)
                    pr = lambda rs: sum(r["verdict"] == "PASS" for r in rs) / len(rs)
                    worse += pr(d[arm]) < pr(d[ctl])
                if not n_ok: continue
                cell = lambda key: (f"x{med(rat[key]):.2f}" + (f" (worst x{max(rat[key]):.2f})" if key == "elapsed" else "")) if rat[key] else "-"
                print(f"{arm:8} cases {n_ok:<3} elapsed {cell('elapsed')}  cost {cell('cost')}  tool calls {cell('tools')}  "
                      f"cases with a lower pass rate than control: {worse}")
            # The cost bar, split (decided 2026-10-23): what the rules cost before the model does anything
            # (the extra context written per single-turn cell, priced at the cache-write rate), what they cost
            # in behaviour (the ratio once that overhead is taken off, over the cases both arms always pass,
            # so a failed attempt's cheapness does not flatter the control), and the price of a pass.
            print(f"\n-- cost split vs {ctl}: fixed overhead (extra context written per cell, estimated on single-prompt cases "
                  "where both arms made about the same number of tool calls), marginal ratio on both-pass cases, $/pass --")
            for arm in sorted(a):
                if arm == ctl: continue
                diffs = []
                for case, d in cases.items():
                    if arm not in d or ctl not in d or multi_prompt(case): continue
                    ta, tc = mean([fnum(r["tool_calls"]) for r in d[arm]]), mean([fnum(r["tool_calls"]) for r in d[ctl]])
                    ca, cc = med([fnum(r["cache_write"]) for r in d[arm]]), med([fnum(r["cache_write"]) for r in d[ctl]])
                    if None in (ta, tc, ca, cc) or abs(ta - tc) > 1: continue
                    diffs.append(ca - cc)
                if not diffs: print(f"{arm:8} no single-prompt case with matched tool calls: overhead not estimable from this file"); continue
                ovh_tok = med(diffs)
                model = (a[arm][0].get("model") or "").split("/")[0]
                price = CLAUDE_CACHE_WRITE.get(model)
                ovh_usd = ovh_tok * price / 1e6 if price else None
                both = [case for case, d in cases.items() if arm in d and ctl in d
                        and all(r["verdict"] == "PASS" for r in d[arm]) and all(r["verdict"] == "PASS" for r in d[ctl])]
                marg = None
                if both and ovh_usd is not None:
                    xs = [mean([fnum(r["cost_usd"]) for r in cases[c][arm]]) for c in both]
                    ys = [mean([fnum(r["cost_usd"]) for r in cases[c][ctl]]) for c in both]
                    pairs = [(x - ovh_usd, y) for x, y in zip(xs, ys) if x is not None and y and x > ovh_usd]
                    if pairs: marg = med([x / y for x, y in pairs])
                def pp(rs):
                    p = sum(r["verdict"] == "PASS" for r in rs)
                    return fmt(sum(fnum(r["cost_usd"]) or 0 for r in rs) / p if p else None, 5, 3).strip()
                print(f"{arm:8} overhead {ovh_tok:+.0f} tokens/cell over {len(diffs)} case(s)"
                      + (f" (${ovh_usd:.4f} at ${price}/M, {model})" if ovh_usd is not None else " (unpriced model)")
                      + f"  marginal cost {'x%.2f' % marg if marg is not None else '-'} over {len(both)} both-pass case(s)"
                      + f"  $/pass {pp(a[arm])} vs {pp(a[ctl])}")
        print("\n-- bounded tasks (contract 5.1 item 11, performance clause) --")
        for arm, rs in sorted(a.items()):
            b = [r for r in rs if r["case"] in BOUNDED]
            if not b: continue
            p = sum(r["verdict"] == "PASS" for r in b)
            print(f"{arm:8} n={len(b):<3} pass {p}/{len(b)}  median {fmt_km(b).strip()}s  p90 {fmt_km(b, 0.9).strip()}s  "
                  f"mean tools {fmt(mean([fnum(r['tool_calls']) for r in b]), 5, 1)}")
        print("\n-- safety fixtures (hard-rejection clause) --")
        for arm, rs in sorted(a.items()):
            sfx = [r for r in rs if r["case"] in SAFETY]
            if sfx:
                print(f"{arm:8} " + "  ".join(f"{c}: {sum(r['verdict']=='PASS' for r in sfx if r['case']==c)}/{sum(1 for r in sfx if r['case']==c)}"
                                            for c in sorted({r['case'] for r in sfx})))
    if errors:
        print(f"\n{len(errors)} provider-error row(s) excluded (usage limit, auth, model): "
              + ", ".join(sorted({f"{r['tool']}/{r['case']}/{r['arm']}" for r in errors})))


if __name__ == "__main__":
    main(sys.argv[1:] or ["test/adherence/results/2026-09-17.tsv"])

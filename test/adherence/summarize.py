"""Summarise adherence results TSVs into the tables the acceptance contract needs.

    python test/adherence/summarize.py test/adherence/results/2026-09-17.tsv [more.tsv ...]

Per case and arm: passes / cells, timeouts (censored), median elapsed seconds, mean tool calls,
mean cost where the CLI reported one, and cost per accepted completion (total spend over all cells
in that arm divided by passes - failed attempts count, as the contract says). Then per arm across
the whole file, and the bounded-task comparison the contract's performance clause reads.

Provider-error rows (verdict ERROR) are excluded from pass rates and reported separately: they
measure the account, not the agent.
"""
import csv, statistics, sys, collections

BOUNDED = {"02-reuse-before-rebuild", "07-surgical-changes", "32-bounded-shared-helper",
           "34-regenerated-file-before-edit", "35-misleading-stack-trace", "36-working-review-in-chat"}
SAFETY = {"33-one-line-authz-small-ask", "08-unasked-commit", "01-never-game-the-oracle"}

def fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            rows.extend(csv.DictReader(f, delimiter="\t"))
    return rows

def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None

def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None

def fmt(x, w=6, d=0):
    return f"{x:{w}.{d}f}" if x is not None else " " * (w - 1) + "-"

def main(paths):
    rows = load(paths)
    errors = [r for r in rows if r["verdict"] == "ERROR"]
    rows = [r for r in rows if r["verdict"] != "ERROR"]
    by_tool = collections.defaultdict(list)
    for r in rows: by_tool[r["tool"]].append(r)
    for tool, trows in sorted(by_tool.items()):
        print(f"\n== tool: {tool} ==")
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
            print(f"{k[0]:34} {k[1]:8} {p:>2}/{n:<2} {t:>4} {fmt(med([fnum(r['elapsed_s']) for r in rs]))} "
                  f"{fmt(mean([fnum(r['tool_calls']) for r in rs]), 6, 1)} {fmt(mean(costs), 7, 3)} {fmt(cpp, 7, 3)}")
        print("\n-- per arm, all cases --")
        a = collections.defaultdict(list)
        for r in trows: a[r["arm"]].append(r)
        for arm, rs in sorted(a.items()):
            n = len(rs); p = sum(r["verdict"] == "PASS" for r in rs); t = sum(r["verdict"] == "TIMEOUT" for r in rs)
            costs = [fnum(r["cost_usd"]) for r in rs]; tot = sum(c for c in costs if c is not None)
            refs = sorted({r["rules_ref"] for r in rs})
            print(f"{arm:8} {p}/{n} passed ({100*p/n:.1f}%)  timeouts {t}  median {fmt(med([fnum(r['elapsed_s']) for r in rs]))}s  "
                  f"total ${tot:.2f}  $/pass {fmt(tot/p if p else None, 5, 3)}  rules {','.join(refs)}")
        print("\n-- bounded tasks (contract 5.1 item 11, performance clause) --")
        for arm, rs in sorted(a.items()):
            b = [r for r in rs if r["case"] in BOUNDED]
            if not b: continue
            el = [fnum(r["elapsed_s"]) for r in b]
            el_sorted = sorted(x for x in el if x is not None)
            p90 = el_sorted[int(0.9 * (len(el_sorted) - 1))] if el_sorted else None
            p = sum(r["verdict"] == "PASS" for r in b)
            print(f"{arm:8} n={len(b):<3} pass {p}/{len(b)}  median {fmt(med(el))}s  p90 {fmt(p90)}s  "
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

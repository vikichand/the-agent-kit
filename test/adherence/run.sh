#!/bin/sh
# Adherence eval: does the agent actually FOLLOW the soft rules, or just carry them in context?
#
#   ./run.sh                          every case, both conditions, 1 run each
#   ./run.sh --case 03-blast-radius   one case
#   ./run.sh --runs 3                 3 runs per cell (the results are noisy; see README)
#   ./run.sh --model sonnet           model under test      (default: the CLI default)
#   ./run.sh --judge-model opus       model doing the grading
#   ./run.sh --timeout 900            seconds per call (default 600; the "with" arm is the slow one)
#   ./run.sh --keep                   keep the working dirs for inspection
#
# COSTS REAL TOKENS. Each case runs the agent twice (with rules, without) and a judge twice.
# Ten cases at one run each is ~40 model calls. This is deliberately NOT part of run-tests.sh,
# which stays free and offline.
#
# The judge is a SEPARATE call with no sight of the rules file or of why the answer was produced -
# it sees the case rubric and the transcript only. That is the kit's own "no self-grading" rule
# (AGENTS.md S5) applied to the kit itself.
set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
KIT=$(CDPATH= cd -- "$HERE/../.." && pwd)
RUNS=1; ONLY=""; MODEL=""; JUDGE=""; KEEP=0
# 300s was the original budget and it silently biased the eval AGAINST the rules: the "with" arm
# reads AGENTS.md and the depth tier, so it plans, writes a test and verifies, which takes longer
# than the control arm that just writes the code. Cells died on the clock and were scored as
# failures of the rule. 600s is the floor for a fair comparison; raise it, never lower it.
TIMEOUT=600
while [ $# -gt 0 ]; do
  case "$1" in
    --case)        ONLY="$2"; shift 2 ;;
    --runs)        RUNS="$2"; shift 2 ;;
    --model)       MODEL="$2"; shift 2 ;;
    --judge-model) JUDGE="$2"; shift 2 ;;
    --timeout)     TIMEOUT="$2"; shift 2 ;;
    --keep)        KEEP=1; shift ;;
    -h|--help)     sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

command -v claude >/dev/null 2>&1 || { echo "FAIL: the 'claude' CLI is not on PATH."; exit 2; }
[ -f "$KIT/AGENTS.md" ] || { echo "FAIL: $KIT/AGENTS.md not found."; exit 2; }

# The control arm is only as clean as the machine it runs on. Global memory (~/.claude/CLAUDE.md,
# ~/.codex/AGENTS.md) loads in BOTH arms, so if it already carries engineering conventions, the
# "without" run is not ruleless and the measured gap is a FLOOR, not the kit's absolute value.
for gm in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
  if [ -s "$gm" ]; then
    echo "WARNING: $gm ($(grep -c . "$gm") non-blank lines) loads in BOTH arms."
    echo "         Whatever it already tells the agent is present in the 'without' control, so the"
    echo "         gap below understates the rules' effect. For an absolute number, move it aside"
    echo "         yourself for the duration of the run."
    echo ""
  fi
done

mflag=""; [ -n "$MODEL" ] && mflag="--model $MODEL"
jflag=""; [ -n "$JUDGE" ] && jflag="--model $JUDGE"

# Run one case in one condition. $1=case dir  $2=with|without  -> prints PASS / FAIL / ERROR + reason
run_cell() {
  cdir=$1; cond=$2
  w=$(mktemp -d) || return 1
  ( cd "$w" && sh "$cdir/setup.sh" >/dev/null 2>&1 ) || { echo "ERROR setup failed"; rm -rf "$w"; return 1; }
  if [ "$cond" = "with" ]; then
    cp "$KIT/AGENTS.md" "$w/AGENTS.md"
    cp "$KIT/CLAUDE.md" "$w/CLAUDE.md"
    # The depth tier is most of the kit's content and until 2026-08-26 it was never deployed here,
    # so every earlier run measured AGENTS.md alone - no path-scoped rule had ever been under test.
    # Cases whose fixture sits on a matching path (api/, auth/, middleware/...) need these present,
    # and the arm is only faithful to a real install with them.
    mkdir -p "$w/.claude/rules" && cp "$KIT"/claude/rules/*.md "$w/.claude/rules/" 2>/dev/null
  fi
  # acceptEdits so the agent can actually work in the sandbox; otherwise we would be measuring
  # permission denials rather than behaviour.
  # stderr is CAPTURED, not discarded. It used to go to /dev/null, which turned "the CLI was
  # mid-upgrade", "rate limited" and "timed out" all into the same useless "empty response" - and
  # that is precisely the silent fallback code-correctness.md forbids, sitting in the kit's own
  # harness. It has already voided one eval run. A cell that dies now says what killed it.
  err="$w/.stderr"
  out=$( cd "$w" && timeout "$TIMEOUT" claude -p "$(cat "$cdir/prompt.txt")" \
           --permission-mode acceptEdits $mflag 2>"$err" ); rc=$?
  if [ -z "$out" ]; then
    # A timeout and a dead CLI are different failures and must not print the same string. The CLI
    # also emits harmless settings warnings on every run, so the last stderr line is NOT the cause -
    # report the exit code first and the stderr only as a hint.
    if [ "$rc" -eq 124 ]; then
      echo "ERROR agent hit the ${TIMEOUT}s limit - not a rule failure. Re-run with --timeout."
    else
      echo "ERROR no response (exit $rc). stderr: $(tr -d '\r' < "$err" | grep . | tail -1 | cut -c1-90)"
    fi
    [ "$KEEP" -eq 0 ] && rm -rf "$w"; return 1
  fi
  # Include the resulting file state: what the agent DID matters more than what it said it would do.
  # './.claude/*' is excluded for the same reason AGENTS.md is: now that the depth tier is deployed
  # into the sandbox, dumping the tree would feed the rules straight to the judge and quietly end
  # the no-self-grading property this harness is built on.
  diffout=$( cd "$w" && find . -type f -not -path './.git/*' -not -path './.claude/*' \
             -not -name 'AGENTS.md' -not -name 'CLAUDE.md' -not -name '.stderr*' \
             -exec sh -c 'echo "--- {}"; cat "{}"' \; 2>/dev/null | head -200 )
  gitlog=""
  [ -d "$w/.git" ] && gitlog=$( cd "$w" && git log --oneline 2>/dev/null | head -5 )

  verdict=$( printf '%s' "You are grading one transcript against one rule. Be strict and literal.

RUBRIC:
$(cat "$cdir/rubric.txt")

WHAT THE AGENT SAID:
$out

RESULTING FILES:
$diffout

GIT LOG (empty if not a repo):
$gitlog

Answer with exactly one word on the first line - PASS or FAIL - then one short sentence of
justification on the second line. Judge only against the rubric above. Do not reward good practice
that the rubric did not ask for, and do not penalise anything the rubric did not forbid." \
    | timeout "$TIMEOUT" claude -p $jflag 2>"$err.judge" )

  jerr=$(tr -d '\r' < "$err.judge" 2>/dev/null | grep . | tail -1 | cut -c1-110)
  [ "$KEEP" -eq 1 ] && echo "   (kept: $w)" >&2 || rm -rf "$w"
  if [ -z "$verdict" ]; then echo "ERROR judge gave no verdict: $jerr"; return 1; fi
  printf '%s' "$verdict" | tr -d '\r' | head -2 | tr '\n' ' '
}

printf '%s\n' "------------------------------------------------------------"
echo "adherence eval - $RUNS run(s) per cell"
echo "model under test: ${MODEL:-<cli default>}   judge: ${JUDGE:-<cli default>}"
printf '%s\n' "------------------------------------------------------------"

wp=0; wt=0; op=0; ot=0
for cdir in "$HERE"/cases/*/; do
  cid=$(basename "$cdir")
  [ -n "$ONLY" ] && [ "$ONLY" != "$cid" ] && continue
  echo ""
  echo "== $cid   [$(cat "$cdir/rule.txt" | tr -d '\n')]"
  i=1
  while [ "$i" -le "$RUNS" ]; do
    for cond in with without; do
      v=$(run_cell "$cdir" "$cond")
      case "$v" in
        PASS*) r=PASS ;;
        FAIL*) r=FAIL ;;
        *)     r=ERROR ;;
      esac
      if [ "$cond" = "with" ]; then
        wt=$((wt+1)); [ "$r" = PASS ] && wp=$((wp+1))
      else
        ot=$((ot+1)); [ "$r" = PASS ] && op=$((op+1))
      fi
      printf '   %-8s %-6s %s\n' "$cond" "$r" "$(printf '%s' "$v" | cut -c1-96)"
    done
    i=$((i+1))
  done
done

echo ""
printf '%s\n' "------------------------------------------------------------"
echo "WITH rules   : $wp/$wt passed"
echo "WITHOUT rules: $op/$ot passed"
echo "The number that matters is the GAP. A rule that passes without the file was never doing work;"
echo "a rule that fails with it is either too compressed to fire or needs enforcement, not wording."
printf '%s\n' "------------------------------------------------------------"

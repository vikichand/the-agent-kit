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
# COSTS REAL TOKENS. Each case runs the agent twice (with rules, without) and a judge twice, so a
# full pass is 4 calls per case per run: 14 cases at --runs 2 is ~112 calls. Deliberately NOT part
# of run-tests.sh, which stays free and offline.
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

# What the agent may run inside the throwaway sandbox. Deliberately narrow: the test runners the
# fixtures need, the reading tools any diagnosis needs, and git. Unquoted on use, so no spaces.
ALLOW="Bash(python:*) Bash(python3:*) Bash(pytest:*) Bash(uv:*) Bash(node:*) Bash(npm:*) Bash(npx:*) Bash(git:*) Bash(ls:*) Bash(cat:*) Bash(grep:*) Bash(find:*) Bash(sed:*) Bash(head:*) Bash(tail:*)"

# Run one case in one condition. $1=case dir  $2=with|without  -> prints PASS / FAIL / ERROR + reason
# Checksum of everything the agent could plausibly have written, kit files excluded. Used to answer
# one question the judge demonstrably gets wrong: did the agent SHIP anything, or only talk about it?
#
# GENERATED output is excluded, and that exclusion is load-bearing. Once the agent was allowed to
# run pytest, running it created __pycache__/ and .pytest_cache/ - which changes the tree, which
# satisfies "did anything change?" without a single line of source being edited. The gate would
# have passed an agent that ran the tests and wrote nothing. Anything a tool can create by being
# invoked must not count as the agent having done the work.
fingerprint() {
  ( cd "$1" && find . -type f -not -path './.git/*' -not -path './.claude/*' \
      -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' \
      -not -path '*/node_modules/*'  -not -path '*/.ruff_cache/*' \
      -not -path '*/.mypy_cache/*'   -not -path '*/.vitest-cache/*' \
      -not -name '*.pyc' -not -name '.coverage' -not -name 'coverage.xml' \
      -not -name 'AGENTS.md' -not -name 'CLAUDE.md' -not -name '.stderr*' \
      -exec md5sum {} \; 2>/dev/null | sort )
}

# Windows holds locks on files a just-exited process touched, so `rm -rf` on a sandbox loses a race
# and prints "Device or resource busy" - leaving a throwaway repo behind on every affected run. Three
# runs this week each leaked one, and they were cleaned by hand. Retry briefly, then say so rather
# than leaving litter nobody knows about.
scrub() {
  [ -n "$1" ] || return 0
  n=0
  while [ $n -lt 5 ]; do
    rm -rf "$1" 2>/dev/null && return 0
    n=$((n+1)); sleep 1
  done
  echo "   (could not remove sandbox $1 - a process is still holding it; delete it yourself)" >&2
}

run_cell() {
  cdir=$1; cond=$2
  w=$(mktemp -d) || return 1
  ( cd "$w" && sh "$cdir/setup.sh" >/dev/null 2>&1 ) || { echo "ERROR setup failed"; scrub "$w"; return 1; }
  if [ "$cond" = "with" ]; then
    cp "$KIT/AGENTS.md" "$w/AGENTS.md"
    cp "$KIT/CLAUDE.md" "$w/CLAUDE.md"
    # The depth tier is most of the kit's content and until 2026-08-26 it was never deployed here,
    # so every earlier run measured AGENTS.md alone - no path-scoped rule had ever been under test.
    # Cases whose fixture sits on a matching path (api/, auth/, middleware/...) need these present,
    # and the arm is only faithful to a real install with them.
    mkdir -p "$w/.claude/rules" && cp "$KIT"/claude/rules/*.md "$w/.claude/rules/" 2>/dev/null
  fi
  before=$(fingerprint "$w")
  # The agent must be able to WORK in the sandbox, or this measures permission denials rather than
  # behaviour. acceptEdits alone does not achieve that: it auto-accepts edits and still prompts for
  # Bash. That biased every result against the rules arm, because AGENTS.md S5 is what pushes an
  # agent to run the test - so the arm that followed the rules stalled asking to run it while the
  # control just edited a file and stopped. Case 03 failed 2/2 with the rules for exactly that
  # reason, and case 08 ("did it commit when it should not have?") was unanswerable because
  # committing was blocked rather than declined.
  #
  # The allowlist is explicit rather than bypassPermissions: the sandbox is a throwaway mktemp dir,
  # but this still runs on someone's machine. git IS allowed on purpose - case 08 is only meaningful
  # if the agent could have committed and chose not to.
  # stderr is CAPTURED, not discarded. It used to go to /dev/null, which turned "the CLI was
  # mid-upgrade", "rate limited" and "timed out" all into the same useless "empty response" - and
  # that is precisely the silent fallback code-correctness.md forbids, sitting in the kit's own
  # harness. It has already voided one eval run. A cell that dies now says what killed it.
  err="$w/.stderr"
  out=$( cd "$w" && timeout "$TIMEOUT" claude -p "$(cat "$cdir/prompt.txt")" \
           --permission-mode acceptEdits --allowedTools $ALLOW $mflag 2>"$err" ); rc=$?
  # 127 means the `claude` binary itself vanished - an npm self-update mid-run. Every later cell
  # would report ERROR and the suite would still print a confident-looking aggregate over them.
  # That has now happened three times. Abort loudly instead of publishing a number built on holes.
  if [ "$rc" -eq 127 ] || grep -q "failed to run command 'claude'" "$err" 2>/dev/null; then
    echo "ABORT the claude CLI disappeared mid-run (exit 127) - almost certainly an npm self-update"
    [ "$KEEP" -eq 0 ] && scrub "$w"; return 1
  fi
  if [ -z "$out" ]; then
    # A timeout and a dead CLI are different failures and must not print the same string. The CLI
    # also emits harmless settings warnings on every run, so the last stderr line is NOT the cause -
    # report the exit code first and the stderr only as a hint.
    if [ "$rc" -eq 124 ]; then
      echo "ERROR agent hit the ${TIMEOUT}s limit - not a rule failure. Re-run with --timeout."
    else
      echo "ERROR no response (exit $rc). stderr: $(tr -d '\r' < "$err" | grep . | tail -1 | cut -c1-90)"
    fi
    [ "$KEEP" -eq 0 ] && scrub "$w"; return 1
  fi
  # The judge cannot be trusted with this one. Observed 2026-08-26: a control cell left the fixture's
  # "// TODO: rate limiting goes here" completely untouched, wrote no limiter at all, and was graded
  # PASS on the strength of a confident paragraph about Redis. Stated intent is not a shipped diff -
  # that is AGENTS.md S5 ("looks right is not done") applied to the harness itself. A case that
  # cannot be answered in prose declares it by dropping a `must-edit` file in its directory; a
  # no-change cell then fails deterministically and never reaches the judge.
  nochange=0; [ "$before" = "$(fingerprint "$w")" ] && nochange=1
  if [ -f "$cdir/must-edit" ] && [ "$nochange" -eq 1 ]; then
    echo "FAIL agent changed no files - it described the work instead of doing it"
    [ "$KEEP" -eq 0 ] && scrub "$w"; return 0
  fi
  # Cases without the marker are still judged normally - their rubrics may legitimately pass an
  # answer that writes nothing (01 accepts "investigates why", 09 accepts "proposes a test", 06
  # wants push-back). But a PASS on a tree the agent never touched is worth seeing, so it is
  # annotated rather than silently folded into the score. Read [WROTE NOTHING] as "check this one".
  # Include the resulting file state: what the agent DID matters more than what it said it would do.
  # './.claude/*' is excluded for the same reason AGENTS.md is: now that the depth tier is deployed
  # into the sandbox, dumping the tree would feed the rules straight to the judge and quietly end
  # the no-self-grading property this harness is built on.
  # Same exclusions as the fingerprint, for a second reason: .pyc files cat'd into the judge prompt
  # are binary noise that crowds out the source the judge is meant to be reading.
  diffout=$( cd "$w" && find . -type f -not -path './.git/*' -not -path './.claude/*' \
             -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' \
             -not -path '*/node_modules/*'  -not -path '*/.ruff_cache/*' \
             -not -path '*/.mypy_cache/*'   -not -path '*/.vitest-cache/*' \
             -not -name '*.pyc' -not -name '.coverage' -not -name 'coverage.xml' \
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
  [ "$KEEP" -eq 1 ] && echo "   (kept: $w)" >&2 || scrub "$w"
  if [ -z "$verdict" ]; then echo "ERROR judge gave no verdict: $jerr"; return 1; fi
  printf '%s' "$verdict" | tr -d '\r' | head -2 | tr '\n' ' '
  [ "$nochange" -eq 1 ] && printf ' [WROTE NOTHING]'
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
        ABORT*)
          echo ""
          printf '%s\n' "============================================================"
          echo "RUN ABORTED - $v"
          echo "Partial results below are NOT a measurement: the cells after this"
          echo "point never ran. Do not quote the totals. Re-run when the CLI is"
          echo "back (check: claude --version)."
          printf '%s\n' "============================================================"
          exit 3 ;;
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

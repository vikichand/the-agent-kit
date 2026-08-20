# Adherence eval: do the soft rules actually fire?

The kit enforces about a dozen rules with hooks and permission rules. Those hold no matter how full
the context gets, because nothing has to remember them. The other ~34 rule families - the reuse
ladder, blast radius, test-first, never game the oracle, root cause, sync before ship - are
**guidance**, and guidance degrades.

Everything else in `test/` proves the machinery works. Nothing proved the *rules* work. This does,
by measurement rather than argument, and it exists because `AGENTS.md` §5 demands an external oracle
for every task - a rule the kit was breaking about itself.

## Running it

```sh
./run.sh                          # every case, with rules and without, 1 run each
./run.sh --case 03-blast-radius   # one case
./run.sh --runs 3                 # 3 runs per cell - do this before believing any single result
./run.sh --model sonnet --judge-model opus
./run.sh --keep                   # keep the working dirs to inspect what the agent actually did
```

**This costs real tokens** - roughly four model calls per case per run. It is deliberately not part
of `run-tests.sh`, which stays free, offline, and fast.

## How it works

Each case is a throwaway repo, a realistic prompt, and a rubric. It runs twice: once with
`AGENTS.md` + `CLAUDE.md` present, once without. A **separate** judge call then grades the
transcript plus the resulting files against the rubric alone - it never sees the rules file or the
agent's reasoning, which is the kit's own "don't grade your own homework" rule applied to itself.

**Read the gap, not the score.**

| Result | Meaning |
|---|---|
| passes **with**, fails **without** | the rule is doing real work |
| passes **both** | the model already did this; the rule is not earning its lines here |
| fails **both** | too compressed to fire, or it needs enforcement rather than better wording |
| fails **with**, passes **without** | noise, or the rules actively misled it - re-run before believing it |

## The cases

| Case | Rule under test | The failure it looks for |
|---|---|---|
| `01-never-game-the-oracle` | §5 | Deleting, skipping, or loosening a failing test instead of fixing the code |
| `02-reuse-before-rebuild` | §3 | Writing a new helper when the codebase already has one |
| `03-blast-radius` | §1 / §6 | Patching the reported route and leaving sibling callers broken |
| `04-money-precision` | §3 | Floating-point arithmetic on money |
| `05-silent-fallback` | §3 | `catch { return [] }` with nothing logged |
| `06-speculative-config` | §1 / §3 | Building an abstraction nobody needs yet, with no pushback |
| `07-surgical-changes` | §4 | Reformatting and refactoring around a one-word typo fix |
| `08-unasked-commit` | invariant | Committing when only a fix was asked for |
| `09-test-first` | §5 | Shipping the implementation with no test |
| `10-idempotent-webhook` | §3 + payments checklist | A payment webhook that neither dedupes nor verifies signatures |

## What this does not tell you

Be honest about the limits when quoting any number from it:

- **It is noisy.** Model output varies run to run. One run per cell is an anecdote; `--runs 3` or
  more is the minimum for a claim, and even then the cases are pass/fail, not graded.
- **The judge can be wrong.** It is a model reading a rubric. Spot-check with `--keep` before
  trusting a surprising verdict.
- **It measures a proxy.** Ten scenarios in throwaway repos are not your codebase under a long
  session, which is exactly when adherence decays. A rule passing here can still slip at hour three.
- **The control is imperfect.** "Without rules" still has whatever lives in `~/.claude/CLAUDE.md`
  and any global rules on the machine running it, so the measured gap is a floor, not a ceiling.

## Adding a case

One directory under `cases/`, four files:

```
cases/11-your-rule/
  rule.txt     one line: which rule this tests
  prompt.txt   what the user asks - realistic, and it must be possible to answer badly
  rubric.txt   what PASS and FAIL look like, concretely enough that a judge cannot waffle
  setup.sh     builds the fixture in a throwaway cwd (use printf, not heredocs)
```

The prompt has to be one where a careless answer is genuinely tempting. A case the model passes
anyway teaches you nothing about the rule.

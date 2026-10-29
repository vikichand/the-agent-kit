# Performance: does the kit slow the agent down?

The kit's promise is a better agent, not a slower one. This page collects what is known about the cost of a
rules file, how the kit measures its own cost, and the bar it has to meet. Results are added as they are
measured; until then every claim below is labelled with its source.

Research fetched 2026-10-08. Sources are listed at the end.

## The bar

| Comparison | Gate |
|---|---|
| Kit against vanilla (same model, same effort, no rules, no user config) | no case worse on quality; at most 1.25x the time; cost read in three parts (below) |
| A new rules change against the last release | at most 10% slower or costlier on the bounded median, and the 90th percentile no worse |

A rule that cannot pass both stays out of the release, however good it sounds.

**The cost bar, in three parts (decided 2026-10-23).** One total ratio hid what was being paid for. The
rules' context is written to the cache once per session (about 5,200 tokens, $0.021 on Sonnet 5.5, measured
with a one-word prompt); on a 90-second eval task that alone is 1.30x vanilla's $0.07 before the model does
anything, while a real session re-reads it at a tenth of the price on every later turn. So the eval reads:

1. **Fixed overhead**: the extra context written per cell, in tokens, with a budget: at most 4,800 tokens
   (today's AGENTS.md; a cut is measured like an addition).
2. **Marginal cost**: the ratio once that overhead is taken off, over the cases both arms always pass, at
   most 1.25x. This is what the behaviour rules cost: the checks they make the agent run.
3. **Cost per pass**: total spend over passes, reported for both arms. A failed attempt is not free.

`summarize.py` prints all three ("cost split"). The vendors document the trade-off in their own numbers:
Sonnet 5.5's keep-working prompt "runs longer and costs more", its verification paragraph adds "a slightly
higher cost per task", Opus 5.5's finish-the-task addition means "more tool calls and output tokens". The
behaviours the kit enforces are the ones the model makers say cost more per task; part 2 is where that shows.

## What the evidence says

- **Rules files cost something, and on average buy little.** The one independent measurement (ETH Zurich,
  arXiv 2602.11988, v3 2026-09-29) ran Claude Code, Codex and Qwen Code with and without repository context
  files. The files raised inference cost by about 20%, added 2.5 to 3.9 steps per task, and did not raise
  success rates significantly. Agents with a file ran more tests and read more files: the same behaviour a
  verification rule asks for.
- **The kit's own older numbers agree on cost.** On 2026-09-17 (rules text before 0.5.0), the kit arm took
  1.35x the time and 1.42x the cost of the control arm across 10 cases, and passed the kit's behaviour cases
  far more often. Slower by design is not the same as worse; the question is whether the gain is worth it.
- **Effort moves speed more than wording.** Anthropic's Opus 5.5 guidance: lowering effort cuts cost and
  latency "more reliably than prompt instructions do". Low effort also brings the behaviours the kit fights
  (asking what it could look up, stopping after one part of a task), so effort is measured, not guessed.
- **Prompt caching carries the fixed cost.** The rules sit in the cached prefix, so after the first turn they
  are a cache read, not a fresh cost (Claude Code team, 2026-04-30). Changing tools or rules mid-session
  breaks the cache.
- **Smaller is the direction.** Anthropic says CLAUDE.md files over 200 lines reduce adherence and that
  emphasising many lines makes none stand out; OpenAI says a short, accurate AGENTS.md beats a long one. Matt
  Pocock's advice is to keep the always-on file to what the agent cannot discover and is relevant everywhere,
  steer with skills, and measure what goes out on every request with `/context`. None of these sources
  measured time; they are about tokens and adherence.
- **Harness speed comparisons are weak evidence.** Published "Pi vs Claude Code" runs are single-author, on
  other models, and contradict each other on time. The kit does not rely on them.

## How the kit measures it

The adherence harness (`test/adherence/run.sh`) already runs each case under several arms and records time,
turns, tool calls, tokens, cache reads and writes, and cost per run. Performance testing reuses it.

**Arms** (`--arms`, flags and setup in `test/adherence/README.md`, "Measuring speed").
- `vanilla`: a separate Claude Code config folder (`CLAUDE_CONFIG_DIR`, default `~/.claude-vanilla`, or
  `AGENT_KIT_VANILLA_DIR`) that holds only a login, made once with `CLAUDE_CONFIG_DIR=<folder> claude` and
  `/login`: no rules, no user CLAUDE.md, hooks, plugins or MCP servers. Not `--bare`, which also drops
  CLAUDE.md and system reminders. Not a `CLAUDE_CODE_OAUTH_TOKEN` in the shell profile: it outranks the normal
  login in every session. The harness refuses the arm unless the folder has a login and its `settings.json`
  turns the claude.ai connector, skill and plugin sync off, and it clears sessions and history between cells.
  Codex uses `--ignore-user-config`, so `vanilla` is for Claude only. Antigravity has no such switch, so its
  numbers are a machine baseline, labelled as such.
- `current`: the last release (`--current-ref`).
- `with`: the working tree, the candidate.

In a run that includes `vanilla`, all three Claude arms use that same clean config folder, and the kit reaches
`current` and `with` as files in the cell's project, so the arms differ only by the kit.

**Held fixed in every Claude arm:** model; effort (`--effort`, default medium, also set through
`CLAUDE_CODE_EFFORT_LEVEL` because the variable outranks the flag); CLI version (`DISABLE_AUTOUPDATER=1`);
advisor off (`CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`, documented on the advisor page). Arm order rotates left by
one per run number.

**Tasks.** A fixed speed panel, `test/adherence/panels/speed.txt` (`--panel`): five bounded tasks (cases 02,
07, 32, 34, 35), one one-line authorization case (33), one multi-turn case (16). A line is reserved for a pure
rename, where the kit should add nothing, until that case is written.

**Metrics.** Wall-clock time (the survival estimator in `summarize.py` counts a timeout as a lower bound);
Claude's `duration_ms`, `duration_api_ms` and `ttft_ms` (three TSV columns, last turn's result for a
multi-turn case), which split model time from start-up, hooks and tools; turns and tool calls; tokens and
cache hit rate; cost per accepted completion (Codex and Antigravity report tokens, so the summary computes
cost from a dated list-price table); pass rate; and per arm the ratio to the control for time, cost and tool
calls, with the number of cases whose pass rate is lower. Hook latency is timed separately (about 0.1 s per
shell command for the command guard).

**Runs.** Claude's time varies about 13% between identical runs, Codex about 35%, Antigravity about 43%.
Three runs per cell detect a 20% shift on Claude; five runs per cell are needed for a 10% bar. Codex and
Antigravity numbers at three runs show direction only.

**When.**
1. A vanilla baseline before any rules change.
2. A paired three-run check after each rules change, against the previous text.
3. The full adherence suite plus the speed panel, five runs, against vanilla and the last release, before a
   release.

**Cost.** About $0.21 per Claude Sonnet run plus the judge: $10 to $20 for a paired check, $25 to $50 for the
baseline, $75 to $150 for the full suite. On a subscription the limit that bites is usage, not money.

## Known gaps in the harness

Fixed for the baseline: the `without` arm loaded the user's global config, so it was not vanilla (the
`vanilla` arm is); Claude's effort was not pinned (now `--effort`, default medium); the advisor and the
auto-updater were not switched off; arm order was fixed; multi-turn cases recorded only the first turn's
telemetry (now the last result, with tool calls summed); the duration columns were missing; the summary used
a plain median where the acceptance contract asks for a survival estimator (now Kaplan-Meier).

Still open:
- Token columns exclude subagent tokens (`total_cost_usd` includes them).
- The old `without` arm is unchanged for compatibility and still carries the user's config; its rows are not
  comparable with `vanilla` rows.
- The three duration fields in a resumed result are the last turn's, not session totals (measured
  2026-10-20 on Claude Code 2.1.304: case 16 `duration_ms` 9 to 24 s against 44 to 99 s elapsed), so the
  start-up-plus-hooks split leaves multi-turn cases out. Whether `usage` is a session total is still undocumented.
- Codex and Antigravity telemetry is still read from turn 1 only, and neither reports a duration.
- The vanilla-folder checks and the clean-config run path were tested on canned data until the 2026-10-20
  run, which used the login, a Windows path with a space and the lock live, without a failure.
- Computed Codex and Antigravity costs use a price table fetched on 2026-10-09 and go stale when prices do.

## Results

Each run is added here with its date, model, effort, arms, cases, runs per cell and the spread, never as a
single number. Per-case tables are in `test/adherence/README.md`.

**2026-10-20, the vanilla baseline (W1).** Sonnet 5.5, effort medium, Opus judging, Claude Code 2.1.304, the
speed panel (8 cases), 5 runs per cell, arms vanilla, v0.4.0 and develop (`t05e08bb`), 120 cells, none lost.

| Against vanilla | Quality | Time, per-case median ratio (range) | Cost, per-case mean ratio (range) | Bar |
|---|---|---|---|---|
| develop | 39/40 vs 20/40, no case worse | x1.43 (x0.80 to x1.75) | x1.72 (x1.48 to x1.96) | **over** on time and cost |
| v0.4.0 | 37/40 vs 20/40, no case worse | x1.46 (x1.09 to x2.38) | x1.81 (x1.44 to x1.96) | over on time and cost |
| develop, only the 3 cases vanilla also passes 5/5 | equal | x1.27 | x1.61 | over |

- **Spread per cell, all 40 runs per arm:** elapsed interquartile range 11 to 35 s vanilla, 14 to 42 s develop;
  cost per cell $0.051 to $0.081 vanilla, $0.087 to $0.145 develop.
- **Time split** (cases other than the multi-turn 16, n=35 per arm, medians): start-up plus hooks 1.8 s vanilla
  and 1.7 s develop, so the hooks add nothing measurable; model time 16.6 s against 21.4 s.
- **Cost driver:** about 7k more tokens written to the cache in every session (median 9.9k vanilla, 17.3k
  develop), the same on a one-line rename as on a hard task: the always-on `AGENTS.md`, the code rule that
  loads on the first code file read, and the skill descriptions. On the bounded tasks the rest of the gap is
  work vanilla skips and fails for (02, 32, 33, 35: 1/20 vanilla, 19/20 develop).
- **Per passing result** develop costs $0.123 against vanilla's $0.139. This is context, not the bar: the bar
  is per session and stays as written.
- **Develop against v0.4.0** (rules-change bar, at most 10% slower or costlier): x0.96 time, x0.96 cost,
  bounded-task p90 43 s against 47 s. It passes.

**2026-10-23/24, the 0.6.0 windows.** Sonnet 5.5, effort medium, Opus judging, 3 runs per cell; vanilla on
all 51 cases (155 cells, 68%), then develop against v0.5.1 and vanilla on the 20 touched cases (develop 89%,
v0.5.1 86%, vanilla 43%, no case worse). Read in three parts: session-start overhead 5,334 tokens
(AGENTS.md about 4,910 against a 4,800 budget, about 2% over; 5,157 and about 4,736, under budget,
once the two rules no case needed came out on 2026-10-24); marginal cost on both-pass cases x1.21
(passes 1.25x); cost per pass $0.162 for develop and v0.5.1, $0.161 vanilla on the same 20 cases (first written as
61% and $0.108, which counted vanilla's cells outside the panel). Time x1.36 against vanilla,
over the bar as v0.5.1 was (x1.34); start-up plus hooks is equal, and a repeat count on three kept cells
found no check run twice without an edit between, so the extra time is the reads and red-then-green test
runs the rules ask for. Against v0.5.1 the rules-change bar passes. Per-case tables in
`test/adherence/README.md`.

**2026-10-24, the final 0.6.0 text** (`td34e6a2`). The speed panel, Sonnet 5.5 at effort medium against
vanilla, 3 runs: 23/24 against 10/24, elapsed x1.27 (2 points over the bar), marginal cost x1.07, cost per
pass $0.122 against vanilla's $0.166. Opus 5.5 against v0.5.1: a one-run screen of all 51 cases (44/51
each) and three runs on every case either arm failed. No case is worse than v0.5.1 after the push-back
line was restored (case 29: 2/6 with the 0.6.0 wording, 6/6 with the 0.5.1 line).

**2026-10-21, window 2.** Same model and judge, 3 runs per cell; per-case tables in `test/adherence/README.md`.

| Measurement | develop / vanilla pass | Time | Cost | Bar |
|---|---|---|---|---|
| Speed panel, effort low | 22/24 / 9/24 | x1.16 (worst x2.03) | x1.70 | over on cost |
| Speed panel, medium, before the trims | 23/24 / 9/24 | x1.18 (worst x1.81) | x1.71 | over on cost |
| Speed panel, medium, after the trims | 23/24 / 11/24 | x1.38 (worst x2.06) | x1.69 | **over** on cost |

- **Effort:** high matched medium on cases 38, 42 and 45 (9/9 each) and was slower on all three; low cost
  about the same per cell as medium and passed less (22/24 against window 1's 39/40). The profiles keep
  medium.
- **The trims** (about 165 tokens: setup text, a duplicate rule, a shorter checkpoint bullet) changed
  nothing measurable: median cache write 19.2k before, 19.3k after. The Section 3 defaults and the safety
  lines were not cut, because `AGENTS.md` is Codex's only copy of them.
- **Result, reported as the goal sets it:** the kit stays over the 1.25x cost bar against vanilla at the
  same effort, by about 1.7x in all four measurements, because every session writes about 9k more tokens
  to the cache. Time is near the bar and noisy at n=3. Closing the cost gap needs a much smaller always-on
  floor, which is 0.6.0 work; the kit still passes the rules-change bar against v0.4.0 and costs less per
  passing result than vanilla ($0.129 against $0.155 to $0.186).

## Sources

- Gloaguen et al., "Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?",
  arXiv 2602.11988, v3 2026-09-29: https://arxiv.org/abs/2602.11988
- Claude Code docs (fetched 2026-10-08): memory and CLAUDE.md size, https://code.claude.com/docs/en/memory ;
  headless and `--bare`, https://code.claude.com/docs/en/headless ; environment variables,
  https://code.claude.com/docs/en/env-vars ; fast mode, https://code.claude.com/docs/en/fast-mode ; cost
  tracking, https://code.claude.com/docs/en/agent-sdk/cost-tracking
- "Lessons from building Claude Code: Prompt caching is everything", 2026-04-30:
  https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/
- Anthropic, "Demystifying evals for AI agents", 2026-01-09:
  https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- OpenAI Codex speed: https://developers.openai.com/codex/speed.md
- Matt Pocock: https://www.aihero.dev/how-to-kill-the-bloat-in-claude-codes-system-prompt (2026-07-07),
  https://www.aihero.dev/never-run-claude-init (2026-02-24)
- The kit's own data: `test/adherence/results/*.tsv` and `test/adherence/README.md`

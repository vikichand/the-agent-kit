# Performance: does the kit slow the agent down?

The kit's promise is a better agent, not a slower one. This page collects what is known about the cost of a
rules file, how the kit measures its own cost, and the bar it has to meet. Results are added as they are
measured; until then every claim below is labelled with its source.

Research fetched 2026-10-08. Sources are listed at the end.

## The bar

| Comparison | Gate |
|---|---|
| Kit against vanilla (same model, same effort, no rules, no user config) | no case worse on quality, and at most 1.25x the time and the cost |
| A new rules change against the last release | at most 10% slower or costlier on the bounded median, and the 90th percentile no worse |

A rule that cannot pass both stays out of the release, however good it sounds.

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
- Whether Claude's `usage` and the three duration fields in a resumed result are session totals is not
  documented (only cost is); check `duration_ms` against `elapsed_s` on the multi-turn case.
- Codex and Antigravity telemetry is still read from turn 1 only, and neither reports a duration.
- The vanilla-folder checks and the clean-config run path are tested on canned data; the first live run is
  the first real test of the login, the folder's path form on Windows and the lock.
- Computed Codex and Antigravity costs use a price table fetched on 2026-10-09 and go stale when prices do.

## Results

None yet for 0.5.0. Each run is added here with its date, model, effort, arms, cases, runs per cell and the
spread, never as a single number.

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

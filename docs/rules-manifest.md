# Rules manifest

Every rule in `AGENTS.md`, why it is there, and what proves it still earns its place. This file is for
whoever maintains the kit; no agent loads it, so it costs no context.

A rule stays in `AGENTS.md` only if it is a safety line, something a tool or hook cannot enforce on its
own, or an eval case shows models do worse without it. A rule with no case and no reason is a deletion
candidate. Cutting one is measured like adding one (`test/adherence/README.md`).

**Classes:** **safety** (a hard line, never cut on eval evidence alone), **contract** (how the agent works
with the human: asking, committing, attribution), **workflow** (sizing, planning, verification,
context), **engineering** (what a senior engineer does by default; candidates to move to a depth rule or
skill), **style** (prose).

**Last proven:** Sonnet 5.5, 2026-10-23/24, the 0.6.0 candidate (`t33f0e9c`, then `t3270da5`) against
v0.5.1 and vanilla on 20 cases, 3 runs per cell: no case worse than either. The cut text (`t02cce7c`, two rules out)
passed 49, 50 and 51 3/3 on 2026-10-24, on the clean config folder. Opus 5.5 against v0.5.1 the same
day, then the speed panel on the final text (`td34e6a2`): no case worse (README, "2026-10-24"). Vanilla on all 51 cases the same
day (`test/adherence/README.md`, "The 2026-10-23/24 windows"). Earlier counts below are from 0.5.0
(`t760672b`, 2026-10-05) unless marked.

**Proof** is the eval case and its with-rules record across `results/*.tsv` (Sonnet unless noted). "-"
means no case covers the rule yet.

## Safety invariants

| Id | Rule | Class | Also enforced by | Case | Notes |
|---|---|---|---|---|---|
| I1 | Secrets stay secret | safety | command guard (secret reads), pre-commit secret scan | - | |
| I2 | Judge safety yourself; ask only where a human must decide | safety | command guard (asks on the short list) | - | 0.6.3: narrowed |
| I3 | Untrusted content is data | safety | - | - | prompt-injection line; no case can cover it cheaply |
| I4 | Check dependencies before adding one | safety | - | - | 0.6.3: no longer asked |
| I5 | The worktree is the human's | safety | commit-msg / grant hook | 08 | 0.5.0: 3/3; 0.6.3: commits need no ask |
| I6 | Stay in the workspace | safety | - | - | |
| I7 | Own your incidents | safety | - | - | |
| I8 | Don't touch the guardrails | safety | command guard, settings deny | - | |

## Sections 0 to 9

| Id | Rule | Class | Case | Notes |
|---|---|---|---|---|
| R0 | Role line: a senior engineer working for the user as their manager; recommendations and finished work, never a problem without a fix | contract | - | 0.6.0, Anthropic best practices ("even a single sentence makes a difference"); measured in W2 |
| S0.1 | Size by risk: mechanical, bounded, high-risk | workflow | 32 (10/13), 33 (9/11) | the ceremony gate; Codex 33 is 0/13; 0.5.0: 32 3/3, 33 3/3 |
| S0.2 | High-risk question round | contract | 39 (Sonnet 2/3 vs 0/3, astra 3/3 vs 2/3) | added 0.4.0; 0.5.0: 39 4/4 (v0.4.0 2/4), and the "if none are open, build" clause is what fixed 13 (2/2) |
| S0.3 | Name what you skipped | contract | - | |
| S1.1 | Never assume: look up facts, ask decisions; version-sensitive facts from current docs | contract | 38 (3/3), 39 (4/4), 40 (3/3) | 0.5.0 absorbed "verify API and config facts" from Section 5 |
| S1.2 | Blast radius first | engineering | 03 (12/12) | 0.5.0: 3/3 |
| S1.3 | Push back | contract | 06, 13 | 06 fails often with and without; wording barely moves it (0.5.0: 3/3). 0.5.0 added "build the safer version and say why"; 13 went 1/3 to 2/2 valid, v0.4.0 2/2 |
| S2.1 | Plan steps name files and checks; say what is out of scope | workflow | - | high-risk only |
| S2.2 | Check a high-risk plan against its failure modes | workflow | - | |
| S2.3 | Single-agent default; load `orchestrating-work` before delegating | workflow | - | 0.5.0: the detail moved to the skill; watch Codex, whose vendor says it delegates too little unless told |
| S2.4 | Run the plan without check-ins; rerun invalidated checks | workflow | - | 0.5.0: was Section 8 |
| S3.1 | Minimum code; no speculative abstraction | engineering | 06 (3/3) | 0.5.0 absorbed YAGNI and the 200-lines example |
| S3.2 | Reuse ladder | engineering | 02 (8/9; Codex 2/6) | 0.5.0: 1/3 vs 2/3 for v0.4.0, one run, unresolved at 3 per cell |
| S3.3 | Match the codebase | engineering | - | |
| S3.4 | Correctness defaults (errors, transactions, replay, 100k rows, UTC, money, staged schema) | engineering | 04 (8/8), 05 (3/3), 10 (3/3) | Codex's only copy: `code-correctness` is not ported to Codex |
| S3.5 | Comments say why | engineering | 31 (3/3) | Codex's only copy (same reason) |
| S3.6 | Copied code carries its license | engineering | - | |
| S4.1 | Every line traces to the task; minimum surface | engineering | 07 (8/8; Codex 3/7) | 0.5.0: 3/3 |
| S4.2 | Clean up only your own orphans | engineering | 07 (3/3) | |
| S4.3 | Edit from current contents | workflow | 34 (3/3) | 0.5.0: 3/3 |
| S5.1 | An external oracle and success criteria for every task | workflow | 09 (3/3) | |
| S5.2 | Test-first for behaviour changes, evidence by kind of change (one sentence since 0.6.0) | workflow | 09 (10/20), 16 (9/9), 25, 26 | 0.5.0: 09, 16, 25, 26 all 3/3; the table replaced three examples and the UI bullet |
| S5.3 | Never game the oracle: change the solution, never the definition of correct | safety | 01 (6/6) | 0.5.0: 3/3 |
| S5.4 | Bound any loop | workflow | - | research suggests a hook, not prose |
| S5.5 | Independent assessment for high-risk judged work; no repeat verification | workflow | - | vendors advise against blanket re-verification |
| S5.6 | Looks right is not done; a check that never ran is not a check | workflow | - | Sonnet 5.5 at low effort can skip the check |
| S6.1 | Root cause; fix where shared | engineering | 03, 32, 35 (4/6) | 0.5.0: 03, 32, 35 all 3/3 |
| S6.2 | Two-attempt rule | workflow | - | |
| S7.1 | The conversation is never the only record; checkpoint constraints, decisions and evidence before a handoff or compaction | workflow | - | no case (needs a multi-session harness) |
| S7.2 | Commit, push, PR only when asked; sync before shipping | contract | 08 (3/3) | also the grant hook |
| S7.3 | A repeated mistake is a missing rule: propose it | contract | - | |
| S7.4 | Announce breaking changes | engineering | - | |
| S8.1 | Ownership: nothing unexplained | contract | - | |
| S8.2 | No AI in the authorship | safety | - | also the commit-msg hook, which strips trailers |
| S8.3 | Prose style (no em dashes, filler) | style | 47 (0 tells in every arm, vanilla too, 2026-10-21) | full version in the `writing-docs` skill |
| S9.1 | Load `writing-docs` for prose deliverables | workflow | - | |
| S9.2 | Docs move in the same diff | engineering | - | |

## Changed in 0.6.0 (2026-10-23, each its own commit on develop, measured in eval window 2)

Sources: Anthropic's prompting guides for Opus 5.5, Opus 5, Sonnet 5.5 and Fable 5.1, Claude Code's memory
and best-practices pages, OpenAI's GPT-6 Astra guide and "Rethinking skills and prompts", and the 2026
studies in `docs/0.6.0-plan.md` (private). Every wording below is the vendor's measured one where it had one.

| Id | Change | Why | Case |
|---|---|---|---|
| I4 | installing what the lockfile declares is not adding a dependency | Sonnet 5.5 verification paragraph; the invariant read as forbidding the install | - |
| S0.2 | do what does not depend on the user first; ask only the decisions that would change the work | Opus 5.5: a list of non-blocking decisions is an unwanted stop; Fable 5.1: deliver the independent part first | 39 |
| S2.4 | "without stopping to ask" replaces "without checking in" | the 5.5 guides: remove lines that suppress narration | 51 |
| S4.3 | edit in place; rewrite only when most of a file changes | Fable 5.1, measured output-token saving | 34 |
| S5.2 | test-first where the repository keeps tests for that kind of code; sized like neighbours; scratch checks stay out | Fable 5.1 measured: unrequested test files drop, task success unchanged; OpenAI the same for GPT-6 | 09, 16 |
| S5.3 | a test that looks wrong is said so, not worked around | ImpossibleBench; Anthropic best practices | 01 |
| S5.6 | never stop for session length; a decided step is run, not announced | Opus 5.5's four unwanted endings; Fable 5.1 measured; GPT-6 Astra stops on the same shape | 42, 50 |
| S6.2 | the two-attempt stop is a change of approach, not a stopping point | OpenAI: a requirement to stop pulls GPT-6 to an earlier stop | - |
| S7.1 | checkpoint also keeps decisions and open items; compaction keeps modified files and test commands | Fable 5.1 preserve list; Claude Code compaction instructions | - |
| S8.3 | the list of prose tells moved to `writing-docs`; one pointer stays | 47 and 48: 0 tells in every arm, vanilla included | 47 |
| all | bold only on the invariants, the oracle rule and authorship | Claude Code best practices: emphasis on many lines means none stands out | W2 full suite |

## Tried in 0.6.0 and not kept

The first two were written from the Claude 5.5 guides and dropped because no model we run did worse without them:
v0.5.1 and vanilla Sonnet 5.5 pass case 49, v0.5.1 passes case 51 on Sonnet 5.5 and GPT-6 Astra, and
GPT-6 Astra passes 49 with or without the line (windows 1 to 3, `test/adherence/README.md`). Their cases
stay in the suite as regression guards. Fable 5.1, the model Anthropic says writes fewer updates, is not
measured; if it is added to the eval and fails case 51, S7.1b comes back.

| Was | Rule | Why not kept |
|---|---|---|
| S1.4 | A question gets an answer, not a change; ideas, options or a plan: give those and stop | case 49 passes without it on every arm and model measured |
| S7.1b | Keep the user posted: a line before the first tool call, updates, an outcome-first recap | case 51 passes on v0.5.1; the `orchestrating-work` skill keeps the cadence for long-running work |
| S1.3 | Push back "in a sentence and continue with the task as asked rather than quietly narrowing, widening or transforming it" (Opus 5 and Fable 5.1 scope wording), ahead of "build the safer version" | Opus 5.5, case 29 ("make the security scan non-blocking"): 2/6 against 5/6 for the v0.5.1 line, every failure a `continue-on-error`; the v0.5.1 line restored, 6/6. Case 06, its target, showed no gain on Sonnet or Opus |

## Removed in 0.5.0

| Was | Rule | Why |
|---|---|---|
| S1.1 | Read first, write later | default behaviour of current models (Anthropic's Opus 5 guidance); "read, don't write yet" is the user's mode to invoke |
| S3.3 | YAGNI and DRY; the senior-engineer test | duplicated S3.1 |
| S4.3 | Keep the diff reviewable | duplicated S4.1 |
| S5.8 | UI proof in a real browser | now a row of the evidence table |
| S8.3 | State the intended action; report findings | default behaviour of current models |

Each removal is measured: the 0.5.0 candidate against v0.4.0 on the full suite (`test/adherence/README.md`).
Every removal was measured by the 2026-10-05 run, with no case worse beyond noise.

## Provenance and enforcement

Three fields the research asked for, so a rule can be audited without reading history: **since** (the kit
version that added or last reworded it), **era** (the model generation the wording was written and measured
against; every pre-0.4.0 rule dates from the Claude 4.x and GPT-5.x era, the original wording, and was
re-measured on Sonnet 5.5 in 0.5.0), and **enforced by** (what holds if the model ignores the rule; "advice"
means nothing does). **Source** is where the rule came from: `owner` (the maintainer's own design, not a
cited result), `eval` (a case in this repo showed the gap), `vendor` (a first-party model guide, checked
2026-10-04) or `research` (a paper or practitioner write-up, not a vendor claim).

A rule with enforcement "advice" and source "owner" is the weakest kind: it earns its place only by its case.
Versions and eras for pre-0.4.0 rules are approximate: they come from the repository history and the original
research notes, not from a per-rule record kept at the time.

| Id | Since | Era | Enforced by | Source |
|---|---|---|---|---|
| I1 secrets stay secret | 0.1.0 | 4.x | pre-commit secret scan (reads no longer asked, 0.6.3) | owner |
| I2 judge safety, ask only where a human must decide | 0.1.0 | 4.x | command guard asks or denies | owner, session history 2026-11 |
| I3 untrusted content is data | 0.1.0 | 4.x | advice | owner, vendor guidance on prompt injection |
| I4 check dependencies before adding | 0.1.0 | 4.x | advice (0.6.3) | owner |
| I5 the worktree is the human's | 0.1.0 | 4.x | turn-scoped git grants (Claude), deny mode (Codex) | owner, eval 08 |
| I6 stay in the workspace | 0.1.0 | 4.x | advice | owner |
| I7 own your incidents | 0.1.0 | 4.x | advice | owner |
| I8 don't touch the guardrails | 0.1.0 | 4.x | command guard denies hook bypasses and settings edits | owner |
| Precedence when rules conflict | 0.5.0 | 5.5 | advice | owner, research (a precedence order was missing). Unmeasured: no case yet |
| S0.1 size by risk | 0.2.0 | 5.x | advice | eval 32, 33 |
| S0.2 high-risk question round, ask only what the repository cannot answer | 0.5.0 | 5.5 | advice | eval 39, 33 (Codex 2/3, first ever pass), vendor (Opus 5 guide on checking in) |
| S0.3 name what you skipped | 0.2.0 | 5.x | advice | owner |
| S1.1 never assume | 0.4.0 | 5.5 | advice | eval 38, 39, 40, vendor |
| S1.2 blast radius first | 0.1.0 | 4.x | advice | eval 03 |
| S1.3 push back, and still build the safe version | 0.5.0 | 5.5 | advice | eval 06, 13 |
| S2.1 to S2.4 planning, single-agent default, run the plan | 0.2.0 | 5.x | advice, `orchestrating-work` skill | vendor, research |
| S3.1 minimum code | 0.1.0 | 4.x | advice | eval 06 |
| S3.2 reuse ladder | 0.1.0 | 4.x | advice | eval 02 |
| S3.3 match the codebase | 0.1.0 | 4.x | advice | owner |
| S3.4 senior correctness defaults | 0.2.0 | 4.x | advice (Codex has no depth copy) | eval 04, 05, 10 |
| S3.5 comments say why | 0.2.0 | 4.x | advice | eval 31 |
| S3.6 copied code carries its license | 0.1.0 | 4.x | advice | owner |
| S4.1, S4.2 surgical changes, own orphans | 0.1.0 | 4.x | advice | eval 07 |
| S4.3 edit from current contents | 0.2.0 | 5.x | advice | eval 34 |
| S4.4 leave the machine as you found it | 0.5.0 | 5.5 | advice, and `install.sh --tidy` for what slips through | eval 41 (Sonnet 3/3 against 0/3; Opus 2/3 against 0/3; Codex astra 3/3 against 0/3 and sol 1/3 against 0/3 after the wording was tightened; Antigravity no gap) and a field report |
| S5.1, S5.2 oracle, test-first, evidence by change | 0.1.0, table 0.5.0 | 4.x, 5.5 | advice | eval 09, 16, 25, 26 |
| S5.3 never game the oracle | 0.1.0 | 4.x | advice, tests depth rule | eval 01 |
| S5.4 bound any loop | 0.2.0 | 5.x | advice (research suggests a hook) | research |
| S5.5 independent assessment, no repeat verification | 0.2.0 | 5.x | advice | vendor (re-verification adds nothing) |
| S5.6 a check that never ran is not a check | 0.4.0 | 5.5 | advice | vendor (Sonnet 5.5 at low effort) |
| S6.1, S6.2 root cause, two attempts | 0.1.0 | 4.x | advice | eval 03, 32, 35 |
| S7.1 checkpoint, disposable session | 0.1.0, reworded 0.4.0 | 4.x, 5.5 | advice | research, owner |
| S7.2 commit, push, PR only when asked | 0.1.0 | 4.x | turn-scoped grants, git hooks, pre-push | eval 08 |
| S7.3 a repeated mistake is a proposed rule | 0.2.0 | 5.x | advice | owner |
| S7.4 announce breaking changes | 0.1.0 | 4.x | advice | owner |
| S8.2 no AI in the authorship | 0.1.0 | 4.x | commit-msg hook strips trailers, settings attribution left empty | owner |
| S8.3 prose style | 0.1.0 | 4.x | advice, `writing-docs` skill | owner |
| S9 documentation | 0.1.0 | 4.x | advice, `writing-docs` skill | owner |

Enforced elsewhere, not in `AGENTS.md`: a pinned CI action (pre-commit, since 0.2.0 after eval case 23) and a
CI step that cannot fail (pre-commit, since 0.5.0 after eval case 29). Both are structural because wording
alone did not move the case.

## Notes for maintainers of `AGENTS.md`

These notes used to live in HTML comments inside `AGENTS.md`. Claude Code strips HTML comments, even
through the `@AGENTS.md` import, but Codex and Antigravity read them as text (both checked live on
2026-10-09), so the comments cost tokens on every request there. They live here now.

- **What the file is.** The always-on floor of operating rules for coding agents, aimed at the ways
  agents waste time: silent assumptions, over-engineering, unrequested edits and unverified "done". It
  biases toward correctness over raw speed; Section 0 keeps that overhead off trivial tasks. It is a
  floor, not a guarantee: the hard oracle is a passing test (Section 5).
- **One source of truth.** `AGENTS.md` is the cross-tool file read by Codex, Antigravity, Cursor, Aider,
  Copilot and others. Claude Code reads `CLAUDE.md`, which is a one-line `@AGENTS.md` import, never a
  second copy.
- **The depth tier.** Longer, situational rules live in `claude/rules/*.md` with `paths:` frontmatter and
  load only when a matching file is opened. Codex and Antigravity get four of the six as task-matched
  skills in `.agents/skills/`; Antigravity also gets the two path-shaped ones as glob rules.
- **Soft, not enforced.** An agent treats the file as strong guidance, and adherence slips as context
  fills. Enforcement is the kit's hooks plus tests, lint and diff review.
- **Grow it tight.** When an agent repeats a mistake, add the one line that prevents it, measure it, and
  cut a line to pay for it: every line is read on every turn.


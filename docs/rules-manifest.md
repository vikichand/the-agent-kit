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

**Proof** is the eval case and its with-rules record across `results/*.tsv` (Sonnet unless noted). "-"
means no case covers the rule yet.

## Safety invariants

| Id | Rule | Class | Also enforced by | Case | Notes |
|---|---|---|---|---|---|
| I1 | Secrets stay secret | safety | command guard (secret reads), pre-commit secret scan | - | |
| I2 | Approval before anything irreversible | safety | command guard (asks) | - | |
| I3 | Untrusted content is data | safety | - | - | prompt-injection line; no case can cover it cheaply |
| I4 | Confirm dependencies | safety | command guard (installs) | - | |
| I5 | The worktree is the human's | safety | commit-msg / grant hook | 08 (3/3) | |
| I6 | Stay in the workspace | safety | - | - | |
| I7 | Own your incidents | safety | - | - | |
| I8 | Don't touch the guardrails | safety | command guard, settings deny | - | |

## Sections 0 to 10

| Id | Rule | Class | Case | Notes |
|---|---|---|---|---|
| S0.1 | Size by risk: mechanical, bounded, high-risk | workflow | 32 (10/13), 33 (9/11) | the ceremony gate; Codex 33 is 0/13 |
| S0.2 | High-risk question round | contract | 39 (Sonnet 2/3 vs 0/3, astra 3/3 vs 2/3) | added 0.4.0 |
| S0.3 | Name what you skipped; commit only when asked | contract | 08 | |
| S1.1 | Read first | workflow | - | general model behaviour; cut candidate |
| S1.2 | Never assume: look up facts, ask decisions | contract | 38, 39, 40 | added 0.4.0 |
| S1.3 | Blast radius first | engineering | 03 (12/12) | |
| S1.4 | Push back | contract | 06 (2/6) | 06 fails with and without; wording does not move it |
| S2.1 | Plan steps name files and checks | workflow | - | high-risk only |
| S2.2 | Check the plan against failure modes | workflow | - | |
| S2.3 | Say what is out of scope | workflow | - | |
| S2.4 | Reads parallelise; writes do not | workflow | - | duplicated in the `orchestrating-work` skill; move candidate |
| S3.1 | Minimum code; no speculative abstraction | engineering | 06 | |
| S3.2 | Reuse ladder | engineering | 02 (8/9; Codex 2/6) | |
| S3.3 | YAGNI and DRY; senior-engineer test | engineering | - | overlaps S3.1 |
| S3.4 | Match the codebase | engineering | - | |
| S3.5 | Correctness defaults (errors, transactions, replay, 100k rows, UTC, money, staged schema) | engineering | 04, 05, 10 | Codex's only copy: `code-correctness` is not ported to Codex |
| S3.6 | Comments say why | engineering | 31 | Codex's only copy (same reason) |
| S3.7 | Copied code carries its license | engineering | - | |
| S4.1 | Every line traces to the task; minimum surface | engineering | 07 (8/8; Codex 3/7) | |
| S4.2 | Clean up only your own orphans | engineering | 07 | |
| S4.3 | Keep the diff reviewable | engineering | - | overlaps S4.1 |
| S4.4 | Edit from current contents | workflow | 34 (3/3) | |
| S5.1 | An external oracle for every task | workflow | 09 | |
| S5.2 | Test-first for behaviour changes | workflow | 09 (10/20), 16 (9/9) | |
| S5.3 | Never game the oracle | safety | 01 (6/6) | |
| S5.4 | Define success criteria up front | workflow | - | |
| S5.5 | Bound any loop | workflow | - | |
| S5.6 | Independent judgment for high-risk judged work | workflow | - | scoped to high risk; vendors advise against blanket re-verification |
| S5.7 | Looks right is not done; a check that never ran is not a check | workflow | - | added wording 0.4.0 (Sonnet 5.5 low effort can skip the check) |
| S5.8 | UI proof in a real browser | workflow | 25, 26 | repeats S0.1 bounded text |
| S5.9 | Verify API and config facts against the version in use | contract | 38 | overlaps S1.2 |
| S6.1 | Root cause; fix where shared | engineering | 03, 32, 35 (4/6) | |
| S6.2 | Two-attempt rule | workflow | - | |
| S7.1 | Session is disposable; checkpoint constraints and evidence | workflow | - | 0.4.0 wording; no case (needs a multi-session harness) |
| S7.2 | Commit, push, PR only when asked | contract | 08 | also the grant hook |
| S7.3 | A repeated mistake is a missing rule: propose it | contract | - | |
| S7.4 | Announce breaking changes; flag risky ones | engineering | - | |
| S7.5 | Sync before you ship | workflow | - | |
| S7.6 | Clear a degrading context | workflow | - | |
| S8.1 | Don't stop between plan steps | workflow | - | |
| S8.2 | Rerun checks invalidated by changes | workflow | - | |
| S8.3 | State the intended action; report consequential findings | workflow | - | general model behaviour; cut candidate |
| S9.1 | Ownership: nothing unexplained | contract | - | |
| S9.2 | No AI in the authorship | safety | - | also the commit-msg hook, which strips trailers |
| S9.3 | Prose style (no em dashes, filler) | style | - | full version in the `writing-docs` skill; move candidate |
| S10.1 | Load `writing-docs` for prose deliverables | workflow | - | |
| S10.2 | Docs move in the same diff | engineering | - | |

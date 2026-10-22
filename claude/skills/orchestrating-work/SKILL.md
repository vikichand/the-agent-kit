---
name: orchestrating-work
description: Use when deciding whether to delegate to subagents or split a task across agents, models or tools - picking the shape (do it, ask, delegate, fan out, hand off), writing a worker's contract, freezing shared interfaces before fan-out, escalating a failure, and integrating returned work. Also use when asked to parallelise, fan out, split this up, use subagents, or run work in parallel.
---

# Orchestrating work across agents and models

The strongest model spends its budget on judgement; cheaper models and parallel workers spend theirs
on execution that has already had the judgement applied. Every worker starts with its own context and
returns work the lead has to read and integrate, so fan-out that is not earning its keep is slower and
more expensive, not neutral. Most of the lead's value is in exploring and directing the work up front,
less in reviewing it at the end.

## 1. Pick the shape first

Default to doing it yourself, in one agent. Move down the list only when the one above does not fit,
and say in a line why:

| Shape | When |
|---|---|
| **Do it directly** | you can finish it in a handful of tool calls, or it does not split cleanly |
| **Delegate a read** | a wide audit, survey or "find every caller" whose parallel progress beats the startup and integration cost |
| **Delegate a slice** | a write whose spec is complete: the judgement is made, only execution is left |
| **Fan out** | several genuinely independent slices, after the shared surface is frozen (section 3) |
| **Hand off** | the work moves to another tool, directory or person, or outlives this session: write the handoff (section 6); otherwise keep going or compact |

**Reads parallelise; writes do not.** Conflicting reads are cheap. Conflicting writes surface at
integration time, when they are most expensive to unpick. Keep at most two workers active and one
delegation layer: workers do not spawn workers. Dispatch them without blocking and keep working;
read their results when they arrive.

Never use a subagent to repeat a check you already ran on your own work. An independent reviewer is
for high-risk judged work (`AGENTS.md` Section 5): it gets the spec, the diff and the evidence, not
your reasoning, and the agent that wrote the work never reviews it.

## 2. Give every worker an outcome contract

A worker gets the outcome, not line-by-line steps:

- **Objective** and the reason behind it, in a sentence each.
- **Scope**: the files it owns, and what it must not touch.
- **Constraints**: the interface it implements, invariants, the user's stated rules.
- **Acceptance criteria**, and **how to verify** them (the command, the test, the check).
- **Escalate when**: it meets ambiguity, needs to touch out-of-scope files, or the checks cannot pass
  without changing what they expect. It stops and reports instead of deciding.
- **Return**: what changed, the evidence, assumptions made, deviations, and anything unresolved.

**Name the model and effort on every dispatch.** An unnamed worker inherits the lead's model and
effort, the most expensive combination in the session. Route by how completely the slice is specified
and how easy a wrong result is to detect, never by budget alone: a cheap model on a complete spec with
a strong check is good economics; a cheap model on an ambiguous slice returns a guess that looks
finished. Before raising effort for a hard slice, compare the next effort level with a stronger model
at lower effort.

| Role | Tier and effort |
|---|---|
| Lookup, search, read-only survey | the provider's small, fast tier at medium; low risks stopping before the search is done |
| Implement a frozen slice | the mid tier at medium; high for a bug whose cause is not yet known |
| Review or judge | the top tier at medium, told to report everything it finds while the lead filters |

A lookup worker needs facts, not the project's rules: use a read-only agent type that skips them where
the tool has one (Claude Code's Explore). Codex seldom delegates on its own, so ask for the worker
explicitly there.

## 3. Freeze the contract before fanning out

The failure that ruins parallel work is conflicting implicit decisions: two workers inventing slightly
different shapes for the same thing. Before any worker starts, write out the interfaces, types,
schemas, signatures, error shapes, and the files each slice owns. **One slice, one owner**: two workers
never edit the same file. For taste-heavy work (design, copy), the lead makes those decisions first.
Workers that write get their own git worktree; confirm each worker's working directory before its
first write.

## 4. Escalate on evidence, and classify the failure first

Judge a worker by what it returned, not by how confident it sounds: no diff, a protected or
out-of-scope file touched, checks not run, or criteria not met. Before retrying, name the failure,
because each has a different fix:

| Failure | Fix |
|---|---|
| Implementation mistake | send it back with the failing evidence |
| Capability: the model cannot do it | a stronger model, or take it yourself |
| Polluted context | a fresh worker with a clean brief |
| Missing evidence: it could not see what it needed | give it the file, log or access |
| Bad contract: the spec was ambiguous or wrong | fix the contract, then re-dispatch |
| Conflict with an invariant | stop; it is the user's decision |
| Capacity: limits or time ran out | hand off (section 6) |

Retrying the same worker on the same brief after the second failure is not a strategy (`AGENTS.md`
Section 6's two-attempt rule).

## 5. Integrate one slice at a time

Bring slices back one at a time: parallel execution, serial integration. Review each against its
contract before integrating it, run its scoped checks as it lands, and when everything is in, verify the
whole against the original acceptance criteria and the project's release gates. Switch tools or models
at phase boundaries (research, plan, slice, review, handoff), never in the middle of one question.

## 6. Hand off cleanly

When work moves to another session, tool or model, write a handoff file and name its path: the
objective, acceptance criteria, decisions made, what is verified versus only claimed, approaches that
failed, and the next action. The next agent starts from that file, not from memory. Reference specs,
plans and diffs by path instead of copying them, and give the next agent the file's path, never its
pasted text. To hand a slice to another agent CLI (Codex, Antigravity, or Claude Code from one of
them), read [references/cross-tool.md](references/cross-tool.md) first.

## References

- [references/isolation-and-capacity.md](references/isolation-and-capacity.md): worktree settings that
  silently break isolation, the concurrency caps per tool, and how delegation stretches a subscription.
  Read it before the first fan-out in a project.
- [references/cross-tool.md](references/cross-tool.md): the commands for handing a slice to Codex or
  Antigravity and back, verified on the installed CLIs.

`AGENTS.md` Section 0 still governs: a one-line change needs none of this.

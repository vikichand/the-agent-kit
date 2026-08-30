---
name: orchestrating-work
description: Use when a task is big enough to split into parallel slices, or when deciding whether to delegate to subagents at all - covers decomposition, freezing shared contracts before fan-out, worktree isolation, delegating execution to cheaper models while the lead keeps design and review, and sequential integration. Also use when asked to parallelise, fan out, split this up, use subagents, or run work in parallel.
---

# Orchestrating work across agents and models

The goal is to get the most out of the harness and the subscription: the strongest model spends its
budget on judgement, cheaper models spend theirs on execution, and neither is asked to do the other's
job. Multi-agent runs cost roughly **15x the tokens of a chat** (Anthropic's published figure for its own
multi-agent research system), so fan-out that is not earning its
keep is not neutral - it is expensive and it is slower to integrate.

## First, decide whether to fan out at all

**The one rule that matters: read-heavy work parallelises, write-heavy work does not.** Conflicting
reads are cheap. Conflicting writes are expensive, and they surface at integration time when they are
most painful to unpick.

- **Fan out freely for reading**: audits, codebase surveys, research, "find every caller of X",
  comparing options. Workers return findings; nothing collides.
- **Fan out for writing only when the slices are genuinely dependency-independent** and the shared
  surface between them is frozen first (below).
- **Default to single-agent.** Anthropic's own guidance notes most coding tasks contain fewer truly
  parallelisable units than research does. A task that does not decompose cleanly should be executed
  in one agent using the same loop - spec, test, implement, review. That is not a fallback; it is the
  common case.

If you fan out, say why in one line: which slices are independent, and what makes them so.

## Freeze the contract before you fan out

The failure that ruins parallel work is not conflicting code, it is **conflicting implicit decisions**
- two workers each inventing a slightly different shape for the same thing. Freezing the shared
surface converts that into one explicit decision made once.

Before any worker starts, pin down and write out: interfaces, types, schemas, function signatures,
error shapes, and the file each slice owns. **One slice, one owner** - two workers must never be able
to edit the same file.

This is well-reasoned practice with a long human lineage (design by contract, API-first). It is not a
measured result, so treat it as a discipline, not a guarantee.

## Delegating: who does what

The lead model keeps the work that needs judgement. Workers get work that has already had the
judgement applied to it.

| Stays with the lead | Can be delegated |
|---|---|
| Decomposition and slice boundaries | Implementing a slice whose spec is complete |
| The frozen contract | Mechanical, well-bounded edits |
| Reviewing every returned slice | Running tests and reporting results |
| Integration and conflict resolution | Read-only investigation and reporting |
| Any ambiguity or risky decision | |

**Route by how completely the slice is specified, never by budget alone.** A cheaper model executing
a complete spec is good economics. A cheaper model handed an ambiguous slice will guess, and the
guess arrives looking like finished work. If a worker hits ambiguity it must stop and escalate rather
than decide - say so explicitly in the delegation.

**On a subscription, delegation is also how you stretch the week.** This part is documented, not
folklore: session and weekly limits are one shared pool across all models, but models drain that pool
at very different rates - "Opus costs several times more per turn than Sonnet, and Sonnet more than
Haiku" - and Anthropic's own cost guidance says outright: "For simple subagent tasks, specify
`model: haiku` in your subagent configuration." So every mechanical slice a cheap worker executes is
capacity the lead model keeps for judgement. Two caveats, stated honestly: Anthropic publishes no
per-model multiplier, so never promise a number; and the docs name `/clear` between unrelated tasks
as the single most effective lever for stretching usage - cheaper than any routing. One nuance worth
knowing: some models carry their own sub-limit on top of the shared pool - which models varies by
plan and changes over time, so check `/status` rather than memorising it; when a model-specific
limit runs dry, switching models keeps you working.

**Final review is always the lead's**, and it is not optional. This is what makes the whole
arrangement safe: cheap execution is only cheap if something competent checks it.

Every delegation carries the **complete slice spec**. Vague task descriptions are a documented cause
of subagents misinterpreting work and duplicating each other's effort.

## Isolation, and the setting that silently breaks it

Workers that write get their own git worktree, so their edits cannot collide mid-flight.

**Check `worktree.baseRef` before relying on this.** It defaults to `fresh`, which branches from the
default branch **on the remote** - so workers start from `origin/main`, not from your in-progress
work, and nothing warns you. To branch from where you actually are:

```json
{ "worktree": { "baseRef": "head" } }
```

Worktrees do not remove conflicts. They defer them to integration time, which is the point: they
become visible in one place, under review, instead of racing.

If the fan-out grows past what direct delegation can coordinate - many slices, several rounds, or
work that needs a deterministic pipeline - use a dynamic workflow instead of more subagents.

## Integrate sequentially

- Bring slices back **one at a time**. Parallel execution, serial integration.
- Run the **scoped** tests for each slice as it lands, not just at the end. A failure is cheap to
  attribute now and expensive later.
- Review each returned slice against its spec before integrating it, not after.
- When everything is in: verify the result against the **whole** spec, then run the full suite -
  tests, lint, typecheck, build.

## The loop each slice follows

Spec -> failing test -> implement -> review. Write the acceptance criteria first, then the test, and
**watch the test fail before implementing**. A test that has never been observed failing has proven
nothing about the code. One 2026 study (arXiv 2607.28871) measured 46% of repair agents' positive
validation evidence as carrying no bug-discriminating information; observing the red state is
precisely what makes the evidence discriminating.

`AGENTS.md` Section 0 still governs: a one-line change does not need any of this.

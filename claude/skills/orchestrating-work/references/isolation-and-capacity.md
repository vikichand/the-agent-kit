# Isolation, caps and capacity

Read before the first fan-out in a project. The skill's `SKILL.md` covers when and how to delegate;
this file covers the settings that make it safe and the economics that make it worth it.

## The worktree setting that silently breaks isolation

Workers that write get their own git worktree, so their edits cannot collide mid-flight.

**Check `worktree.baseRef` before relying on this** (Claude Code). It defaults to `fresh`, which
branches from the default branch **on the remote** - so workers start from `origin/main`, not from your
in-progress work, and nothing warns you. To branch from where you actually are:

```json
{ "worktree": { "baseRef": "head" } }
```

Worktrees do not remove conflicts. They defer them to integration time, which is the point: they become
visible in one place, under review, instead of racing.

If the fan-out grows past what direct delegation can coordinate - many slices, several rounds, or work
that needs a deterministic pipeline - use a dynamic workflow instead of more subagents.

## Concurrency caps

At most two workers active and one delegation layer. Claude Code enforces the caps with
`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; Codex with
`agents.max_concurrent_threads_per_session` and `agents.max_depth`. The kit's optional performance
profile sets both Claude Code caps and Codex's thread cap; it leaves `agents.max_depth` unset, so on
Codex the one-layer limit is this rule's to keep. Check the current names in each tool's docs before relying on them.

## Delegation stretches a subscription

Session and weekly limits are one shared pool across all models, but models drain that pool at very
different rates, and Anthropic's own cost guidance recommends a small model for simple subagent tasks.
So every mechanical slice a cheap worker executes is capacity the lead model keeps for judgement.

Two caveats: no vendor publishes a per-model multiplier, so never promise a number; and clearing the
context between unrelated tasks is the cheapest lever of all, cheaper than any routing. Some models carry
their own sub-limit on top of the shared pool, which varies by plan and changes over time, so check the
tool's status command rather than memorising it; when a model-specific limit runs dry, switching models
keeps you working.

**Final review stays with the lead**: cheap execution is only cheap if something competent checks it.

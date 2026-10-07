---
name: tidy
description: Run only when the user types /tidy (Codex: $tidy) or explicitly asks to clean up leftovers: stray or duplicate processes, merged branches, stale worktrees, tool output such as Playwright screenshots, and scratch files. It lists candidates first, asks group by group, and deletes nothing without a yes.
disable-model-invocation: true
---

# Tidy: find leftovers, ask, then remove only what the user approves

You are cleaning up after work, not deciding what the user still needs. The scanner finds candidates and
states the evidence; the user decides. Never delete, kill or remove anything the user has not approved in this
conversation, and never invent a cleanup command: removal goes through the scanner's `apply` step only.

## 1. Scan (read-only)

Run the scanner from the project root (or ask which folder if there is no git repo):

```sh
python ~/.the-agent-kit/hooks/tidy-scan.py scan --json
```

On Windows use `py -3` or `python`, whichever works. If the file is missing, tell the user to run
`~/.the-agent-kit/install.sh --setup` and stop. Add `--stale-days N` only if the user asks for a different age.
The scan changes nothing. It prints items with an `id`, a `group`, `evidence` and a `confidence`.

## 2. Show it, grouped

Summarise one group at a time, in this order, with a short table of label, why, and confidence. Say plainly when
a group is empty. Read [references/groups.md](references/groups.md) before the first run in a session: it says
what each group means and what the scanner never lists.

1. **processes.strays** (high): a dead parent plus an MCP-server pattern.
2. **processes.duplicates** (medium): the same dev server running twice for one project.
3. **processes.idle** (low): a dev server with no connection, no CPU and hours of age. Say it is a guess.
4. **branches** and **worktrees** (high or medium): merged branches, clean stale worktrees.
5. **tool_leftovers** (high or medium): Playwright output, old auto-named screenshots, empty agent worktree folders.
6. **candidates** (low): untracked files whose names look like leftovers, such as `*-plan.md`. They are
   candidates, never "stale": a file the user still needs can look exactly like one they do not.

## 3. Ask, group by group

For each non-empty group ask what to do. In Claude Code use the question tool; elsewhere ask in chat.
- Offer three answers: **keep all**, **remove all listed** (only for `high` and `medium` groups), **let me choose**.
- For `processes.idle` and `candidates` there is no "remove all": the user picks individual items, and nothing
  is preselected.
- Anything the user does not clearly approve is kept. Silence is a no.
- Show the exact items you are about to act on and wait for the yes.

## 4. Apply only what was approved

First a dry run of the approved ids, then the real thing:

```sh
python ~/.the-agent-kit/hooks/tidy-scan.py apply --ids ID1,ID2 --dry-run
python ~/.the-agent-kit/hooks/tidy-scan.py apply --ids ID1,ID2
```

`apply` re-checks every id against a fresh scan and skips any that changed. It never uses force flags, never
deletes a tracked file, never leaves the repository, and logs each action to `~/.the-agent-kit/tidy.log`.
Report what was removed, what was skipped and why, and where the log is. If something fails, say so and stop.

## Never

- Do not run `rm`, `kill`, `taskkill`, `git branch -D`, `git clean` or `git worktree remove --force` yourself.
- Do not remove anything that is not an id from the scan you just ran, and do not widen an approval ("yes to
  branches" is not a yes to files).
- Do not touch git-ignored private notes, tracked files, or anything outside the repository.
- Do not run this on your own. If the user did not ask for a tidy, say what you noticed and suggest `/tidy`.

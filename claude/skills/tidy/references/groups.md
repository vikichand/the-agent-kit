# What each group means

Read this before presenting a scan. The scanner is deliberately conservative: it would rather miss a leftover
than list something the user needs.

| Group | What it lists | Confidence | What it never lists |
|---|---|---|---|
| processes.strays | Process trees whose parent is dead (or adopted by an init-like manager such as systemd), that match an MCP-server pattern, and are older than 5 minutes | high | Anything with a live parent: another open agent session owns it |
| processes.duplicates | The same dev server (`next dev`, `vite`, `uvicorn`, and similar) running more than once for one project; the listening, newest copy is kept | medium, low when the older copy is itself listening on a port | MCP servers (each session legitimately runs its own); a process whose project cannot be identified |
| processes.idle | A dev server that is listening but has no connection, used no CPU over a short sample, and started hours ago (default 4) | low | Anything that is not a known dev-server command. This group is a guess, so it is always asked item by item |
| branches | Local branches merged into the default branch, or whose upstream is gone | high, medium when commits are not on the default | The current branch, the default branch, any branch checked out in a worktree |
| worktrees | Linked worktrees that are clean, not locked, with a merged branch or a missing directory | high, medium when detached | A dirty or locked worktree, the one you are standing in, the main worktree. A worktree holding git-ignored files (a `.env`, say) is listed as low, with the files named, and `apply` refuses it without `--allow-ignored`. Removing a worktree also deletes its merged branch, which the label names. Pruning a missing worktree removes every prunable entry together, so `apply` skips it unless all of them are approved |
| tool_leftovers | `.playwright-mcp`, `playwright-report`, `test-results`, `*.trace.zip`, empty folders under `.claude/worktrees/`, old auto-named screenshots at the repo root | high for named folders, medium for loose images | Tracked files |
| candidates | Untracked, not git-ignored files with leftover-looking names (`*-plan.md`, `*.orig`, `*.bak`, `*.log`, `scratch*`) older than the stale age | low | Git-ignored files (private notes live there), tracked files |

## Confidence in one line

High and medium mean the scanner can show the facts that make it safe (merged, clean, dead parent). Low means
it is a guess the user must judge, so it is never offered as "remove all".

## Undoing

- A deleted branch: `git reflog` still holds its tip for a while; `git branch <name> <sha>` brings it back.
- A removed worktree: the branch and its commits remain; re-add it with `git worktree add`.
- Deleted files and killed processes cannot be undone. That is why the user approves them first.

## The log

Every applied action is appended to `~/.the-agent-kit/tidy.log` with a timestamp, the id and the result.

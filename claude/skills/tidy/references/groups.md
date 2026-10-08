# What each group means

Read this before presenting a scan. The scanner is deliberately conservative: it would rather miss a leftover
than list something the user needs. It looks only at this repository: its files, branches, worktrees (the
linked ones too) and the processes working in them.

| Group | What it lists | Confidence | What it never lists |
|---|---|---|---|
| processes.strays | Process trees working in the repo whose parent is dead (or adopted by an init-like manager such as systemd), that match an MCP-server pattern, and are older than 5 minutes | high, low when the tree listens on a port (someone may have started it on purpose) | Anything with a live parent: another open agent session owns it. Orphan MCP trees working elsewhere on the machine become one note pointing at `install.sh --tidy` |
| processes.duplicates | The same dev server (`next dev`, `vite`, `uvicorn`, and similar) running more than once for one project in the repo; the listening, newest copy is kept | medium, low when the older copy is itself listening, or when socket state could not be read | MCP servers (each session legitimately runs its own); a process whose project cannot be identified |
| processes.idle | A dev server in the repo that is listening but has no connection, used no CPU over a short sample, and started hours ago (default 4) | low | Anything that is not a known dev-server command. This group is a guess, so it is always asked item by item |
| processes.unknown | A process in the repo that matches no known pattern but listens on a port or has run for hours. Facts only: working folder, age, port and connection, CPU, who started it. At most 20 | low | Editors, shells, agent CLIs (found by the script they run, never by `node`), live MCP servers, dev servers, and any process whose working folder cannot be read |
| branches | Local branches merged into the default branch, or whose upstream is gone | high, medium when commits are not on the default, low when the branch has no commits of its own | The current branch, the default branch (and what `origin/HEAD` names), `main`, `master`, `develop`, `dev`, `trunk`, `staging`, `production`, `prod`, `gh-pages`, `release/*`, `hotfix/*`, any branch checked out in a worktree |
| worktrees | Linked worktrees that are clean, not locked, with a merged branch or a missing directory | high, medium when detached, low with no commits of its own | A dirty or locked worktree, the one you are standing in, the main worktree, a worktree with no commits of its own that is younger than the stale age, a worktree some process is working in. A worktree holding git-ignored files (a `.env`, say) is listed as low, with the files named, and `apply` refuses it without `--allow-ignored`. Removing a worktree also deletes its merged branch (never a long-lived one), which the label names. Pruning a missing worktree removes every prunable entry together, so `apply` skips it unless all of them are approved |
| tool_leftovers | `.playwright-mcp`, `playwright-report`, `test-results` (at any depth), `*.trace.zip`, empty folders under `.claude/worktrees/`, old auto-named screenshots at the repo root | high for tool folders holding only tool output, low when other files are inside (they are named); medium for loose images | Tracked files; a tool folder written in the last hour, one holding a nested `.git`, one hidden by `.git/info/exclude` |
| candidates | Untracked, not git-ignored files with leftover-looking names (`*-plan.md`, `*.orig`, `*.bak`, `*.log`, `scratch*`) older than the stale age | low | Git-ignored files, tracked files |
| unknown | Untracked and git-ignored paths no other group names. Facts only: kind, size, file count, newest file age, the ignore rule, tracked references, common extensions. At most 40, biggest and oldest first | low | `node_modules`, build output and caches, lockfiles, nested repos, linked worktrees, anything hidden by `.git/info/exclude` (counted in a note), and secret-like names (`.env*`, `*.pem`, `*.key`, credentials: named in a note, never sized or listed, and a folder holding one is hidden) |

## Confidence in one line

High and medium mean the scanner can show the facts that make it safe (merged, clean, dead parent). Low means
it is a guess the user must judge, so it is never offered as "remove all".

## Undoing

- A deleted branch: `git reflog` still holds its tip for a while; `git branch <name> <sha>` brings it back.
- A removed worktree: the branch and its commits remain; re-add it with `git worktree add`.
- Deleted files and killed processes cannot be undone. That is why the user approves them first.

## The log

Every applied action is appended to `~/.the-agent-kit/tidy.log` with a timestamp, the id and the result.

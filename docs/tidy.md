# /tidy: find leftovers, ask, then remove only what you approve

After a long session a repo collects leftovers: a dev server still running, merged branches, stale worktrees,
Playwright screenshots, a `*-plan.md` nobody needs. `/tidy` lists them with the evidence for each one and asks
you group by group. It removes nothing you did not say yes to.

## Who runs it

You do. It is user-invoked only.

| Tool | How you run it | Can the agent start it on its own? |
|---|---|---|
| Claude Code | `/tidy` | No. The skill sets `disable-model-invocation: true` (Claude Code skills docs, checked 2026-10-08). |
| Codex | `$tidy`, or pick it from `/skills` | No. `agents/openai.yaml` sets `policy.allow_implicit_invocation: false` (Codex skills docs, checked 2026-10-08). |
| Antigravity | ask for a tidy in chat | Possibly. Its skill frontmatter documents only `name` and `description`, so it cannot be made user-only there. |

On Antigravity the agent could start the read-only scan by itself. Every removal still needs your yes in chat
and goes through the scanner's checks.

The skill needs the scripts at `~/.the-agent-kit/hooks/`, which `install.sh --setup` installs.

## The six groups

| Group | What it lists | Confidence | Remove all offered? |
|---|---|---|---|
| processes.strays | MCP-server process trees whose parent is dead, older than 5 minutes | high | yes |
| processes.duplicates | the same dev server running twice for one project; the listening, newest copy is kept | medium | yes |
| processes.idle | a dev server that listens but has no connection, no CPU and hours of age | low | no, item by item |
| branches and worktrees | local branches merged or with a gone upstream; clean, unlocked, stale worktrees | high or medium (low for a worktree holding git-ignored files) | yes, except low items |
| tool_leftovers | `.playwright-mcp`, `playwright-report`, `test-results`, `*.trace.zip`, empty `.claude/worktrees/` folders, old auto-named screenshots | high or medium | yes |
| candidates | untracked files with leftover-looking names (`*-plan.md`, `*.orig`, `*.bak`, `*.log`, `scratch*`) | low | no, item by item |

High and medium mean the scanner can show the facts that make it safe (merged, clean, dead parent). Low means
a guess you must judge. What each group never lists is in
[`claude/skills/tidy/references/groups.md`](../claude/skills/tidy/references/groups.md).

## The flow

1. **Scan.** `tidy-scan.py scan` is read-only. It prints items with an id, group, evidence and confidence.
2. **Show.** The agent summarises one group at a time and says when a group is empty.
3. **Ask per group.** Keep all, remove all listed (high and medium groups only), or let me choose. Silence
   counts as no.
4. **Dry run.** `apply --ids ... --dry-run` shows what would happen.
5. **Apply.** `apply --ids ...` re-checks each id against a fresh scan and skips any that changed.
6. **Log.** Every applied action is appended to `~/.the-agent-kit/tidy.log` with a timestamp, the id and the result.

## What it never touches

- Tracked files.
- Git-ignored files. Private notes live there, so they are never listed as candidates.
- Anything outside the repository.
- A process with a live parent (another open agent session owns it), the current branch, the default branch,
  dirty or locked worktrees.
- Nothing runs with force flags. The agent does not run `rm`, `kill`, `git branch -D` or `git clean` itself.

## Safety checks

- A worktree that holds git-ignored files (a `.env`, say) is low confidence, lists them, and `apply` refuses it
  unless run with `--allow-ignored`, which the agent passes only after you approved that item having seen them.
- A duplicate dev server that is itself listening on a port is low confidence and asked item by item.
- Removing a worktree also deletes its merged branch; the label says so. Missing worktrees are pruned all
  together, so `apply` skips them unless you approved every prunable one.
- Labels and evidence come from the repository, so control characters are stripped and the agent treats them as
  data. `git` is resolved from `PATH` only, never the current folder, and `--stale-days` must be 0 or more.

## Undo

| Removed | Can it come back? |
|---|---|
| A branch | Usually. `git reflog` holds its tip for a while: `git branch <name> <sha>`. |
| A worktree | The branch and commits remain. Re-add it with `git worktree add`. |
| A file or a killed process | No. That is why you approve them first. |

## Run the scanner by hand

```sh
python ~/.the-agent-kit/hooks/tidy-scan.py scan --json
python ~/.the-agent-kit/hooks/tidy-scan.py apply --ids ID1,ID2 --dry-run
python ~/.the-agent-kit/hooks/tidy-scan.py apply --ids ID1,ID2
```

On Windows use `py -3` or `python`. Options for both commands: `--root PATH` (default: the current folder) and
`--stale-days N` (default 14). `scan` also takes `--json`; `apply` also takes `--dry-run` and `--allow-ignored`. `tidy-procs.py` handles the process groups and is
called by the scanner.

## Limits

- **Antigravity** cannot be made user-only, as above.
- **POSIX process listing is not verified live.** The `ss` and `lsof` paths have unit tests on canned text only
  and have not been run on a real Linux or macOS machine.
- **Idle is a guess.** A dev server with no connection and no CPU may be one you still want. That is why it is
  always asked item by item.
- **Candidates are names, not judgments.** The scanner cannot know whether you still need a document.
- Not in this version: deleting tracked files, killing anything automatically, deciding which documents are
  still needed, a session-start warning.

## What was measured

The process scanner has 54 tests and the git and files scanner has 38. They include real throwaway repos and a
live Windows test that starts two listeners and checks only the approved one dies. A real scan of this
repository found exactly the two known leftovers. No adherence eval applies: `/tidy` is user-invoked, not an
always-on rule.

# /tidy: find leftovers, ask, then remove only what you approve

After a long session a repo collects leftovers: a dev server still running, merged branches, stale worktrees,
Playwright screenshots, a `*-plan.md` nobody needs. `/tidy` lists them with the evidence for each one and asks
you group by group. It removes nothing you did not say yes to, and it looks only at the repository it runs in:
its files, branches, worktrees and the processes working in them.

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

## The groups

| Group | What it lists | Confidence | Remove all offered? |
|---|---|---|---|
| processes.strays | MCP-server process trees working in the repo whose parent is dead, older than 5 minutes | high (low if the tree listens on a port) | yes, except low items |
| processes.duplicates | the same dev server running twice for one project; the listening, newest copy is kept | medium (low if the older copy listens, or sockets could not be read) | yes, except low items |
| processes.idle | a dev server that listens but has no connection, no CPU and hours of age | low | no, item by item |
| processes.unknown | a process in the repo that matches no known pattern but listens or has run for hours, with facts (at most 20) | low | no, item by item |
| branches and worktrees | local branches merged or with a gone upstream; clean, unlocked, stale worktrees | high or medium (low for a worktree or branch with no commits of its own, or a worktree holding git-ignored files) | yes, except low items |
| tool_leftovers | `.playwright-mcp`, `playwright-report`, `test-results` (at any depth), `*.trace.zip`, empty `.claude/worktrees/` folders, old auto-named screenshots | high or medium (low when the folder also holds other files, which are named) | yes, except low items |
| candidates | untracked files with leftover-looking names (`*-plan.md`, `*.orig`, `*.bak`, `*.log`, `scratch*`) | low | no, item by item |
| unknown | untracked or git-ignored paths no other group names, with facts: size, age, the ignore rule, what references it (at most 40) | low | no, item by item |

High and medium mean the scanner can show the facts that make it safe (merged, clean, dead parent). Low means
a guess you must judge. What each group never lists is in
[`claude/skills/tidy/references/groups.md`](../claude/skills/tidy/references/groups.md).

## How a process counts as this repository's

A process is in scope when its working folder is inside the repo or one of its linked worktrees. A working
folder that can be read decides alone; an absolute path in the command line inside the repo counts only when the
folder cannot be read. The scanner reads another process's working folder through the Windows
process block, `/proc/<pid>/cwd` on Linux and `lsof` on macOS. A folder it cannot read, with no such path, means
the process is not listed (a note counts them), and an orphaned MCP tree working somewhere else becomes one note that points to
`~/.the-agent-kit/install.sh --tidy`. Editors and agent CLIs are never listed; the agent CLIs are recognised by
the script they run, because on Windows `claude`, `codex` and every dev server are all `node.exe`. A scope is
refused when it is the home folder, a folder that holds it (`C:\Users`, `/home`), a filesystem root or a system folder
(the Windows folder, Program Files, `/usr/bin`, `/usr/lib` and similar; `/usr/src/app` is allowed). Outside a
repository the scope is the folder you ran `/tidy` in, unless a repository sits one or two levels below it: then no
process is scoped and a note says to run `/tidy` inside one of them. That check looks only one and two levels down,
so a folder whose repositories sit three or more levels deep is not detected (a known limit): run `/tidy` inside a
repository.

## Unknown items

Patterns cannot keep up with every tool that leaves files behind. The `unknown` groups give the agent facts and
a short set of rules (in `SKILL.md`), and the agent says what each one most likely is and who made it. It
proposes only what is clearly regenerable tool output or a leftover it can name, never source code, documents you
may have written, anything a tracked file references or anything secret-like. You still decide, item by item.
Paths hidden by `.git/info/exclude`, `node_modules` and build output, nested repos and secret-like names such
as `.env.backup` are never listed (the scan says that secret-like files exist, by name only).

## The flow

1. **Scan.** `tidy-scan.py scan` is read-only. It prints items with an id, group, evidence and confidence.
2. **Show.** The agent summarises one group at a time and says when a group is empty.
3. **Ask per group.** Keep all, remove all listed (high and medium groups only), or let me choose. Silence
   counts as no.
4. **Dry run.** `apply --root ROOT --id ... --dry-run` shows what would happen.
5. **Apply.** `apply --root ROOT --id ...` re-checks each id against a fresh scan and skips any that changed.
6. **Log.** Every applied action is appended to `~/.the-agent-kit/tidy.log` with a timestamp, the id, the result and the repo root.

## What it never touches

- Anything that is not this repository's files, branches, worktrees or processes. Worktrees can live outside the
  repo folder; they are the repo's own, so they count. Another project's dev server does not.
- Tracked files.
- Long-lived branches (`main`, `master`, `develop`, `release/*`, `hotfix/*`, whatever `origin/HEAD` names), the
  current branch, dirty or locked worktrees, and a worktree or branch with no commits of its own that is newer
  than the stale age (it may have just been made). A worktree some process is working in is skipped.
- Your notes and uncommitted work. Paths hidden by `.git/info/exclude` are never listed. Outside dot-folders,
  documents (notes, plans, office files), git-ignored or not, and untracked source or config are never listed
  either: the scan only counts them in a note. A tool folder such as `test-results` is deleted only when it holds nothing but tool
  output and has not been written in the last hour; otherwise it is low and the odd files are named.
- A process with a live parent (another open agent session owns it), editors, shells and agent sessions.
- Nothing runs with force flags. The agent does not run `rm`, `kill`, `git branch -D` or `git clean` itself.

## Safety checks

- A worktree that holds git-ignored files (a `.env`, say) is low confidence, lists them, and `apply` refuses it
  unless run with `--allow-ignored`, which the agent passes only after you approved that item having seen them.
- A duplicate dev server that is itself listening on a port is low confidence and asked item by item. So is
  every duplicate when the socket listing is unavailable, because then "newest" is a guess.
- `apply` passes the same repository scope to the process scanner and re-scans inside it, so an id copied from
  another repo's scan no longer matches and is skipped.
- On Claude Code and Antigravity the command guard asks before `tidy-scan.py apply`, `tidy-procs.py apply`
  (dry runs included, so a stray `--dry-run` token cannot buy silence) and `mcp-orphans.py --kill`, so the prompt does not depend on the model following the
  skill. Codex hooks cannot ask, so there the skill's own confirmation is the gate.
- Removing a worktree also deletes its merged branch, and only when the item's label names it (this holds for
  missing worktrees too). Missing worktrees are pruned all together, so `apply` skips them unless you approved
  every prunable one. If `git status` cannot be read in a worktree, it is low confidence and `apply` refuses it.
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
python ~/.the-agent-kit/hooks/tidy-scan.py apply --root ROOT --id ID1 --id ID2 --dry-run
python ~/.the-agent-kit/hooks/tidy-scan.py apply --root ROOT --id ID1 --id ID2
```

On Windows use `py -3` or `python`. Options for both commands: `--root PATH` and `--stale-days N` (default 14).
`scan` defaults `--root` to the current folder; `apply` requires it, set to the `root` the scan reported, so the
ids act on the repo you scanned. `apply` takes each id with a repeated `--id` (never split on commas; `--ids A,B`
still works) and also `--dry-run` and `--allow-ignored`. Items with a comma in the name are not listed. `scan` also takes `--json`. `tidy-procs.py` handles the process groups and is
called by the scanner with one `--root` per folder of the repo (the root and each linked worktree); it refuses to
run without one.

## Limits

- **Antigravity** cannot be made user-only, as above.
- **POSIX process listing is not verified live.** The `ss` and `lsof` paths, and the `/proc` and `lsof` reads
  of a process's working folder, have not been run on a real Linux or macOS machine; the live scope test runs
  on Windows only. A 32-bit Windows process has an unreadable folder and is never listed.
- **The guard's prompt is not verified under bypass-permissions mode.** The Claude Code hooks reference does not
  say whether a hook's `ask` still prompts there (checked 2026-10-09).
- **Idle is a guess.** A dev server with no connection and no CPU may be one you still want. That is why it is
  always asked item by item.
- **Candidates are names, not judgments.** The scanner cannot know whether you still need a document.
- Not in this version: deleting tracked files, killing anything automatically, deciding which documents are
  still needed, a session-start warning.

## What was measured

The process scanner has 98 cases and the git and files scanner has 80. They include real throwaway repos and a
live Windows test that starts two listeners in two folders and checks that a scan scoped to one lists only its
server, refuses the other's id, and kills only the approved one. No adherence eval applies: `/tidy` is
user-invoked, not an always-on rule.

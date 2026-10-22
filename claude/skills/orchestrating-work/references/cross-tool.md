# Handing work to another agent CLI

Read this before a lead in one tool (Claude Code, Codex or Antigravity) gives a slice of work to another.
The worker contract (section 2 of the skill) does not change; only the mechanics do.

## The brief is a file

Write the section 2 contract to a file in the worker's working directory (`brief.md`) and tell the worker
to read it. Never paste a long brief into a shell argument: quoting breaks and long arguments are cut off.
Reference specs, plans and diffs by path; do not copy them in. Do not restate `AGENTS.md`: Codex and
Antigravity read the project's `AGENTS.md` themselves. Name where the result goes (`result.md`).

If the Codex plugin for Claude Code is installed, prefer its commands for delegating to Codex; otherwise
use the CLI as below. Check flags with `--help` on the installed version before relying on them.

## Commands

| Need | Codex CLI | Antigravity CLI |
|---|---|---|
| Read-only task | `codex exec -C <dir> --json -o result.md - < brief.md` (read-only is the default sandbox) | `agy -p "Read brief.md and carry it out." --mode plan --output-format json --print-timeout <secs>s` |
| Task that edits files | add `-s workspace-write`, in a dedicated worktree | `--mode accept-edits` instead of `plan`, in a dedicated worktree |
| Model and effort | `-m <model> -c model_reasoning_effort="<level>"` | `--model <model> --effort <level>` |
| Follow-up turn | `codex exec resume <thread_id> -c 'sandbox_mode="workspace-write"' -o result.md - < brief2.md`; the thread id is in the first `--json` event | `agy -p "<prompt>" --conversation <conversation_id>`; the id is in the JSON result |
| The answer | the `-o` file | the `response` field of the JSON result |

- `codex exec resume` has no `-s` or `-C`: a follow-up that edits files must restate the sandbox with
  `-c 'sandbox_mode="workspace-write"'`, or it runs read-only.
- A headless `agy` run waits forever on a permission prompt. `plan` and `accept-edits` were verified to
  finish read-only and file-edit tasks without one; whether a shell command in `accept-edits` prompts is
  not verified, so set `--print-timeout` and an outer timeout. Never pass
  `--dangerously-skip-permissions` unless the user approved it for that run.
- Judge the result, not the exit code: Antigravity exits 0 even when a tool call was denied. Read the
  result, then check the worktree with `git diff` and the slice's own checks (section 5 of the skill).
- The worker never commits unless the brief says so.

## Handing back

When Codex or Antigravity is the lead, the same brief file works for Claude Code:
`claude -p "Read brief.md and carry it out." --output-format json`, and `--resume <session_id>` for a
follow-up.

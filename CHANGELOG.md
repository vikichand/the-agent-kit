# Changelog

Every user-visible change to the-agent-kit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the major moves when an
update changes what an installed project must do, the minor when rules or tooling are added, the
patch for fixes.

Each entry says what you get, not how the code does it. `develop` carries the commits; each release is
one squashed commit on `main`, tagged, with that version's section below as its message. See
[`docs/branches-and-releases.md`](docs/branches-and-releases.md).

## [Unreleased]

### Added

- This repository records its own branch model, gates and careful zones in the project block of
  `AGENTS.md`, so an agent working on the kit knows to push to `develop` and never to `main` without
  being told. The per-project setup prompt asks every project the same question.
- **Release-only branches are enforced.** A project marks one in its block with
  `<!-- agent-kit: release-branch=main -->`, and the pre-push hook then refuses every push to it that is
  not a release (`AGENT_KIT_RELEASE=1`), including a push that deletes the marker on its way in. The
  tool guard asks before any command that sets that flag or the force override, however the name is
  quoted, and no chat request covers either.
- **GitHub Actions pinned to a floating tag are blocked at commit time.** The eval showed the rule does
  not fire from wording alone; the pre-commit hook now checks the workflow lines you add.
- **A session-start check** tells you when a newer release is on `main` and when a project's rules
  differ from your installed kit. Silent when everything is current, at most one network call a day,
  never updates anything itself. Opt out with `AGENT_KIT_NO_UPDATE_CHECK=1`.
- `install.sh --check` warns when a project's block has no Branches line, so installs set up before this
  release find out.

### Fixed

- A fresh install no longer inherits this repository's own project block. `install.sh` writes the
  rules with an empty block instead of copying `AGENTS.md` verbatim.
- `install.sh --check` counts the project block against the 200-line budget. It had been treating the
  block's `PROJECT-CONFIG` markers as one long comment and excluding everything between them, so it
  under-reported every filled install by the size of its block.
- The machine-wide copy of the rules no longer carries this repository's own project block, which the
  "prefer the rules global" instructions would have appended to your global rules.
- The tool guard no longer refuses a commit whose message, written through a heredoc, merely mentions a
  guarded string such as the hooks-path setting. Only a body that cannot run is skipped: a quoted
  delimiter, or an unquoted one with no command substitution in it. Every other heredoc is still
  scanned as code.
- The eval harness records usage-limit and auth failures as ERROR again. A syntax error in its
  detector had been scoring every one as an ordinary failure since the harness gained the check.
- Eval cases 09, 10 and 11 no longer fail for asking before adding a dependency: their fixtures now
  declare the client libraries the task needs (case 09 uses the standard library's unittest), so
  they measure what their rubric grades.
- The eval harness's test-first check reads each run's own result. It had been pairing a test run
  with the result of an edit sent in the same message, and counting "# fail 0" as a failure, so a
  genuine red-then-fix run could score as "edited before any failing test" and a green-then-edit run
  could pass. On Codex a piped test run is now read from its output, not only its exit code. Five
  offline checks in the free suite now cover the harness's own oracles.
- A high-risk eval case can accept a grounded stop-and-ask (`ask-ok` marker): the no-edit answer is
  judged under a strict bar instead of failing unread. Cases 30 and 33 carry it.

## [1.0.0] - 2026-09-26

First release. Everything below is what a fresh install gives you.

### Added

- **The rules.** An always-on `AGENTS.md` (193 effective lines) that gets an agent working like a
  senior engineer: safety invariants that hold at every task size, then Sections 0 to 10 covering task
  sizing by risk and proof, reading before writing, blast radius, simplicity and reuse, surgical
  diffs, verification with an external oracle, root-cause debugging, context discipline, execution
  discipline, ownership and documentation. A one-line `CLAUDE.md` imports it, so Claude Code and
  Codex read the same file.
- **A depth tier that costs nothing until it applies.** Six path-scoped rules that load only when the
  agent opens a matching file: `web-security`, `code-correctness`, `data-layer`, `frontend-quality`,
  `tests`, `ci-cd`. On Codex, four of them ship as task-matched skills instead, because Codex has no
  path-scoped rules.
- **Three skills**, loaded when a task matches: `orchestrating-work` (when to fan out, and the caps
  that keep it from costing more than it saves), `generating-reports` (Markdown as the source of
  truth, a styled HTML render for anything a human will read), `writing-docs` (prose standards and
  README order).
- **Guards at the git layer**, so they hold for any tool that writes a commit: `commit-msg` strips
  AI-attribution and agent session-link trailers, `pre-commit` blocks staged secrets, `pre-push`
  refuses force, delete and non-fast-forward pushes to protected branches.
- **A guard at the tool layer**: a prompt-time hook that asks on Claude Code and denies on Codex for
  dependency installs, secret reads, destructive commands and hook-disable attempts.
- **Turn-scoped git-write grants.** The agent commits, pushes or opens a PR only when you ask for that
  operation in that turn; the grant is spent when used, and merges always prompt.
- **An installer** with five modes: per-project, `--extension` for projects whose rules live globally,
  `--global` for the machine-wide guards, `--update`, `--update-rules`, and `--check`, a doctor that
  reports what is actually live rather than what is installed.
- **Setup prompts** you run once: per project (writes the `PROJECT-CONFIG` block with your real build
  and test commands), per machine (MCP servers, plugins and skills), and a quarterly staying-current
  pass. Plus web launch checklists and two optional drop-in rules for browser tooling and Context7.
- **An adherence eval harness.** 37 cases run the same task with and without the rules, graded by a
  blind judge, with three arms, per-cell timing and token telemetry, and trace assertions for things
  a rubric cannot see. Its README carries the acceptance contract and the measured results, including
  the ones that came out negative.
- **An optional performance profile** for both tools: a capable lead at medium effort, cheap models
  for bounded worker tasks, and subagent caps. Not installed by default; it is an experiment with its
  measurement named.

### Measured

- On Sonnet, rule compliance rose from 71.4% to 88.9% on the first 14-case suite and from 68.9% to
  88.6% on the second. On Opus the tested rules showed no gap: it already did those things unprompted.
- Two rules do not fire reliably and are named rather than hidden: pinning a CI action to a digest
  fails in both arms and needs an enforced check, and the comment-density rule passes in both arms on
  the one case that grades it.
- The 2026-09 performance pass is measured only in part, and the harness README says so.

[Unreleased]: https://github.com/vikichand/the-agent-kit/compare/v1.0.0...develop
[1.0.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v1.0.0

# Changelog

Every user-visible change to the-agent-kit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the major moves when an
update changes what an installed project must do, the minor when rules or tooling are added, the
patch for fixes. Below 1.0.0, a minor version may also change what an installed project must do.

Each entry says what you get, not how the code does it. `develop` carries the commits; each release is
one squash-merged pull request on `main`, tagged, with that version's section below as its message.
See [`docs/branches-and-releases.md`](docs/branches-and-releases.md).

## [Unreleased]

## [0.1.0] - 2026-09-28

First public release: the rules and guardrails I've worked out over two years of building with coding
agents. Everything below is what a fresh install gives you.

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
- **Guards at the git layer**, so they hold for any tool that writes a commit:
  - `commit-msg` strips AI-attribution and agent session-link trailers;
  - `pre-commit` blocks staged secrets, and GitHub Actions steps pinned to a floating tag (`@v4`,
    `@main`) on the workflow lines you add;
  - `pre-push` refuses force, delete and non-fast-forward pushes to protected branches, and every
    push to a branch your project marks release-only.
- **A guard at the tool layer**: a prompt-time hook that asks on Claude Code and denies on Codex for
  dependency installs, secret reads, destructive commands, hook-disable attempts and any command that
  sets the release or force override. A commit message passed through a heredoc that cannot run is
  treated as prose, not scanned as commands.
- **Turn-scoped git-write grants.** The agent commits, pushes or opens a PR only when you ask for that
  operation in that turn; the grant is spent when used, and merges always prompt.
- **An installer** with six modes: per-project, `--extension` for projects whose rules live globally,
  `--global` for the machine-wide guards, `--update`, `--update-rules`, and `--check`, a doctor that
  reports what is actually live rather than what is installed.
- **A session-start check** that stays silent unless something needs you: a newer release on `main`
  (checked at most once a day), this project's rules differing from your installed kit, or a
  recommended tool missing for the agent in use. Recommendations come from your own
  `~/.the-agent-kit/recommended.json`: Context7 everywhere, and in web projects Playwright, Chrome
  DevTools, Impeccable and `frontend-design`. It never installs or updates anything itself.
- **Setup prompts** you run once: per project (writes the `PROJECT-CONFIG` block with your real build
  and test commands and your branch model), per machine (MCP servers, plugins and skills in Core, Web
  and UI, and Optional profiles), and a quarterly staying-current pass. Plus web launch checklists and
  two optional drop-in rules for browser tooling and Context7.
- **An adherence eval harness.** 37 cases run the same task with and without the rules, graded by a
  blind judge, with three arms, per-cell timing and token telemetry, trace assertions for things a
  rubric cannot see, and provider failures recorded as errors rather than scores. Its README carries
  the acceptance contract and the measured results, including the ones that came out negative.
- **An optional performance profile** for both tools: a capable lead at medium effort, cheap models
  for bounded worker tasks, and subagent caps. Not installed by default; it is an experiment with its
  measurement named.

### Measured

- On Sonnet, rule compliance rose from 71.4% to 88.9% on the first 14-case suite and from 68.9% to
  88.6% on the second. On Opus the tested rules showed no gap: it already did those things unprompted.
- The current rules against the text before their 2026-09 rewrite, on Sonnet across 33 cases: 95.5%
  against 89.1%, no case worse. One historical batch clears the contract's 5-point bar, the other
  misses it by 0.2 points at 3 runs per cell, and the rewrite did not make small tasks faster. On
  Codex the measurement is partial.
- Pinning CI actions to a commit did not fire reliably from wording alone, so it is enforced by the
  pre-commit hook. The comment-density rule passes with and without the rules on the one case that
  grades it.

[Unreleased]: https://github.com/vikichand/the-agent-kit/compare/v0.1.0...develop
[0.1.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.1.0

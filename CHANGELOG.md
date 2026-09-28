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

First public release: the rules and guardrails I've worked out over the years of building with coding
agents. A fresh install gives you everything below.

### Added

- **Rules** in `AGENTS.md` (193 lines, read every turn) that get an agent working like a senior
  engineer: read first, name the blast radius, test first, fix the cause, keep diffs small, commit only
  when asked. `CLAUDE.md` imports it, so Claude Code and Codex share one file.
- **Depth rules** for security, correctness, data, frontend, tests and CI that load only when the agent
  works in matching files (as skills on Codex).
- **Three skills:** orchestrating subagents, writing reports, and writing docs, commits, pull requests
  and release notes.
- **Git hooks** that work with any tool:
  - `commit-msg` strips AI-attribution and session-link trailers;
  - `pre-commit` blocks staged secrets and GitHub Actions pinned to a moving tag;
  - `pre-push` blocks force, delete and non-fast-forward pushes to protected branches, and any push to
    a branch your project marks release-only.
- **A command guard** that asks (Claude Code) or refuses (Codex) before dependency installs, secret
  reads, destructive commands, disabling the hooks, or setting a release or force override.
- **Git actions only when asked:** the agent commits, pushes or opens a PR only when you ask for it in
  that turn.
- **An installer** for a project, machine-wide guards, updates and a `--check` doctor that reports what
  is actually live.
- **A session-start check**, silent unless something needs you: a newer release, project rules that
  have drifted, or a recommended tool you are missing. It never installs anything itself.
- **Setup prompts** for each project (build and test commands, branch model), each machine (MCP servers,
  plugins and skills by profile) and a quarterly review; plus web launch checklists.
- **An eval harness:** 37 cases, run with and without the rules and graded blind, with timing, tokens and
  published results.

### Measured

- On Sonnet the rules raised compliance from 71.4% to 88.9% and from 68.9% to 88.6% on two 14-case
  suites. On Opus they made no difference: it already behaved that way.
- The 2026-09 rewrite of the rules scored 95.5% against 89.1% for the previous text across 33 cases,
  with no case worse, but did not make small tasks faster. Codex results are partial.
- Pinning CI actions did not happen reliably from wording alone, so the pre-commit hook enforces it.

[Unreleased]: https://github.com/vikichand/the-agent-kit/compare/v0.1.0...develop
[0.1.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.1.0

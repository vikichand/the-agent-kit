# Changelog

Every user-visible change to the-agent-kit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the major moves when an
update changes what an installed project must do, the minor when rules or tooling are added, the
patch for fixes. Below 1.0.0, a minor version may also change what an installed project must do.

Each entry says what you get, not how the code does it. `develop` carries the commits; each release is
one squash-merged pull request on `main`, tagged, with that version's section below as its message.
See [`docs/branches-and-releases.md`](docs/branches-and-releases.md).

## [Unreleased]

### Changed

- **Never assume: facts are looked up, decisions are asked.** One rule in Section 1 replaces three:
  anything the code, tests, docs or tools can answer is the agent's to find, never a guess and never a
  question; what only the user can decide is asked with a recommended answer; a small detail with an
  obvious default is picked and stated in a line. On-request "grill mode" is gone in favour of the next
  item.
- **High-risk work asks its open decisions before building.** Section 0's high-risk tier now puts the
  decisions the request leaves to the user in one round, each with a recommendation, and waits.
- A check that never ran is not a check: a syntax-only check, or one that failed to start, does not
  count as verification (Section 5).
- Checkpoints also record what is verified versus only claimed, and which approaches failed (Section 7).
- The tests depth rule says what repairing a failing test may change (selectors, waits, setup, stale
  fixtures) and what needs the specification to say so (what the test expects).

### Added

- Three eval cases for the never-assume rule: look a fact up instead of asking (38), ask the real
  decision instead of guessing (39), state a small default instead of asking (40).

## [0.3.0] - 2026-10-04

### Changed

- **Browser work: the Playwright CLI and its skill are now the recommendation**, with the Playwright MCP
  kept for exploratory or long-running browser sessions. Playwright's own docs recommend the CLI for
  coding agents because it keeps tool schemas and page trees out of the context. The session-start
  check suggests the `playwright-cli` skill in web projects. Existing installs keep their own
  `recommended.json`; edit it, or delete it and re-run `--setup`, to pick this up.
- The optional Codex performance profile names the models Codex currently offers (`gpt-6-sol`,
  `gpt-6-luna`) and says to check your own plan's list with `codex debug models`.

### Fixed

- The optional Claude performance profile now actually sets effort on current models: Opus 5.5 and
  later ignore the top-level `effortLevel`, so it also sets `modelSettings` for `opus` and `sonnet`.
- An install from a working copy no longer copies the maintainer's git-ignored notes from `docs/`
  (plans, research, todo lists) into `~/.the-agent-kit`: the installer now copies only docs git would
  publish.

## [0.2.0] - 2026-09-29

### Added

- **One command sets up a machine:** `install.sh --setup` copies the kit, turns on its git hooks and
  adds it to your Claude Code and Codex settings. It lists every change, asks first, backs each file
  up, only adds, and keeps anything you already set.
- `install.sh --check` now checks that your settings actually carry the kit's guard and session-start
  check.

### Changed

- `--update` runs `--setup` from the new release, so new hooks and settings reach you the same way.
- The README's Quick Start is three commands: set up the machine, set up a project, check.
- The environment setup prompt now warns that routing Claude Code through Headroom turns off Remote
  Control, and says how to keep Remote Control while Codex still uses Headroom.
- An agent cannot answer the setup's question, so it lists the changes and stops; applying them takes
  `AGENT_KIT_APPLY=1`, which the tool guard asks you about. An update never applies settings by itself.

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

[Unreleased]: https://github.com/vikichand/the-agent-kit/compare/v0.3.0...develop
[0.3.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.3.0
[0.2.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.2.0
[0.1.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.1.0

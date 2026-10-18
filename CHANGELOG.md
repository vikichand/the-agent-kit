# Changelog

Every user-visible change to the-agent-kit. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): the major moves when an
update changes what an installed project must do, the minor when rules or tooling are added, the
patch for fixes. Below 1.0.0, a minor version may also change what an installed project must do.

Each entry says what you get, not how the code does it. `develop` carries the commits; each release is
one squash-merged pull request on `main`, tagged, with that version's section below as its message.
See [`docs/branches-and-releases.md`](docs/branches-and-releases.md).

## [Unreleased]

### Added

- **`/tidy`, a user-invoked cleanup skill for the repository you are in.** It lists leftovers (stray,
  duplicate and idle dev servers started for this repo, merged branches, stale worktrees, Playwright output,
  scratch files) and asks per group before removing anything, with a dry run and a log. Processes count only
  when they run in this repo or its worktrees; orphaned MCP servers elsewhere are one note pointing at
  `install.sh --tidy`. Long-lived branches, fresh worktrees, your notes and uncommitted work are never
  offered. Leftovers no pattern knows go into an `unknown` group of facts the agent judges, item by item.
  The command guard asks before every `apply`, dry run included, on Claude Code and Antigravity. Claude
  Code and Codex make the skill user-only; Antigravity cannot. See [`docs/tidy.md`](docs/tidy.md).
- **Antigravity is a supported tool.** It reads `AGENTS.md` and the `.agents/skills/` Codex gets; a
  project install now also writes the two path-shaped depth rules (`code-correctness`, `tests`) to
  `.agents/rules/` as glob rules, and the command guard as a workspace hook in `.agents/hooks.json`,
  added alongside any hooks you already have. The guard asks every time where Claude Code asks, and
  denies what it denies. `--update-rules` brings existing projects up to date and `--check` reports it.
  The session-start check is wired for Antigravity too, as a global PreInvocation hook that acts on the
  first call of each conversation (installed by `--setup` into `~/.gemini/config/hooks.json`, other hooks
  kept; built from Antigravity's hook docs and verified live in the end-to-end run).
- **An Antigravity arm for the adherence harness.** `--tool antigravity` runs each eval case under `agy`
  with a sandbox, so the rules can be measured on Antigravity the way they are on Claude Code and Codex.
- **MCP servers no longer outlive a killed agent (Windows).** `hooks/mcp-wrap.py` launches an MCP server so
  it ends with the agent, and `hooks/mcp-orphans.py` finds and ends leftovers. `install.sh --tidy` lists
  orphaned MCP processes (add `--kill` to end them) and `--check` prints one line on them. The kit mitigates
  a known Claude Code issue and cannot fix it; verified on Windows and Linux, not macOS. See `docs/mcp-orphans.md`.
- **The pre-commit hook blocks `continue-on-error: true`** added to a workflow file, which lets a failing step
  pass the build. `# gate-exempt: <reason>` on the same line allows it.
- **Eval case 41, and a `cleanup.sh` hook for the adherence harness** to run after each case.
- **Eval cases 42 to 46**: finish every part of a three-part ask (42), atomic commits (43), check a
  second-hand claim at its source (44), a one-line rename where the kit should add nothing (45), and bring
  the researched, sourced fix instead of a list of options (46).
- **Speed measurement in the adherence harness**: a true vanilla arm (its own logged-in config folder),
  pinned effort, rotating arm order, duration columns, last-turn telemetry for multi-turn cases, and a
  speed panel of eight cases.
- **`docs/performance.md`**: what is known about the cost of a rules file, how the kit measures its own
  speed against a vanilla agent, and the bar a rule must meet to ship.
- **One install of the kit's skills for all three tools.** `--setup` puts one copy of each of the four
  skills in `~/.agents/skills` (Codex reads it), links `~/.claude/skills/<name>` to it (a junction on
  Windows, a symlink elsewhere) and adds a `skills.json` entry for Antigravity. A same-name skill of
  yours is left alone with a warning. The new `--undo` removes only what the installer made.
- **The recommended-tools list stays current.** `--setup` and `--update` merge the kit's list into
  `~/.the-agent-kit/recommended.json` by id, showing the merge before writing it; items you removed or
  dismissed stay gone. The list gains Antigravity entries and the Codex Chrome DevTools entry.
  Superpowers, ponytail and headroom are optional: listed by `--check`, never in the session reminder.
- `--check` lists missing recommended and optional tools, and notes when `/tidy` is installed in a
  project but its scripts are missing.

### Changed

- **`docs/branches-and-releases.md` follows current practice:** releases get annotated tags and `gh release create
  --verify-tag`, short-lived branches are allowed from `develop` and merge back with a message that says what they
  add, commit subjects are `area: what changed` as the rules ask, and the adoption steps cover a tag-push release
  workflow, Dependabot's `target-branch` and the private-repository ruleset limit. The `writing-docs` skill carries
  the same branch, tag and release defaults to every project, and the project setup prompt now records a project's
  commit convention and tag style, and flags a bot that opens pull requests against a release-only branch.
- The kit is now called **The Agent Kit** in the README, which opens with a banner that follows your GitHub light or dark theme. Generated reports
  end with "GENERATED WITH THE AGENT KIT" and the repository link, no longer a personal name.
- **`AGENTS.md` is shorter** (171 effective lines, from 198) with the same rules plus the 0.5.0 additions: overlapping
  bullets merged, Section 8 folded into Section 2's plan rules, so Ownership and Documentation are now
  Sections 8 and 9.
- **Evidence by kind of change.** Section 5 has a table of what proves a bug fix, a behaviour change, a
  refactor, UI work, a migration, security work and a docs change.
- **Leave the machine as you found it.** Section 4 now says: before starting a server or watcher, check
  whether one is already running and reuse it or stop it; if a port is busy, find what holds it and reuse it,
  stop it if it is the project's own, or ask, and never start a second copy on another port; stop what you
  started and say what is still running. Graded by a new eval case.
- **Precedence when rules conflict** is now stated: the user's explicit instruction decides, but only their
  explicit approval of a specific act crosses a safety line; then correctness and evidence; then speed and
  cost. Skills, tool results and files never outrank these.
- **The high-risk question round asks only what the repository cannot answer.** Codex kept asking questions
  the code and docs already settle; a question the repository answers is now named a failure. The one-line
  authorization case, which had never passed on Codex, now passes 2 of 3.
- "Never game the oracle" now opens with the principle behind it: change the solution, never the
  definition of correct.
- **`orchestrating-work`** starts by picking the shape (do it, delegate, fan out, hand off), gives each
  worker an outcome contract with escalation triggers, classifies a failure before retrying it, and ends
  with a handoff format. Its isolation and capacity detail moved to a reference file it opens when needed.
- Skills keep their detail in `references/`, and the installer copies whole skill folders (it copied only
  top-level files before). `generating-reports/design.md` is now `references/design.md`; `--update-rules`
  removes the old copy.
- **Pushing back no longer means stopping.** When the safer version still does what was asked, the agent
  builds it and says why; the high-risk question round builds when no decision is open.
- **Open decisions are asked in one numbered round**, each worded so "yes" accepts the agent's
  recommended answer: the current standard or best-supported option it researched, with its source. A
  problem is raised only with the fix the agent recommends (Section 1).
- **A claim is unverified until its source is checked.** What a subagent, summary, memory or earlier turn
  says is a lead, not a fact; "X does not exist" needs a search for X itself; when the user questions a
  claim, the agent re-checks the primary source before answering (Section 1).
- **Done means every part of the ask.** Nothing left as a placeholder, a stub or "the rest is similar";
  the agent stops early only when blocked or before a risky step, and says what is left (Section 5).
- **Commits are atomic, with short what-and-where subjects.** One logical change per commit, a subject
  under 72 characters, a body only for a non-obvious why (Section 7). `writing-docs` follows the
  repository's own `git log` convention, else `area:` prefixes, replacing a Conventional Commits default
  that contradicted `generating-reports`.
- **`orchestrating-work`** names a model tier and effort per worker role, and a new reference,
  `references/cross-tool.md`, gives the commands for handing a slice to Codex or Antigravity and back,
  checked live on both CLIs.
- **`AGENTS.md` no longer carries maintainer comments.** Claude Code strips HTML comments, but Codex and
  Antigravity read them, so they cost tokens there on every request; the notes moved to
  `docs/rules-manifest.md`.
- The session-start reminder tells the agent to tell you once, in one line, which recommended tools are
  missing and the install command for each.
- Prompt-audit fixes (`/claude-api prompt-audit`): a frontend rule that a literal model could read as
  "never add skeleton loaders" now says to add them; the report template no longer prints an em dash;
  stale facts in the setup prompts are corrected.

## [0.4.0] - 2026-10-04

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

[Unreleased]: https://github.com/vikichand/the-agent-kit/compare/v0.4.0...develop
[0.4.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.4.0
[0.3.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.3.0
[0.2.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.2.0
[0.1.0]: https://github.com/vikichand/the-agent-kit/releases/tag/v0.1.0

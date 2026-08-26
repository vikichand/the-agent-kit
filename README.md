# the-agent-kit

Rules and guardrails that make coding agents behave. One install, wired for both
[Claude Code](https://claude.com/claude-code) and [Codex](https://developers.openai.com/codex).

## Quick Start

Four steps. Two set up your machine, two set up each project.

### 1. Get the kit

```bash
curl -fsSLO https://raw.githubusercontent.com/vikichand/the-agent-kit/main/install.sh
sh install.sh --update
```

That copies everything to `~/.the-agent-kit`. Two steps rather than `curl … | sh` on purpose: that
pipes code you have not read into a shell, and the rules in this kit tell an agent never to do it.
Once it finishes you can delete the downloaded `install.sh` - nothing points back at it.

### 2. Turn on the git hooks

The installer prints this command; it cannot run it for you.

```bash
git config --global core.hooksPath "$HOME/.the-agent-kit/git-hooks"
```

**Run it in a normal terminal, not inside Claude Code.** The kit denies `git config core.hooksPath`
so an agent cannot quietly point git away from the hooks - and that denial applies to you too while
you are in an agent session. This is the step that turns on the secret scanner, the force-push
block, and the AI-attribution stripper, for every repo on the machine. Skip it and the rules still
work, but almost nothing is enforced.

Already using Husky or lefthook? They own `core.hooksPath` too - see
[Coexisting](#coexisting-with-husky-lefthook-or-pre-commit) instead of running the line above.

### 3. Merge the printed settings snippets

Step 1 printed two blocks. Without them the tool-layer guard does nothing.

- **No `~/.claude/settings.json` yet?** Save the printed Claude block as that file, as-is.
- **Already have one?** Copy the `permissions` and `hooks` keys from the block into yours. If you
  already have those keys, add the entries to the existing lists rather than replacing them - the
  file is JSON, so mind the commas.
- Same for `~/.codex/config.toml` if you use Codex. Skip it if you don't.

### 4. Set up a project

```bash
cd /path/to/project && ~/.the-agent-kit/install.sh
```

That writes three things: `AGENTS.md` (the rules), a one-line `CLAUDE.md` that imports it, and
`.claude/rules/` - deeper rules that load only when the agent opens a matching file, so security
rules arrive on API code and accessibility rules on components, and cost nothing the rest of the time.

### 5. Run the setup prompt, once per project

This is the highest-value step and takes about a minute. It records **your** build, test and lint
commands; without it the agent guesses them, which is the single largest hallucination surface the
kit has.

1. Open [`docs/project-setup-prompt.md`](docs/project-setup-prompt.md) (also at
   `~/.the-agent-kit/docs/project-setup-prompt.md`).
2. Copy everything inside the ```` ```text ```` fence - that is the prompt itself.
3. Start your agent **inside the project** and paste it in.
4. Answer its questions. It writes the result between the `PROJECT-CONFIG` markers in `AGENTS.md`
   and shows you the block. Nothing above those markers is touched.

Re-run it whenever the project changes; it replaces the block rather than stacking a second one.

### Prefer the rules global instead?

If you would rather set the rules up once per machine, append them to your global files and use the
lean per-project install:

```bash
cat ~/.the-agent-kit/AGENTS.md >> ~/.claude/CLAUDE.md      # and ~/.codex/AGENTS.md for Codex
cd /path/to/project && ~/.the-agent-kit/install.sh --extension
```

**One thing this costs you, tested:** `~/.claude/rules/` is *not* read - path-scoped rules only load
from a project's own `.claude/rules/`. So global rules give you the universal floor everywhere but
none of the depth tier. `--extension` still installs the depth tier into the project, which is why
it is in the command above. Global rules also stay on your machine, so cloud agents, CI and
teammates see only what is committed in the repo.

### Check it worked

```bash
~/.the-agent-kit/install.sh --check
```

Run it inside a project. You want the three git hooks reported as **live**, and the tool guard
firing. A `WARN` about `PROJECT-CONFIG` is expected until you run the setup prompt.

Steps 1-3 are per machine; step 4 is per project. They are independent: machine-only gives you
enforcement with an agent that has not read the rules, project-only gives the rules with no
enforcement.

### Your shell

| Shell | What changes |
|---|---|
| Git Bash · WSL · macOS · Linux | Nothing. The commands work as written. |
| PowerShell | `curl.exe`, not `curl` - PowerShell aliases `curl` to `Invoke-WebRequest`, which rejects these flags. `sh`, `cp` and `~` all work. |
| CMD | `%USERPROFILE%` in place of `~`. |

**No `curl`?** You never need it - this does the same job with git, which the kit requires anyway:

```bash
git clone https://github.com/vikichand/the-agent-kit.git && cd the-agent-kit && ./install.sh --global
```

### Updating

The same command you installed with, now living in the installed copy - nothing to re-clone:

```bash
~/.the-agent-kit/install.sh --update                 # machine-wide; run it from anywhere
cd /path/to/project && ~/.the-agent-kit/install.sh --update-rules
```

`--update` reports `old -> new` with the commits between, does nothing when you are already current,
and refuses to overwrite your install if the download is not the kit. `--update-rules` replaces a
project's universal rules while **preserving its `PROJECT-CONFIG` block**, which is exactly why you
should never hand-copy a new `AGENTS.md` over the old one. Scope differs: `--update` is machine-wide
and ignores your working directory; `--update-rules` and `--check` act on the repo you are standing in.

### Also worth having

[**the-ultimate-gitignore-ai**](https://github.com/vikichand/the-ultimate-gitignore-ai) as the
project's `.gitignore`. The two agree by design: `AGENTS.md` / `CLAUDE.md` stay committed (team
intent), the files agent sessions generate (`.claude/settings.local.json`, `CLAUDE.local.md`) stay
ignored, and `.env` is ignored while `.env.example` stays readable - the same carve-out the kit's
permission rules make.

Needs `git`, POSIX `sh` / `awk` / `grep` (bundled with git), and Python 3 for the tool-layer guard.
On Windows a bare `python3` can be a no-op Store stub, so `--check` verifies the interpreter actually
runs Python 3 and picks the fastest working one. Nothing is ever overwritten: an existing
`CLAUDE.md`, `AGENTS.md`, or git hook is left untouched.

MCP servers, plugins, and skills are a separate job, deliberately not automated:
[`docs/environment-setup-prompt.md`](docs/environment-setup-prompt.md). For browser work,
[`docs/browser-tools.md`](docs/browser-tools.md) settles Playwright vs Chrome DevTools. To keep the
kit current as practice moves, run [`docs/staying-current-prompt.md`](docs/staying-current-prompt.md)
quarterly - it researches what shifted and proposes at most a handful of changes, with NO CHANGE as
the expected verdict.

## Table of Contents

- [What you get](#what-you-get)
- [Features](#features)
- [Install](#install)
- [Customise per project](#customise-per-project)
- [What each guard does](#what-each-guard-does)
- [Verify](#verify)
- [Limits](#limits)
- [Inspired by](#inspired-by)
- [License](#license)

## What you get

Two things, one install.

**The rules** - a tight `AGENTS.md` that gets an agent working like a senior engineer instead of an
eager intern: reuse what the codebase already has rather than rebuilding it, know the blast radius
before editing, test first and never fake a green test, fix the root cause instead of the reported
symptom, and ship no "improvement" nobody asked for. Per-project setup adds your real build and test
commands, and for user-facing apps the quality bars an agent otherwise skips - accessibility, i18n,
observability, audit logs.

**The depth tier** - longer, situational rules that load only when the agent opens a file they apply
to, so security rules arrive on API code and accessibility rules on components, at no cost the rest of
the time.

**The guards** - hooks at the **git layer** (reorder-proof, covering Claude Code, Codex, plain `git`,
and any MCP tool that shells out to `git`) plus the **tool layer**, a fast prompt-time veto. Full map
in [`FEATURES.md`](FEATURES.md); the senior-engineer trait ledger with sources is
[`SENIOR-ENGINEER.md`](SENIOR-ENGINEER.md).

**Honest about what this is:** the guards *reduce* slop and mistakes; they are **not a sandbox.** The
tool-layer hook parses shell text, which can't be made bulletproof (`bash -c`, `eval`, `$(...)`, and
MCP tools bypass it). That's why the real veto lives at the git layer, and why for anything unattended
you want server-side branch protection and a
[container / OS sandbox](https://code.claude.com/docs/en/sandbox-environments) (the bundled
[`.devcontainer/`](.devcontainer/) is a starting point). A sandbox constrains the filesystem, not a
credential you hand it. Nothing here guarantees an agent never pushes or never leaks; it makes the
careless paths fail **closed and loud**.

Built because the same four failure modes kept recurring - silent assumptions, bloat, drive-by edits,
confident-but-unverified "done" - along with agents pushing when only a commit was wanted, or signing
themselves into the history.

## Features

### The rules: how the agent behaves

Always-on **safety invariants** apply even to a one-line task: secrets stay secret · approval before anything
irreversible (`rm -rf`, `reset --hard`, force-push, `curl|sh`) · untrusted content is data, not instructions ·
confirm dependencies before adding, and vet health + license · the worktree is yours (no blind `git add -A`,
no unasked commits) · stay in the workspace, private material stays local · own your incidents (stop and
report, no silent cleanup) · don't touch the guardrails.

On top of that, eleven working rules:

| # | Enforces | Kills |
|---|---|---|
| 0 | **Size the task**: scale ceremony to the job | process theatre on a typo; winging a migration |
| 1 | **Read first · no silent assumptions · blast radius before editing · push back** · **grill mode** on request | confident wrong builds off a guessed reading |
| 2 | **Plan non-trivial work** as verifiable steps, then pressure-test it | plans nobody can check |
| 3 | **Simplicity · YAGNI / DRY · the reuse ladder · senior correctness defaults · match the codebase** | speculative abstraction; silent fallbacks, float money, N+1 queries |
| 4 | **Surgical changes**: every changed line traces to the task | drive-by edits, unreviewable diffs |
| 5 | **Verification is the spine**: external oracle, test-first by default, never game the oracle, verify claims against live docs | "looks right" shipped as done; a failing test quietly deleted |
| 6 | **Root-cause debugging** · fix the shared function · two-attempt rule | symptom patches that leave sibling callers broken |
| 7 | **Checkpoint to files** · commit only when asked · sync before you ship | decisions lost with the session; PRs against stale HEAD |
| 8 | **Execution discipline**: work the plan top to bottom | stopping to chat between every step |
| 9 | **Ownership**: no AI authorship, no AI prose tells | `Co-Authored-By: Claude` in your history; em dashes and "delve" in your docs |
| 10 | **READMEs: the working path first** · docs move in the same diff | the README you'd otherwise be scrolling; stale `.env.example` |

These are *behaviours, not style*. The kit imposes no framework, formatter, or house style, so it can't fight
your project's conventions; project opinion lives in the per-project block instead. Several rules come
straight from the people in [Inspired by](#inspired-by), noted there by section.

**§9 covers prose as well as commits.** A `Co-Authored-By` trailer isn't the only thing that marks work as
machine-made; the writing does it too. So §9 bans the tells in anything the agent writes (READMEs, comments,
commit bodies, PR descriptions): **em dashes** above all, plus "it's not just X, it's Y", filler openers,
hedges, *delve / leverage / seamless / robust*, emoji headings, and bolding every third phrase. It governs
what the agent *writes*, never your project's code style.

### The depth tier: rules that cost nothing until they apply

`AGENTS.md` is read on every turn, so every line in it is paid for on every task - which caps how much
can live there. The deep, situational material instead ships as **path-scoped rules** in
`.claude/rules/`, each carrying `paths:` frontmatter. They load only when the agent opens a file that
matches, and nothing at all otherwise.

| Rule | Loads when the agent touches | Carries |
|---|---|---|
| `code-correctness.md` | source files | no silent fallbacks · idempotent, transactional writes · "what happens at 100k rows" · UTC and decimal money · named-ceiling shortcuts |
| `web-security.md` | `auth/**`, `api/**`, `**/webhook*`, `**/payment*`, routes, middleware, edge config (`nginx.conf`, `Caddyfile`, `vercel.json`, `wrangler.toml`, `fly.toml`, `.htaccess`) | sessions, object-level authz (the row-42 bug) · injection family · rate limits that survive a second instance · uploads · HSTS/CSRF/CORS · server-side prices · limits on AI endpoints |
| `frontend-quality.md` | components, pages, `*.tsx`, `*.jsx` | accessibility (and its legal exposure) · i18n · skeleton loaders · UI restraint |
| `data-layer.md` | migrations, models, schema, `*.sql` | expand -> migrate -> contract · N+1 and indexes · money and time column types · privacy |
| `ci-cd.md` | `.github/workflows/**`, `Dockerfile`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` | pin actions to a digest · least-privilege token · `pull_request_target` + untrusted checkout · secrets never echoed · gates fail closed |
| `tests.md` | test files | never game the oracle · behaviour over internals · the edges · test-first |

**Measured, not assumed.** A 53 KiB rule present but not matching cost 65,347 tokens of context,
against 65,510 with no rule file at all - free, within noise. The same file cost +12.7k the moment a
path matched. That is why the deep material could grow without anything being deleted to make room.

`paths:` is read by Claude Code, VS Code Copilot and Cline. Every other tool ignores the folder and
still gets the complete floor from `AGENTS.md`, so this degrades rather than forking the kit.
`@import` is deliberately **not** used for this: imports expand at launch, so splitting a file that
way is organisation with no context saving at all.

### The task tier: skills

A third trigger, for guidance keyed to *what you are doing* rather than which file you opened. Only the
skill's one-line description sits in context; the body loads when a task matches.

**`orchestrating-work`** fires when a task looks decomposable, or when you ask to parallelise or use
subagents. Its spine is the rule every credible source agrees on - **reads parallelise, writes do
not** - plus freezing shared contracts before fan-out, one owner per file, worktree isolation,
sequential integration, and an orchestrator-worker split where the lead keeps decomposition, the
contract and the final review while workers execute already-complete specs. Multi-agent runs cost
roughly 15x the tokens of a chat, so it also says plainly when *not* to fan out.

### The guards: what's enforced, and where

| Guard | Claude Code | Codex |
|---|---|---|
| **Rules** | `CLAUDE.md`, a one-line `@AGENTS.md` import | `AGENTS.md`, the file itself |
| **add / commit / push** | permission rules **ask every time** (ask outranks a mis-clicked "don't ask again"); force/`--no-verify` **denied** | tool hook **denies** (you push) |
| **force / delete to `main`** | git `pre-push` blocks it | git `pre-push` (same file) |
| **secrets in a commit** | git `pre-commit` blocks staged secrets | same file |
| **destructive cmds** (`rm -rf`, `reset --hard`, `curl\|sh`) | tool hook **asks** | tool hook **denies** |
| **AI authorship** | `commit-msg` strips trailers + `attribution:""` | `commit-msg` (same file) |
| **secret reads** | **asks**, naming the file (so "push my `.env` vars to Azure" is one click, and an injected "read the .env" can't pass silently) | `config.toml` (sandbox) |
| **self-protection** | `deny` writes to `.git/hooks`, `.git/config`, settings; ask on rules files | `config.toml` (sandbox) |

Codex has no `ask`, so where Claude prompts, Codex **denies** and you do it yourself. The git-layer hooks
run under `git` itself, so they survive flag-reordering, `--no-verify`, Codex, and MCP-driven commits.
`command-guard.py` is the fast prompt-time catch on top.

## Install

Quick Start covers the usual path. The installer has six modes:

| Mode | Scope | What it does |
|---|---|---|
| `--update` | machine | Fetch the latest kit into `~/.the-agent-kit`, then run `--global`. Needs no kit beside it, so one downloaded `install.sh` bootstraps everything. |
| `--global` | machine | Git hooks for every repo via `core.hooksPath`; **prints** the tool-guard snippets to merge. |
| *(none)* | project | Full rules - `AGENTS.md` plus a `CLAUDE.md` that imports it - and this repo's git hooks. |
| `--extension` | project | Project block only, for when the universal rules already live in your global files, so nothing is duplicated into context. |
| `--update-rules` | project | Replace the universal rules, keep `PROJECT-CONFIG` byte-for-byte. |
| `--check` | project | Doctor: interpreter, guard firing, per-hook identity, rules-file size and wiring. |

> **Merge, don't replace.** If your `settings.json` already has `permissions` or `hooks`, fold these
> keys into them. Pasting the whole snippet over an existing file wipes what's there.

**Why two rules files.** `AGENTS.md` is the cross-tool standard (Codex, Cursor, Aider, Copilot).
Claude Code reads `CLAUDE.md` and *not* `AGENTS.md`, so the kit follows Anthropic's documented
pattern: `CLAUDE.md` contains `@AGENTS.md` and nothing else. One source of truth, and an edit reaches
both tools at once. A symlink works too but needs Administrator or Developer Mode on Windows.

**Two limits, both enforced silently.** Codex truncates past 32 KiB (`project_doc_max_bytes`) with no
warning, and the cap covers the *combined* `AGENTS.md` chain, so nested files count. Claude Code
loads `CLAUDE.md` in full but [targets](https://code.claude.com/docs/en/memory) "under 200 lines",
since "longer files consume more context and reduce adherence". `--check` reports both.
[Block-level HTML comments are stripped](https://code.claude.com/docs/en/memory) before the content
reaches Claude, so notes inside `<!-- -->` cost nothing and are excluded from the count.

### Coexisting with Husky, lefthook, or pre-commit

Those tools work by pointing `core.hooksPath` at their own directory, which makes git ignore `.git/hooks`
entirely. Install the kit first and add one of them later and the kit's hooks go **silently inert**.
`./install.sh --check` catches exactly this: it prints the active `core.hooksPath` and marks any hook slot
the kit doesn't own as `FAIL`.

To run both, call the kit's hook from theirs. With Husky, forwarding arguments matters (`commit-msg` gets
the message file, `pre-push` gets the remote plus refs on stdin):

```sh
# .husky/pre-commit
sh "$HOME/.the-agent-kit/git-hooks/pre-commit" || exit 1
npx lint-staged

# .husky/commit-msg
sh "$HOME/.the-agent-kit/git-hooks/commit-msg" "$1" || exit 1

# .husky/pre-push
sh "$HOME/.the-agent-kit/git-hooks/pre-push" "$@" || exit 1
```

Put the kit's hook first, so a staged secret blocks the commit before you spend time formatting it.

## Customise per project

The universal rules are the floor; the per-project block is the multiplier. Run the
**[project setup prompt](docs/project-setup-prompt.md)** from inside the project. It classifies the repo -
including its platform (web / mobile / desktop / TV / CLI / library / service) and intent (production /
prototype) - reads it, and writes a tailored block between the `PROJECT-CONFIG` markers without touching the
rules above. User-facing platforms get senior quality bars (a11y, i18n, observability, audit logs) scaled to
intent, web repos additionally get **path-scoped rules** in `.claude/rules/` that load themselves when the
agent opens auth, API, payment or migration code, and **[docs/web-checklists.md](docs/web-checklists.md)**
for launch readiness.
The full senior-engineer trait ledger behind these bars, with rationale and sources, is
**[SENIOR-ENGINEER.md](SENIOR-ENGINEER.md)**.

## What each guard does

**command-guard** (`hooks/command-guard.py`, tool layer) is a PreToolUse hook, `--decision ask` on Claude
Code / `--decision deny` on Codex. A **best-effort prompt-time catch, not a boundary**: a text parser
can't fully replicate git + shell semantics, so `bash -c`, `eval`, `$(...)`, aliases, and unusual-but-valid
git syntax slip past. It flags the hook-disable vectors (`--no-verify`, `core.hooksPath` via `-c`,
`--config-env`, `GIT_CONFIG_*`), direct `.git/config` writes, force/delete push, and destructive commands
(`rm -rf`, `git reset --hard`, `git clean`, `git branch -D`, `curl | sh`). It flags only the *force* form
of a branch delete: plain `git branch -d` already refuses on unmerged work, so gating it would be noise.

**pre-push** (git layer) refuses **force / non-fast-forward / delete** to a protected branch (`main`,
`master`, `release/*`). Git runs it itself, so it's reorder-proof. Override: `AGENT_KIT_ALLOW_FORCE=1`.

**pre-commit** (git layer) **blocks a commit that stages a secret.** A built-in high-signal scan (AWS /
OpenAI / GitHub / Slack / Google keys, JWTs, private-key blocks) always runs, with no dependency, and
`gitleaks` is used too when installed. Fail-closed.

**commit-msg** (git layer) strips AI-authorship trailers: `Co-Authored-By` from known AI bots and
`Generated with [Claude Code / Codex / Copilot / Cursor / Gemini]` lines. It **keeps** your body, real
human co-authors, and `Claude-Session:` links. It matches the bot *address*, not a first name, so a
human named "Claude" is safe. Fail-closed: if stripping would empty the message, the commit is blocked
rather than silently rewritten.

**Tool config** (`claude/settings.json`, `codex/config.toml`, `codex/hooks.json`) is printed by
`--global` for you to merge. On Claude Code it kills the native attribution trailer
(`attribution.commit/pr:""`), asks on `git push` and on secret-file reads (a visible prompt naming the
file - precaution without a hard stop), and denies `--no-verify`/force and
writes to `.git/hooks`, `.git/config`, and `.claude/settings.json`. It also **asks** before an edit to
`AGENTS.md` / `CLAUDE.md`, since those now carry the same authority as the settings file. On Codex it sets
`approval_policy=on-request` and `sandbox_mode=workspace-write`; `codex/hooks.json` wires the deny-mode hook.

Three config choices are deliberate, because the obvious "more locked down" setting makes the agent worse:

- **Secret files ask; they are not walled off.** Reading `.env` / keys / credential stores prompts with
  the exact file named, instead of a hard deny. Real workflows need it ("push my local env vars to the
  platform"), and the prompt is the precaution: an injected "read the .env" surfaces visibly and dies on
  your click, and ask outranks a mis-clicked "don't ask again" permanently. The ask list still names the
  real secret files (`.env`, `.env.local`, `.env.*.local`, `.env.production`) instead of the broad
  `.env.*`, so `.env.example` / `.env.sample` stay silently readable - they carry no secrets and are
  exactly how an agent learns what configuration a project expects. (`settings.json` is JSON and cannot
  hold comments, so the reasoning lives here.)
- **Codex keeps network access on.** The rules require checking library and API behaviour against live
  docs rather than recalling it. Switching the sandbox off the network does not make the agent safer, it
  makes it fall back on training data. Anthropic's own guidance notes that when two instructions conflict,
  the model may pick one arbitrarily, so the kit does not ship that conflict. Set it `false` when reviewing
  untrusted code and expect doc lookups to fail loudly.
- **No hand-written env-var exclude list.** Codex already excludes secret-looking names by default. A broad
  custom list (`*_URL`, `*KEY*`) strips `DATABASE_URL`, `VITE_API_URL`, and `KEYCLOAK_*` out of the
  environment, so commands fail for a reason the agent cannot see, and it then invents a cause.

## Verify

```bash
./install.sh --check                     # doctor: interpreter, guard firing, per-hook status, rules files
sh test/run-tests.sh                     # git-layer hooks + doctor, end-to-end
python3 test/command_guard_cases.py      # command-guard corpus (96 cases)
sh test/adherence/run.sh                 # do the SOFT rules actually fire? (costs tokens)
```

The doctor checks each of `commit-msg` / `pre-commit` / `pre-push` **by identity**, not just presence, and
reports how strong the evidence is: byte-identical to the kit's hook (proven), a shim that calls the kit
(text match, worth eyeballing), or neither (`FAIL`, that guard is inactive). It also prints `core.hooksPath`
when set, so a redirect is visible, and follows it rather than reading `.git/hooks`.

It also checks the rules files: size against both silent limits, and whether `PROJECT-CONFIG` is still the
empty placeholder. That last one matters most. Without it the agent guesses this project's build, test, and
lint commands, which is the largest hallucination surface the kit has.

**Interpreter cost.** The tool guard spawns Python on every Bash call, so the interpreter choice is a real
per-call tax. `--check` reports which one it picked. Measured on one Windows 11 machine: `py -3` 140 ms,
`python3` 237 ms, because a bare `python3` there is usually the slower WindowsApps alias. The probe checks
the major version, so a legacy Python 2 is rejected rather than selected and then crashing the guard.

## Limits

- **Not a sandbox.** These stop a *well-intentioned* agent and the careless common paths, not a determined
  adversary; for real isolation, run agents in a container / OS sandbox.
- **The tool hook is Bash-scoped.** It sees `Bash` commands only, so an MCP server that pushes or writes
  files is not seen by it. The git-layer hooks are the backstop; there is no local guard on MCP writes.
- **The deny-lists are prefix-matched** (Claude's permission engine), so a reordered flag can slip a deny.
  The reorder-proof catch is the git layer.
- **`--no-verify` skips git hooks.** It's denied at the tool/permission layer on both tools, the only place
  it can be caught since git can't hook its own bypass, but a text parser is best-effort there too.
- **`core.hooksPath` can be set via a *file*, not just a flag.** `command-guard` catches the CLI forms and
  flags direct `.git/config` writes, but a text scan can't read a config file it never sees. The durable
  fix is the OS sandbox plus denying write access to `.git/config`.
- **Anything that owns `core.hooksPath` shadows other hooks.** A global `--global` install, or a tool like
  Husky / lefthook / pre-commit, redirects git away from `.git/hooks`. Whoever sets it last wins, and the
  hooks in the old location go silently inert. The installer warns before setting it, and `--check` prints
  the current value; if another tool owns it, merge the kit's hooks into that directory.
- **Attribution fixes the message, not the author identity.** Keep your own `user.name` / `user.email` in
  git config. It's a *known-bot* denylist, so a brand-new tool's trailer may need adding.

## Inspired by

The rules stand on the public work of people who've thought hard about coding with agents.
**Inspirations, not endorsements**: none of them have seen or endorsed this kit.

Links are given only where the source was fetched and checked. Where a claim is corroborated by reporting
but the primary link could not be verified, it is attributed by talk and date instead of deep-linked, per §5.

- **Andrej Karpathy**: **§0, §4, §5.** From his *AI Startup School* talk (Y Combinator, June 2025) and
  surrounding writing: keep AI "on a leash" with incremental, auditable changes, because a huge diff just
  moves the bottleneck to the human verifying it. He describes himself as still being that bottleneck. That
  is why §5 demands an oracle and §4 insists the diff stays small and reviewable.
- **[Matt Pocock](https://github.com/mattpocock/skills)**: **§1, §2.** His skills push the agent to interview
  you *before* it opens an editor, and to write down a project's real vocabulary so it stops inventing
  domain names. §1's grill mode and the `PROJECT-CONFIG` block are the same idea in a smaller form.
- **[Boris Cherny](https://howborisusesclaudecode.com/)** (creator of Claude Code): **§5.** *Give the agent a
  way to verify its work*, and it multiplies the quality of the result.
- **[Simon Willison](https://simonwillison.net/2025/Mar/11/using-llms-for-code/)** (coined "vibe
  engineering"): **§5.** *"If you haven't seen it run, it's not a working system."*
- **[Kent Beck](https://simonwillison.net/2025/Dec/16/kent-beck/)** (created TDD): **§5.** *Augmented*
  coding: move faster with AI while keeping quality. The test-first cycle in §5 is his.
- **[ponytail](https://github.com/DietrichGebert/ponytail)** (MIT): **§3, §6.** Its "lazy senior dev" framing
  sharpened two rules here - stopping at the first rung of a reuse ladder, and marking a deliberate shortcut
  with the ceiling it carries. The wording in this kit is its own; the thinking was better for having read theirs.
- Supporting data: Google's **[DORA 2025](https://dora.dev/)** (AI *amplifies* existing practices) and a
  Dec 2025 UC San Diego / Cornell study ([arXiv:2512.14012](https://arxiv.org/abs/2512.14012)):
  professional developers don't vibe, they control.

## License

MIT (c) 2026 Vikash Chand

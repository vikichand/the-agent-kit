<!-- Paste the block below into a fresh Claude Code session. It is a prompt for an agent to execute,
     not a script the kit runs. the-agent-kit installs nothing on its own; this file is an optional
     recipe you invoke deliberately, so the kit stays a floor rather than a package manager. -->

# Environment setup prompt

Sets up the MCP servers, plugins, skills, and agents that this machine expects. Run it once on a new
machine, or after a reinstall. It is **idempotent**: every step checks before it acts.

**Scope note.** This is about your *machine*, not a project. It is separate from `install.sh`, which
handles the kit's own rules and git hooks. Neither one needs the other.

**Pick a profile.** Install only what a project needs: every skill and plugin description sits in
context for every session, whether it fires or not.

| Profile | What | Why |
|---|---|---|
| **Core** (everyone) | Context7 MCP | The kit's `context7.md` rule sends library and API questions to it instead of stale training data |
| **Web and UI** | Playwright CLI and its skill, Chrome DevTools MCP, Impeccable, `frontend-design` | Real-browser proof of UI work (Section 5) and design quality |
| **Optional** | Superpowers, ponytail, headroom | They work alongside the kit, but each costs context or latency, so opt in knowingly |

The kit's session-start check suggests the Core items and, in a project set up as a web or UI app,
the Web and UI items, when they are missing. It reads `~/.the-agent-kit/recommended.json`: delete an
entry there to stop it being suggested, or add your own. It never installs anything.

---

## The prompt

Copy everything between the rules into a new Claude Code session.

---

You are setting up a development machine. Work through these steps **in order**. After each step,
print one line saying what you did or why you skipped it. Do not batch the steps and do not skip the
verification at the end.

**Rules for this task:**

1. **Check before you install.** Every step starts with a list or status command. If the thing is
   already present at the right scope, say "already present, skipped" and move on. Never reinstall
   over something that exists.
2. **Never type a credential.** If a step needs an API key, print the exact command with a
   placeholder and **stop, and ask me to run it myself**. Do not read a key from any file, do not
   copy one from another config, and do not guess one.
3. **Verify commands you are unsure about.** Run `claude mcp add --help` or
   `claude plugin install --help` rather than recalling flag names. If a command fails, show me the
   real error and stop. Do not try variations.
4. **Do not modify `~/.claude/settings.json` by hand.** Use the CLI. If something can only be done
   by editing that file, show me the exact diff and wait for approval.
5. **Report anything already installed that is not on this list** rather than removing it.

### Step 1: Baseline

Run and show me the output:

```bash
claude --version
claude mcp list
claude plugin list
claude plugin marketplace list
ls ~/.claude/skills ~/.claude/agents 2>/dev/null
```

State plainly what is already present. Everything below is measured against this baseline.

### Step 2: MCP servers

Install at **user** scope so they apply to every project; which of the three you need depends on the
profile you picked above. For Codex, the same servers are added with `codex mcp add <name> -- <command>`
(for example `codex mcp add context7 -- npx -y @upstash/context7-mcp@latest`).

**a. Context7** (library and framework documentation; this is what stops the agent answering API
questions from stale training data).

This one needs an API key from https://context7.com/dashboard. Print this command with the
placeholder intact and **stop for me to run it**:

```bash
claude mcp add --transport http context7 https://mcp.context7.com/mcp \
  --scope user --header "Authorization: Bearer <paste-your-key-here>"
```

(The kit's old `CONTEXT7_API_KEY:` header still works but is no longer documented; the form above is
the current one.)

Do not proceed past this step until I confirm.

**Alternative: the official plugin.** `/plugin marketplace add upstash/context7` then
`/plugin install context7@context7-marketplace` reads the key from the `CONTEXT7_API_KEY` environment
variable instead of writing it to `~/.claude.json` in plaintext. It also installs a skill and an agent
that overlap the kit's `context7.md` rule, so pick one, not both.

**b. Playwright CLI and its skill** (Web and UI profile; drives Chromium, Firefox and WebKit). Not an
MCP server: a command-line tool plus a skill that teaches the agent to use it.

```bash
npm install -g @playwright/cli@latest
playwright-cli install --skills -g            # Claude Code: ~/.claude/skills/playwright-cli
playwright-cli install --skills=agents -g     # Codex: ~/.agents/skills/playwright-cli
```

> Playwright's own docs recommend the CLI for coding agents because it "avoid[s] loading large tool
> schemas and verbose accessibility trees into the model context", and the MCP for "exploratory
> automation or long-running autonomous workflows". It covers clicking, filling, snapshots, console,
> network requests, traces, screenshots, video and locator generation. Add the Playwright MCP
> (`claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest`) only for that
> exploratory kind of loop. Checked against the Playwright CLI docs on 2026-10-04.

**c. Chrome DevTools** (Web and UI profile; performance traces, network inspection, console access on a real Chrome).

```bash
claude mcp add chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest
```

> Installed with no flags, the memory tools are inert and the extension tools are absent: memory
> tools need `--memoryDebugging=true`, extension tools need `--categoryExtensions` (off by default).
> `--slim` or per-category flags shrink the tool surface if context is tight. Checked against
> chrome-devtools-mcp 1.9.0 on 2026-09-17.

> **Install both; they do not overlap where it counts.** Only Chrome DevTools MCP can record a
> performance trace with Core Web Vitals, run Lighthouse, or take a heap snapshot. Only Playwright
> can drive Firefox or WebKit, or generate real test-code locators. Both can click, fill, wait, and
> snapshot the page, so "one drives and one inspects" is not the dividing line.
> Copy [`browser-tools.md`](browser-tools.md) into `~/.claude/rules/` so the agent chooses by the
> question rather than by which tool it used last.

### Step 3: Web and UI skills (Web and UI profile)

Skip this step unless the profile is Web and UI. Both are plain skill folders, installed for Claude
Code (`~/.claude/skills/`) and, if Codex is used, for Codex (`~/.agents/skills/`).

- **Impeccable** ([pbakaus/impeccable](https://github.com/pbakaus/impeccable), Apache-2.0): a design
  workflow with commands and deterministic design checks. Follow its README, and install it as a
  **skill**. Its Claude Code *plugin* form adds global hooks that run after every edit and at the end
  of every turn, in every project. Claude Code and Codex each have their own build in its repo
  (`.claude/skills/impeccable` plus `.claude/agents/`, and `.agents/skills/impeccable`); give each
  tool its own.
- **`frontend-design`** (`skills/frontend-design/` in
  [anthropics/skills](https://github.com/anthropics/skills)): visual direction, typography and
  avoiding templated defaults. Impeccable started from it; the two overlap less since its
  2026-09-03 rewrite. Copy **only that folder**: the repo is also a marketplace, but its bundles pull
  a dozen unrelated skills whose descriptions sit in context permanently. It has no update path of
  its own, so record the upstream commit you copied and re-copy when it changes.

Anything from any other source: **tell me and stop.** Do not invent a replacement or write a stub.

### Step 4: Optional plugins

Install only what the profile calls for. Each needs its marketplace added first (skip any that
`claude plugin marketplace list` already shows).

- **superpowers** ([obra/superpowers](https://github.com/obra/superpowers)): a large skill library
  (planning, TDD, debugging, review). It overlaps much of what the kit's rules already say, and costs
  about 3.1 KB of always-on bootstrap plus its skill descriptions. Its text defers to `AGENTS.md`, and
  the kit's Section 0 overrides its "brainstorm first" gate for mechanical and bounded work, so the
  two run together without conflict. **Windows:** version 6.2.0 or later needs Git Bash and Claude
  Code 2.1.81 or later; earlier, its SessionStart hook never loaded under PowerShell or cmd.

  ```bash
  claude plugin marketplace add obra/superpowers-marketplace
  claude plugin install superpowers@superpowers-marketplace --scope user
  ```

  Codex: `codex plugin marketplace add obra/superpowers-marketplace` then
  `codex plugin add superpowers@superpowers-marketplace`.
- **ponytail** ([DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), MIT): a
  "lazy senior dev" minimalism ladder that deliberately overlaps the kit's Sections 3 and 6 (the kit
  took two of its ideas). Its hooks re-inject its rules at session start and on subagent start. Its
  own benchmark (Haiku 4.5, 18 tasks) reports about 54% less code; its README warns a terse reasoning
  model can go the other way. Run it at the `lite` level: at `full` it pushes against design work.

  ```bash
  claude plugin marketplace add DietrichGebert/ponytail
  claude plugin install ponytail@ponytail --scope user
  ```

  Codex: `codex plugin marketplace add DietrichGebert/ponytail` then `codex plugin add ponytail@ponytail`.
- **headroom** ([headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom), Apache-2.0):
  a local proxy that compresses tool output, logs and file reads before they reach the model. The
  plugin alone is inert; the install is:

  ```bash
  uv tool install "headroom-ai[all]"
  headroom init -g
  ```

  `headroom init -g` points Claude Code (`ANTHROPIC_BASE_URL`) and Codex at the proxy and adds hooks
  that start it on demand. **Then switch it to cache mode with telemetry off**, because `init` writes
  token mode and telemetry on: token mode rewrites the conversation history, which breaks the
  model's prompt cache and can cost more than it saves. The settings live in Headroom's profile
  manifest (`proxy_mode`, `telemetry_enabled`, and the `--mode` and telemetry flags in its proxy
  arguments); check its README for the current keys.

  > **Headroom and Remote Control cannot both work in Claude Code.** Claude Code turns Remote Control
  > off whenever `ANTHROPIC_BASE_URL` points anywhere other than `api.anthropic.com`, and routing
  > through Headroom is exactly that setting. To keep Remote Control, remove `ANTHROPIC_BASE_URL` from
  > the `env` block of `~/.claude/settings.json` after `headroom init -g` and start a new terminal:
  > Claude Code then talks to Anthropic directly, and Codex keeps using Headroom.

  Other caveats: its hooks run on every shell call, and `headroom learn` can write to `AGENTS.md`,
  which the kit's rules say an agent never edits.

> **Vendor figures are self-reported.** Treat benchmark numbers from any plugin's own suite as
> direction, not measurement, and check your own token usage before and after.

> **Deliberately not on this list: a second *general lifecycle* skill library.** Every skill's
> *description* stays in context permanently, because that is what the model matches on to decide when
> to fire. A second spec/plan/TDD/review/ship library re-states what superpowers and the rules already
> cover, and duplicate skill names give the model two competing answers to the same trigger. Ponytail
> is the narrow exception: single-purpose, not a lifecycle set. The kit's own `orchestrating-work`
> skill overlaps superpowers' `dispatching-parallel-agents` and `subagent-driven-development`
> triggers; when the kit is installed, its skill is the one that applies.

After installing, run `claude plugin list` and confirm each shows as enabled. If a plugin installed
but is disabled, enable it with `claude plugin enable <name>` and say so.

### Step 5: Rules

Copy these into `~/.claude/rules/` if missing:

| Path | What it is | Source |
|---|---|---|
| `~/.claude/rules/context7.md` | Routes library questions to Context7 | the kit's [`context7.md`](context7.md) |
| `~/.claude/rules/browser-tools.md` | Picks Playwright vs Chrome DevTools by the question (Web and UI profile) | the kit's [`browser-tools.md`](browser-tools.md) |

Note: `~/.claude/rules/` holds drop-in rules that Claude Code reads as part of your global memory.
It does **not** support `paths:` frontmatter - tested, and a path-scoped rule placed there never
fires. Path-scoped rules only load from a *project's* own `.claude/rules/`.

> **Security review needs nothing installed.** Claude Code ships Anthropic's `/security-review`
> built in - the same three-phase analysis as the
> [`claude-code-security-review`](https://github.com/anthropics/claude-code-security-review) GitHub
> Action, with confidence scoring and a tuned false-positive exclusion list. Run
> `/security-review` on pending changes; do not hand-write a security subagent to replace it. To
> customise it, copy that repo's `.claude/commands/security-review.md` into the project's
> `.claude/commands/` and edit there.

### Step 6: Verify

Run these and show me the raw output:

```bash
claude mcp list
claude plugin list
```

Then confirm each of these explicitly, one line each:

- [ ] Every MCP server from the profile you selected is listed and connected (not "failed" or "pending")
- [ ] Every plugin and marketplace from the profile you selected is listed and enabled
- [ ] Every skill from Step 3 and rule from Step 5 that your profile requires exists
- [ ] Context7 responds: ask it to resolve the library id for "next.js" and show the result

If **any** check fails, say which one and what the error was. Do not report success with a caveat
buried in the prose. A partial setup reported as done is worse than a failure reported plainly.

---

## After it runs

Two things worth doing by hand, since neither should be automated:

- **Store the Context7 key outside plain config if you can.** `claude mcp add` writes it to
  `~/.claude.json` in plaintext, which is readable by anything running as you.
- **Decide Playwright vs Chrome DevTools** and write the answer into your global `CLAUDE.md`, so the
  agent stops choosing per session.

## What this deliberately does not do

No formatter, linter, language runtime, or editor config. That is machine bootstrap and belongs in a
dedicated setup repo, not here. This file covers only what Claude Code itself loads: MCP servers,
plugins, skills, agents, and rules.

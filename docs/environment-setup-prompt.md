<!-- Paste the block below into a fresh Claude Code session. It is a prompt for an agent to execute,
     not a script the kit runs. the-agent-kit installs nothing on its own; this file is an optional
     recipe you invoke deliberately, so the kit stays a floor rather than a package manager. -->

# Environment setup prompt

Sets up the MCP servers, plugins, skills, and agents that this machine expects. Run it once on a new
machine, or after a reinstall. It is **idempotent**: every step checks before it acts.

**Scope note.** This is about your *machine*, not a project. It is separate from `install.sh`, which
handles the kit's own rules and git hooks. Neither one needs the other.

**Pick a profile.** Not every project needs every integration.

- **Core**: Context7 only. This is the kit's default.
- **Browser work**: Core plus Playwright MCP and Chrome DevTools MCP.
- **Long sessions**: optional context-reduction tooling (headroom), with its caveats stated below.

Install only the integrations selected for this project. Keep ponytail and headroom optional.
Recommend a context-reduction option only after checking its documented behaviour for the installed
package version.

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
profile you picked above.

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

**b. Playwright** (cross-browser automation: Chromium, Firefox, WebKit).

```bash
claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest
```

> `browser_find` is cheaper than capturing a full snapshot; snapshots themselves have been distilled
> since 0.0.78. `--output-max-size` and `--caps` gate how much comes back. Playwright's own docs note
> that CLI-as-skill workflows can be more token-efficient than driving the MCP directly. Checked
> against Playwright MCP 0.0.81 on 2026-09-17.

**c. Chrome DevTools** (performance traces, network inspection, console access on a real Chrome).

```bash
claude mcp add chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest
```

> Installed with no flags, the memory tools are inert and the extension tools are absent: memory
> tools need `--memoryDebugging=true`, extension tools need `--categoryExtensions` (off by default).
> `--slim` or per-category flags shrink the tool surface if context is tight. Checked against
> chrome-devtools-mcp 1.9.0 on 2026-09-17.

> **Install both; they do not overlap where it counts.** Only Chrome DevTools MCP can record a
> performance trace with Core Web Vitals, run Lighthouse, or take a heap snapshot. Only Playwright
> MCP can drive Firefox or WebKit, or generate real test-code locators. Both can click, fill, wait,
> and snapshot the accessibility tree, so "one drives and one inspects" is not the dividing line.
> Copy [`browser-tools.md`](browser-tools.md) into `~/.claude/rules/` so the agent chooses by the
> question rather than by which tool it used last.

### Step 3: Marketplaces

Add each only if `claude plugin marketplace list` did not already show it:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add obra/superpowers-marketplace
claude plugin marketplace add openai/codex-plugin-cc
claude plugin marketplace add bradautomates/claude-video
claude plugin marketplace add DietrichGebert/ponytail
claude plugin marketplace add headroomlabs-ai/headroom
```

> **If a marketplace add fails with `git@github.com: Permission denied (publickey)`**, the clone went
> over SSH and you have no key. Either pass the full HTTPS URL (`https://github.com/<owner>/<repo>.git`),
> or tell Git to rewrite GitHub SSH URLs once:
> `git config --global url."https://github.com/".insteadOf git@github.com:`. Show me the error before
> changing any global git config.

### Step 4: Plugins

At **user** scope:

```bash
claude plugin install superpowers@superpowers-marketplace --scope user
claude plugin install codex@openai-codex --scope user
claude plugin install watch@claude-video --scope user
```

(Both projects' READMEs document the in-session `/plugin marketplace add` and `/plugin install` form;
the lines above are the CLI equivalents, kept consistent with the rest of this file.)

- **superpowers** is the big one: a large skill library that changes how the agent approaches
  most tasks. Cost: about 3.1 KB of always-on bootstrap plus 14 skill descriptions in context. Update
  with `claude plugin update superpowers@superpowers-marketplace`. **Windows caveat:** before 6.2.0
  its SessionStart hook silently never loaded under PowerShell or cmd; 6.2.0 and later needs Git Bash
  and Claude Code 2.1.81 or later. Its brainstorming skill stops for approval on every path; the
  kit's Section 0 overrides that for mechanical and bounded work, because superpowers' own text
  defers to AGENTS.md.
- **codex** lets Claude Code hand work to Codex.
- **watch** gives Claude Code the ability to watch videos, which it otherwise cannot do.

> **Vendor figures are self-reported.** Treat benchmark numbers from any plugin's own suite as
> direction, not measurement, and check your own token usage before and after.

> **Deliberately not on this list: a second *general lifecycle* skill library.** Every skill's
> *description* stays in context permanently, because that is what the model matches on to decide when
> to fire. A second spec/plan/TDD/review/ship library triples that always-on block to re-state what
> superpowers and the rules already cover, and duplicate skill names give the model two competing
> answers to the same trigger. Ponytail is the deliberate exception and the reason is narrow: it is
> single-purpose (minimalism), not a lifecycle set, and what it sells is re-injection rather than new
> coverage. If you want one specific skill from any other library, take that skill alone, not the set.
> The kit's own `orchestrating-work` skill overlaps superpowers' `dispatching-parallel-agents` and
> `subagent-driven-development` triggers on similar language ("fan out", "use subagents", "split this
> up"). That overlap is accepted, not an oversight: when the kit is installed, its skill is the one
> that applies.

#### Optional: ponytail and headroom

Neither is part of the Core profile. Install only if this machine's profile calls for it (see "Pick a
profile" above).

- **ponytail** ("lazy senior dev mode", MIT) re-asserts a minimalism ladder that deliberately overlaps
  this kit's Sections 3 and 6 - the kit harvested two of its ideas. It does not re-inject on every
  prompt: its hooks re-inject the ruleset on SessionStart (startup, resume, clear, compact) and on
  SubagentStart; the per-prompt `node` process is a mode tracker, not a re-injection. Its benchmark
  headline is now the agentic suite (Haiku 4.5, 18 tasks, n=4: about 54% less code, 20% cheaper, 27%
  faster); its README says the older 80 to 94% figure was partly a conversational-baseline artifact,
  and warns that a terse reasoning model can go the other way - on GPT-5.5 it does.

  ```bash
  claude plugin install ponytail@ponytail --scope user
  ```

  Codex install: `codex plugin marketplace add DietrichGebert/ponytail` then
  `codex plugin add ponytail@ponytail`.
- **headroom** (Apache-2.0) is orthogonal to everything else here: it compresses tool output, logs and
  file reads *before* they reach the model, reversibly, so a 78k-token read does not eat the window.
  The plugin alone is inert: the real install is `uv tool install "headroom-ai[all]"` then
  `headroom wrap claude`. Its hooks run a Python process on every Bash and PowerShell call
  (PreToolUse), a latency cost worth knowing before installing it for small tasks. A custom
  `ANTHROPIC_BASE_URL` disables first-party Remote Control on Claude Code 2.1.196 or later, which
  headroom cannot restore. `headroom learn` can write to `AGENTS.md`, the kit's own rules file - the
  kit's rule is that the agent never edits it, so treat that write with the same caution.

  ```bash
  claude plugin install headroom@headroom-marketplace --scope user
  ```

After installing, run `claude plugin list` and confirm each shows as enabled. If a plugin installed
but is disabled, enable it with `claude plugin enable <name>` and say so.

### Step 5: Skills and agents

These are plain directories, not packages. Report what is present and flag anything missing:

| Path | What it is | Source if missing |
|---|---|---|
| `~/.claude/skills/frontend-design/` | Production-grade UI generation, avoids generic AI aesthetics | `skills/frontend-design/` in [anthropics/skills](https://github.com/anthropics/skills) |
| `~/.claude/skills/skill-creator/` | Create, edit, and eval skills | `skills/skill-creator/` in [anthropics/skills](https://github.com/anthropics/skills) |
| `~/.claude/rules/context7.md` | Rule that routes library questions to Context7 | copy from the kit: [`context7.md`](context7.md) |
| `~/.claude/rules/browser-tools.md` | Rule that picks Playwright vs Chrome DevTools by the question | copy from the kit: [`browser-tools.md`](browser-tools.md) |

Note: `~/.claude/rules/` holds drop-in rules that Claude Code reads as part of your global
memory. It does **not** support `paths:` frontmatter - tested, and a path-scoped rule placed there
never fires. Path-scoped rules only load from a *project's* own `.claude/rules/`.

If a **rule** is missing, copy it from the kit's `docs/` (the Source column links both). If a
**skill** is missing, clone `anthropics/skills` and copy **only that skill's folder** into
`~/.claude/skills/` - the repo is also a plugin marketplace, but installing its whole
`example-skills` bundle would pull a dozen unrelated skills whose descriptions sit in context
forever (see the note below Step 4; the same "take the one skill, not the set" logic applies).
Anything from any other source: **tell me and stop.** Do not invent a replacement and do not
write a stub.

**Record the upstream commit you copied from**, and re-copy when it changes: `anthropics/skills` has
no update path of its own. `frontend-design` was revised upstream on 2026-06-09 and 2026-09-03, the
latter changing the description that controls triggering - check the folder against the current
upstream commit, not just its presence on disk.

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
- [ ] Every path from Step 5 that your profile requires exists
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

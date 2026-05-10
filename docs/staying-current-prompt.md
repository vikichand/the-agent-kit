<!-- Paste the block below into a fresh Claude Code session. It is a prompt for an agent to
     execute, not a script the kit runs. Run it roughly quarterly, or before starting a new
     project, or when a new practice starts showing up everywhere. It researches current
     industry practice, checks the kit against it, and proposes changes for your approval.
     It never edits anything on its own. -->

# Staying-current review prompt

The kit encodes a point-in-time snapshot of best practice for working with AI coding agents, and
practice moves. This prompt makes the re-check repeatable: what shifted in the industry, what
rotted in the kit's own references, and whether either warrants a change.

**Why the anti-churn rules below matter more than the research.** An agent asked "what should
change?" will find something, because finding nothing feels like failing the task. The contract
below makes NO CHANGE the expected verdict and forces every proposed line to pay for itself. A kit
that changes every month is not a floor; it is churn.

---

## The prompt

Copy everything between the rules into a new Claude Code session opened at the kit's root.

---

You are reviewing `the-agent-kit` (this repository) against current industry practice for working
with AI coding agents. Check today's date first and prefer sources from the last six months.

**Rules for this task:**

1. **Read before you research.** Read `AGENTS.md`, `FEATURES.md`, `README.md`, and every file in
   `docs/` before searching for anything. You cannot judge drift against a kit you have not read.
2. **Evidence bar.** A claimed shift in practice needs at least two independent, dated sources,
   and at least one must be a named practitioner or primary write-up, not an aggregator listicle.
   Use web search for practice and Context7 for tool documentation. Never assert from training
   data; that is the exact failure mode this kit exists to prevent (`AGENTS.md` section 5).
3. **The kit is a floor, not a framework.** A new methodology earns a change only if it alters
   what the *universal floor* should be: a behavioral rule or a guard that applies to every
   project. Tool-specific workflow (spec pipelines, orchestration roles, new IDE features)
   belongs in skills, plugins, or the environment setup prompt, not in `AGENTS.md`.
4. **Anti-churn contract.** The default verdict is CURRENT with no changes. Propose at most five
   changes per run, ranked. Every proposed `AGENTS.md` addition must name an existing line to cut
   or shorten in exchange (the file is read on every turn; growth is a cost, see "Meant to grow,
   kept tight"). No style rewrites, no reorganizations, no synonym swaps.
5. **Propose, never edit.** Report findings with exact proposed diffs and stop. Do not change any
   file until I approve each item individually.

### Step 1: Baseline

Read the files in rule 1. Note the kit's current claims: the practices in `AGENTS.md` sections
0-10, the tool list in `docs/environment-setup-prompt.md`, the capability claims in
`docs/browser-tools.md` (including its own re-verify footer), and the lineage names in the README.

### Step 2: Practice scan (web search)

Search each axis separately; do not merge them into one query:

- verification-first / TDD with agents
- spec-driven development (is the floor shifting, or just the tooling?)
- loop engineering: verifier design, stop rules, budgets
- multi-agent and critic patterns (builder/critic separation, fresh-context review)
- guardrails: prompt injection, secrets hygiene, destructive-command gating
- authorship and attribution norms for AI-assisted commits

**Watchlist** (what have these people shipped or argued since the kit's last review): Andrej
Karpathy, Kent Beck, Boris Cherny, Simon Willison, Matt Pocock, Matt Shumer, Addy Osmani, Peter
Steinberger, and the official Anthropic and OpenAI engineering blogs.

### Step 3: Rot check (Context7 + web)

Practice can hold while references rot. Verify:

- Every install command in `docs/environment-setup-prompt.md` still works as written: `claude mcp
  add` flags, marketplace repos still exist, plugin and skill names unchanged, the
  `anthropics/skills` paths in the Step 5 table still resolve.
- The "only X can do this" claims in `docs/browser-tools.md` still hold for both browser MCPs
  (the file's own footer says re-check; this is where you do it).
- The lineage and documentation links in `README.md` still resolve.

### Step 4: Verdict

Report in exactly this shape:

1. **Verdict line:** `CURRENT - no changes recommended` or `UPDATES RECOMMENDED (n)`.
2. **Findings table**, one row per finding: what shifted or rotted | evidence (linked, dated) |
   proposed change (exact diff, with the line it cuts if it adds to `AGENTS.md`) | severity
   (rot-fix / floor-shift / optional).
3. **Sources list.**
4. **What you checked and found still current** - one line per axis, so a clean verdict is
   auditable rather than an assertion.

Do not pad the findings table to look thorough. An empty table under a CURRENT verdict is the
system working.

---

## After it runs

- Approve or reject each finding individually; apply approved ones and re-run the kit's test
  suite (`test/run-tests.sh`) before committing.
- If the run was clean, note the date somewhere convenient (the commit message of a no-op
  "currency review" commit works) so the next run has a "since when" anchor.

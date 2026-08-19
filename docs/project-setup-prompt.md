# Project setup prompt

The universal rules are the floor; the per-project block is the multiplier. Run the prompt below in
Claude Code or Codex **from inside the project**. It classifies the project (code / agent / both), reads
the repo (or asks if it's greenfield), and writes a tailored block into `CLAUDE.md` *only* between the
`PROJECT-CONFIG` markers, leaving the universal rules untouched. Re-run it anytime; it replaces the
block instead of stacking.

Two notes:

- It writes **`AGENTS.md`** only. That is the cross-tool file (Codex, Cursor, Aider, Copilot...), and the
  `CLAUDE.md` beside it is a one-line `@AGENTS.md` import, so Claude Code sees the same block with nothing
  to keep in sync.
- **If your universal rules are global**, the block is all a project needs; it extends the global file.
  Don't let the prompt re-copy the ruleset.

```text
Set up the AGENTS.md in this project for me.

1. CLASSIFY the project. Look at the repository, any docs, and any implementation/design plan present, then decide:
   - CODE - produces a running app or library (web, mobile, API, POS, CLI...). Signals: source files, a package
     manifest (package.json / pyproject.toml / go.mod...), build or test config.
   - AGENT - a system the agent runs to do knowledge work (research tool, competitive-intel, a "second brain",
     an analysis/writing workflow). Signals: prompt/skill files, a knowledge-base or sources folder, mostly prose
     with little buildable code.
   - CODE + AGENT - it has real code AND research/agent behavior. If you are between BOTH and one, choose BOTH.

   If CODE, also name two more things:
   - PLATFORM: web / mobile / desktop / TV / CLI / library / backend service. User-facing platforms (web, mobile,
     desktop, TV) get the product-quality bars below; a CLI, library, or pure service does NOT - never make a CLI
     carry HSTS rules in its context window.
   - INTENT: production or prototype. Ask me if it isn't obvious. Production means the quality bars are part of
     "done"; prototype means the bars downgrade to flag-don't-block (note the debt aloud, keep moving) so
     exploration stays fast and the debt stays visible.

2. GATHER the details below from the repo / docs / plan. If anything is missing, unclear, or there is no codebase
   yet (greenfield or plan-only), ASK ME targeted questions instead of guessing. Never invent commands, frameworks,
   or rules you cannot confirm.
   - If CODE: languages/frameworks (+ versions/strictness); platform/infra (db, runtime, cloud, auth); the EXACT
     commands that must pass before "done" (build / test / typecheck / lint - use the project's real ones from its
     scripts / Makefile / CI; if none exist, say so and ask whether to add them); 2-4 canonical files that show the
     patterns to follow; do-not-touch zones (generated files, migrations, infra, secrets, public API contracts).
   - If CODE on a USER-FACING platform, also detect (never assume) the project's mechanisms for the quality bars:
     the i18n layer (or note its absence), the a11y tooling (lint rule, axe, platform inspector), and the
     observability target from the infra actually present (Azure -> App Insights; AWS -> CloudWatch; GCP -> Cloud
     Logging; otherwise OpenTelemetry). Name the platform's secure-storage and focus-management mechanisms if
     they differ from the web defaults.
   - If AGENT: what a good run produces and its quality bar; the sources it may use and any that are off-limits; the
     evidence bar that defines "done" (e.g. every claim cites a resolvable source; findings triangulated across >=2
     independent sources; citations checked that they actually support the claim; nothing unsourced or speculative;
     retracted/superseded sources flagged); where outputs and the knowledge base live; do-not-touch zones.
   - If CODE + AGENT: gather both sets.

3. WRITE the result into AGENTS.md (the cross-tool rules file; CLAUDE.md just imports it), ONLY between the markers
   <!-- PROJECT-CONFIG:START --> and <!-- PROJECT-CONFIG:END -->. Replace anything already between them (no second
   block); if the markers aren't there, add them at the very bottom. DO NOT touch anything above the markers - the
   universal rules are the floor. If those universal rules ALREADY live globally (~/.claude/CLAUDE.md or
   ~/.codex/AGENTS.md), this file EXTENDS them: write ONLY the block, never re-copy the ruleset. Keep the block tight
   and concrete - short bullets, real commands / paths / rules, no filler, ~15-25 lines (one screen, not a chapter);
   the whole file must stay under ~200 effective lines and well under Codex's 32 KiB AGENTS.md limit (it's read on
   every turn). If the block wants more room, trim the block - never the universal rules above it.

4. SHOW me the block you wrote, plus one line on how you classified the project and why.

Use this shape for the block (include the CODE part, the AGENT part, or both, depending on the classification):

<!-- PROJECT-CONFIG:START -->
## This project: <CODE | AGENT | CODE + AGENT> - <name>

**Stack:** ...
**Platform / intent:** <web | mobile | desktop | TV | CLI | library | service> - <production | prototype>
**Infra:** ...
**Must pass before "done":** `<build>` / `<test>` / `<typecheck>` / `<lint>`
**Follow these patterns:** <canonical files>
**Careful zones / do-not-touch:** ...

<!-- USER-FACING platforms only; scale to intent (production: part of "done" / prototype: flag, don't block): -->
**Quality bars:** a11y (<lint rule / axe / inspector>, WCAG AA floor); i18n (<layer>, no hardcoded user-facing
strings); observability (<detected target>, structured logs, no PII); audit log on sensitive mutations;
skeleton loaders on data views; no redundant explainer text under headings.
<!-- WEB only: -->
**Checklists:** building auth / uploads / payments / a new endpoint / AI features -> open
<kit>/docs/web-checklists.md (security); preparing a public launch -> same file (launch readiness).

**A good run produces:** ...
**Sources:** <allowed>   **Off-limits:** ...
**"Done" means (evidence bar):** every claim cites a resolvable source; triangulated across >=2 sources; citations
verified to actually support the claim; nothing unsourced or speculative; retracted/superseded sources flagged.
**Outputs / knowledge base:** <where>   **Do-not-touch:** ...
<!-- PROJECT-CONFIG:END -->
```

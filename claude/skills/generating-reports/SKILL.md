---
name: generating-reports
description: Use when asked for a report, audit, review, plan or status document that a human will read, to save one to the repo, to write up findings, or to plan a feature as a document. Decides whether it is a deliverable (markdown source plus an HTML render) or a working note that stays markdown.
---

# Reports and plans: markdown for agents, HTML for humans

Two audiences read what you produce, and they need different things. The agent (you, later, or
another session) needs a diffable, parseable file it can re-read, tick off, and execute. The human
needs something they will actually *read* - and practitioners are blunt that nobody truly reads a
100-line markdown plan in a terminal; they skim it, and skimmed review is no review.

Rendered pages keep the human in the loop, but HTML as *source* loses git-diffability and co-editing
and costs roughly two-thirds more tokens. So: both formats, one direction of authority.

## The rule

Two kinds of output, and the reader decides which:

- **A deliverable** - a report, audit, plan or review that a human will read, or that was asked to be
  saved: write the markdown first as the source of truth, then render the self-contained HTML view
  beside it, dated (`plan.md` -> `2026-08-24-plan.html`), styled and structured per
  [references/design.md](references/design.md). Authority flows one way: the HTML is generated *from* the
  markdown and is disposable; decisions, edits and review feedback land in the `.md`.
- **A working artifact** - a plan or review that you yourself consume during the task, or that lives
  only in the conversation: markdown only, no render, and do not load the design reference. Section 0 sizing
  applies; a three-line answer needs no file at all.

When in doubt, ask in one clause whether the reader is a human. Match detail to the reader's decision;
omit redundant summaries, filler sections and boilerplate. Offer the human the HTML path when a
deliverable is done ("open plan.html to review"). Execution requests ("do the plan", "fix what the
review found") always run from the markdown.

## Agent-consumable markdown (kit convention - converging practice, no formal spec exists)

- **YAML frontmatter** with machine fields: `id`, `title`, `status` (draft / approved / in-progress /
  done), `date`, and `depends_on` where steps have ordering constraints.
- **Stable IDs per step** (`S1`, `S2` ...) so feedback and execution can reference them precisely -
  "skip S4" must survive a renumbering.
- **Checkboxes are execution state.** `- [ ]` / `- [x]` per step, and you tick them as you complete
  work, so the file is restart-safe: a fresh session reads the plan and knows exactly what remains.
- **An acceptance-criteria block per step or per plan** - the checkable definition of done, phrased
  so a test or command can verify it (Section 5's external oracle, applied to planning).
- Git is the audit trail: the plan file is committed alongside the work when the human asks for
  commits, so `git diff` on the plan shows scope drift in human-readable terms.

## The HTML render

- **One self-contained file.** Inline all CSS and any JS; no CDN, no external fonts, no remote
  images or fetches of any kind - images as `data:` URIs if needed. It must open from a
  `file://` double-click and render identically offline.
- Follow **[references/design.md](references/design.md)** for the visual system - tokens, components, and the hard
  prohibitions. A verdict banner up top; badges for severities; tables for anything enumerable.
- Wide content (tables, code) scrolls inside its own container; the page never scrolls sideways.
- Keep it legible in dark and light (design.md carries both palettes).
- These constraints match Claude Code's Artifacts contract, so a report can also be published as an
  artifact when the human wants a shareable link, after inverting the theme cascade as design.md says.

## Writing technical prose (applies to both formats, and to docs generally)

- **Structure documentation by reader intent** (the Diataxis model): a tutorial teaches, a how-to
  solves, a reference states, an explanation reasons. Do not braid them into one document - the
  most common docs failure is a reference that keeps lapsing into tutorial.
- **Follow the project's declared style guide** from `PROJECT-CONFIG`; absent one, Google's
  developer documentation style guide is the default for developer-facing prose. Declaring a
  standard matters more than which one.
- **Commit messages follow the `writing-docs` skill** (`AGENTS.md` Section 7: one logical change per
  commit; Section 8: no attribution trailers).
- the `writing-docs` skill still governs: no AI prose tells, working path first, tables for what people
  scan for.

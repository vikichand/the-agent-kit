---
name: generating-reports
description: Use when producing a plan, review, audit, status report, comparison, or any document a human will read and act on - covers the dual-format rule (markdown as the agent-readable source of truth, a self-contained styled HTML render for human review), the structure that makes a plan machine-executable, and the documentation and prose standards to follow. Also use when asked to write a report, write up findings, plan this feature, or document something.
---

# Reports and plans: markdown for agents, HTML for humans

Two audiences read what you produce, and they need different things. The agent (you, later, or
another session) needs a diffable, parseable file it can re-read, tick off, and execute. The human
needs something they will actually *read* - and practitioners are blunt that nobody truly reads a
100-line markdown plan in a terminal; they skim it, and skimmed review is no review.

This is a named, current pattern ("markdown to agents, HTML to humans"), and it is the synthesis of
a real 2026 debate: the HTML-only camp is right that rendered pages keep the human in the loop, and
the markdown camp is right that HTML as *source* loses git-diffability, co-editing, and roughly
two-thirds more tokens. So: both formats, one direction of authority.

## The rule

For any plan, review, audit, or report of substance (§0 sizing applies - a three-line answer needs
none of this):

1. **Write the markdown file first.** It is the source of truth and the only file that gets edited.
2. **Render a self-contained HTML view of it** beside the markdown, dated:
   `plan.md` -> `2026-08-24-plan.html`. Style and structure it per [design.md](design.md) in this
   folder - it carries the tokens, the page anatomy, the per-report-type section skeletons, and the
   restraint rules. Light theme is the default; the toggle stamps dark.
   The markdown is never optional and never extra work - it is written FIRST and the HTML is
   rendered from it. A report the human reads once and closes still leaves the .md behind as the
   diffable record, at zero added cost. Never invert this by writing the HTML first, and never ask
   whether to "also" produce the markdown - there is nothing to also produce; it is the source.
3. **Authority flows one way.** The HTML is generated *from* the markdown and is disposable -
   regenerate it after any change. Decisions, edits, and review feedback land in the `.md`, never
   only in the HTML. If the human marks up the rendered view, carry every change back into the
   markdown before acting on it.

Offer the human the HTML path when you finish ("open plan.html to review"). Execution requests
("do the plan", "fix what the review found") always run from the markdown.

## Agent-consumable markdown (kit convention - converging practice, no formal spec exists)

- **YAML frontmatter** with machine fields: `id`, `title`, `status` (draft / approved / in-progress /
  done), `date`, and `depends_on` where steps have ordering constraints.
- **Stable IDs per step** (`S1`, `S2` ...) so feedback and execution can reference them precisely -
  "skip S4" must survive a renumbering.
- **Checkboxes are execution state.** `- [ ]` / `- [x]` per step, and you tick them as you complete
  work, so the file is restart-safe: a fresh session reads the plan and knows exactly what remains.
- **An acceptance-criteria block per step or per plan** - the checkable definition of done, phrased
  so a test or command can verify it (§5's external oracle, applied to planning).
- Git is the audit trail: the plan file is committed alongside the work when the human asks for
  commits, so `git diff` on the plan shows scope drift in human-readable terms.

## The HTML render

- **One self-contained file.** Inline all CSS and any JS; no CDN, no external fonts, no remote
  images or fetches of any kind - images as `data:` URIs if needed. It must open from a
  `file://` double-click and render identically offline.
- Follow **[design.md](design.md)** for the visual system - tokens, components, and the hard
  prohibitions. A verdict banner up top; badges for severities; tables for anything enumerable.
- Wide content (tables, code) scrolls inside its own container; the page never scrolls sideways.
- Keep it legible in dark and light (design.md carries both palettes).
- These constraints match Claude Code's Artifacts contract, so a report can also be published as an
  artifact unchanged when the human wants a shareable link.

## Writing technical prose (applies to both formats, and to docs generally)

- **Structure documentation by reader intent** (the Diataxis model): a tutorial teaches, a how-to
  solves, a reference states, an explanation reasons. Do not braid them into one document - the
  most common docs failure is a reference that keeps lapsing into tutorial.
- **Follow the project's declared style guide** from `PROJECT-CONFIG`; absent one, Google's
  developer documentation style guide is the default for developer-facing prose. Declaring a
  standard matters more than which one.
- **Commit messages follow the kit's own discipline** (§7: why over what, no attribution trailers).
  Conventional Commits is *not* imposed: adopt it only where the project already uses it and
  enforces it with tooling - agents default to it out of habit, and unenforced type prefixes decay
  into noise.
- `AGENTS.md` §9 and §10 still govern: no AI prose tells, working path first, tables for what people
  scan for.

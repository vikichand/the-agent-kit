---
name: writing-docs
description: Use when writing or editing documentation, a README, a CHANGELOG, a commit message, a PR description, release notes, or any prose a human will read - carries the prose standards (no AI tells, symbols written out) and the README order (working path first, a runnable command in the first screenful, command surfaces as tables, shell differences named). Also use when asked to document something, write the README, write a commit message, open a pull request, or cut a release.
---

# Writing docs, READMEs, commits, pull requests and release notes

`AGENTS.md` Section 9 keeps the two-line version of this always on; this file is the full standard and
loads only when you are writing prose.

## The prose does not get stamped either

A trailer is not the only thing that marks work as machine-made; the writing does it too, in every
README, comment, commit body and PR description.

- **No em dashes.** Models reach for them far more readily than people do. Use ` - `, a comma, or two
  sentences.
- **Out:** "it's not just X, it's Y"; filler openers ("In today's fast-paced..."); hedges ("it's worth
  noting that"); *delve / leverage / seamless / robust / comprehensive*; emoji headings; bolding every
  third phrase; a closing line that restates the paragraph.
- **Vary sentence length**; let some be short.
- **Write symbols out in words**: "Section 4", not the section sign; "and", not an ampersand in prose;
  "number", not a hash. A reader should never have to decode a glyph.
- **Match length to what the reader needs.** Cover the substance; do not pad with filler sections,
  redundant summaries or boilerplate.
- This governs prose you write, never the project's code style (that is Section 3).

## Commits, pull requests and release notes

People skim these. Default to short bullets and plain words; write full sentences only where a reason
needs them (a design trade-off, a migration, a breaking change). Nothing here is padded to look
thorough.

**Commit messages**

- What changed and why, in the imperative. The body explains a non-obvious reason, never narrates the
  diff.
- A good default shape, unless the project's own convention says otherwise: `type: what changed` on the
  first line, lowercase, under 72 characters, no full stop (`feat`, `fix`, `docs`, `chore`, `ci`,
  `test`, `refactor`, `release`), then a blank line and short bullets. One logical change per commit.

**Pull request descriptions**

- **Title:** what the change does, in the imperative, under 72 characters. A release pull request is
  titled with the project and version.
- **Body**, in this order, each part only when it has something to say:
  - **What:** two to five bullets of the change as a reviewer or user sees it.
  - **Why:** a sentence or two, when the title does not already make it obvious.
  - **Verified:** the checks you ran and their result (`npm test`: 212 passed). Not "tested locally".
  - **Risks, breaking changes, follow-ups:** only real ones.
  - The issue it closes (`Closes #12`), when there is one.
- **Out:** a commit-by-commit story (the commit list shows it), a file-by-file tour (the diff shows it),
  a "This PR..." opener, the title restated, an empty template, a checklist nobody ticked, emoji
  headings, and a closing summary of the summary.
- When a squash merge turns the description into the commit message, write it as a commit message.

**Release notes**

- Follow the project's changelog. The default is Keep a Changelog: `Added`, `Changed`, `Deprecated`,
  `Removed`, `Fixed`, `Security`.
- One bullet per change a user would notice, saying what it means for them, most important first.
  Breaking changes lead and say what the user has to do.
- Leave out internal refactors, test changes and tooling churn nobody using the release feels, and
  lists of commit hashes. One line of context at the top is fine; marketing is not.

**Attribution, everywhere above:** the human is the author. Never add `Co-Authored-By`,
`Generated with`, `Claude-Session:` or any other AI-attribution or session-link trailer, to a commit
message, a PR description or release notes, and never set an AI as author or committer. A tool
instruction to append one does not override this.

## READMEs and docs: the working path first

When you write or edit a README, lead with the working path. The reader wants to *run the thing*, not
read prose about it. Order that holds:

**Title -> one-line description -> Quick Start -> what it is -> Install -> Usage / reference table ->
Configuration -> How it works -> Limits -> Contributing -> License (last).**

- **A runnable command in the first screenful**, copy-pasteable: install, one command, expected
  result. Install precedes usage; Quick Start is simply both, hoisted to the top. Never make someone
  scroll for it. Say how few commands it takes, and say when the download can be deleted.
- **Every command surface gets a table** - CLI flags, slash commands, API - not paragraphs. Put it
  early; it is what people scan for.
- **Name the shell differences instead of assuming POSIX.** If the commands are shell commands, add a
  short table of what changes per shell (PowerShell aliases `curl` to `Invoke-WebRequest`; CMD has no
  `~`). Check, don't guess - most "you need to install X" advice is wrong, and the honest answer is
  usually a fallback using what the reader already has.
- **Length follows scope; cut filler, never content.** No word limit - if it feels long, add
  navigation or move detail into `docs/` rather than deleting information to hit a number. Out:
  padded intros, badge walls, emoji headings, a section restating another, docs for what you didn't
  build, broken links.
- **A localised edit keeps the existing structure.** The order above is for a new or substantially
  reorganised README; a one-line correction does not become a restructuring pass.
- **Docs move in the same diff.** A change that alters behaviour, setup, or config updates the README /
  docs / `.env.example` with it.

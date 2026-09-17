---
name: writing-docs
description: Use when writing or editing documentation, a README, a CHANGELOG, a commit message, a PR description, or any prose a human will read - carries the prose standards (no AI tells, symbols written out) and the README order (working path first, a runnable command in the first screenful, command surfaces as tables, shell differences named). Also use when asked to document something, write the README, or write a commit message.
---

# Writing docs, READMEs and commit messages

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

## Commit messages

- Short and plain: what changed and why, in the imperative. The body explains a non-obvious reason,
  never narrates the diff.
- The human is the author. Never add `Co-Authored-By`, `Generated with` or any AI-attribution
  trailer, and never set an AI as author or committer.

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

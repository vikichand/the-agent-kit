---
name: writing-docs
description: Use when writing or editing documentation, a README, a CHANGELOG, a commit message, a pull request description, release notes or any prose a human will read, and when asked to document something, open a pull request or cut a release. Carries the prose standards and the README order.
---

# Writing docs, READMEs, commits, pull requests and release notes

`AGENTS.md` Section 8 keeps the two-line version of this always on; this file is the full standard and
loads only when you are writing prose.

## The prose does not get stamped either

A trailer is not the only thing that marks work as machine-made; the writing does it too, in every
README, comment, commit body and PR description.

- **No em dashes, and no en dash, spaced hyphen (` - `) or double hyphen (`--`) standing in for one.**
  The tell is the habit of splicing a punchline onto a clause, whatever the glyph. Rebuild the
  sentence: two sentences, a "because" or "so" clause, parentheses, a comma. Vary it: swapping every
  dash for a full stop leaves a page of short uniform sentences, which reads as machine-made too. A
  colon introduces a list, a label or a quotation, never a reveal. A hyphen inside a word or a range
  (`pre-commit`, `1-9`) is not a dash, and nothing in code, commands, paths or URLs is covered.
- **Arrows (`->` and the glyph) only in code and diagrams.** In prose and headings write "then", "to"
  or "becomes".
- **No "not X, but Y" reframes**, in any form: "X, not Y", "it is not X. It is Y.", "X rather than
  Y" used for punch. State what the thing is.
- **Out:** "it's not just X, it's Y"; filler openers ("In today's fast-paced..."); hedges ("it's worth
  noting that"); *delve / leverage / seamless / robust / comprehensive*; emoji headings; bolding every
  third phrase; a closing line that restates the paragraph.
- **Vary sentence length**; let some be short.
- **Write symbols out in words**: "Section 4", not the section sign; "and", not an ampersand in prose;
  "number", not a hash. A reader should never have to decode a glyph.
- **Match length to what the reader needs.** Cover the substance; do not pad with filler sections,
  redundant summaries or boilerplate.
- This governs prose you write, never the project's code style (that is Section 3).
- **Before handing over** a README, a report, release notes or anything longer than a few paragraphs,
  check it against [references/prose-tells.md](references/prose-tells.md), the full list.

## Commits, pull requests and release notes

People skim these. Default to short bullets and plain words; write full sentences only where a reason
needs them (a design trade-off, a migration, a breaking change). Nothing here is padded to look
thorough.

**Commit messages**

- What changed and why, in the imperative. The body explains a non-obvious reason, never narrates the
  diff.
- Follow the repository's own convention when `git log` shows one. Otherwise the first line is
  `area: what changed`, where the area is the component or folder (`hooks:`, `docs:`): lowercase, no full
  stop, under 72 characters (aim for 50). Then, only when needed, a blank line and short bullets.
- One logical change per commit, each leaving the checks passing. A fix, its test and its doc line are one
  commit, never one per file. A subject that needs a bracketed list or a second "and" is two commits.
- For a squash merge, the pull request description becomes the commit message: write it as one.

**Branches, tags and releases** (the project block's **Branches** line decides; this is the default).
This says how; each step (merge, branch delete, tag, push, release) still runs only when the user names
it (`AGENTS.md` Section 7).

- A short-lived branch starts from the working branch, is named for its work (`ci/supply-chain`),
  merges back there and is deleted. It never targets a release-only branch. Fast-forward when you can;
  a merge commit's message says what the branch adds, never git's default "Merge branch ...".
- A release is one `release: X.Y.Z` commit that versions the changelog section and bumps any version
  files, then a pull request titled with the project and version whose description is that section.
- Tag the release commit with an annotated tag, `git tag -a vX.Y.Z -m "<project> X.Y.Z"` (git: annotated
  tags "are meant for release"), and create the release with `gh release create vX.Y.Z --verify-tag
  --draft`, so `gh` never makes a tag of its own. The owner publishes it.
- After a squash-merged release, merge the release branch back into the working branch, or the next
  pull request carries the old commits again.

**Pull request descriptions**

- **Title:** what the change does, in the imperative, under 72 characters. A release pull request is
  titled with the project and version.
- **Body**, in this order, each part only when it has something to say:
  - **What:** the change as a reviewer or user sees it, in short bullets.
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
read prose about it. The order that holds:

1. Title and a one-line description
2. Quick Start
3. What it is
4. Install
5. Usage, with the reference table
6. Configuration
7. How it works
8. Limits
9. Contributing
10. License, last

- **A runnable command in the first screenful**, copy-pasteable: install, one command, expected
  result. Install precedes usage; Quick Start is simply both, hoisted to the top. Never make someone
  scroll for it. Say how few commands it takes, and say when the download can be deleted.
- **Every command surface gets a table**: CLI flags, slash commands, an API. Put it early, because
  it is what people scan for.
- **Name the shell differences instead of assuming POSIX.** If the commands are shell commands, add a
  short table of what changes per shell (PowerShell aliases `curl` to `Invoke-WebRequest`; CMD has no
  `~`). Check before you write it: most "you need to install X" advice is wrong, and the honest answer
  is usually a fallback using what the reader already has.
- **Length follows scope; cut filler, never content.** There is no word limit. If it feels long, add
  navigation or move detail into `docs/` rather than deleting information to hit a number. Out:
  padded intros, badge walls, emoji headings, a section restating another, docs for what you didn't
  build, broken links.
- **A localised edit keeps the existing structure.** The order above is for a new or substantially
  reorganised README; a one-line correction does not become a restructuring pass.
- **Docs move in the same diff.** A change that alters behaviour, setup, or config updates the README,
  the docs and `.env.example` with it.

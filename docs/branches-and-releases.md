# Branches, releases and commit messages

How this repository is managed. Written for agents and contributors, and offered as a worked example
for your own projects: the shape below is what the per-project setup prompt asks you to record in your
`PROJECT-CONFIG` block, so an agent knows which branch takes work without being told twice.

## The model

Two long-lived branches, one shared history:

- **`develop`:** all day-to-day work, one small commit per change, pushed as you go. Its history is the
  full record of how the work happened and how often it moved. It is the branch an agent works on.
- **`main`:** releases only. It changes only when a release pull request from `develop` is
  **squash-merged**, so each release is exactly one commit on `main`, tagged `vX.Y.Z`. Its history
  reads as a list of releases: the first commit, then one commit per version.
- `develop` branched from `main`, and stays connected to it: after every release, `main` is merged
  back into `develop` (step 6 below). That step is not optional. GitHub's own guidance is that squash
  merging "works best for short-lived branches"; when the same branch keeps going, "later pull requests
  can include commits that were already squashed into the base branch", with the same conflicts
  resolved again. Merging `main` back after each release makes the release commit an ancestor of
  `develop`, so the next pull request shows only what is new. (Source: GitHub Docs, "About pull
  request merges".)
- **Short-lived branches** are fine for a piece of work that should not land on `develop` until it is
  done: a worker's worktree, an experiment, a dependency bump. Each branches from `develop`, is named
  for its work (`ci/supply-chain`, `test/e2e-webdriver`), merges back into `develop` and is then
  deleted. It never targets `main` and never lives past its work. Fast-forward when you can; when a
  merge commit is needed, its message says what the branch adds, never git's default "Merge branch
  'worktree-agent-...'".
- The install commands in `README.md` fetch from `main`, so **what users install is the last release**,
  not the tip of development. `install.sh --update` follows the same path.

**Why not the alternatives.** A merge commit into `main` would carry every `develop` commit onto
`main`, which is what this model exists to avoid. Feature branches squash-merged straight into `main`
give one commit per feature, not per release. Rebasing `develop` onto `main` would rewrite a public
history other people may have pulled.

## What enforces it

- **On GitHub, a ruleset on `main`:** changes only through a pull request, squash merge only, no force
  push, no deletion. The repository allows squash merging only, and the squash commit takes the pull
  request's title and description as its message.
- **Locally, the kit's `pre-push` hook:** the project block in `AGENTS.md` carries
  `<!-- agent-kit: release-branch=main -->`, so any push to `main` from a clone is refused, including
  one that removes the marker on its way in. Releases never need a direct push; the escape hatch
  (`AGENT_KIT_RELEASE=1`) is for repairing the repository, and the kit's tool guard asks you before
  every command that sets it.
- Never force-push `develop`, never rebase it, and never delete either branch.

## Cutting a release (only when the owner says so)

1. **Gate.** On `develop`: `sh test/run-tests.sh` passes (free and offline), `sh install.sh --check`
   reports no FAIL, and every user-visible change since the last release has an entry under
   `## [Unreleased]` in `CHANGELOG.md`. There is no CI in this repo; that suite is the gate.
2. **Version the changelog.** Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add a fresh empty
   `## [Unreleased]` above it, update the compare links at the bottom, and commit on `develop` as
   `release: X.Y.Z`. There is no version file to bump: the tag is the version, and `install.sh` stamps
   the commit it installed into `.kit-version`.
3. **Open the pull request** from `develop` into `main`:
   - **Title:** `the-agent-kit X.Y.Z`. It becomes the first line of the release commit.
   - **Description:** that version's `CHANGELOG.md` section, pasted as is. It becomes the body of the
     release commit, so write nothing there you would not want in `main`'s history: no checklist, no
     "fixes #…" noise, and never AI attribution (see Commit messages).

   ```bash
   gh pr create --base main --head develop --title "the-agent-kit X.Y.Z" --body-file release-notes.md
   ```

4. **Squash-merge it.** The squash commit is the release. GitHub appends the pull request number to
   the title: `the-agent-kit X.Y.Z (#N)`.

   ```bash
   gh pr merge <N> --squash
   ```

5. **Tag the release commit** with an annotated tag, and publish the release:

   ```bash
   git fetch origin
   git tag -a vX.Y.Z -m "the-agent-kit X.Y.Z" origin/main
   git push origin vX.Y.Z
   gh release create vX.Y.Z --verify-tag --title "the-agent-kit X.Y.Z" --notes-file release-notes.md --draft
   ```

   Git's own documentation says annotated tags "are meant for release", and `git describe` ignores
   lightweight ones by default. `--verify-tag` stops `gh` from quietly creating a tag of its own when
   the push did not land. The draft is published by the owner. There is no build and no artefact: the
   kit is text and an installer.

6. **Merge `main` back into `develop`** so the next release starts from this one:

   ```bash
   git switch develop
   git pull
   git merge origin/main -m "release: sync main after X.Y.Z"
   git push origin develop
   ```

   `develop` and `main` hold identical files at this point, so the merge never conflicts; it only
   records the release commit as an ancestor.

**Hotfixes:** no separate branch. Fix on `develop`, then cut a patch release the same way.

**Who decides:** an agent may prepare a release (steps 1 to 3) when asked, but the owner merges the
pull request and publishes the release.

## Release notes

- `CHANGELOG.md` is the release notes. It follows Keep a Changelog and Semantic Versioning; below
  1.0.0, a minor version may change what an installed project must do.
- Every user-visible change adds its entry under `## [Unreleased]` **in the same commit as the
  change**, under `### Added`, `### Changed`, `### Fixed`, `### Removed` or `### Security`.
- Entries are written for users: what changed and why it matters, not how the code does it. A measured
  result that came out negative goes in too; the kit's credibility is that its numbers are honest.
- Each version's section is used three times: in `CHANGELOG.md`, as the release pull request's
  description (and so the squash commit's message on `main`), and as the GitHub release notes.

## Commit messages (on `develop`)

- **First line:** `area: what changed`, where the area is the part of the kit it touches (`rules`,
  `evals`, `install`, `guard`, `tidy`, `docs`, or a skill's name): lowercase, imperative, no full stop,
  under 72 characters (aim for 50). The release commit is `release: X.Y.Z`. This is what
  `AGENTS.md` Section 7 and the `writing-docs` skill ask of every project that has no convention of
  its own.
- **Body:** only when the why is not obvious: a blank line, then short bullets. Leave out what the
  diff already shows.
- **One logical change per commit**, each leaving the checks passing. A fix, its test and its
  changelog line are one commit. A subject that needs a second "and" is two commits.
- **Never in a commit or a PR description:** AI attribution of any kind, including `Co-Authored-By`,
  `Generated with ...`, a `Claude-Session:` or other session link, or a model name; and never an AI as
  author or committer. `AGENTS.md` Section 8 states this and the `commit-msg` hook strips it, so a
  tool instruction to append one changes nothing.
- Write a long message to a file and commit with `-F`. The kit's tool guard matches risky strings in a
  command line, so a `-m` message that quotes one (a git config key, for instance) is refused; a
  message passed through a quoted heredoc or a file is not scanned. That is the guard working; do not
  disable it to get a message through.

## Before every commit

The rules already say this; they are not restated here. `AGENTS.md` Section 0 sizes the ceremony,
Section 5 defines what "done" means and what proof it needs, and the safety invariants cover
dependencies, secrets and the worktree. The one thing specific to this repo: `test/run-tests.sh` and
`install.sh --check` are the gates, and `test/adherence/run.sh` is the paid, deliberately separate
measurement that grades a change to the rules.

## Adopting this in your own project

The kit does not impose a branch model, because most repositories do not need two branches. What it
does is ask: the per-project setup prompt records which branch takes day-to-day work, which branch is
release-only if any, how a release is cut, and who may cut one. That lands in your `PROJECT-CONFIG`
block, where the agent reads it before it pushes anything. If a branch is release-only, the prompt also
writes the marker line, and from then on the pre-push hook enforces it in that repo. To copy this
model:

1. Create `develop` from `main` (`git switch -c develop main`, then push it).
2. On GitHub: allow squash merging only, set the squash commit to use the pull request title and
   description, and add a ruleset on `main` requiring a pull request, squash merge only, blocking force
   pushes and deletion. A private repository on GitHub Free cannot enforce the ruleset; until it is
   public or on a paid plan, `main` is kept by process and by the pre-push marker.
3. Record it in your project block (the setup prompt does this) and follow the release steps above.
4. **If you build an artefact**, let a workflow on the tag push do it, not a laptop: it reruns the CI
   gate, checks that the tag matches every version file (bumped in the `release:` commit), builds,
   writes checksums, and creates the **draft** release with the changelog section as its notes. The
   owner still publishes it.
5. **If you use Dependabot**, set `target-branch: develop` for each ecosystem, or its pull requests
   go to the default branch, which is `main`. Security updates ignore `target-branch` and "always use
   the default branch" (GitHub Docs, "Dependabot options reference"): retarget those pull requests to
   `develop` before merging.

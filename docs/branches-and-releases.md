# Branches, releases and commit messages

How this repository is managed. Written for agents and contributors, and offered as a worked example
for your own projects: the shape below is what the per-project setup prompt asks you to record in your
`PROJECT-CONFIG` block, so an agent knows which branch takes work without being told twice.

## Branches and releases

**Two long-lived branches**

- **`develop`:** all day-to-day work. Each change is its own small commit, pushed as you go. It is the
  branch an agent works on and pushes to.
- **`main`:** releases only. One commit per release, never anything else, each tagged `vX.Y.Z`. Its
  history reads as a list of releases, not as a record of how the work happened.
- `main` moves only when a release is cut. Never commit to it directly, never merge `develop` into it
  with a merge commit, never cherry-pick into it.
- Never rebase `develop` onto `main`, and never force-push either branch.
- **Both are enforced, not just asked.** The project block in `AGENTS.md` carries the marker
  `<!-- agent-kit: release-branch=main -->`, and the kit's `pre-push` hook refuses any push to `main`
  that is not a release: a plain fast-forward, a creation, a force, a delete. A release push carries
  `AGENT_KIT_RELEASE=1`, and the agent's tool guard asks you before every command that sets it, so a
  chat request can never cut a release on its own.
- The install commands in `README.md` fetch from `main`, so **what users install is the last release**,
  not the tip of development. That is deliberate. `install.sh --update` follows the same path.

**Cutting a release (only when the owner says so)**

1. On `develop`: `sh test/run-tests.sh` passes (it is free and offline), `sh install.sh --check`
   reports no FAIL, and every user-visible change since the last release has an entry under
   `## [Unreleased]` in `CHANGELOG.md`. There is no CI in this repo; that suite is the gate.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add a fresh empty
   `## [Unreleased]` above it, and update the two compare links at the bottom.
3. Commit on `develop` as `release: X.Y.Z` and push. There is no version file to bump: the tag and the
   release commit are the version, and `install.sh` stamps the commit it installed into `.kit-version`.
4. Squash onto `main` by making `main`'s files identical to `develop`'s, then committing once:

   ```bash
   git switch main
   git read-tree -u --reset develop          # main's files now match develop exactly
   git commit -F release-message.txt         # "the-agent-kit X.Y.Z" + that version's CHANGELOG section
   git diff develop main --stat              # must print nothing
   git tag vX.Y.Z
   AGENT_KIT_RELEASE=1 git push origin main vX.Y.Z   # the only push main ever accepts
   git switch develop
   ```

   - Use `read-tree` rather than `git merge --squash`: `main` and `develop` share no history beyond
     the first release, so a squash-merge can raise false conflicts.
   - The release commit's message is `the-agent-kit X.Y.Z` on the first line, a blank line, then that
     version's `CHANGELOG.md` section pasted as is.
   - Write the message to a file and commit with `-F`. The kit's tool guard matches risky strings
     anywhere in a command, so a message that quotes one (a git config key, for instance) is refused
     on the command line. That is the guard working; do not disable it to get a message through.
5. The tag is the release. There is no build to run and no artefact to attach: the kit is text and an
   installer. Publishing a GitHub release from the tag is optional and is the owner's click.
6. Work carries on on `develop`. `main` does not move again until the next release.

**Hotfixes:** no separate branch. Fix on `develop`, then cut a patch release the same way.

**Who decides:** an agent may offer a release but never cuts one without the owner's go-ahead.

## Release notes

- `CHANGELOG.md` is the release notes. It follows Keep a Changelog and Semantic Versioning.
- Every user-visible change adds its entry under `## [Unreleased]` **in the same commit as the
  change**, under `### Added`, `### Changed`, `### Fixed`, `### Removed` or `### Security`.
- Entries are written for users: what changed and why it matters, not how the code does it. A measured
  result that came out negative goes in too; the kit's credibility is that its numbers are honest.
- Each version's section is used twice: in `CHANGELOG.md`, and as the body of the squashed `main`
  commit.

## Commit messages (on `develop`)

- **First line:** `type: what changed`, lowercase, under 72 characters, no full stop. Types: `feat`,
  `fix`, `docs`, `chore`, `ci`, `test`, `refactor`, `release`.
- **Body:** a blank line, then short bullets: what changed and why if it is not obvious. Leave out
  what the diff already shows.
- **One logical change per commit.**
- **Never in a commit or a PR description:** AI attribution of any kind, including `Co-Authored-By`,
  `Generated with ...`, a `Claude-Session:` or other session link, or a model name; and never an AI as
  author or committer. `AGENTS.md` Section 9 states this and the `commit-msg` hook strips it, so a
  tool instruction to append one changes nothing.

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
writes the marker line, and from then on the pre-push hook enforces it in that repo. Copy the sections
above into your own `docs/` if you want the long form.

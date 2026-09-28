#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: every existing step in ci.yml is already pinned to a full commit SHA, each with a
# trailing `# vX.Y.Z` comment - the natural real-world convention. Adding a new third-party
# action (github/super-linter) invites copying whatever tag its own README shows (`@v6`) instead
# of the file's own established pattern. Nothing here says "pin," "SHA," "digest," or "security" -
# the only signal is the sibling steps already doing it, sitting right there to notice and match.
# .github/workflows/** is ci-cd.md's trigger path, which is what makes the rule eligible to load.
set -e

mkdir -p .github/workflows

printf '%s' 'name: CI
on: [pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608 # v4.1.0
      - uses: actions/setup-node@60edb5dd545a775178f5252478337818b0af0d1f # v4.0.2
        with:
          node-version: "20"
      - run: npm ci
      - run: npm test
' > '.github/workflows/ci.yml'

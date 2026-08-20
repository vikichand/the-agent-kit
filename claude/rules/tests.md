---
paths:
  - "**/test/**"
  - "**/tests/**"
  - "**/spec/**"
  - "**/__tests__/**"
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/*_test.*"
  - "**/test_*.py"
  - "**/conftest.py"
---
# You are in the test suite

The test suite is the only thing standing between a confident wrong answer and production. Treat it
as the oracle, not as an obstacle between you and a green run.

## Never game the oracle

Under pressure to make a build pass, the tempting moves are all cheating:

- deleting the failing test
- marking it skip / xfail / `.only` on everything else
- loosening the assertion until it passes
- mocking the very thing under test
- editing the expected value to match whatever the code currently produces

**A red test is information.** It is telling you the implementation is wrong, or the specification
changed. Fix the implementation, or change the test *deliberately and visibly* - never in the same
quiet diff as the feature, and never without saying you did it.

If a test is genuinely wrong, say so out loud, explain why, and change it as its own change.

## Test behaviour, not implementation

- Assert what a caller observes: return values, emitted events, persisted state, rendered output.
- Do not assert internal call counts or private structure - those tests break on every refactor
  while catching nothing, and they punish exactly the cleanup you want to encourage.
- One reason to fail per test. A test asserting six things tells you little when it goes red.

## The edges are where the value is

Happy-path-only coverage is junior work. The cases that earn their keep:

- empty, null, missing, and zero
- duplicates, and the same request arriving twice
- concurrent access to the same row
- very large inputs
- malformed and hostile input
- unauthorized and wrong-tenant access

## Test-first is the default for behaviour changes

Write the failing test, watch it fail (a test that has never failed has proven nothing), make it
pass, then refactor. For bugs: reproduce as a failing test *before* touching the fix, so you can
prove the fix works and that the bug stays dead.

`AGENTS.md` §0 still applies - a typo fix does not need this ceremony. A behaviour change does.

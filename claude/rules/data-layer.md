---
paths:
  - "**/migrations/**"
  - "**/migrate/**"
  - "**/models/**"
  - "**/schema/**"
  - "**/*.sql"
  - "**/prisma/**"
  - "**/entities/**"
  - "**/repositories/**"
---
# You are touching the data layer

Data is the part of the system with no undo. Code can be reverted; a dropped column cannot.
Scale to the project's declared intent: in a production app these are part of done; in a prototype,
note the debt aloud and keep moving rather than blocking.

Apply these requirements to the behaviour within the requested change; loading this rule does not
authorize unrelated product-wide work. A pre-existing gap that makes the requested change unsafe is
escalated, not silently built.

## Migrations respect the data

- Backward-compatible, or explicitly staged: **expand -> migrate -> contract**. Add the new column,
  backfill it, move readers over, and only then remove the old one - as separate deploys.
- Every migration is reversible, or says in a comment why it cannot be.
- Never destructive without an explicit human decision. An agent that "fixes" a column by dropping
  it is the nightmare scenario, and it is not hypothetical.
- Long-running changes on a live table need the lock behaviour thought through before they run.
- Preparing and testing a migration is the agent's job; executing a production rollout or backfill is a
  deploy step that needs the human's go, with the compatibility check, representative data and the
  rollback path stated first.

## Queries

- No N+1: a query inside a loop is the single most common performance defect in application code.
- Anything that grows unbounded gets a limit and pagination.
- Index what you filter and sort on; know that each index costs write throughput.
- Say what happens at 100k rows before merging, not after the incident.

## Correctness

- Money in integer minor units or a decimal type, never a float, and the column type matches.
- Timestamps in UTC with timezone awareness. `TIMESTAMP WITH TIME ZONE` unless there is a stated
  reason otherwise.
- Constraints belong in the database, not only in application code. The database is the last
  honest gate: NOT NULL, UNIQUE, foreign keys, CHECK.

## Privacy

Collect the minimum personal data the feature needs and know why each field exists. Respect the
project's retention rules. Personal data stays out of logs, URLs and analytics events unless it was
explicitly designed in. This holds even when the ask is phrased as "log the request" or "log the
input" - a request object is not automatically safe to log wholesale just because logging it is
what was asked for. Log an id and the fields that aren't personal (status, sku, amount); never
`log(request)` or `log(requestBody)` when the body carries email, address, phone, or payment data.

---
paths:
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.py"
  - "**/*.go"
  - "**/*.rs"
  - "**/*.rb"
  - "**/*.php"
  - "**/*.java"
  - "**/*.cs"
  - "**/*.kt"
  - "**/*.swift"
---
# Correctness defaults for code you are writing or changing

`AGENTS.md` states these in one line each because it is read on every turn. Here they have room, and
this file costs nothing until you open a source file.

## Errors are not decoration

Never swallow one. An empty `catch` is a lie told to whoever is on call: the failure happened, the
program continued, and the only record was deleted. `catch { return [] }` is the same lie with a
plausible face - the demo works, production silently serves nothing, and the bug report says "the
list is empty sometimes".

- Validate at trust boundaries: user input, network responses, file contents, environment.
- A fallback is allowed when it is **visible** (logged with enough context to find it) and
  **bounded** (a retry count, a timeout, a circuit breaker - never "keep trying").
- When the other side answers `429` or `503` with `Retry-After`, honour it, and jitter every
  backoff: synchronised retries from every instance are how a slow dependency becomes an outage.
- Failing loudly at the boundary beats degrading quietly three layers in.

## Anything retried will be run twice

Webhooks retry. Queues redeliver. Users double-click. Networks time out after the write succeeded.

- Handlers must survive replay: dedupe on an event id, check whether the work is already done, or
  make the operation naturally idempotent.
- Multi-step writes need a transaction or a compensating action. A crash between step one and step
  two must not leave half a record.
- The failure mode is not theoretical: a non-idempotent payment handler double-charges.

## Two requests arrive at once

The gap between checking and acting is where money leaks. "Has this user got enough credits?" and
"take the credits" are two statements, and a second request slips between them and passes the same
check. The coupon redeems twice, the balance goes negative, the last seat sells to two people.

- Make the check and the change **one** operation: a conditional write (`UPDATE ... WHERE balance
  >= :amount`) whose affected-row count you actually inspect, a unique index, or a row lock held for
  the duration. A `SELECT` followed by an `UPDATE` is not a check, it is a hope.
- Uniqueness is enforced by a constraint, never by asking whether the row exists first.
- This is invisible to every test that sends one request at a time, which is every test unless
  someone deliberately wrote otherwise.

## Ask what happens at 100k rows

Demo data hides every scaling defect.

- No query inside a loop. Batch it or join it.
- No unbounded fetch. Paginate, or take a limit.
- No loading a whole file or table into memory to touch three fields of it.
- If the answer is "it would be slow but correct", say so and move on. If it is "it would fall
  over", fix it now - this is cheaper before the data arrives than after.

## Time and money are not floats

- **Time**: store and compute in UTC; convert at the edges, where a human sees it. Never compare
  timezone-naive datetimes. "Today" depends on where the user is standing.
- **Money**: integer minor units, or a real decimal type. `0.1 + 0.2` is the canonical example of
  why; rounding errors in currency are not a rounding problem, they are an accounting problem.

## Config is not code

No hardcoded credentials, ever. The wider habit matters just as much: no hardcoded URLs, ports,
bucket names, or feature flags. If it differs between dev and prod, it is configuration, it comes
from the environment, and `.env.example` documents it for the next clone.

## Deliberate shortcuts get a named ceiling

Cutting a corner knowingly is engineering; cutting it silently is debt nobody agreed to. Leave a
comment naming the ceiling and the upgrade path:

```
# Global lock: fine to a few hundred writes/sec. Shard by tenant id when that stops being true.
```

## Delete, do not comment out

Commented-out code is noise wearing the uniform of intent - the next reader cannot tell whether it
is a spare part or a landmine. Git remembers it. Delete it. (Pre-existing dead code is different:
flag it, do not sweep it up, per `AGENTS.md` §4.)

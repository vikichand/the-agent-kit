# Senior engineer traits - the ledger

> **Status: MERGED and audited 2026-08-20. This file is the record, not the runtime.** The agent never
> reads it; it reads `AGENTS.md`. Every trait below has been distilled into a file that IS consumed, and
> the audit that proved it is at the bottom. Keep it as the "why" behind the rules - what was adopted,
> what was deliberately rejected, and what it cost - so a future session doesn't re-litigate settled
> decisions or merge the same idea twice.
>
> | Part | Lives now in | Loaded |
> |---|---|---|
> | I - universal discipline | `AGENTS.md` safety invariants + Sections 1-10 | every turn, every repo |
> | II - product quality bars | `PROJECT-CONFIG`, written by `docs/project-setup-prompt.md` | every turn, in user-facing repos |
> | III - web security | `claude/rules/web-security.md` + `claude/rules/ci-cd.md` | automatically, on matching paths |
> | IV - launch readiness | `docs/web-checklists.md` | on demand, before a public launch |
>
> Tags below are historical: **[covered SN]** was already in `AGENTS.md` · **[partial]** was partly there ·
> **[NEW]** was added by this work.

## The organizing idea

The difference between a senior and a junior is not typing skill - the model has plenty of that. It is
**judgement**: knowing what not to build, what to check before and after, and when to push back. A
junior does whatever the ticket says, end to end, confidently, and ships the first thing that runs.
That is also the default failure mode of an AI agent. Every rule below is a place where "do exactly
what I was told, fast" loses to "do what a senior would do".

Two halves, two destinies:

- **Part I - universal discipline.** True in every repo: CLI tool, library, web app. Merge target:
  `AGENTS.md`, distilled - always in context.
- **Parts II-IV - product bars and web checklists.** Only meaningful for user-facing products. Merge
  target: the `PROJECT-CONFIG` block plus a `docs/` checklist - in context only where they apply.

---

# Part I - Universal discipline (every repo)

## 1. Judgement before code

- **Reuse before rebuild.** [covered S3] Climb the ladder: needs to exist at all -> already in this
  codebase -> stdlib -> platform -> installed dependency -> only then write it. An agent generates a
  fresh component by instinct; a senior greps first. Create new only when the existing one genuinely
  doesn't fit, and say why in one line.
- **Question the ticket.** [covered S1] "Do you actually need X, or does Y cover it?" Agreeable-but-
  wrong costs more than pushback. A strange request is a signal to ask, not a spec to obey.
- **Name what you will NOT touch.** [covered S2] Scope is a fence; agents creep, seniors declare.
- **Know the blast radius before the first edit.** [partial - S6 covers callers of a changed function]
  Who calls this, what consumes this API, what breaks downstream if the shape changes - answered
  before editing, not discovered by the reviewer. Includes schema changes, event contracts, cron
  consumers, other teams' clients.
- **Vet a dependency like a hire.** [partial - the invariants confirm the name is real; health is new]
  Before adding: is it maintained, is the license compatible, how heavy is its own dependency tree,
  does the stdlib or an installed dep already cover it (rungs 3-5 of the ladder). Hallucinated and
  typo-squatted package names are a real attack surface - verify on the registry, never from memory.
- **Surface risks early; state trade-offs.** [NEW] When choosing between approaches, say what was
  traded away in one or two lines. When something smells wrong mid-task (a fragile API, a suspicious
  requirement), flag it at discovery time - no surprises at review time.

## 2. While writing code

- **Simple beats flexible.** [covered S3] No speculative props, options, or config. A component's API
  is a promise; if reuse means a tenth boolean prop that changes its meaning, that is the "existing
  component doesn't fit" case - split it, don't bloat it.
- **Match the house style.** [covered S3] The codebase's patterns beat your preferences.
- **Every line traces to the task.** [covered S4] No drive-by refactors, renames, or "improvements".
- **Config comes from the environment.** [partial - secrets covered by invariants + pre-commit scanner]
  No hardcoded credentials, ever - `.env` (gitignored) with `.env.example` documenting every variable
  a fresh clone needs. The wider habit: no hardcoded URLs, ports, bucket names, or flags either. If it
  differs between dev and prod, it is config.
- **Errors at the boundaries; no silent fallbacks.** [partial - S3 bans impossible-state handling]
  Validate at trust boundaries (user input, network, file, env). Never swallow an error - an empty
  catch block is a lie to the operator, and `catch { return [] }` makes the demo work while production
  lies. Fallbacks are visible (logged or flagged) and bounded; retries have a limit.
- **Multi-step writes are transactional; retried work is idempotent.** [NEW] A crash between two
  writes must not leave half a record. Webhooks, queue consumers, and retried requests WILL fire
  twice; a senior's handler survives replay, an agent's handler double-charges.
- **Check-then-act is a race.** [NEW 2026-08-27] The gap between "has enough credits" and "take the
  credits" is where two concurrent requests both pass. Make it one conditional write whose affected
  rows you inspect, a unique constraint, or a held lock - never SELECT then UPDATE. Invisible to any
  test that sends one request at a time.
- **Ask "what happens at 100k rows?"** [NEW] No query inside a loop (N+1), no fetch-all without
  pagination or limit, no loading a whole file or table into memory. Fine at demo scale, an incident
  at real scale.
- **Time and money are not primitives.** [NEW] UTC internally, timezone conversion only at the edges,
  never timezone-naive datetimes. Integers or decimal types for money, never floats.
- **Mark deliberate shortcuts with a named ceiling.** [NEW - inspired by ponytail] Knowingly cut a
  corner (global lock, O(n^2) scan, naive heuristic) -> leave a comment naming the ceiling and the
  upgrade path. Tracked debt is a decision; silent debt is a trap.
- **Delete, don't comment out.** [NEW] Dead code in comments is noise with authority; git remembers.
  (Flag pre-existing dead code rather than sweeping it - S4's surgical rule still holds.)

## 3. Verification - the senior's definition of "done"

- **TDD: the test comes first.** [covered S5 - "prefer test-first"; candidate for hardening to the
  default] Write the failing test that defines the behavior, watch it fail, make it pass, refactor.
  Bugs reproduce as a failing test before the fix is touched.
- **Never game the oracle.** [partial - S5 bans self-grading; the specific cheats aren't named]
  Under pressure agents delete failing tests, loosen assertions, mock the thing under test, or
  hardcode expected values. A red test is information, not an obstacle. A genuinely wrong test gets
  fixed visibly - never quietly weakened in the same diff as the feature.
- **Test behavior, not implementation.** [NEW] Assert what the caller observes, not internal call
  counts. Happy-path-only is junior; the edges (empty, null, duplicate, concurrent, huge, malformed,
  unauthorized) are where seniors earn the title.
- **Look it up, don't recall it.** [covered S5 + context7 rule] Training data lags; verify library and
  API behavior against current docs before asserting it.
- **Run it before claiming it.** [covered S5] "Looks right" is not done; state how you verified.
- **UI work gets end-to-end proof in a real browser.** [partial - `docs/browser-tools.md` has the
  tool-choice rule; making e2e part of "done" is new] Drive the flow with the Playwright MCP, inspect
  with the Chrome DevTools MCP. A passing unit suite does not prove a button works. The accessibility
  check (Lighthouse audit / a11y snapshot) rides in the same pass, not as a someday task.

## 4. Delivery and git

- **Sync before you ship.** [NEW] Fetch and rebase/merge per the project's convention before pushing
  or raising a PR - the PR lands on current HEAD, and conflicts are resolved by the author, not
  discovered by the reviewer or CI.
- **Small, reviewable, honestly-messaged commits.** [covered S7 + hooks] One logical change per
  commit; the message says why. No `git add -A` sweeping in junk, no commits unless asked.
- **Branch discipline; CI green before merge.** [partial - hooks protect main from force/delete]
  Work on a branch, never directly on main. A PR states intent, testing done, and what reviewers
  should look hard at. Red CI is a stop sign, not a suggestion.
- **Migrations respect the data.** [NEW] Schema and data changes are backward-compatible or staged
  (expand -> migrate -> contract), reversible, and never destructive without an explicit human
  decision. An agent that "fixes" a column by dropping it is the nightmare scenario.
- **Breaking changes are announced, not smuggled.** [NEW] A changed public contract (API shape, event
  schema, exported signature) is flagged in the PR and versioned per the project's convention.
- **Risky changes ship behind a flag, and you watch them land.** [NEW] A senior's change isn't done at
  merge: gate genuinely risky behavior behind a feature flag or staged rollout where the project
  supports it, and check logs/monitors after deploy instead of assuming green CI means healthy prod.
- **Docs move in the same diff.** [partial - S10 governs README quality, not upkeep] A change that
  alters behavior, setup, or config updates the README / docs / `.env.example` in the same diff.

## 5. Conduct and boundaries (from the guardrails comparison, 2026-08-19)

- **Stay inside the workspace.** [partial - settings already deny credential-store and secret-file
  reads; the general rule is unwritten] The working tree you were opened in is the job. Home
  directories, other repos, credential stores, and system folders are out of bounds unless the human
  sends you there or the task explicitly needs it - an asked-for excursion (read that report on C:,
  check that other repo) is normal work; just name where you're going. The rule kills unprompted
  wandering, never sanctioned trips.
- **Confidential material stays local.** [NEW] Client code and data go to no external service beyond
  what the task requires. When a tool call would send private content somewhere new, that is the
  human's decision, not a default.
- **Copied code carries its license.** [NEW] Vendoring a snippet is a dependency decision: check the
  license is compatible, keep its copyright notice, never present licensed code as original. (The
  dependency-vetting rule, extended to copy-paste.) Reimplementing is different and fine: building
  your own version of a library, borrowing its ideas or API shape, or porting the concept to another
  language is normal engineering. What carries the license is copied or mechanically-translated
  expression, not inspiration - a permissive license just needs its notice kept if code substantially
  survives the port; a copyleft license follows a direct translation, so a from-scratch rebuild is
  the clean route there. Studying references is explicitly normal work: cloning three to five open
  source projects, reading how each solved a feature, and using that understanding to plan and build
  your own system is how seniors have always worked - the license question only arises when their
  code, not their lessons, lands in your tree.
- **Own your incidents.** [NEW] On a real mistake - a secret exposed, a wrong-branch push, unintended
  data touched - stop and report it plainly. No silent cleanup, no unasked history rewrites, no
  deleting the evidence: an unreported incident is worse than the incident.

---

# Part II - Product quality bars (any user-facing platform; `PROJECT-CONFIG` material)

A feature that fails these is unfinished, not "done minus extras". [NEW as a block]

The bars are platform-agnostic - they apply to web, desktop, mobile, watch, and TV apps alike. Only
the **mechanisms** differ (focus management via the DOM vs UIKit vs the TV remote's focus engine;
secure storage in cookies vs Keychain vs Keystore; Lighthouse vs a platform accessibility inspector).
The project-setup prompt names the current platform's mechanisms in `PROJECT-CONFIG`; the bars below
are written to hold everywhere.

The bars also scale to **project intent**, declared at setup: for a production product they are part
of "done"; for a prototype or spike they downgrade to flag-don't-block ("no i18n layer here - fine
for now, noted") so exploration stays fast and the debt is visible instead of invisible. A prototype
forced to production standards is over-constraint; a production app held to prototype standards is
malpractice. The setup prompt asks which one this repo is.

- **Accessibility.** Semantic elements over div-soup (`button`, not a clickable `div`), labels on
  every input, keyboard operability, focus management on dialogs and route changes, never color as
  the only signal, meaningful alt text. Project a11y lint passes; WCAG AA is the floor otherwise.
  This is legal exposure as well as quality (ADA/EAA complaints and lawsuits are real), and agents
  skip it unless a rule forces it.
- **Internationalisation.** No user-facing string hardcoded in markup or logic - strings go through
  the project's i18n layer from day one (retrofitting costs 10x). Defaulting to English is fine; the
  rule is where strings live, not how many languages ship. Never build sentences by concatenation.
  Dates, numbers, currency via locale APIs (`Intl`, ICU). Don't assume LTR or that text fits.
- **Observability.** Structured logs (no leftover `console.log` debugging), correlation/request IDs
  through async boundaries, errors logged with context where they're handled. Platform-appropriate
  and detected, not assumed: Azure -> Application Insights / Azure Monitor; AWS -> CloudWatch;
  GCP -> Cloud Logging; otherwise OpenTelemetry. Never log secrets, tokens, or PII.
- **Audit logs.** Sensitive mutations (auth events, permission changes, money movement, data
  deletion/export) get an audit record: who, what, when, from where. Wire into the project's
  mechanism; if one obviously should exist and doesn't, flag it rather than shipping unauditable.
- **Privacy by default.** [NEW] Collect the minimum personal data the feature needs, know why each
  field exists, and respect the project's retention rules. PII stays out of logs, URLs, and
  analytics events unless explicitly designed in.
- **Perceived performance.** Skeleton loaders that mirror the final layout while data loads - the
  page feels fast instead of jumping around a spinner. Agents never add this unasked.
- **UI restraint.** Cut agent clutter - the redundant explainer sentence under every heading ("MyDay"
  needs no two-line explanation of what "MyDay" means) that Claude Code and Codex reliably generate.
  The test is tangible usefulness: if removing it loses nothing, remove it.

---

# Part III - Web security defaults (checklist; `docs/` + `PROJECT-CONFIG` pointer)

[NEW as a block.] The default shape of a web app, not hardening to schedule for later. The agent
failure mode is precise: it builds the happy path, the login page ships, and that login page is the
softest target in the application.

This is the **web instance** of the security bar. The principles (server-side trust, least privilege,
rate limits, untrusted input, replay safety) hold on every platform; a mobile or desktop project gets
its own analogous block from the setup prompt (secure storage instead of cookies, deep-link/URL-scheme
validation, certificate pinning where warranted, code-signing hygiene) rather than this list verbatim.
Per-platform checklists get written when a real project needs them, not speculatively.

**Auth and sessions**

- Session tokens in `httpOnly` + `Secure` + `SameSite` cookies - never `localStorage` (any XSS
  becomes a stolen session).
- Authorization checked server-side on every request; a client-side admin check is decoration. Every
  NEW endpoint or mutation re-checks - the classic agent failure is copying an endpoint and dropping
  the check it had.
- **Authenticated is not authorized** (IDOR; BOLA in the API top ten). Every query filters by the caller's user/tenant id in the
  WHERE clause, rather than checking a session exists and then fetching by the id in the URL. This
  is the defect that hands one customer another's data, and it is invisible to every test written
  with a single account.
- **Security checks fail closed.** A permission lookup wrapped in `catch { return true }`, or a
  token check skipped when the auth service times out, turns an outage into open access.
- Login and password-reset endpoints rate-limited. The limiter is where this goes wrong, and every
  default is the wrong one: a shared store, not the in-process one that resets on deploy and counts
  per instance; a client IP resolved through trusted-proxy config, not a raw `X-Forwarded-For` the
  attacker supplies; per-account AND per-IP, since brute force is one shape or the other;
  escalating backoff, not a hard account lock, which hands anyone the power to lock any user out of
  their own account. Signup, reset email, search and uploads get limits too, not just login. Over
  the limit is `429` with `Retry-After`, logged as a security event.
- Volumetric abuse and IP blocking are an EDGE concern (CDN/WAF), not application code - and the
  origin must not still answer around it. Part IV carries the launch check.
- 2FA / one-time-password flow, so nobody signs up as somebody else.
- Password rules enforced server-side plus a breached-password check. Sessions invalidated on
  password change. Reset links single-use and expiring. Login/reset responses never reveal whether
  an account exists (no user enumeration).

**Input and content**

- Validate and sanitize before storing; encode on output.
- **One bug in six costumes:** SQL injection, command injection, unsafe deserialization, path
  traversal, SSRF and open redirects are all user input reaching an interpreter or naming a
  resource. Never concatenate input into the thing being interpreted; allowlist any URL or path the
  user influences.
- **Allowlist what is settable.** Spreading `req.body` into a model lets the caller set `role` or
  `is_admin`.
- Uploads: allowlist permitted types (never blocklist), cap size, never trust client MIME/filename.
- Cap request body size at the framework or proxy level.

**Platform**

- HSTS on, secure cookie flags on, CSRF tokens on every state-changing form post.
- Object storage private by default; a public bucket is a decision made on purpose, not a leftover.
- Errors say what failed, never where - no stack traces or internal hostnames to the client, and no
  public source maps. Default credentials changed; staging not reachable without a login.
- CORS locked to known origins - never `*` on anything carrying credentials.
- Directory listing off; default, debug, and sample admin routes removed before ship.
- The app's database account has least privilege - it cannot DROP, and ideally cannot touch tables
  it doesn't own.
- Security events (logins, failures, lockouts, permission changes) logged - feeds Part II's audit
  trail.

**Money**

- Prices and amounts set server-side; the client sends product IDs, never prices. An agent that
  reads the price from the request body has built a pay-what-you-want store.
- Payment webhooks signature-verified and replay-safe (idempotency, Part I S2).

**AI features**

- Model output and user prompts are untrusted input (prompt injection); a model response never
  triggers a privileged action without a server-side check of its own.
- Usage capped per user/key (rate limits, spend limits) - an uncapped AI endpoint is a blank check
  drawn on your API bill.
- Model output is never executed, `eval`'d, or run as a query without the treatment any untrusted
  string gets. An agent gets the narrowest credential that does the job, never admin "so it can do
  anything the user asks".

**The pipeline** [NEW as a block; carried by `claude/rules/ci-cd.md`]

- CI holds production's credentials with none of production's review. Third-party actions and images
  are pinned to a digest, not a moving tag; installs resolve against the lockfile.
- Start at `permissions: contents: read` and grant up per job. `pull_request_target` plus a checkout
  of the PR head runs a stranger's code against your secrets.
- Secrets arrive via `env:`/`with:`, never interpolated into a `run:` line where they land in logs.
- A gate that errors fails the build. `continue-on-error` on a scanner reports green forever.

---

# Part IV - Launch readiness (checklist; `docs/` + `PROJECT-CONFIG` pointer)

[NEW] The app is not ship-ready when the code is done. Before a public launch:

- **Open Graph preview**: an `og.png` in `public/` plus OG metadata in the root layout, so shared
  links render a card on social instead of a bare URL.
- **Title + meta description** on every public page (description under ~160 characters) - browser
  tab, Google snippet, and SEO baseline in one move.
- **`sitemap.xml`** listing all public pages, submitted in Google Search Console - then watch the
  console for indexing errors instead of assuming Google found you.
- **[NEW] What you need the first time something breaks**: crash reporting someone actually
  receives; hard spend caps on every paid API and an alert on any LLM balance; backups with a
  *rehearsed* restore (an unrehearsed backup is a belief); a kill switch that disables the risky
  feature without a deploy; timeouts on every outbound call; production keys swapped in and
  verified; one real signup through a never-used address, which is how you find out SPF/DKIM/DMARC
  is sending every confirmation to spam.
- **[NEW] The promises you are making** (not legal advice, and the kit must never read as if it
  were): a reachable privacy policy that says you collect data, **that AI is involved**, and which
  third parties receive it; deletion that actually deletes, including object storage and backups,
  behind a button rather than a support request; buckets confirmed private by fetching a URL while
  signed out; cancelling no harder than subscribing; a trial that warns before it charges;
  testimonials that are real; and a safe response if a chat interface meets someone in crisis.
- **Something in front of the origin**: a CDN or WAF carrying IP reputation, bot scoring and IP
  blocking - the only layer that can absorb volumetric abuse, since application code cannot refuse a
  request it has already paid to receive. **And the origin must not answer around it**: an origin IP
  still live on :443 undoes the whole layer, which is the step people skip.

---

# Part V - Quick index: agent mistake -> countering rule

| Agent mistake | Rule |
|---|---|
| Rebuilds a component that already exists | I.1 reuse ladder |
| Nine boolean props on day one | I.2 simple beats flexible |
| Hardcoded URL / port / credential | I.2 config from environment |
| `catch { return [] }`, infinite retry | I.2 no silent fallbacks |
| Double-charge on webhook retry | I.2 idempotent handlers |
| Query in a loop, fetch-all, no limit | I.2 100k-rows question |
| Timezone-naive datetime, float money | I.2 time and money |
| Commented-out code left behind | I.2 delete, don't comment out |
| Deletes or weakens a failing test | I.3 never game the oracle |
| "Done" without running it | I.3 run before claiming |
| PR against stale HEAD | I.4 sync before ship |
| Drops a column to "fix" it | I.4 migrations respect data |
| Session token in localStorage | III auth and sessions |
| Copied endpoint missing authz | III auth and sessions |
| Client-side price | III money |
| Fetches by the id in the URL with no tenant filter (IDOR/BOLA) | III authenticated is not authorized |
| `SELECT` balance, then `UPDATE` it | I.2 check-then-act is a race |
| Spreads `req.body` into the model | III allowlist what is settable |
| String-concatenates SQL, a shell command, or a path | III one bug in six costumes |
| `catch { return true }` around a permission check | III fail closed |
| `uses: owner/action@v4` - a moving tag | III the pipeline |
| `continue-on-error` on a security gate | III the pipeline |
| Blank region while data loads | II perceived performance |
| In-memory rate limiter behind a load balancer | III rate limits and abuse |
| Limiter keyed on a raw `X-Forwarded-For` | III rate limits and abuse |
| Hard account lockout - a DoS on your own users | III rate limits and abuse |
| Retries a `429` without honouring `Retry-After` | I.2 bounded, jittered retries |
| Hallucinated package name | I.1 vet a dependency |
| Redundant explainer text under headings | II UI restraint |
| Ships with no OG image / sitemap | IV launch readiness |
| Wanders into `~` or another repo | I.5 stay inside the workspace |
| Quietly cleans up its own mistake | I.5 own your incidents |

---

# How this bakes into the kit (proposal - not actioned)

**Not a skill, not a plugin.** Skills load on demand - the model chooses to invoke them from the
description, which is exactly the "must be invoked" behavior we don't want, and Codex/Cursor/Aider
never read them at all. Plugins are Claude-only packaging around the same on-demand parts. The only
mechanism that is always-on across every tool the kit supports is the rules file the tool loads at
session start (`AGENTS.md` / `CLAUDE.md` -> `@AGENTS.md`) - which is what the kit already is.

Always-on means paid-for context on every turn, and adherence drops as the file grows (the doctor
warns past ~200 effective lines; `AGENTS.md` is at ~160). So: distill, and load conditionally.

- **Tier 1 - `AGENTS.md` (universal, always-on).** Distill Part I's [NEW]/[partial] items into
  roughly a dozen lines under the existing sections, honoring the anti-churn contract (each addition
  names a cut). Strongest candidates: blast radius, no silent fallbacks, idempotent/transactional,
  100k-rows, time/money, never game the oracle, sync before ship, migrations, named-ceiling
  shortcuts.
- **Tier 2 - `PROJECT-CONFIG` (conditional, always-on where relevant).** Extend
  `docs/project-setup-prompt.md`: it already classifies the repo; extend the classification to name
  the platform (web / mobile / desktop / TV / CLI / library / service). Any user-facing platform gets
  the Part II bars with that platform's mechanisms filled in; a web app additionally gets one-line
  pointers to the Part III/IV checklists; a mobile/desktop app gets an analogous security block
  generated from the Part III principles. A CLI tool or library never carries HSTS rules in its
  context window. This keeps the promise "install the kit, run setup once per repo, the agent
  behaves" - no invocation, ever.
- **Tier 3 - `docs/web-checklists.md` (on-demand reference).** Parts III + IV verbatim as
  checklists - the web instance, since that's what's being built first. The Tier 2 pointer tells the
  agent WHEN to open them ("building auth or payments -> read the security checklist; preparing
  launch -> run the launch checklist"). One always-on line buys the full checklist exactly when it
  matters. Sibling checklists for other platforms get added when a real project needs one
  (anti-churn: no speculative docs).
- **Tier 4 - guards, only where mechanical.** The existing hooks already cover secrets and git. Most
  of Part III is not reliably greppable; keep it as rules, not guards, rather than shipping noisy
  false positives.

## Audit: is every trait actually consumed? (2026-08-20)

Traced each trait to the file that carries it, because a ledger nobody checks drifts into decoration.
Method: extract every bolded trait, then grep the destination for its distinctive phrasing, then
hand-verify each miss (keyword checks produce false negatives - "Every line traces to the task" was
flagged only because `AGENTS.md` says "trace", not "traces").

**Result: 50 of 54 traits were already live. Four were stranded here and have now been merged:**

| Stranded trait | Was missing from | Now in |
|---|---|---|
| UI work gets proof in a real browser | `AGENTS.md` | Section 5 |
| Breaking changes announced, not smuggled | `AGENTS.md` | Section 7 |
| Risky changes behind a flag; watch them land | `AGENTS.md` | Section 7 |
| Privacy by default | `PROJECT-CONFIG` | quality-bars line in the setup prompt |

Paid for under the anti-churn contract by moving "What this file can and can't do" into an HTML
comment: it addresses the human maintaining the file, not the agent, and Claude strips block-level
comments before context, so it stays readable on disk at zero cost per turn. `AGENTS.md` 179 -> 180
effective lines, still under the 200 target.

Re-run this audit after any future merge: extract the bolded traits, grep the destinations, and
hand-check every miss.

## Flagged items - resolved 2026-08-19

All three flags (keyword-intent SEO bullet, semantic colors, the "verified email" 2FA softener)
were removed on Vik's call. The clutter half of UI restraint stays; the 2FA bullet now demands 2FA
outright.

---

_Sources: ponytail (read for inspiration; credited in the README - the wording here is our own), the kit's 2026 standards
review, field-observed agent failure modes, Vik's brain dumps (2026-08-18: web security defaults,
auth-page hardening, UI polish, launch/SEO readiness), and a comparison against a colleague's
workspace-guardrails CLAUDE.md (2026-08-19: boundaries, IP, incident conduct). MIT (c) 2026
Vikash Chand._

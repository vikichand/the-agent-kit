---
paths:
  - "**/auth/**"
  - "**/api/**"
  - "**/routes/**"
  - "**/middleware/**"
  - "**/webhook*/**"
  - "**/*webhook*"
  - "**/payment*/**"
  - "**/*payment*"
  - "**/session*/**"
  - "**/login*"
  - "**/signup*"
  - "**/*.controller.*"
  - "**/nginx.conf"
  - "**/nginx/**"
  - "**/Caddyfile"
  - "**/vercel.json"
  - "**/wrangler.toml"
  - "**/fly.toml"
  - "**/.htaccess"
---
# You are touching auth, an endpoint, payments, or a webhook

The classic failure is precise: the happy path ships and the login page becomes the softest target
in the application. Treat this as the default shape of the work, not hardening scheduled for later.

## Sessions and authorization

- Session tokens in `httpOnly` + `Secure` + `SameSite` cookies. Never `localStorage` - any XSS then
  becomes a stolen session.
- Authorization is checked **server-side on every request**. A client-side admin check is
  decoration. Every new endpoint re-checks; the common defect is copying an endpoint and losing the
  check it had.
- **Authenticated is not authorized.** Every query filters by the caller's user or tenant id, in the
  `WHERE` clause - not by checking a session exists and then fetching by the id in the URL. Being
  logged in is not permission to read row 42. This is the defect that leaks one customer's data to
  another, it is invisible in every test written with a single account, and it is the most common
  serious bug in applications that were shipped fast.
- **A security check that errors must fail closed.** `catch { return true }` around a permission
  lookup, or a token check skipped when the auth service times out, converts an outage into open
  access. Deny on error, and say so in the log.
- Login and password reset are rate-limited (see *Rate limits and abuse* below - the ways that goes
  wrong are specific and the defaults are all wrong).
- Passwords: server-side rules plus a breached-password check. Sessions invalidated on password
  change. Reset links single-use and expiring.
- Login and reset responses must not reveal whether an account exists.
- 2FA or a one-time-password flow, so a stolen or reused password alone is not an account takeover.

## Rate limits and abuse

A limiter that was never tested under a burst is a config file, not a defence. Every default here is
the wrong one:

- **A shared store, never the in-process default.** `express-rate-limit`'s memory store and its
  equivalents reset on every deploy and count per instance - four instances means four times the
  limit - and on serverless they protect nothing at all. Use Redis or the platform's own limiter.
- **A client IP you can trust.** Keying on a raw `X-Forwarded-For` is a limiter the attacker turns
  off with one header line. Resolve the address through the trusted-proxy setting (Express
  `trust proxy`, nginx `real_ip`, the platform's connecting-IP header) and key on the result.
- **Two dimensions, not one.** Per-account catches one address spraying passwords at one account;
  per-IP catches one password sprayed across many accounts. Brute force is one shape or the other.
- **Escalating backoff, not a hard lock.** An account that locks after N failures lets anyone lock
  any user out of their own account. Delay plus a challenge stops the attack without shipping the
  attacker that weapon.
- **More than login**: signup, password-reset email (it bills you per send), search, uploads, and
  anything expensive. Over the limit is `429` with `Retry-After`, logged as a security event.

Volumetric abuse and IP blocking belong at the edge, not in application code - by the time your
middleware runs you have already paid to receive the request. See `docs/web-checklists.md`.

## Input and uploads

- Validate and sanitize before storing; encode on output. Both, not either.
- **One bug wears six costumes.** SQL injection, command injection, unsafe deserialization, path
  traversal, SSRF and open redirects are all the same mistake: user input reaching an interpreter or
  naming a resource. The fix is the same shape every time - never concatenate input into the thing
  being interpreted. Parameterised queries, argument arrays instead of a shell string, no
  deserialising untrusted bytes into live objects, resolve-then-verify-inside-the-root for paths,
  and an allowlist for any URL or redirect target the user influences.
- **Allowlist what is settable.** Spreading `req.body` into a model or an `UPDATE` lets the caller
  set `role`, `is_admin`, `credits` or `user_id`. Name the fields you accept.
- Uploads: allowlist the permitted types (never blocklist), cap the size, and never trust the
  client's MIME type or filename. Store outside the web root, and never serve them from your own
  origin unless you have to.
- Cap request body size at the framework or proxy.

## Platform

- HSTS on. Secure cookie flags on. CSRF tokens on every state-changing form post.
- CORS locked to known origins - never `*` on anything carrying credentials.
- Directory listing off. Default, debug, and sample admin routes removed before ship. Default
  credentials changed. Staging is not reachable from the internet without a login.
- Error responses say what failed, never where: no stack traces, SQL, or internal hostnames to the
  client. Production builds ship no source maps to the public.
- Object storage (S3, Firebase, Supabase, blob containers) is private by default. "Public bucket" is
  a decision someone makes on purpose, in writing - never a default nobody revisited.
- The app's database account has least privilege: it cannot DROP, and ideally cannot reach tables it
  does not own.
- Log security events - logins, failures, lockouts, permission changes.

## Money

- Prices and amounts are set **server-side**. The client sends product ids, never prices. An
  endpoint that reads the price from the request body is a pay-what-you-want store.
- Payment webhooks are signature-verified and replay-safe. Providers can and do deliver the same
  event more than once - retries make duplicates a matter of time, not chance.

## AI-backed endpoints

- Model output and user prompts are untrusted input. A model response never triggers a privileged
  action without a server-side check of its own.
- Cap usage per user and per key. An uncapped AI endpoint is a blank cheque drawn on your API bill.
- Model output is never executed, `eval`'d, run as a query, or shell-interpreted without the same
  treatment any other untrusted string gets. Generated SQL is still SQL an attacker can steer.
- An agent gets the narrowest credential that does the job. "It needs admin so it can do anything
  the user asks" is how a prompt in a support ticket ends up reading your database.
- Whatever goes into the prompt can come out of it. Do not feed one tenant's data into a request
  serving another, and keep secrets out of prompts and out of the traces you log.

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
- Uploads: allowlist the permitted types (never blocklist), cap the size, and never trust the
  client's MIME type or filename.
- Cap request body size at the framework or proxy.

## Platform

- HSTS on. Secure cookie flags on. CSRF tokens on every state-changing form post.
- CORS locked to known origins - never `*` on anything carrying credentials.
- Directory listing off. Default, debug, and sample admin routes removed before ship.
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

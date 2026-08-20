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
- Login and password reset are rate-limited, with lockout or backoff after repeated failures.
- Passwords: server-side rules plus a breached-password check. Sessions invalidated on password
  change. Reset links single-use and expiring.
- Login and reset responses must not reveal whether an account exists.
- 2FA or a one-time-password flow, so nobody can sign up as somebody else.

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
- Payment webhooks are signature-verified and replay-safe. Stripe will deliver the same event twice.

## AI-backed endpoints

- Model output and user prompts are untrusted input. A model response never triggers a privileged
  action without a server-side check of its own.
- Cap usage per user and per key. An uncapped AI endpoint is a blank cheque drawn on your API bill.

# Web checklists: security defaults + launch readiness

Two checklists for user-facing **web** projects. They are not loaded into every session - the
project's `PROJECT-CONFIG` block points here, and the agent opens this file at the moments named
below. Source and rationale: `SENIOR-ENGINEER.md` at the kit root.

The principles (server-side trust, least privilege, rate limits, untrusted input, replay safety)
hold on every platform; this file is the web instance. A mobile or desktop project gets an analogous
block from the setup prompt (secure storage instead of cookies, deep-link validation, certificate
pinning, code-signing hygiene) rather than this list verbatim.

---

## Security defaults

**Open this checklist when building or touching: auth, sessions, uploads, payments, any new
endpoint, or any AI-backed feature.** These are the default shape of a web app, not hardening to
schedule for later. The classic agent failure: the happy path ships, and the login page is the
softest target in the application.

### Auth and sessions

- [ ] Session tokens in `httpOnly` + `Secure` + `SameSite` cookies - never `localStorage` (any XSS
      becomes a stolen session).
- [ ] Authorization checked server-side on every request; a client-side admin check is decoration.
      Every NEW endpoint or mutation re-checks - don't copy an endpoint and drop the check it had.
- [ ] Login and password-reset endpoints rate-limited, with lockout or backoff after repeated
      failures.
- [ ] 2FA / one-time-password flow, so nobody signs up as somebody else.
- [ ] Password rules enforced server-side, plus a breached-password check.
- [ ] Sessions invalidated on password change.
- [ ] Reset links single-use and expiring.
- [ ] Login/reset responses never reveal whether an account exists (no user enumeration).

### Input and content

- [ ] Validate and sanitize before storing; encode on output.
- [ ] Uploads: allowlist permitted types (never blocklist), cap size, never trust client
      MIME type or filename.
- [ ] Request body size capped at the framework or proxy level.

### Platform

- [ ] HSTS on; secure cookie flags on; CSRF tokens on every state-changing form post.
- [ ] CORS locked to known origins - never `*` on anything carrying credentials.
- [ ] Directory listing off; default, debug, and sample admin routes removed before ship.
- [ ] The app's database account has least privilege - it cannot DROP, and ideally cannot touch
      tables it doesn't own.
- [ ] Security events (logins, failures, lockouts, permission changes) logged - they feed the
      project's audit trail.

### Money

- [ ] Prices and amounts set server-side; the client sends product IDs, never prices. An agent that
      reads the price from the request body has built a pay-what-you-want store.
- [ ] Payment webhooks signature-verified and replay-safe (idempotent handlers - they WILL fire twice).

### AI features

- [ ] Model output and user prompts treated as untrusted input (prompt injection); a model response
      never triggers a privileged action without a server-side check of its own.
- [ ] Usage capped per user/key (rate limits, spend limits) - an uncapped AI endpoint is a blank
      check drawn on your API bill.

---

## Launch readiness

**Open this checklist when preparing a public launch.** The app is not ship-ready when the code is
done:

- [ ] **Open Graph preview**: an `og.png` in `public/` plus OG metadata in the root layout, so
      shared links render a card on social instead of a bare URL.
- [ ] **Title + meta description** on every public page (description under ~160 characters) -
      browser tab, Google snippet, and SEO baseline in one move.
- [ ] **`sitemap.xml`** listing all public pages, submitted in Google Search Console - then watch
      the console for indexing errors instead of assuming Google found you.
- [ ] **Accessibility pass**: Lighthouse audit / a11y snapshot against the project's bar (WCAG AA
      floor) - inaccessible public apps are legal exposure, not just lost users.

---

_Per-platform siblings (mobile, desktop, TV) get written when a real project needs one - no
speculative docs. MIT (c) 2026 Vikash Chand._

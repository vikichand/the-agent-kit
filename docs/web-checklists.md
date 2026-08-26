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

**These moved.** They now live in `claude/rules/web-security.md` as a **path-scoped rule**, installed
into your project as `.claude/rules/web-security.md`. That means they arrive automatically the moment
the agent opens anything under `auth/`, `api/`, `routes/`, `middleware/`, `**/webhook*` or
`**/payment*`, or an edge config file (`nginx.conf`, `nginx/`, `Caddyfile`, `vercel.json`,
`wrangler.toml`, `fly.toml`, `.htaccess`) - rather than waiting for someone to remember to open this
file, which is what used to happen and why they were being missed.

Keeping a second copy here would guarantee the two drift apart, so this is a pointer, not a summary.
Read the rule file if you want the list.

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
- [ ] **Something in front of the origin**: a CDN or WAF carrying IP reputation, bot scoring, and
      geo/IP blocking. This is the only layer that can absorb volumetric abuse - application code
      cannot refuse a request it has already paid to receive, so per-route limits in the app
      (`.claude/rules/web-security.md`) sit *behind* this, they do not replace it.
- [ ] **The origin is not reachable around it**: whatever you put in front is decorative if the
      origin IP still answers on :443. Lock it to the edge provider's ranges, or use their tunnel.
      This is the step people skip, and skipping it undoes the previous one entirely.

## Operations: what you need the first time something goes wrong

Launch day is not when you discover you cannot see errors, cannot stop the bleeding, and cannot get
the data back. Each of these is cheap before launch and impossible during an incident.

- [ ] **Crash and error reporting wired up**, with someone actually receiving the alert. Nobody
      reports the bug that made them close the tab.
- [ ] **Hard spend caps on every paid API**, plus a balance alert on any LLM credit. An
      uncapped key and a retry loop is a five-figure night.
- [ ] **Backups exist and a restore has been rehearsed.** An unrehearsed backup is a belief, not a
      backup - the first restore always surfaces a missing role, an unset extension, or a broken
      credential, and you want that on a Tuesday.
- [ ] **A kill switch**: one flag that disables the risky feature without a deploy. Pair it with a
      path to ship a fix fast, so "roll back" is not your only move.
- [ ] **Timeouts on every outbound call.** No timeout means one slow dependency takes the app down
      with it, holding every worker while it waits.
- [ ] **Production keys swapped in and verified** - payment, email, storage. Test keys that reach
      production accept money that never arrives.
- [ ] **A real signup, end to end, with an address you have never used.** Deliverability
      (SPF/DKIM/DMARC on your sending domain) is the step that silently sends every confirmation
      email to spam, and it only shows up on a fresh mailbox.
- [ ] **Support reachable at your own domain**, not a personal inbox, and not a home address on
      anything public.

## Before it is public: the promises you are making

Not legal advice, and no substitute for someone qualified - these are the questions worth answering
before launch rather than after a complaint, because most of them are also just honesty.

- [ ] **A privacy policy exists and is reachable**, and it actually describes what you do: that you
      collect user data, **that AI is involved**, and which third parties data is sent to. A policy
      that omits your model provider describes a different product.
- [ ] **Deletion deletes.** If the product promises uploads are removed, verify they leave object
      storage and backups too, and that "delete account" is a button a user can find - not a support
      request.
- [ ] **Storage buckets confirmed private** by actually fetching an object's URL while signed out.
- [ ] **Cancelling is no harder than subscribing.** If signup is two clicks and cancellation is an
      email to support, that asymmetry is the thing regulators name.
- [ ] **A free trial that auto-charges warns before it charges.** Silence and a card on file is the
      complaint pattern.
- [ ] **Testimonials and metrics on the marketing site are real.** Placeholder praise left in from
      the template is a misrepresentation once money changes hands.
- [ ] **If there is a chat interface, it has a safe response to someone in crisis.** A general
      assistant will eventually be asked, and "it wasn't designed for that" is not an answer.

---

_Per-platform siblings (mobile, desktop, TV) get written when a real project needs one - no
speculative docs. MIT (c) 2026 Vikash Chand._

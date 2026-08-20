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
`**/payment*` - rather than waiting for someone to remember to open this file, which is what used to
happen and why they were being missed.

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

---

_Per-platform siblings (mobile, desktop, TV) get written when a real project needs one - no
speculative docs. MIT (c) 2026 Vikash Chand._

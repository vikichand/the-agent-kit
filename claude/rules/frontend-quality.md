---
paths:
  - "**/components/**"
  - "**/pages/**"
  - "**/app/**"
  - "**/views/**"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.vue"
  - "**/*.svelte"
  - "**/*.css"
  - "**/*.scss"
---
# You are touching user-facing UI

A feature that fails these is unfinished, not "done minus extras". Scale to the project's declared
intent: in a production app these are part of done; in a prototype, note the debt aloud and keep
moving rather than blocking.

## Accessibility

Not optional, and not only a quality question - inaccessible public apps draw real complaints and
litigation (ADA, EAA).

- Semantic elements over div-soup. A `button` is a `button`, not a clickable `div`.
- Every input has a label. Every image has meaningful alt text (empty alt if decorative).
- Keyboard operability throughout; visible focus; focus managed on dialogs and route changes.
- Never colour as the only signal - pair it with text or an icon.
- The project's a11y lint passes. Absent one, WCAG AA is the floor.

## Internationalisation

- No user-facing string hardcoded in markup or logic. It goes through the project's i18n layer from
  the first day, because retrofitting costs an order of magnitude more.
- Defaulting to English is fine. The rule is about **where strings live**, not how many languages
  ship.
- Never build a sentence by concatenation - word order differs across languages.
- Dates, numbers and currency go through locale APIs (`Intl`, ICU), never hand-formatting.
- Do not assume left-to-right, and do not assume translated text is the same length.

## Perceived performance

Skeleton loaders that mirror the final layout, so the page feels fast and does not jump when data
arrives. Agents never add this unasked; it is a product feature, not a flourish.

**Match the indicator to the wait, because the wrong one reads as broken.** A spinner that flashes
for 300ms looks like a glitch; a blank screen for three seconds looks like a dead app and people
leave. Roughly:

| Wait | Show |
|---|---|
| Under ~1s | Nothing. Just render the result. |
| ~1-3s | A plain spinner. No text needed. |
| ~3-10s | Say what is happening - "finding the best match" beats a bare spinner, because a wait you understand is shorter than one you don't. |
| Over ~10s | A progress bar. People stay patient when they can see movement toward an end. |

Never leave a blank region with no indicator at all - that is the one that loses the user.

## Restraint

Cut the clutter agents reliably generate - most often the redundant explainer sentence under every
heading. A page titled "My Day" does not need two lines explaining what "My Day" means. The test is
tangible usefulness: if removing it loses nothing, remove it.

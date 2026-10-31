---
paths:
  - "**/components/**"
  - "**/pages/**"
  - "**/app/**/page.*"
  - "**/app/**/layout.*"
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

Apply these requirements to the behaviour within the requested change; loading this rule does not
authorize unrelated product-wide work. A pre-existing gap that makes the requested change unsafe is
escalated, not silently built.

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
  the first day, because retrofitting costs an order of magnitude more. A project with no i18n layer
  yet: keep the new strings in one place and flag the gap; building the layer is the user's decision.
- Defaulting to English is fine. The rule is about **where strings live**, not how many languages
  ship.
- Never build a sentence by concatenation - word order differs across languages.
- Dates, numbers and currency go through locale APIs (`Intl`, ICU), never hand-formatting.
- Do not assume left-to-right, and do not assume translated text is the same length.

## Perceived performance

Data views you build or change get skeleton loaders that mirror the final layout, so the page feels
fast and does not jump when data arrives. Add them without being asked: they are part of the feature,
not a flourish.

**Match the indicator to the wait, because the wrong one reads as broken.** A spinner that flashes
for 300ms looks like a glitch; a blank screen for three seconds looks like a dead app and people
leave. Roughly:

| Wait | Show |
|---|---|
| Under ~1s | Nothing. Just render the result. |
| ~1-3s | A skeleton for a data view (above); a plain spinner for an action. No text needed. |
| ~3-10s | Say what is happening - "finding the best match" beats a bare spinner, because a wait you understand is shorter than one you don't. |
| Over ~10s | A progress bar. People stay patient when they can see movement toward an end. |

Never leave a blank region with no indicator at all - that is the one that loses the user.

## Restraint

Leave out clutter, most often a redundant explainer sentence under a heading. A page titled "My Day"
does not need two lines explaining what "My Day" means. The test is
tangible usefulness: if removing it loses nothing, remove it.

Follow the project's design system. Where it leaves a choice open (type, colour, radius, shadow,
layout), choose for this product and check the choice against the looks that read as generated: an
indigo-to-violet gradient, gradient headline text, Inter or Space Grotesk by habit, emoji as icons,
glass panels and pills, a kicker label over every heading, a "New" pill over the hero, cards inside
cards, a coloured stripe down one edge of a card, one radius and one grey shadow on everything, pure
`#000` or `#fff` surfaces, `hover:scale` on every element, a fake browser bar around a screenshot, an
invented stat row ("10k+ users"). Removing a default is half the job; put a decision in its place.

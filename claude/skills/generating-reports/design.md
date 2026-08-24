# design.md - the report page look: neobrutalism, pixel-display variant

The style is **neobrutalism** (the neobrutalism.dev / RetroUI component lineage) with a
pixel/terminal display face for headings - the merged aesthetic the 8bitcn library codified. Token
values below are taken from the neobrutalism-components registry, not invented. Every page is ONE
self-contained .html: inline CSS, no CDN, no external fonts or images. System-font fallbacks only -
do not fetch Departure Mono or Silkscreen from the network; if a licensed .woff2 is present in the
project it may be embedded as a base64 data: URI, otherwise the fallback stacks below carry the look.

## Tokens - paste as-is

```css
:root {
  /* light (default) */
  --bg: #FEF2E8;            /* cream page ground - never pure white */
  --surface: #FFFFFF;       /* cards, tables */
  --text: #000000;
  --muted-text: #4A4A4A;
  --border: #000000;        /* ALL borders are black, always */
  --main: #FFDC58;          /* primary accent (yellow); alt sets at the bottom */
  --main-fg: #000000;       /* text on an accent fill is always black */
  --accent-blue: #88AAEE;  --accent-green: #A3E636;
  --accent-red:  #FF6B6B;  --accent-purple: #A388EE;  --accent-orange: #FD9745;
  --shadow: 4px 4px 0px 0px var(--border);   /* hard offset, NO blur, NO alpha */
  --shadow-sm: 2px 2px 0px 0px var(--border);
  --radius: 5px;            /* small; 0 is allowed for a harder look; never more than 8px */
  --bw: 2px;                /* border width for every component */
  --w-base: 500;  --w-heading: 800;
  --font-display: "Departure Mono", "Silkscreen", "Cascadia Mono", Consolas, monospace;
  --font-body: system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Code", Consolas, Menlo, monospace;
}
/* dark - borders stay black, accents unchanged */
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #272933; --surface: #212121;
  --text: #E6E6E6; --muted-text: #A0A0A0;
  --shadow: 4px 4px 0px 0px #000; --shadow-sm: 2px 2px 0px 0px #000;
} }
:root[data-theme="dark"] {
  --bg: #272933; --surface: #212121;
  --text: #E6E6E6; --muted-text: #A0A0A0;
  --shadow: 4px 4px 0px 0px #000; --shadow-sm: 2px 2px 0px 0px #000;
}
body { background: var(--bg); color: var(--text); font-family: var(--font-body);
       font-weight: var(--w-base); font-size: 16px; line-height: 1.6;
       max-width: 880px; margin: 0 auto; padding: 32px 24px; }
```

## What makes it read as "the style" - all four are required

1. **Hard offset shadows**: `box-shadow: var(--shadow)` on every card, badge, and button - solid
   black, zero blur. One blurred or grey shadow breaks the whole aesthetic.
2. **Uniform 2px black borders** on every component, in light AND dark mode.
3. **Flat saturated fills**: accents as full block fills with black text. No gradients, no
   transparency, no glassmorphism.
4. **Chunky display type**: headings in `--font-display`, UPPERCASE.

## Type rules (accessibility)

- The pixel/display font is HEADLINE-ONLY: h1-h3, badges, kbd chips, big stat numbers, minimum
  18px. Never body paragraphs - pair it with the plain readable body stack, which is standard
  practice for this aesthetic.
- h1: display font, 28-36px, uppercase, sitting on a `--main` block or over a 4-6px black underline
  bar. h2: display, 20-24px. Body: 16px `--font-body`.
- Contrast: black-on-accent passes AA for every accent above. In dark mode, accent fills KEEP black
  text (`--main-fg`) - never white on yellow or green.

## Components (the report vocabulary)

- **Card**: `--surface` bg, 2px border, `--shadow`, `--radius`, 24px padding, 32px gaps between cards.
- **Verdict banner** (top of every report): full-width card, accent fill by outcome
  (green = pass, red = fail, yellow = warn), display font, large - the first thing the eye hits.
- **Badge** (severity/status): inline-block, accent fill, black text, 2px border, `--shadow-sm`,
  radius 0-3px, display font 11-12px uppercase, padding 2px 10px.
  Map: red = BLOCKER/FAIL · orange = MAJOR · yellow = MINOR/WARN · green = PASS · blue = INFO.
- **Table**: 2px black outer border + `--shadow` on a wrapper with `overflow-x: auto`; header row
  `--main` fill, black text, display font; 2px black row separators; no zebra striping.
- **Checklist**: square 18px custom boxes (2px border, `--shadow-sm`); checked = accent fill with a
  black check mark. Never native rounded checkboxes.
- **Code block**: `#1B1B1B` bg in both modes, `#E6E6E6` text, `--font-mono` 13-14px, 2px border +
  `--shadow`, 16px padding. Inline code: `--main`-tinted bg with a 1px border.
- **Links**: text-colored with a 2px underline; hover flips to a `--main` background.
- **Hover on interactive elements**: `translate(4px, 4px)` with `box-shadow: none` - the element
  presses into its own shadow. Transitions 100ms or less; no fades.

## Hard prohibitions

No gradients. No blur or soft shadows. No border-radius above 8px. No grey hairline borders. No
opacity on text. No pastel accents. No external requests of any kind.

## Alt accent sets (swap `--main` and the light `--bg` together; dark mode stays unchanged)

- blue: main `#88AAEE`, bg `#DFE5F2`
- green: main `#A3E636`, bg `#E9F5D8`
- purple: main `#A388EE`, bg `#E3DFF2`

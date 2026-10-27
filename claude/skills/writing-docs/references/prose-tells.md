# Prose tells: the full list

`SKILL.md` keeps the short version. Read this before you hand over a README, a report, release notes or
any prose longer than a few paragraphs, and check the draft against it. Every item is a pattern people
have learned to read as machine-written. The fix is almost always the plainer sentence: say the fact.

## Words

- **Puffery.** "a pivotal moment", "plays a vital role", "stands as a testament", "a rich tapestry".
  State the fact and let the reader judge whether it matters.
- **Fake-strong verbs.** "serves as", "stands as", "boasts", "features" where "is" or "has" is meant.
- **Stock vocabulary.** *underscore, showcase, foster, navigate, pivotal, testament, tapestry, deep dive,
  game-changer, crucial, enhance, highlighting, align with, intricate, meticulous*; and the newer set,
  *matters, quietly, practical, dependable, steady, multifaceted, prioritize, universally*; "when it comes to", "at the end of the day", "the reality is"; *Moreover, Furthermore,
  Additionally* opening a sentence.
- **Empty adverbs and intensifiers.** *just, simply, truly, fundamentally, crucially*; "a real
  improvement", "genuinely useful". Keep one only when it carries contrast or doubt.
- **Synonym cycling.** If "the agent" is the right word, repeat it. Rotating to "the assistant" and "the
  tool" makes the reader wonder whether these are three things.
- **Promotional tone.** *vibrant, groundbreaking, nestled, cutting-edge*. Docs are not an advert.
- **Chat residue.** "I hope this helps", "Great question", "Certainly!", "Here is...", "As of my last
  update". None of these belong in a file.

## Sentences

- **Trailing "-ing" analysis.** "adds file search, highlighting the team's commitment to..." Cut the
  clause, or replace it with the actual consequence ("so users find old drafts without leaving the
  editor").
- **Portable filler.** If a sentence could move unchanged into another project's README, it says nothing
  about this one. Replace it with a fact, a number, an example or a consequence.
- **Telling the reader what to think.** "This is the key point", "That part matters more than it
  sounds", "Interestingly". Show why, or delete the aside.
- **Weasel attribution.** "Experts agree", "studies show", "widely regarded". Name the source or cut it.
- **Kicker contrasts.** "X, not Y" and "this is not X, it is Y" closing a line for effect: "the stop
  is a change of approach, not a stopping point". Say what it is and stop.
- **Staged reveals.** A colon before a dramatic payoff ("The best part: it learns"), "Not X. Not Y. Just
  Z.", a rhetorical question answered in the next sentence. Make the point directly.
- **Forced triads.** Three adjectives or three parallel clauses because three sounds finished. Use the
  number of items there actually are.
- **Things doing people's verbs.** "The data tells us", "the decision emerges". Name who did it.
- **Kickers.** A last line built to be quoted, an aphorism or a metaphor. End on the last concrete point.
- **Arguing with no one.** "To be clear, this is not about...", "A tempting approach would be..." when
  nobody raised it. State the claim; drop the defence.
- **Vague links.** "associated with", "connected to", "tied to". Say how the two things relate.
- **False ranges.** "From onboarding to scale to culture": no scale runs through those. List what is
  actually covered.
- **Invented labels.** "the supervision paradox", "scope creep trap" used as if established. Describe the
  problem instead of naming it.

## Structure

- **Default scaffolding.** "Overview", "Key Points", "Summary", "Conclusion" headings, and a heading over
  every two-sentence section. Headings name this document's own subjects.
- **The recap ending.** "In conclusion", "Overall", a final paragraph that repeats the piece.
- **Diff-anchored docs.** "This function was added to replace the previous approach of..." Describe the
  thing as it is; the history goes in the commit message.
- **The challenges-and-outlook section.** "Despite these challenges...", "The future looks bright".
- **The heading said again.** `## Performance` followed by "Performance matters." Start with the fact.
- **One metaphor everywhere.** Introduced once, it is a tool; carried through every paragraph, it is a
  tic.

## Formatting

- **Bullets where prose fits.** Reports and explanations read best as paragraphs; a list is for truly
  separate items. Never a run of three-word bullets.
- **Bold labels that repeat the line.** "**Performance:** Performance improved by 20%."
- **Title Case Headings.** Use sentence case unless the project's style says otherwise.
- **Bold scattered mid-sentence**, emoji in headings, a horizontal rule between every section.
- **Dashes and their stand-ins.** The em dash, the en dash, and a spaced hyphen or double hyphen used as
  one. A comma, a colon, parentheses or a full stop says the same thing without the tell.
- **Decorative arrows.** `->` or the arrow glyph in a heading, a list item or a sentence ("Plan -> build
  -> ship"). Write the words: "plan, then build, then ship".

## Checking a draft

1. Search the draft for the stock words above, for dashes and their stand-ins (U+2014, U+2013, ` - `,
   ` -- `) and for arrows; each hit is rewritten or justified.
2. Read the first and last sentence of every section: the opener is not a preamble and the closer is
   not a recap or a kicker.
3. For each paragraph, ask what fact it adds. A paragraph with none is cut.

Not every hit is wrong: a word on this list is fine when it is the precise word. The test is whether a
plainer sentence would say the same thing.

## Sources

Distilled, not copied. Anthropic, "Prompting best practices" (platform.claude.com, the
`avoid_excessive_markdown_and_bullet_points` guidance); Wikipedia, "Signs of AI writing" (WP:AISIGNS,
CC BY-SA 4.0); stop-slop by Hardik Pandya (MIT); no-ai-slop by Peter Yang (MIT); avoid-ai-writing by
Conor Bronsdon (MIT); humanizer by Siqi Chen (MIT); skill-deslop by Stephen D. Turner (MIT).

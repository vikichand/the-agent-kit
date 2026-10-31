#!/bin/sh
# Counts AI prose tells in README.md: the list in writing-docs/references/prose-tells.md, reduced to what a
# pattern can find. Code blocks and inline code are skipped, so a command never counts. Every occurrence
# counts once. "old" = what the 0.4.0 rule already named (em dashes, its five words, emoji headings, two
# filler openers); "new" = only the 0.5.0 list; "dash" = the stand-ins for an em dash, added 2026-10-28:
# an en dash, a spaced hyphen or double hyphen after a word, ` -> ` and the arrow glyph. A list bullet, a
# table's empty cell and a hyphenated word are not dashes. Prints PASS or FAIL and the counts, then each hit.
f=README.md
[ -f "$f" ] && [ ! -L "$f" ] || { echo "FAIL $f is missing or a symlink"; exit 0; }   # never read outside the sandbox
prose=$(head -c 1000000 "$f" | awk '/^[[:space:]]*(```|~~~)/{c=!c; next} !c' | sed 's/`[^`]*`//g')
emdash=$(printf '\342\200\224'); emoji=$(printf '\360\237'); endash=$(printf '\342\200\223'); arrow=$(printf '\342\206\222')
# `.{1,3}` for the apostrophe: under LC_ALL=C a curly one is three bytes. `navigat` stops before "ion":
# "navigation" is an ordinary noun, "navigate the landscape" is the tell.
OLD="$emdash|delve|leverag|seamless|robust|comprehensive|it.{1,3}s worth noting|in today.{1,3}s"
NEW="pivotal|testament|tapestry|underscor|showcas|foster|navigat(e|es|ed|ing)|deep dive|game.chang|serves as|stands as"
NEW="$NEW|at the end of the day|when it comes to|the reality is|(^|[.] )(moreover|furthermore|additionally),"
NEW="$NEW|experts agree|studies show|I hope this helps|in conclusion|cutting.edge|groundbreaking|vibrant"
hits_old=$(printf '%s\n' "$prose" | LC_ALL=C grep -a -o -i -E "$OLD"; printf '%s\n' "$prose" | LC_ALL=C grep -a -E "^#+ .*$emoji")
hits_new=$(printf '%s\n' "$prose" | LC_ALL=C grep -a -o -i -E "$NEW"; \
  printf '%s\n' "$prose" | grep -a -i -E '^#+[[:space:]]+(overview|key points|summary|conclusion|introduction)[[:space:]]*$')
hits_dash=$(printf '%s\n' "$prose" | sed 's/^[[:space:]]*[-*+] //' | LC_ALL=C grep -a -o -E "[^|[:space:]] --? |$endash| -> |$arrow")
o=$(printf '%s' "$hits_old" | grep -c .); n=$(printf '%s' "$hits_new" | grep -c .); d=$(printf '%s' "$hits_dash" | grep -c .)
t=$((o + n + d))
[ "$t" -le 2 ] && v=PASS || v=FAIL
echo "$v $t prose tells (old $o, new $n, dash $d)"
printf '%s\n%s\n%s\n' "$hits_old" "$hits_new" "$hits_dash" | grep . | head -50
exit 0

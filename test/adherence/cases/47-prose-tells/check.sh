#!/bin/sh
# Counts AI prose tells in README.md: the list in writing-docs/references/prose-tells.md, reduced to what a
# pattern can find. Code blocks and inline code are skipped, so a command never counts. Every occurrence
# counts once. "old" = what the 0.4.0 rule already named (em dashes, its five words, emoji headings, two
# filler openers); "new" = only the 0.5.0 list. Prints PASS or FAIL and the counts, then each hit.
f=README.md
[ -f "$f" ] && [ ! -L "$f" ] || { echo "FAIL $f is missing or a symlink"; exit 0; }   # never read outside the sandbox
prose=$(head -c 1000000 "$f" | awk '/^[[:space:]]*(```|~~~)/{c=!c; next} !c' | sed 's/`[^`]*`//g')
emdash=$(printf '\342\200\224'); emoji=$(printf '\360\237')
OLD="$emdash|delve|leverag|seamless|robust|comprehensive|it.s worth noting|in today.s"
NEW="pivotal|testament|tapestry|underscor|showcas|foster|navigat|deep dive|game.chang|serves as|stands as"
NEW="$NEW|at the end of the day|when it comes to|the reality is|(^|[.] )(moreover|furthermore|additionally),"
NEW="$NEW|experts agree|studies show|I hope this helps|in conclusion|cutting.edge|groundbreaking|vibrant"
hits_old=$(printf '%s\n' "$prose" | LC_ALL=C grep -a -o -i -E "$OLD"; printf '%s\n' "$prose" | LC_ALL=C grep -a -E "^#+ .*$emoji")
hits_new=$(printf '%s\n' "$prose" | LC_ALL=C grep -a -o -i -E "$NEW"; \
  printf '%s\n' "$prose" | grep -a -i -E '^#+[[:space:]]+(overview|key points|summary|conclusion|introduction)[[:space:]]*$')
o=$(printf '%s' "$hits_old" | grep -c .); n=$(printf '%s' "$hits_new" | grep -c .); t=$((o + n))
[ "$t" -le 2 ] && v=PASS || v=FAIL
echo "$v $t prose tells (old $o, new $n)"
printf '%s\n%s\n' "$hits_old" "$hits_new" | grep . | head -50
exit 0

#!/bin/sh
# Counts generated-code comment tells in services/refunds.js, the list in code-correctness.md ("Out, as
# generated-code tells"), from antislop-code (MIT, Miqdad Badjuber). Comment lines only: a `//` line,
# or a `/*` or ` *` block line. Prints PASS or FAIL and the count on its first line, then the lines.
f=services/refunds.js
[ -f "$f" ] && [ ! -L "$f" ] && [ ! -L services ] || { echo "FAIL $f is missing or a symlink"; exit 0; }   # never read outside the sandbox
e=$(printf '\360\237|\342\234\205|\342\234\224|\342\235\214|\342\232\240')   # emoji: U+1Fxxx, check marks, cross, warning
hits=$(head -c 1000000 "$f" | LC_ALL=C grep -a -E '//|^[[:space:]]*(/\*|\*)' | LC_ALL=C grep -a -E \
  -e '[=*#~-]{4,}' \
  -e '[Ss]tep [0-9]' \
  -e '//[[:space:]]*(First|Next|Then|Finally)[,: ]' \
  -e '(Main|Core|Business) logic|Helper function|Entry point|(Note|Important):[[:space:]]*(This is important|Please read)' \
  -e '(TODO|FIXME)[: ]*(Improve|Optimi[sz]e|Refactor|Add more|Clean ?up|Future)' \
  -e '//[[:space:]]*[Ee]nd( of)? ' \
  -e "$e")
n=$(printf '%s' "$hits" | grep -c .)
[ "$n" -le 1 ] && echo "PASS $n comment tell(s)" || echo "FAIL $n comment tells"
[ -n "$hits" ] && printf '%s\n' "$hits" | head -50
exit 0

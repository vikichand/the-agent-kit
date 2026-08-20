#!/bin/sh
# the-agent-kit test suite - exercises all four hooks in throwaway repos, the command-guard corpus,
# and the installer's doctor (--check).
# set -u plus explicit setup guards: a failed mktemp / git init aborts (exit 2) rather than printing
# misleading PASS lines on empty output. Exits non-zero if any assertion fails.
set -u
KIT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fail=0
pass() { printf 'PASS: %s\n' "$1"; }
bad()  { printf 'FAIL: %s\n' "$1"; fail=1; }
has()  { printf '%s\n' "$2" | grep -qi -- "$1"; }

# ---------- command-guard (tool layer) ----------
echo "== command-guard (tool layer) =="
PY=""; for p in python3 python "py -3"; do [ "$(printf 'print(1)' | $p - 2>/dev/null)" = "1" ] && { PY="$p"; break; }; done
if [ -n "$PY" ]; then
  $PY "$KIT/test/command_guard_cases.py" "$KIT/hooks/command-guard.py" || bad "command-guard corpus"
else
  bad "no working python found - command-guard NOT tested (install Python 3)"
fi

# ---------- commit-msg (attribution) ----------
echo "== commit-msg (attribution) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2; git config user.email t@e.com; git config user.name T
cp "$KIT/hooks/commit-msg" .git/hooks/commit-msg; chmod +x .git/hooks/commit-msg
cat > m1 <<'EOF'
feat: add widget

Implements the widget per the plan.

Claude-Session: https://claude.ai/code/session_ABC123
Co-authored-by: Jane Dev <jane@example.com>
🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
git commit -q --allow-empty -F m1 || bad "C1 setup commit failed"
b=$(git log -1 --format=%B)
has 'Co-Authored-By: Claude' "$b" && bad "C1 Claude co-author NOT stripped" || pass "C1 Claude co-author stripped"
has 'Generated with'        "$b" && bad "C1 Generated-with NOT stripped"    || pass "C1 Generated-with stripped"
has 'session_ABC123'        "$b" && pass "C1 Claude-Session preserved"      || bad  "C1 Claude-Session LOST"
has 'Jane Dev'              "$b" && pass "C1 human co-author preserved"     || bad  "C1 human co-author LOST"
has 'Implements the widget' "$b" && pass "C1 body preserved"               || bad  "C1 body LOST"
printf 'test: fixture\n\nThis fixture was generated with Claude for testing and must stay.\n' > m2
git commit -q --allow-empty -F m2 || bad "C2 setup"; b=$(git log -1 --format=%B)
has 'generated with Claude for testing' "$b" && pass "C2 prose preserved" || bad "C2 prose WRONGLY stripped"
printf 'fix: patch\n\nCo-authored-by: Codex <noreply@openai.com>\n' > m3
git commit -q --allow-empty -F m3 || bad "C3 setup"; b=$(git log -1 --format=%B)
has 'codex' "$b" && bad "C3 Codex co-author NOT stripped" || pass "C3 Codex co-author stripped"
printf 'chore: clean message\n' > m4
git commit -q --allow-empty -F m4 || bad "C4 setup"; b=$(git log -1 --format=%B)
has 'chore: clean message' "$b" && pass "C4 clean message kept" || bad "C4 clean message altered -> [$b]"
printf 'feat: x\n\nCo-authored-by: Claude Martinez <claude.martinez@realco.com>\nCo-authored-by: Devin Smith <devin@realco.com>\n' > m5
git commit -q --allow-empty -F m5 || bad "C5 setup"; b=$(git log -1 --format=%B)
has 'Claude Martinez' "$b" && pass "C5 human 'Claude' preserved" || bad "C5 human 'Claude' STRIPPED"
has 'Devin Smith'     "$b" && pass "C5 human 'Devin' preserved"  || bad "C5 human 'Devin' STRIPPED"
# C6 (reversed): an all-attribution message must be BLOCKED (fail-closed)
printf '\xf0\x9f\xa4\x96 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n' > m6
if git commit -q --allow-empty -F m6 2>/dev/null; then bad "C6 all-attribution commit was ALLOWED"; else pass "C6 all-attribution commit BLOCKED (fail-closed)"; fi
cd "$KIT"; rm -rf "$w"

# ---------- pre-commit (secret scan) ----------
echo "== pre-commit (secret scan) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2; git config user.email t@e.com; git config user.name T
cp "$KIT/hooks/pre-commit" .git/hooks/pre-commit; chmod +x .git/hooks/pre-commit
printf 'ok\n' > clean.txt; git add clean.txt
if git commit -q -m clean 2>/dev/null; then pass "PC clean commit passes"; else bad "PC clean blocked"; fi
sec() { printf '%s\n' "$2" > "$1"; git add "$1"
  if git commit -q -m x 2>/dev/null; then bad "PC $3 committed"; else pass "PC $3 blocked"; fi
  git reset -q >/dev/null 2>&1; rm -f "$1"; }
# These fixtures are SPLIT deliberately. pre-commit scans every staged line, so a literal fake key
# here would make the kit's own repo un-committable by its own hook - with `--no-verify`, which the
# kit denies, as the only way out. Adjacent quoted strings concatenate in sh, so `sec` still receives
# the intact secret and writes it to disk for the scanner to catch. Keep them split.
sec s1 "AKIA""IOSFODNN7EXAMPLE"             'AWS key'
sec s2 "sk-""abcdefghijklmnopqrstuvwx12345" 'sk- key'
sec s3 "-----BEGIN RSA PRIVATE"" KEY-----"  'private key'
cd "$KIT"; rm -rf "$w"

# ---------- pre-push (force / delete / non-ff to a protected branch) ----------
echo "== pre-push (force / delete / non-ff) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2; git config user.email t@e.com; git config user.name T
printf '1\n' > f; git add f; git commit -q -m c1; s1=$(git rev-parse HEAD)
printf '2\n' >> f; git add f; git commit -q -m c2; s2=$(git rev-parse HEAD)
z=0000000000000000000000000000000000000000
pp() { printf '%s\n' "$1" | sh "$KIT/hooks/pre-push" 2>/dev/null; }
pp "refs/heads/main $s2 refs/heads/main $s1" && pass "PP fast-forward allowed"   || bad "PP ff blocked"
pp "refs/heads/main $s1 refs/heads/main $s2" && bad "PP force/non-ff allowed"    || pass "PP force/non-ff blocked"
pp "x $z refs/heads/main $s2"                && bad "PP delete allowed"          || pass "PP delete blocked"
pp "refs/heads/feat $s1 refs/heads/feat $s2" && pass "PP feature-branch allowed" || bad "PP feature blocked"
cd "$KIT"; rm -rf "$w"

# ---------- install.sh --check (doctor) ----------
# The doctor must report what is ACTUALLY live. Existence of a file in the hook slot is not enough:
# another tool's hook there (Husky, lefthook, pre-commit) means OUR guard is not running.
echo "== install.sh --check (doctor) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2

d=$(sh "$KIT/install.sh" --check 2>&1)
has 'pre-commit not installed' "$d" && pass "D1 missing hook reported" || bad "D1 missing hook NOT reported"

for h in commit-msg pre-commit pre-push; do cp "$KIT/hooks/$h" ".git/hooks/$h"; chmod +x ".git/hooks/$h"; done
d=$(sh "$KIT/install.sh" --check 2>&1)
n=$(printf '%s\n' "$d" | grep -c 'live in')
[ "$n" -eq 3 ] && pass "D2 all three kit hooks reported live" || bad "D2 expected 3 live hooks, got $n"

printf '#!/bin/sh\necho some other tool\n' > .git/hooks/pre-commit; chmod +x .git/hooks/pre-commit
d=$(sh "$KIT/install.sh" --check 2>&1)
has "is NOT the kit" "$d" && pass "D3 foreign hook flagged INACTIVE" || bad "D3 foreign hook passed as OK (false green)"

mkdir -p .other-hooks; git config core.hooksPath .other-hooks
cp "$KIT/hooks/pre-commit" .other-hooks/pre-commit; chmod +x .other-hooks/pre-commit
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'core.hooksPath=' "$d" && pass "D4 hooksPath redirect reported" || bad "D4 hooksPath redirect NOT reported"
# Reporting the redirect is not enough: the doctor must actually LOOK there. The kit hook planted in
# .other-hooks is the one it should find, and .git/hooks must no longer be what it reads.
printf '%s\n' "$d" | grep -q 'live in.*\.other-hooks' \
  && pass "D4b doctor follows the redirect into .other-hooks" \
  || bad  "D4b doctor did NOT follow the redirect - it is checking the wrong directory"

# A Husky/lefthook shim that CALLS the kit's hook is a working setup, not a failure. The kit's own
# README recommends exactly this, so flagging it FAIL would make --check lie about a documented recipe.
printf '#!/bin/sh\nsh "$HOME/.the-agent-kit/git-hooks/pre-push" "$@" || exit 1\n' > .other-hooks/pre-push
chmod +x .other-hooks/pre-push
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'calls the kit' "$d" && pass "D8 delegating shim recognised, not flagged" || bad "D8 documented Husky shim wrongly flagged INACTIVE"

# Rules-file wiring: a CLAUDE.md that does NOT import AGENTS.md means two copies that drift apart.
printf 'rules\n' > AGENTS.md; printf 'a second copy of the rules\n' > CLAUDE.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'does not import AGENTS.md' "$d" && pass "D5 un-imported CLAUDE.md warned" || bad "D5 drift risk NOT warned"
printf '@AGENTS.md\n' > CLAUDE.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'one source of truth' "$d" && pass "D6 import wiring confirmed" || bad "D6 correct import NOT confirmed"
# Codex silently truncates AGENTS.md past 32 KiB, so oversize must be loud here.
dd if=/dev/zero bs=1024 count=40 2>/dev/null | tr '\0' 'x' > AGENTS.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'SILENTLY truncates' "$d" && pass "D7 oversize AGENTS.md flagged" || bad "D7 Codex truncation NOT flagged"

# The real rules file: an unfilled PROJECT-CONFIG means the agent guesses this project's commands,
# which is the kit's single largest hallucination surface. It must be called out, not left silent.
cp "$KIT/AGENTS.md" AGENTS.md; printf '@AGENTS.md\n' > CLAUDE.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'PROJECT-CONFIG is still the empty placeholder' "$d" \
  && pass "D9 unfilled PROJECT-CONFIG warned" || bad "D9 unfilled PROJECT-CONFIG NOT warned"
has 'effective lines' "$d" && pass "D10 effective line count reported" || bad "D10 effective line count NOT reported"

# False-positive control: once it IS filled, the warning must go silent.
sed 's/Not configured yet\. Run the setup prompt (the-agent-kit docs\/project-setup-prompt.md) to fill this in\./Build: make all  Test: make test  Lint: make lint/' AGENTS.md > A2 && mv A2 AGENTS.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'PROJECT-CONFIG is still the empty placeholder' "$d" \
  && bad "D11 filled PROJECT-CONFIG still warned (false positive)" || pass "D11 filled PROJECT-CONFIG is silent"
cd "$KIT"; rm -rf "$w"

# ---------- install.sh --update-rules ----------
echo "== install.sh --update-rules =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2
# U1: stale rules + a FILLED block -> rules refreshed, the block survives byte-for-byte
sed 's/## 0\. Size the task before doing anything else/## 0. OLD STALE HEADING/' "$KIT/AGENTS.md" > AGENTS.md
sed 's/Not configured yet\. Run the setup prompt (the-agent-kit docs\/project-setup-prompt.md) to fill this in\./Build: make all  Test: make test/' AGENTS.md > A2 && mv A2 AGENTS.md
sh "$KIT/install.sh" --update-rules >/dev/null 2>&1 || bad "U1 --update-rules exited non-zero"
grep -q 'OLD STALE HEADING' AGENTS.md && bad "U1 stale rules NOT replaced" || pass "U1 stale rules replaced with the kit's"
grep -q 'Build: make all' AGENTS.md && pass "U1 filled PROJECT-CONFIG preserved" || bad "U1 filled PROJECT-CONFIG LOST"
# U2: no markers -> refuse and change nothing (fail-closed: can't tell project config from rules)
printf 'my own rules, no markers\n' > AGENTS.md
if sh "$KIT/install.sh" --update-rules >/dev/null 2>&1; then bad "U2 marker-less file was updated"; else pass "U2 marker-less file refused (fail-closed)"; fi
grep -q 'my own rules' AGENTS.md && pass "U2 marker-less file untouched" || bad "U2 file MODIFIED despite refusal"
# U3: an --extension stub holds no universal rules; updating must redirect to the global files, not inject them
rm -f AGENTS.md CLAUDE.md; sh "$KIT/install.sh" --extension >/dev/null 2>&1
d=$(sh "$KIT/install.sh" --update-rules 2>&1)
has 'GLOBAL' "$d" && pass "U3 extension stub redirected to global rules" || bad "U3 extension stub not recognised"
grep -q 'universal rules live in your global' AGENTS.md && pass "U3 stub untouched" || bad "U3 stub was REWRITTEN"
# U4: already-current file -> explicit no-op, no rewrite
rm -f AGENTS.md; cp "$KIT/AGENTS.md" AGENTS.md
d=$(sh "$KIT/install.sh" --update-rules 2>&1)
has 'already carries the current rules' "$d" && pass "U4 current rules detected, no rewrite" || bad "U4 no-op not detected"
cd "$KIT"; rm -rf "$w"

# ---------- path-scoped rules ----------
# The deep tier. These must ship valid frontmatter and must be installed by BOTH per-project modes,
# or the conditional rules silently never load and nobody finds out.
echo "== path-scoped rules =="
n=0
for r in "$KIT"/claude/rules/*.md; do
  [ -e "$r" ] || continue
  n=$((n+1))
  b=$(basename "$r")
  head -2 "$r" | grep -q '^paths:$' && : || bad "R1 $b missing 'paths:' frontmatter on line 2"
  grep -q '^  - "' "$r" || bad "R1 $b declares no glob patterns"
done
[ "$n" -gt 0 ] && pass "R1 $n path-scoped rule files, all with paths: frontmatter" || bad "R1 no rule files found"
w=$(mktemp -d) || exit 2; cd "$w" || exit 2; git init -q
sh "$KIT/install.sh" >/dev/null 2>&1
c=$(ls .claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$c" = "$n" ] && pass "R2 default install deploys all $n rules" || bad "R2 deployed $c of $n rules"
sh "$KIT/install.sh" >/dev/null 2>&1
c2=$(ls .claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$c2" = "$n" ] && pass "R3 re-install does not duplicate rules" || bad "R3 rule count changed to $c2"
cd "$KIT"; rm -rf "$w"
w=$(mktemp -d) || exit 2; cd "$w" || exit 2; git init -q
sh "$KIT/install.sh" --extension >/dev/null 2>&1
c3=$(ls .claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$c3" = "$n" ] && pass "R4 --extension deploys the rules too" || bad "R4 --extension deployed $c3 of $n"
cd "$KIT"; rm -rf "$w"

# ---------- install.sh --update ----------
# Runs against a LOCAL clone source with a fake HOME: no network, and the real ~/.the-agent-kit
# is never touched. AGENT_KIT_REPO is the same override a fork would use.
echo "== install.sh --update =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
# The source repo is built from the WORKING TREE, not from $KIT's HEAD: --update deliberately runs
# the installer it just downloaded, so cloning the last commit would test yesterday's code and go
# green on a change that is still broken here.
mkdir -p "$w/src" || exit 2
(cd "$KIT" && cp -r install.sh AGENTS.md CLAUDE.md hooks docs claude codex "$w/src/") || exit 2
head=$( (cd "$w/src" && git init -q -b main && git add -A \
        && git -c user.email=t@e.com -c user.name=T commit -qm "working tree" \
        && git rev-parse --short HEAD) 2>/dev/null || printf '' )
if [ -z "$head" ]; then
  echo "SKIP: could not build a source repo - --update not exercised"
else
  d=$(HOME="$w" AGENT_KIT_REPO="$w/src" sh "$KIT/install.sh" --update 2>&1) || bad "U5 --update exited non-zero"
  [ -f "$w/.the-agent-kit/AGENTS.md" ] && pass "U5 --update populated a fresh ~/.the-agent-kit" || bad "U5 kit not installed"
  [ "$(cat "$w/.the-agent-kit/.kit-version" 2>/dev/null)" = "$head" ] \
    && pass "U5 version stamped from the source commit" || bad "U5 .kit-version wrong or missing"
  # Second run must detect it is current and do nothing.
  d=$(HOME="$w" AGENT_KIT_REPO="$w/src" sh "$KIT/install.sh" --update 2>&1)
  has 'already at' "$d" && pass "U6 second --update is a no-op" || bad "U6 no-op NOT detected"
  # A repo that is not the kit must be refused BEFORE anything is overwritten.
  mkdir -p "$w/impostor" && (cd "$w/impostor" && git init -q -b main && printf 'hi\n' > README.md \
    && git add README.md && git -c core.autocrlf=false -c user.email=t@e.com -c user.name=T commit -qm x 2>/dev/null) || exit 2
  if d=$(HOME="$w" AGENT_KIT_REPO="$w/impostor" sh "$KIT/install.sh" --update 2>&1); then
    bad "U7 non-kit repo was accepted"
  else
    has 'not the kit' "$d" && pass "U7 non-kit repo refused" || bad "U7 refused for the wrong reason -> [$d]"
  fi
  [ "$(cat "$w/.the-agent-kit/.kit-version" 2>/dev/null)" = "$head" ] \
    && pass "U7 existing install left intact after refusal" || bad "U7 install was CLOBBERED by a bad source"
  # U8 is the real-world path: updating by running the INSTALLED copy, which --global then overwrites.
  # sh reads a script lazily by byte offset, so a shell that keeps going resumes inside the replaced
  # file and executes fragments of it - hit live as "sac: command not found", with the version
  # silently failing to advance. The fix is the exec handoff in update_kit.
  # HONEST LIMIT: this is a smoke test, not a reproduction. Whether the corruption fires depends on
  # how much of the script the shell had already buffered, so it is not deterministic - removing the
  # exec does NOT reliably fail this case. U9 asserts the structural property instead, which is the
  # part that can be checked reliably. Both are here on purpose; neither alone is enough.
  # The new install.sh must differ in LENGTH from the installed one or this proves nothing: an
  # identical overwrite leaves every byte offset where the running shell expects it, and the bug
  # cannot show. Padding the top shifts everything after it, which is the real-world case.
  { head -1 "$w/src/install.sh"
    i=0; while [ $i -lt 60 ]; do echo "# pad line $i - shifts every byte offset below this point"; i=$((i+1)); done
    tail -n +2 "$w/src/install.sh"; } > "$w/src/install.new" && mv "$w/src/install.new" "$w/src/install.sh"
  head2=$( (cd "$w/src" && git -c core.autocrlf=false add -A \
           && git -c core.autocrlf=false -c user.email=t@e.com -c user.name=T \
              commit -qm "second, shifted offsets" 2>/dev/null && git rev-parse --short HEAD) || printf '' )
  d=$(HOME="$w" AGENT_KIT_REPO="$w/src" sh "$w/.the-agent-kit/install.sh" --update 2>&1)
  has 'command not found' "$d" && bad "U8 self-overwrite corrupted the running script -> [$(printf '%s' "$d" | grep -i 'command not found')]" \
    || pass "U8 updating from the installed copy runs clean"
  [ -n "$head2" ] && [ "$(cat "$w/.the-agent-kit/.kit-version" 2>/dev/null)" = "$head2" ] \
    && pass "U8 update landed when run from the installed copy" || bad "U8 version did NOT advance"
  # U9: the structural guard U8 cannot be. update_kit must END by exec-ing the downloaded installer -
  # exec replaces the process, so not one more byte is read from the file --global is overwriting.
  # Any refactor that turns this back into a plain call reintroduces the corruption, silently.
  awk '/^update_kit\(\)/,/^}/' "$KIT/install.sh" | grep -q '^ *exec sh -c' \
    && pass "U9 update_kit hands off with exec (self-overwrite guard)" \
    || bad  "U9 update_kit no longer execs - it will read the file --global just overwrote"
fi
cd "$KIT"; rm -rf "$w"

echo "---"
[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "FAILURES PRESENT"
exit "$fail"

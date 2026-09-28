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
# The kit's AGENTS.md carries the kit REPO's own PROJECT-CONFIG block, so a fixture that needs the
# shipped template (empty block) must be built the way a fresh install builds it, not by copying the
# file. Before 2026-09-26 these fixtures used `cp` plus a sed on the placeholder sentence; once the
# block was filled the sed silently became a no-op and two tests went green without testing anything.
# Built by a REAL fresh install into a throwaway repo, then copied out: that tests the artifact the
# installer actually ships. (Sourcing install.sh as a library does not work inside a subshell - its
# library-mode guard falls through to `exit`, which ends the subshell before anything is written.)
kit_rules() {  # $1 = target path
  t=$(mktemp -d) || return 1
  ( cd "$t" && git init -q && sh "$KIT/install.sh" >/dev/null 2>&1 )
  cp "$t/AGENTS.md" "$1"; rm -rf "$t"
}

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
# Pin the hooks dir: a machine with the kit's own --global install has a GLOBAL core.hooksPath, and
# without this the throwaway repo runs the INSTALLED hook, not the one under test - so a change to
# hooks/ passes or fails on someone's machine state (found 2026-09-21, when a new strip rule "failed").
git config core.hooksPath .git/hooks
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
has 'session_ABC123'        "$b" && bad  "C1 Claude-Session NOT stripped"   || pass "C1 Claude-Session trailer stripped"
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
# C7: a bare agent session URL on its own line goes; prose that merely mentions a session stays
printf 'fix: session timeout\n\nThe session cookie expired early; see Claude-Session handling in auth.\n\nhttps://claude.ai/code/session_XYZ789\n' > m7
git commit -q --allow-empty -F m7 || bad "C7 setup"; b=$(git log -1 --format=%B)
has 'session_XYZ789' "$b" && bad "C7 bare session URL NOT stripped" || pass "C7 bare session URL stripped"
has 'session cookie expired early' "$b" && pass "C7 prose mentioning a session preserved" || bad "C7 prose WRONGLY stripped"
# C6 (reversed): an all-attribution message must be BLOCKED (fail-closed)
printf '\xf0\x9f\xa4\x96 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n' > m6
if git commit -q --allow-empty -F m6 2>/dev/null; then bad "C6 all-attribution commit was ALLOWED"; else pass "C6 all-attribution commit BLOCKED (fail-closed)"; fi
cd "$KIT"; rm -rf "$w"

# ---------- pre-commit (secret scan) ----------
echo "== pre-commit (secret scan) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2; git config user.email t@e.com; git config user.name T
# Pin the hooks dir: a machine with the kit's own --global install has a GLOBAL core.hooksPath, and
# without this the throwaway repo runs the INSTALLED hook, not the one under test - so a change to
# hooks/ passes or fails on someone's machine state (found 2026-09-21, when a new strip rule "failed").
git config core.hooksPath .git/hooks
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
# PC-A: GitHub Actions pinned to a floating ref are blocked; SHA, local, digest and exempt pass; and an
# UNCHANGED floating line never blocks a commit that only touches another line.
mkdir -p .github/workflows
S40=0123456789abcdef0123456789abcdef01234567
D64=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
wfc() { printf 'jobs:\n  x:\n    steps:\n%s\n' "$1" > .github/workflows/ci.yml; git add .github/workflows/ci.yml
  if git commit -q -m wf 2>/dev/null; then r=0; else r=1; git reset -q >/dev/null 2>&1; fi; return $r; }
wfc "      - uses: actions/checkout@v4"                      && bad "PC-A1 floating tag committed"      || pass "PC-A1 floating tag blocked"
wfc "      - uses: github/super-linter@main"                 && bad "PC-A2 floating branch committed"   || pass "PC-A2 floating branch blocked"
wfc "      - uses: actions/checkout@$S40  # v4"              && pass "PC-A3 SHA-pinned action passes"   || bad "PC-A3 SHA-pinned action BLOCKED"
wfc "      - uses: ./.github/actions/build"                   && pass "PC-A4 local action passes"        || bad "PC-A4 local action BLOCKED"
wfc "      - uses: docker://alpine@sha256:$D64"               && pass "PC-A5 digest-pinned image passes" || bad "PC-A5 digest-pinned image BLOCKED"
wfc "      - uses: docker://alpine:3.20"                      && bad "PC-A6 floating image committed"    || pass "PC-A6 floating image blocked"
wfc "      - uses: acme/internal@main  # pin-exempt: our own repo" && pass "PC-A7 pin-exempt line passes" || bad "PC-A7 pin-exempt line BLOCKED"
# PC-A8: an existing floating step is left alone when an unrelated line changes
printf 'jobs:\n  x:\n    steps:\n      - uses: old/thing@v1  # pin-exempt: seeding\n' > .github/workflows/ci.yml
git add .github/workflows/ci.yml; git commit -q -m seed 2>/dev/null
sed 's/  # pin-exempt: seeding//' .github/workflows/ci.yml > c2 && mv c2 .github/workflows/ci.yml
mv .git/hooks/pre-commit .git/hooks/pre-commit.off   # an old repo's state, committed before the kit existed
git commit -qam 'seed an unpinned step, as an old repo would have' >/dev/null 2>&1
mv .git/hooks/pre-commit.off .git/hooks/pre-commit
printf '      - uses: actions/checkout@%s  # v4\n' "$S40" >> .github/workflows/ci.yml; git add .github/workflows/ci.yml
if git commit -q -m touch 2>/dev/null; then pass "PC-A8 an untouched old floating step does not block"; else bad "PC-A8 an untouched old floating step BLOCKED an unrelated commit"; git reset -q; fi
cd "$KIT"; rm -rf "$w"

# ---------- pre-push (force / delete / non-ff to a protected branch) ----------
echo "== pre-push (force / delete / non-ff) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2; git config user.email t@e.com; git config user.name T
# Pin the hooks dir: a machine with the kit's own --global install has a GLOBAL core.hooksPath, and
# without this the throwaway repo runs the INSTALLED hook, not the one under test - so a change to
# hooks/ passes or fails on someone's machine state (found 2026-09-21, when a new strip rule "failed").
git config core.hooksPath .git/hooks
printf '1\n' > f; git add f; git commit -q -m c1; s1=$(git rev-parse HEAD)
printf '2\n' >> f; git add f; git commit -q -m c2; s2=$(git rev-parse HEAD)
z=0000000000000000000000000000000000000000
pp() { printf '%s\n' "$1" | sh "$KIT/hooks/pre-push" 2>/dev/null; }
pp "refs/heads/main $s2 refs/heads/main $s1" && pass "PP fast-forward allowed"   || bad "PP ff blocked"
pp "refs/heads/main $s1 refs/heads/main $s2" && bad "PP force/non-ff allowed"    || pass "PP force/non-ff blocked"
pp "x $z refs/heads/main $s2"                && bad "PP delete allowed"          || pass "PP delete blocked"
pp "refs/heads/feat $s1 refs/heads/feat $s2" && pass "PP feature-branch allowed" || bad "PP feature blocked"
# PP5: CREATING a branch sends an all-zero remote sha. That must be allowed, or the release flow
# (which creates `main` from an orphan commit the first time) cannot push at all. Untested until
# 2026-09-26, when it became load-bearing.
pp "refs/heads/main $s2 refs/heads/main $z"   && pass "PP new-branch push allowed"  || bad "PP new-branch push BLOCKED"
# PP6-PP10: a release-only branch marked in the PUSHED commit's AGENTS.md. Every push to it is refused -
# a plain fast-forward and a creation included - unless AGENT_KIT_RELEASE=1; other branches and tags pass.
printf '# rules
<!-- PROJECT-CONFIG:START -->
<!-- agent-kit: release-branch=main -->
<!-- PROJECT-CONFIG:END -->
' > AGENTS.md
git add AGENTS.md; git commit -q -m c3; s3=$(git rev-parse HEAD)
pp "refs/heads/main $s3 refs/heads/main $s2"     && bad "PP6 plain push to a release-only branch ALLOWED" || pass "PP6 plain push to a release-only branch refused"
pp "refs/heads/main $s3 refs/heads/main $z"      && bad "PP7 creating a release-only branch ALLOWED"      || pass "PP7 creating a release-only branch refused"
( printf '%s
' "refs/heads/main $s3 refs/heads/main $s2" | AGENT_KIT_RELEASE=1 sh "$KIT/hooks/pre-push" 2>/dev/null )                                                  && pass "PP8 release push with AGENT_KIT_RELEASE=1 allowed" || bad "PP8 release push with the flag BLOCKED"
pp "refs/heads/develop $s3 refs/heads/develop $s2" && pass "PP9 the work branch is unaffected"            || bad "PP9 the work branch BLOCKED"
pp "refs/tags/v1.0.0 $s3 refs/tags/v1.0.0 $z"    && pass "PP10 a release tag is never refused"            || bad "PP10 a release tag BLOCKED"
# PP11: a push cannot exempt itself by deleting the marker - the branch's current tip still carries it.
git checkout -q -b nomark; printf '# rules\n' > AGENTS.md; git commit -q -am c4; s4=$(git rev-parse HEAD)
pp "refs/heads/main $s4 refs/heads/main $s3"     && bad "PP11 a push that removes the marker ALLOWED"    || pass "PP11 a push that removes the marker is still refused"
cd "$KIT"; rm -rf "$w"

# ---------- kit-check.py (session-start update check) ----------
# Silent when everything is current; one line per actionable item; never updates anything; exits 0 on
# every path. A local bare repo stands in for GitHub through AGENT_KIT_REPO, so nothing here needs a
# network, and a fake HOME stands in for the machine-wide share.
echo "== kit-check.py (session-start update check) =="
if [ -n "$PY" ]; then
  k=$(mktemp -d) || exit 2
  git init -q -b main "$k/src" && ( cd "$k/src" && git -c user.email=t@e.com -c user.name=T commit -q --allow-empty -m r1 )
  latest=$(git -C "$k/src" rev-parse HEAD)
  mkdir -p "$k/home/.the-agent-kit"
  printf '# rules v2\n<!-- PROJECT-CONFIG:START -->\n<!-- PROJECT-CONFIG:END -->\n' > "$k/home/.the-agent-kit/AGENTS.md"
  git init -q "$k/proj"
  # Python on Windows reads USERPROFILE and native paths, so /tmp-style paths from this shell must be
  # converted, or the check would silently look in the wrong place and every test would pass empty.
  wp() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }
  KH=$(wp "$k/home"); KS=$(wp "$k/src"); KN=$(wp "$k/nowhere")
  kc() {  # $1 = cwd for the session -> stdout of the check
    printf '{"cwd":"%s","source":"startup"}' "$(wp "$1")" | HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KS" $PY "$KIT/hooks/kit-check.py" 2>/dev/null
  }
  printf '%s\n' "$(printf '%s' "$latest" | cut -c1-7)" > "$k/home/.the-agent-kit/.kit-version"
  o=$(kc "$k/proj"); [ -z "$o" ] && pass "K1 current kit, no rules file: silent" || bad "K1 spoke when current: $o"
  rm -f "$k/home/.the-agent-kit/.update-check"; printf 'abc1234\n' > "$k/home/.the-agent-kit/.kit-version"
  o=$(kc "$k/proj"); has 'install.sh --update' "$o" && pass "K2 behind: one line naming --update" || bad "K2 did not report a newer release"
  o=$(HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KN" $PY "$KIT/hooks/kit-check.py" </dev/null 2>/dev/null)
  has 'install.sh --update' "$o" && pass "K3 same-day answer comes from the cache, no network" || bad "K3 cache not used"
  rm -f "$k/home/.the-agent-kit/.update-check"
  o=$(printf '{}' | HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KN" $PY "$KIT/hooks/kit-check.py" 2>/dev/null); rc=$?
  [ -z "$o" ] && [ "$rc" = 0 ] && pass "K4 unreachable repo: silent, exit 0" || bad "K4 unreachable repo not silent (rc=$rc): $o"
  o=$(printf '{}' | AGENT_KIT_NO_UPDATE_CHECK=1 HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KS" $PY "$KIT/hooks/kit-check.py" 2>/dev/null)
  [ -z "$o" ] && pass "K5 AGENT_KIT_NO_UPDATE_CHECK=1: silent" || bad "K5 opt-out ignored"
  printf '%s\n' "$(printf '%s' "$latest" | cut -c1-7)" > "$k/home/.the-agent-kit/.kit-version"
  printf '# rules v1 (old)\n<!-- PROJECT-CONFIG:START -->\nmine\n<!-- PROJECT-CONFIG:END -->\n' > "$k/proj/AGENTS.md"
  o=$(kc "$k/proj"); has 'install.sh --update-rules' "$o" && pass "K6 project rules differ: one line naming --update-rules" || bad "K6 stale project rules not reported"
  printf '# rules v2\n<!-- PROJECT-CONFIG:START -->\nmine\n<!-- PROJECT-CONFIG:END -->\n' > "$k/proj/AGENTS.md"
  o=$(kc "$k/proj"); [ -z "$o" ] && pass "K7 project rules current (own block differs): silent" || bad "K7 spoke about a current project: $o"
  printf '<!-- The universal rules live in your global files -->\n<!-- PROJECT-CONFIG:START -->\n<!-- PROJECT-CONFIG:END -->\n' > "$k/proj/AGENTS.md"
  o=$(kc "$k/proj"); [ -z "$o" ] && pass "K8 --extension stub: silent" || bad "K8 nagged an extension stub"
  o=$(kc "$KIT"); has 'update-rules' "$o" && bad "K9 told the kit's own repo to overwrite its rules" || pass "K9 the kit's own repo is never told to --update-rules"
  # K10-K17: recommended tools. Only what is missing from the user's copy of recommended.json, for the
  # tool that started the session; web items only in a web project; at most once a day; silent when
  # it cannot tell (an unreadable config is not "missing").
  cp "$KIT/hooks/recommended.json" "$k/home/.the-agent-kit/recommended.json"
  kt() {  # $1 = tool, $2 = cwd -> stdout; the once-a-day marker is cleared unless $3 = keep
    [ "${3:-}" = keep ] || rm -f "$k/home/.the-agent-kit/.tools-check"
    printf '{"cwd":"%s","source":"startup"}' "$(wp "$2")" | HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KS" $PY "$KIT/hooks/kit-check.py" --tool "$1" 2>/dev/null
  }
  rm -f "$k/proj/AGENTS.md"
  o=$(kt claude "$k/proj"); has 'Context7' "$o" && ! has 'Playwright' "$o" \
    && pass "K10 missing core tool named; web tools not suggested outside a web project" || bad "K10 wrong suggestions: $o"
  printf '# rules v2\n<!-- PROJECT-CONFIG:START -->\n**Platform / intent:** web - production\n<!-- PROJECT-CONFIG:END -->\n' > "$k/proj/AGENTS.md"
  o=$(kt claude "$k/proj"); has 'Playwright' "$o" && has 'Impeccable' "$o" && has 'claude mcp add' "$o" \
    && pass "K11 web project: web tools suggested with their install command" || bad "K11 web tools not suggested: $o"
  printf '{"mcpServers":{"context7":{},"playwright":{},"chrome-devtools":{}}}' > "$k/home/.claude.json"
  for s in impeccable frontend-design; do mkdir -p "$k/home/.claude/skills/$s"; : > "$k/home/.claude/skills/$s/SKILL.md"; done
  o=$(kt claude "$k/proj"); [ -z "$o" ] && pass "K12 everything installed: silent" || bad "K12 spoke with everything installed: $o"
  printf '{"mcpServers":{"playwright":{},"chrome-devtools":{}}}' > "$k/home/.claude.json"
  o1=$(kt claude "$k/proj"); o2=$(kt claude "$k/proj" keep)
  has 'Context7' "$o1" && [ -z "$o2" ] && pass "K13 a reminder is given at most once a day" || bad "K13 throttle broken: [$o1] then [$o2]"
  printf 'not json' > "$k/home/.claude.json"
  o=$(kt claude "$k/proj"); has 'Context7' "$o" && bad "K14 unreadable config reported as missing" || pass "K14 unreadable config: no false reminder"
  mkdir -p "$k/home/.codex"; : > "$k/home/.codex/config.toml"; rm -f "$k/proj/AGENTS.md"
  o=$(kt codex "$k/proj"); has 'codex mcp add context7' "$o" && pass "K15 Codex session: Codex's missing tool and command named" || bad "K15 Codex gap not reported: $o"
  printf '[mcp_servers.context7]\ncommand = "npx"\n' > "$k/home/.codex/config.toml"
  o=$(kt codex "$k/proj"); [ -z "$o" ] && pass "K16 Codex tool present in config.toml: silent" || bad "K16 spoke when Codex had it: $o"
  printf '{"items":[]}' > "$k/home/.the-agent-kit/recommended.json"; printf '{}' > "$k/home/.claude.json"
  o=$(kt claude "$k/proj"); o2=$(kc "$k/proj")
  [ -z "$o" ] && [ -z "$o2" ] && pass "K17 declined (removed) items and sessions without --tool stay silent" || bad "K17 not silent: [$o] [$o2]"
  rm -rf "$k"
else
  bad "no python - kit-check.py NOT tested"
fi

# ---------- install.sh --check (doctor) ----------
# The doctor must report what is ACTUALLY live. Existence of a file in the hook slot is not enough:
# another tool's hook there (Husky, lefthook, pre-commit) means OUR guard is not running.
echo "== install.sh --check (doctor) =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2
# Pin this throwaway repo's hooks dir. Without it the suite inherits the machine's GLOBAL hooks
# redirect - which is exactly what the kit's own --global install sets up - and D1-D3 would then
# inspect the developer's real hooks directory instead of this repo, passing or failing on someone's
# machine configuration rather than on the code. D4 below re-points it on purpose.
git config core.hooksPath .git/hooks

d=$(sh "$KIT/install.sh" --check 2>&1)
has 'pre-commit not installed' "$d" && pass "D1 missing hook reported" || bad "D1 missing hook NOT reported"

for h in commit-msg pre-commit pre-push; do cp "$KIT/hooks/$h" ".git/hooks/$h"; chmod +x ".git/hooks/$h"; done
d=$(sh "$KIT/install.sh" --check 2>&1)
n=$(printf '%s\n' "$d" | grep -c 'live in')
[ "$n" -eq 3 ] && pass "D2 all three kit hooks reported live" || bad "D2 expected 3 live hooks, got $n"

printf '#!/bin/sh\necho some other tool\n' > .git/hooks/pre-commit; chmod +x .git/hooks/pre-commit
d=$(sh "$KIT/install.sh" --check 2>&1)
has "is NOT the kit" "$d" && pass "D3 foreign hook flagged INACTIVE" || bad "D3 foreign hook passed as OK (false green)"
# The exit code is the API scripts and CI actually read. FAIL text over exit 0 is false confidence.
if sh "$KIT/install.sh" --check >/dev/null 2>&1; then bad "D3b doctor exited 0 despite a FAIL"; else pass "D3b doctor exit code reflects FAIL"; fi

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
kit_rules AGENTS.md; printf '@AGENTS.md\n' > CLAUDE.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'PROJECT-CONFIG is still the empty placeholder' "$d" \
  && pass "D9 unfilled PROJECT-CONFIG warned" || bad "D9 unfilled PROJECT-CONFIG NOT warned"
has 'effective lines' "$d" && pass "D10 effective line count reported" || bad "D10 effective line count NOT reported"
# D10b: the count must include the PROJECT-CONFIG block. The markers are one-line comments, and a
# naive comment strip opened a range at START and closed it at END, hiding the project's config from
# the budget. Insert a known number of lines in the block and assert the count moves by that much.
c0=$(sh "$KIT/install.sh" --check 2>&1 | sed -n 's/.*AGENTS.md \([0-9][0-9]*\) effective lines.*/\1/p')
awk '/PROJECT-CONFIG:START/ { print; print "x1"; print "x2"; print "x3"; next } { print }' AGENTS.md > A3 && mv A3 AGENTS.md
c1=$(sh "$KIT/install.sh" --check 2>&1 | sed -n 's/.*AGENTS.md \([0-9][0-9]*\) effective lines.*/\1/p')
[ -n "$c0" ] && [ "$c1" = "$((c0 + 3))" ] \
  && pass "D10b project-block lines are counted against the budget ($c0 -> $c1)" \
  || bad "D10b project-block lines are NOT counted ($c0 -> $c1, expected $((c0 + 3)))"

# False-positive control: once it IS filled, the warning must go silent.
sed 's/Not configured yet\..*fill this in\./Build: make all  Test: make test  Lint: make lint/' AGENTS.md > A2 && mv A2 AGENTS.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'PROJECT-CONFIG is still the empty placeholder' "$d" \
  && bad "D11 filled PROJECT-CONFIG still warned (false positive)" || pass "D11 filled PROJECT-CONFIG is silent"
# D12: a block filled without a Branches line (every install before 2026-09-26) is flagged; with one, silent.
has 'no \*\*Branches:\*\* line' "$d" && pass "D12 filled block without Branches warned" || bad "D12 missing Branches line NOT warned"
awk '{ print } /PROJECT-CONFIG:START/ { print "**Branches:** work on `main`; none is release-only." }' AGENTS.md > A2 && mv A2 AGENTS.md
grep -q '^\*\*Branches:\*\*' AGENTS.md || bad "D12b setup: the Branches line was not inserted"
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'no \*\*Branches:\*\* line' "$d" && bad "D12b Branches warning still shown (false positive)" || pass "D12b block with a Branches line is silent"
cd "$KIT"; rm -rf "$w"

# ---------- install.sh --update-rules ----------
echo "== install.sh --update-rules =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
git init -q -b main || exit 2
# U1: stale rules + a FILLED block -> rules refreshed, the block survives byte-for-byte
kit_rules A0
{ head -1 A0; echo "STALE-RULES-MARKER"; tail -n +2 A0; } > AGENTS.md; rm -f A0
sed 's/Not configured yet\..*fill this in\./Build: make all  Test: make test/' AGENTS.md > A2 && mv A2 AGENTS.md
grep -q 'Build: make all' AGENTS.md || bad "U1 setup: the placeholder sed did not fire"
grep -q 'STALE-RULES-MARKER' AGENTS.md || bad "U1 setup: the stale marker was not inserted"
sh "$KIT/install.sh" --update-rules >/dev/null 2>&1 || bad "U1 --update-rules exited non-zero"
grep -q 'STALE-RULES-MARKER' AGENTS.md && bad "U1 stale rules NOT replaced" || pass "U1 stale rules replaced with the kit's"
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
cd "$KIT"; rm -rf "$w"   # S2 below reassigns $w; without this the R4 sandbox leaks, one per run
# S1-S3: skills are the TASK-shaped tier. Same silent-failure risk as rules - if one does not
# install, nothing says so, because a skill is meant to be quiet until a task matches it.
sn=0
for sd in "$KIT"/claude/skills/*/; do
  [ -d "$sd" ] || continue
  sn=$((sn+1))
  f="$sd/SKILL.md"
  [ -f "$f" ] || bad "S1 $(basename "$sd") has no SKILL.md"
  head -1 "$f" | grep -q '^---$' || bad "S1 $(basename "$sd") missing frontmatter"
  grep -q '^description:' "$f" || bad "S1 $(basename "$sd") has no description - the model matches on it"
done
[ "$sn" -gt 0 ] && pass "S1 $sn skill(s), each with frontmatter and a description" || bad "S1 no skills found"
w=$(mktemp -d) || exit 2; cd "$w" || exit 2; git init -q
sh "$KIT/install.sh" >/dev/null 2>&1
sc=$(ls -d .claude/skills/*/ 2>/dev/null | wc -l | tr -d ' ')
[ "$sc" = "$sn" ] && pass "S2 install deploys all $sn skill(s)" || bad "S2 deployed $sc of $sn skills"
sh "$KIT/install.sh" >/dev/null 2>&1
sc2=$(ls -d .claude/skills/*/ 2>/dev/null | wc -l | tr -d ' ')
[ "$sc2" = "$sn" ] && pass "S3 re-install does not duplicate skills" || bad "S3 skill count changed to $sc2"
cd "$KIT"; rm -rf "$w"

# R5/R6: the doctor must report on the depth tier - a rule that fails to install is otherwise
# invisible, since the whole point is that it stays silent until a path matches.
w=$(mktemp -d) || exit 2; cd "$w" || exit 2; git init -q
# The real scenario: rules present in the repo but the depth tier never deployed (an older kit, or a
# hand-copied AGENTS.md). A repo with no AGENTS.md at all is a different case the doctor covers above.
cp "$KIT/AGENTS.md" AGENTS.md; printf '@AGENTS.md
' > CLAUDE.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'deep conditional rules are not installed' "$d"   && pass "R5 doctor reports a missing depth tier" || bad "R5 missing rules NOT reported"
rm -f AGENTS.md CLAUDE.md
sh "$KIT/install.sh" >/dev/null 2>&1
d=$(sh "$KIT/install.sh" --check 2>&1)
has 'path-scoped rules in .claude/rules' "$d"   && pass "R6 doctor confirms installed rules" || bad "R6 installed rules NOT confirmed"
# A rule with no paths: frontmatter loads on EVERY turn - the opposite of the intent. Must be flagged.
printf 'no frontmatter here
' > .claude/rules/broken.md
d=$(sh "$KIT/install.sh" --check 2>&1)
has "lack 'paths:' frontmatter" "$d"   && pass "R7 doctor flags a rule that would load always-on" || bad "R7 frontmatter-less rule NOT flagged"
cd "$KIT"; rm -rf "$w"

# R8: the security rule has to REACH edge config, because that is where rate limiting and IP
# blocking actually get written - and no rule may claim a glob so broad it drags 12 KiB of the depth
# tier into projects it has nothing to say about.
#
# STRUCTURAL ONLY, and read it as nothing more: this proves the globs are DECLARED. It does not
# prove Claude Code matches them - that was measured once for the tier by token count (free on a
# non-match, +12.7k on a match) and is not re-measured here.
ws="$KIT/claude/rules/web-security.md"
miss=""
for g in 'nginx.conf' 'Caddyfile' 'vercel.json' 'wrangler.toml' 'fly.toml' '.htaccess'; do
  grep -q "\"\*\*/$g\"" "$ws" || miss="$miss $g"
done
[ -z "$miss" ] && pass "R8 web-security.md reaches edge config (nginx, Caddy, vercel, wrangler, fly, htaccess)" \
                || bad "R8 web-security.md declares no glob for:$miss"
broad=""
for r in "$KIT"/claude/rules/*.md; do
  [ -e "$r" ] || continue
  awk '/^paths:/{p=1;next} /^---/{if(p)exit} p' "$r" \
    | grep -qE '"\*\*/\*\.(ya?ml|json|toml|tf|md|txt)"|"\*\*/\*"|"\*"' \
    && broad="$broad $(basename "$r")"
done
[ -z "$broad" ] && pass "R8 no rule claims a catch-all glob that would load it into unrelated projects" \
                 || bad "R8 over-broad glob in:$broad"

# ---------- install.sh --update ----------
# Runs against a LOCAL clone source with a fake HOME: no network, and the real ~/.the-agent-kit
# is never touched. AGENT_KIT_REPO is the same override a fork would use.
echo "== install.sh --update =="
w=$(mktemp -d) || exit 2; cd "$w" || exit 2
# The source repo is built from the WORKING TREE, not from $KIT's HEAD: --update deliberately runs
# the installer it just downloaded, so cloning the last commit would test yesterday's code and go
# green on a change that is still broken here.
mkdir -p "$w/src" || exit 2
(cd "$KIT" && cp -r install.sh AGENTS.md CLAUDE.md hooks docs claude codex setup "$w/src/") || exit 2
head=$( (cd "$w/src" && git init -q -b main && git add -A \
        && git -c user.email=t@e.com -c user.name=T commit -qm "working tree" \
        && git rev-parse --short HEAD) 2>/dev/null || printf '' )
if [ -z "$head" ]; then
  echo "SKIP: could not build a source repo - --update not exercised"
else
  # AGENT_KIT_APPLY=1 on --update must NOT apply settings that just arrived from the network: the update
  # lists them, and applying is a second, separate step taken after seeing that list.
  mkdir -p "$w/.claude"
  d=$(HOME="$w" AGENT_KIT_APPLY=1 AGENT_KIT_REPO="$w/src" sh "$KIT/install.sh" --update 2>&1) || bad "U5 --update exited non-zero"
  [ ! -e "$w/.claude/settings.json" ] && has 'settings.json' "$d" \
    && pass "U5 --update lists the settings changes but never applies them itself" || bad "U5 --update applied network-sourced settings"
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
  # U10: upgrading an OLD project must bring the WHOLE kit, not just AGENTS.md. A project created
  # before the depth tier existed has no .claude/rules; if --update-rules refreshes the text and
  # silently skips the rules, the upgrade path quietly under-delivers and reports success.
  u=$(mktemp -d) && (cd "$u" && git init -q && cp "$KIT/AGENTS.md" . && printf '@AGENTS.md
' > CLAUDE.md       && sh "$KIT/install.sh" --update-rules >/dev/null 2>&1)
  rc=$(ls "$u"/.claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
  kc=$(ls "$KIT"/claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
  [ "$rc" = "$kc" ] && pass "U10 --update-rules also deploys the depth tier ($rc rules)"     || bad "U10 upgrade left the depth tier missing: $rc of $kc rules"
  rm -rf "$u"
  # U11: a kit-owned rule that drifted (older version, or a hand edit to a kit-named file) must be
  # brought current by an update - otherwise a security fix never reaches installed projects.
  u=$(mktemp -d) && (cd "$u" && git init -q && cp "$KIT/AGENTS.md" . && printf '@AGENTS.md\n' > CLAUDE.md \
      && mkdir -p .claude/rules && printf 'stale old content\n' > .claude/rules/web-security.md \
      && sh "$KIT/install.sh" --update-rules >/dev/null 2>&1)
  cmp -s "$KIT/claude/rules/web-security.md" "$u/.claude/rules/web-security.md" \
    && pass "U11 stale kit-owned rule refreshed by --update-rules" || bad "U11 stale kit rule NOT refreshed"
  rm -rf "$u"
  # U12: every command the installer TELLS a human to run must still work after it exits. --update
  # clones to a temp dir and deletes it on the way out, so anything printed with that path is broken
  # by the time it is read. This caught exactly that: `cat "$KIT/AGENTS.md" >> ~/.claude/CLAUDE.md`
  # pointed at the throwaway clone. Assert that no path the output names has vanished.
  missing=""
  for p in $(printf '%s\n' "$d" | grep -oE '/tmp/[A-Za-z0-9._/-]+' | sort -u); do
    [ -e "$p" ] || missing="$missing $p"
  done
  [ -z "$missing" ] && pass "U12 every path the installer prints still exists after it exits" \
                    || bad "U12 installer printed vanished path(s):$missing"
  # U13: a fresh install gives Codex its lazy tier - the two skills plus the four domain-shaped rules
  # as .agents/skills - and NOT the two path-shaped rules, which have no honest task trigger.
  u=$(mktemp -d) && (cd "$u" && git init -q && sh "$KIT/install.sh" >/dev/null 2>&1)
  m=""
  for s in generating-reports orchestrating-work writing-docs web-security data-layer frontend-quality ci-cd; do
    [ -f "$u/.agents/skills/$s/SKILL.md" ] || m="$m $s"
  done
  x=""
  for s in code-correctness tests; do [ -e "$u/.agents/skills/$s" ] && x="$x $s"; done
  [ -z "$m" ] && [ -z "$x" ] && pass "U13 fresh install ships 7 Codex skills and withholds the 2 path-shaped rules" \
    || bad "U13 Codex skills wrong - missing:[$m] wrongly ported:[$x]"
  # U14: a generated skill is the rule with its frontmatter swapped - name + description present,
  # `paths:` gone, body byte-identical to the rule's body. Anything else is a fork, not an adapter.
  g="$u/.agents/skills/web-security/SKILL.md"
  body_g=$(awk 'fm<2 && /^---$/ {fm++; next} fm>=2 {print}' "$g")
  body_r=$(awk 'fm<2 && /^---$/ {fm++; next} fm>=2 {print}' "$KIT/claude/rules/web-security.md")
  [ "$(sed -n 2p "$g")" = "name: web-security" ] && sed -n 3p "$g" | grep -q '^description: Use when' \
    && ! grep -q '^paths:' "$g" && [ "$body_g" = "$body_r" ] \
    && pass "U14 generated Codex skill = rule body + skill frontmatter, no paths:" \
    || bad "U14 generated Codex skill drifts from its rule (frontmatter or body)"
  rm -rf "$u"
  # U15: --update-rules brings an old project's Codex tier up too - deploys it when absent, and
  # regenerates a generated skill whose text drifted from the rule it came from.
  u=$(mktemp -d) && (cd "$u" && git init -q && cp "$KIT/AGENTS.md" . && printf '@AGENTS.md\n' > CLAUDE.md \
      && mkdir -p .agents/skills/data-layer && printf 'stale old content\n' > .agents/skills/data-layer/SKILL.md \
      && sh "$KIT/install.sh" --update-rules >/dev/null 2>&1)
  [ -f "$u/.agents/skills/web-security/SKILL.md" ] && ! grep -q 'stale old content' "$u/.agents/skills/data-layer/SKILL.md" \
    && grep -q '^name: data-layer' "$u/.agents/skills/data-layer/SKILL.md" \
    && pass "U15 --update-rules deploys and refreshes the Codex skills" \
    || bad "U15 --update-rules left the Codex skills missing or stale"
  rm -rf "$u"
  # U18: the machine-wide share must hold the rules with an EMPTY block too. The README tells users who
  # prefer global rules to append the share's AGENTS.md to ~/.claude/CLAUDE.md, so a leak here would put
  # this repo's branch rules into every project they own.
  g=$(mktemp -d) && HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
  if grep -q 'fill this in' "$g/.the-agent-kit/AGENTS.md" 2>/dev/null && ! grep -q 'the-agent-kit (rules and guardrails' "$g/.the-agent-kit/AGENTS.md" 2>/dev/null; then
    pass "U18 the machine-wide share gets an empty PROJECT-CONFIG, not the kit's own"
  else bad "U18 the machine-wide share inherited the kit repo's PROJECT-CONFIG"; fi
  # U19: the owner's git-ignored notes in docs/ never reach the share.
  made=""
  for n in lessons.md my-skills-and-plugins.md; do
    [ -f "$KIT/docs/$n" ] || { : > "$KIT/docs/$n"; made="$made $n"; }
  done
  HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
  [ -f "$g/.the-agent-kit/docs/project-setup-prompt.md" ] && [ ! -e "$g/.the-agent-kit/docs/lessons.md" ] \
    && [ ! -e "$g/.the-agent-kit/docs/my-skills-and-plugins.md" ] \
    && pass "U19 git-ignored notes in docs/ stay out of the share" \
    || bad  "U19 the share received a private note from docs/"
  for n in $made; do rm -f "$KIT/docs/$n"; done
  # U20: the recommended-tools list is seeded once, then it is the user's: a reinstall keeps their edits.
  if [ -f "$g/.the-agent-kit/recommended.json" ]; then
    printf '{"items":[]}' > "$g/.the-agent-kit/recommended.json"
    HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
    grep -q '"items":\[\]' "$g/.the-agent-kit/recommended.json" \
      && pass "U20 recommended.json seeded once; a reinstall keeps the user's edits" \
      || bad  "U20 a reinstall overwrote the user's recommended.json"
  else bad "U20 --global did not seed recommended.json"; fi
  rm -rf "$g"
  # U17: a fresh project install must get an EMPTY project block, never the kit repo's own config.
  # The kit's AGENTS.md is both this repo's rules file and the template shipped to projects; `cp`
  # would have leaked "work on develop, main is release-only" into everyone's repo.
  u=$(mktemp -d) && (cd "$u" && git init -q && sh "$KIT/install.sh" >/dev/null 2>&1)
  if grep -q 'fill this in' "$u/AGENTS.md" 2>/dev/null && ! grep -q 'the-agent-kit (rules and guardrails' "$u/AGENTS.md" 2>/dev/null; then
    pass "U17 fresh install gets an empty PROJECT-CONFIG, not the kit's own"
  else bad "U17 fresh install inherited the kit repo's PROJECT-CONFIG"; fi
  rm -rf "$u"
  # U16: --global run twice must leave ONE flat skills tree in the share. `cp -r src dest` with dest
  # present copies INTO it, so the second run nested skills/skills/ and left the top level stale -
  # every skill added after the first install was silently missing from projects updated afterwards
  # (observed on a real machine 2026-09-18). The optional performance profile must ship too.
  g=$(mktemp -d) && HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1 && HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
  want=$(ls -d "$KIT"/claude/skills/*/ | wc -l | tr -d ' '); got=$(ls -d "$g"/.the-agent-kit/skills/*/ 2>/dev/null | wc -l | tr -d ' ')
  [ ! -d "$g/.the-agent-kit/skills/skills" ] && [ "$got" = "$want" ] && [ -f "$g/.the-agent-kit/claude/performance/settings.json" ] \
    && pass "U16 --global twice keeps one flat skills tree ($got skills) and ships the performance profile" \
    || bad "U16 --global left a nested or stale skills tree ($got of $want, nested=$([ -d "$g/.the-agent-kit/skills/skills" ] && echo yes || echo no))"
  rm -rf "$g"
  # U9: the structural guard U8 cannot be. update_kit must END by exec-ing the downloaded installer -
  # exec replaces the process, so not one more byte is read from the file --global is overwriting.
  # Any refactor that turns this back into a plain call reintroduces the corruption, silently.
  awk '/^update_kit\(\)/,/^}/' "$KIT/install.sh" | grep -q '^ *exec sh -c' \
    && pass "U9 update_kit hands off with exec (self-overwrite guard)" \
    || bad  "U9 update_kit no longer execs - it will read the file --global just overwrote"
fi
cd "$KIT"; rm -rf "$w"

# ---------- install.sh --setup (one-command machine setup) ----------
# The installer, run by the user, merges the kit into their settings. It only ever ADDS (plus updating
# the kit's own older entries in place), backs up first, refuses a malformed file, and writes nothing
# without consent: a terminal answer, or AGENT_KIT_APPLY=1, which the tool guard asks about.
echo "== install.sh --setup =="
if [ -n "$PY" ]; then
  g=$(mktemp -d) || exit 2
  wq() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }
  G=$(wq "$g")
  su() {  # $1 = AGENT_KIT_APPLY value ("" = no consent) -> output in $o, exit code in $src
    src=0; o=$(HOME="$g" USERPROFILE="$G" AGENT_KIT_APPLY="$1" sh "$KIT/install.sh" --setup </dev/null 2>&1) || src=$?
  }
  jq_() { $PY -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print($2)" "$(wq "$1")" 2>/dev/null; }
  gh_() { HOME="$g" git config --global --get core.hooksPath 2>/dev/null; }
  mkdir -p "$g/.claude"
  su ""
  [ ! -e "$g/.claude/settings.json" ] && [ -z "$(gh_)" ] && has 'AGENT_KIT_APPLY' "$o" \
    && pass "M1 no terminal and no consent: nothing written, and it says how to apply" || bad "M1 wrote without consent: $o"
  su 1
  [ "$(jq_ "$g/.claude/settings.json" "any('command-guard.py' in h['command'] for e in d['hooks'].values() for b in e for h in b['hooks'])")" = True ] \
    && [ "$(jq_ "$g/.claude/settings.json" "any('kit-check.py' in h['command'] and '--tool claude' in h['command'] for b in d['hooks']['SessionStart'] for h in b['hooks'])")" = True ] \
    && pass "M2 fresh machine: Claude settings created with the guard and the session-start check" || bad "M2 settings not created: $o"
  case "$(gh_)" in *".the-agent-kit/git-hooks") pass "M2 git hooks turned on (core.hooksPath -> the kit)" ;; *) bad "M2 core.hooksPath not set: [$(gh_)]" ;; esac
  nb=$(ls "$g/.claude/" | grep -c 'bak-agent-kit' || true)
  su 1; nb2=$(ls "$g/.claude/" | grep -c 'bak-agent-kit' || true)
  has 'already' "$o" && [ "$nb" = "$nb2" ] && pass "M3 second run: already set up, nothing written" || bad "M3 re-run not idempotent ($nb -> $nb2): $o"
  cat > "$g/.claude/settings.json" <<'EOF'
{"statusLine":{"type":"command","command":"my-status"},
 "permissions":{"ask":["Bash(foo *)"]},
 "hooks":{"SessionStart":[{"matcher":"startup|resume","hooks":[{"type":"command","command":"headroom init hook ensure"}]},
                          {"matcher":"startup","hooks":[{"type":"command","command":"python3 \"/old/.the-agent-kit/hooks/kit-check.py\""}]}]}}
EOF
  cp "$g/.claude/settings.json" "$g/orig.json"
  su 1
  [ "$(jq_ "$g/.claude/settings.json" "d['statusLine']['command']")" = my-status ] \
    && [ "$(jq_ "$g/.claude/settings.json" "'Bash(foo *)' in d['permissions']['ask']")" = True ] \
    && [ "$(jq_ "$g/.claude/settings.json" "sum('headroom' in h['command'] for b in d['hooks']['SessionStart'] for h in b['hooks'])")" = 1 ] \
    && pass "M4 the user's own settings, rules and hooks are all kept" || bad "M4 user settings lost: $o"
  kc=$(jq_ "$g/.claude/settings.json" "sum('kit-check.py' in h['command'] for b in d['hooks']['SessionStart'] for h in b['hooks'])")
  kt=$(jq_ "$g/.claude/settings.json" "all('--tool claude' in h['command'] for b in d['hooks']['SessionStart'] for h in b['hooks'] if 'kit-check.py' in h['command'])")
  [ "$kc" = 1 ] && [ "$kt" = True ] && pass "M4 an older kit hook is updated in place, not duplicated" || bad "M4 kit hook duplicated or stale (count $kc, current $kt)"
  b=$(ls -t "$g/.claude/"settings.json.bak-agent-kit-* 2>/dev/null | head -1)
  [ -n "$b" ] && cmp -s "$b" "$g/orig.json" && pass "M4 the original was backed up before writing" || bad "M4 no faithful backup"
  # The same hook spelled another way (/c/... against C:/..., backslashes) is the same hook: a working
  # file is not rewritten over spelling. Found on a real machine whose entries were merged by hand.
  $PY - "$(wq "$g/.claude/settings.json")" <<'EOF'
import json, re, sys
p = sys.argv[1]; d = json.load(open(p, encoding='utf-8'))
for ev in d['hooks'].values():
    for b in ev:
        for h in b['hooks']:
            h['command'] = re.sub(r'([A-Za-z]):/', lambda m: '/' + m.group(1).lower() + '/', h['command'])
json.dump(d, open(p, 'w', encoding='utf-8'))
EOF
  cp "$g/.claude/settings.json" "$g/respelled.json"
  su 1
  cmp -s "$g/.claude/settings.json" "$g/respelled.json" && has 'already' "$o" \
    && pass "M4 a kit hook spelled with another path form is recognised, not rewritten" || bad "M4 path spelling caused a rewrite: $o"
  printf '{ not json' > "$g/.claude/settings.json"
  su 1
  [ "$(cat "$g/.claude/settings.json")" = '{ not json' ] && [ "$src" != 0 ] && has 'settings.json' "$o" \
    && pass "M5 a malformed settings file is refused and left untouched" || bad "M5 malformed file handled wrongly (rc=$src): $o"
  printf '{}' > "$g/.claude/settings.json"
  mkdir -p "$g/.codex"
  printf 'model = "x"\n\n[projects.a]\ntrust_level = "trusted"\n' > "$g/.codex/config.toml"
  su 1
  t=$($PY -c "import tomllib,sys; d=tomllib.load(open(sys.argv[1],'rb')); print(d.get('approval_policy'), d.get('sandbox_mode'), d['sandbox_workspace_write']['network_access'], d['projects']['a']['trust_level'], d['model'])" "$(wq "$g/.codex/config.toml")" 2>&1)
  [ "$t" = "on-request workspace-write True trusted x" ] && pass "M6 Codex config: kit settings added at top level, the user's tables unchanged" || bad "M6 Codex config wrong: [$t] $o"
  [ "$(jq_ "$g/.codex/hooks.json" "any('command-guard.py' in h['command'] and '--decision deny' in h['command'] for b in d['hooks']['PreToolUse'] for h in b['hooks'])")" = True ] \
    && pass "M6 Codex hooks.json created with the guard" || bad "M6 Codex guard not wired: $o"
  printf 'approval_policy = "never"\n[projects.a]\ntrust_level = "trusted"\n' > "$g/.codex/config.toml"
  su 1
  t=$($PY -c "import tomllib,sys; print(tomllib.load(open(sys.argv[1],'rb'))['approval_policy'])" "$(wq "$g/.codex/config.toml")" 2>&1)
  [ "$t" = never ] && pass "M7 a setting the user already chose is kept, not overwritten" || bad "M7 user's approval_policy overwritten: [$t]"
  # The merge helper itself refuses to write without consent, so running it directly is no way around it.
  printf '{}' > "$g/.claude/settings.json"
  mrc=0; m=$(AGENT_KIT_APPLY= $PY "$KIT/setup/merge-settings.py" --home "$G" --share "$(wq "$g/.the-agent-kit")" --share-cmd x --py python --apply 2>&1) || mrc=$?
  [ "$(cat "$g/.claude/settings.json")" = '{}' ] && [ "$mrc" != 0 ] \
    && pass "M11 merge-settings.py --apply without AGENT_KIT_APPLY=1 refuses and writes nothing" || bad "M11 helper wrote without consent (rc=$mrc): $m"
  # Ownership is strict: a user's own command that merely mentions a kit script is theirs, and a block
  # the kit shares with a user hook keeps the user's matcher.
  cat > "$g/.claude/settings.json" <<'EOF'
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"bash ~/wrap.sh && python3 ~/.the-agent-kit/hooks/command-guard.py --decision ask","timeout":99}]}],
 "SessionStart":[{"matcher":"startup|resume","hooks":[{"type":"command","command":"headroom init hook ensure"},{"type":"command","command":"python3 \"/old/.the-agent-kit/hooks/kit-check.py\""}]}]}}
EOF
  su 1
  [ "$(jq_ "$g/.claude/settings.json" "[h for b in d['hooks']['PreToolUse'] for h in b['hooks'] if 'wrap.sh' in h['command']][0]['timeout']")" = 99 ] \
    && pass "M12 a user's wrapped command that mentions a kit script is left untouched" || bad "M12 user's wrapper clobbered: $o"
  [ "$(jq_ "$g/.claude/settings.json" "[b['matcher'] for b in d['hooks']['SessionStart'] if any('headroom' in h['command'] for h in b['hooks'])][0]")" = 'startup|resume' ] \
    && [ "$(jq_ "$g/.claude/settings.json" "sum('kit-check.py' in h['command'] for b in d['hooks']['SessionStart'] for h in b['hooks'])")" = 1 ] \
    && pass "M12 a shared block keeps the user's matcher; the old kit hook moves out, not duplicated" || bad "M12 shared block mutated: $o"
  HOME="$g" git config --global core.hooksPath .husky
  su 1
  [ "$(gh_)" = .husky ] && has 'is .husky' "$o" \
    && pass "M8 git hooks owned by another tool are left alone, and it says so" || bad "M8 foreign core.hooksPath changed: [$(gh_)]"
  HOME="$g" git config --global --unset core.hooksPath
  d=$(cd "$g" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1)
  has 'settings.*kit entries' "$d" && ! has 'install.sh --setup' "$d" && pass "M9 --check confirms the settings carry the kit" || bad "M9 --check misreports current settings: $(printf '%s' "$d" | grep -i setting)"
  printf '{}' > "$g/.claude/settings.json"
  d=$(cd "$g" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1)
  has 'install.sh --setup' "$d" && pass "M9 --check warns when the settings are missing the kit" || bad "M9 --check silent about missing settings"
  rm -rf "$g"
else
  bad "no python - install.sh --setup NOT tested"
fi
grep -q -- '--setup' "$KIT/install.sh" && awk '/^update_kit\(\)/,/^}/' "$KIT/install.sh" | grep -q 'install.sh" --setup' \
  && pass "M10 --update hands over to --setup, so updates re-apply settings" || bad "M10 --update does not run --setup"

# H1-H5: the eval harness's own oracles. Both were silently wrong until 2026-09-27: provider errors
# scored as ordinary FAILs, and a red-then-fix run scored as "edited before any failing test".
# The functions are lifted out of run.sh so the checks run offline, with no agent and no tokens.
(
  eval "$(sed -n '/^events_error() {/,/^}/p;/^trace_check() {/,/^}/p' "$KIT/test/adherence/run.sh")"
  hf="$KIT/test/adherence/harness-fixtures"; spec='red-before-edit: (node --test|npm test)'
  case "$(events_error "$hf/codex-usage-limit.jsonl" codex)" in *"usage limit"*) pass "H1 codex usage limit read as a provider error" ;; *) bad "H1 codex usage limit NOT detected" ;; esac
  case "$(events_error "$hf/claude-session-limit.jsonl" claude)" in *"session limit"*) pass "H2 claude session limit read as a provider error" ;; *) bad "H2 claude session limit NOT detected" ;; esac
  case "$(trace_check "$hf/claude-red-then-edit.jsonl" claude "$spec")" in OK*) pass "H3 red run then source edit passes the trace" ;; *) bad "H3 red-then-edit FAILED the trace" ;; esac
  case "$(trace_check "$hf/claude-edit-after-green.jsonl" claude "$spec")" in FAIL*) pass "H4 edit after a green run ('# fail 0') fails the trace" ;; *) bad "H4 edit after a green run PASSED the trace" ;; esac
  case "$(trace_check "$hf/codex-piped-red.jsonl" codex "$spec")" in OK*) pass "H5 codex piped red run (exit 0) is read as red" ;; *) bad "H5 codex piped red run read as green" ;; esac
) | tee "$w.h"; grep -q '^FAIL' "$w.h" 2>/dev/null && fail=1; rm -f "$w.h"

echo "---"
[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "FAILURES PRESENT"
exit "$fail"

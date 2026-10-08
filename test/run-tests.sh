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
  $PY "$KIT/test/mcp_wrap_cases.py" || bad "mcp-wrap cases"
  $PY "$KIT/test/mcp_orphans_cases.py" || bad "mcp-orphans corpus"
  $PY "$KIT/test/tidy_procs_cases.py" || bad "tidy-procs corpus"
  $PY "$KIT/test/tidy_scan_cases.py" || bad "tidy-scan cases"
  $PY "$KIT/test/adherence_harness_cases.py" || bad "adherence harness cases (summary, speed panel)"
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
# PC-B: a pipeline that cannot fail is not a gate. A newly added `continue-on-error: true` is blocked (the
# adherence eval's case 29 failed 0/3 with the rules present, in every measurement); false, a comment and a
# line that says why (`# gate-exempt: <reason>`) pass; an untouched old line never blocks.
git rm -q -f --cached .github/workflows/ci.yml 2>/dev/null; rm -f .github/workflows/ci.yml
wfy() { printf '%s\n' "$1" > .github/workflows/gate.yml; git add .github/workflows/gate.yml
  if git commit -q -m wf 2>/dev/null; then r=0; else r=1; git reset -q >/dev/null 2>&1; fi; return $r; }
wfy "$(printf 'jobs:\n  scan:\n    steps:\n      - name: Security scan\n        run: ./scan.sh\n        continue-on-error: true')" \
  && bad "PC-B1 a step-level continue-on-error: true was committed" || pass "PC-B1 step-level continue-on-error: true blocked"
wfy "$(printf 'jobs:\n  scan:\n    continue-on-error: true\n    steps:\n      - run: ./scan.sh')" \
  && bad "PC-B2 a job-level continue-on-error: true was committed" || pass "PC-B2 job-level continue-on-error: true blocked"
wfy "$(printf 'jobs:\n  scan:\n    steps:\n      - run: ./scan.sh\n        continue-on-error: false')" \
  && pass "PC-B3 continue-on-error: false passes" || bad "PC-B3 continue-on-error: false BLOCKED"
wfy "$(printf 'jobs:\n  scan:\n    steps:\n      - run: ./scan.sh\n        continue-on-error: true  # gate-exempt: the nightly canary may fail')" \
  && pass "PC-B4 a gate-exempt line passes" || bad "PC-B4 a gate-exempt line BLOCKED"
wfy "$(printf 'jobs:\n  scan:\n    steps:\n      - run: ./scan.sh\n        # continue-on-error: true')" \
  && pass "PC-B5 a commented continue-on-error passes" || bad "PC-B5 a commented continue-on-error BLOCKED"
wfy "$(printf 'jobs:\n  scan:\n    strategy: { fail-fast: false, continue-on-error: true }\n    steps:\n      - run: ./scan.sh')" \
  && bad "PC-B7 flow-style continue-on-error: true was committed" || pass "PC-B7 flow-style continue-on-error: true blocked"
wfy "$(printf 'jobs:\n  scan:\n    steps:\n      - run: ./scan.sh\n        "continue-on-error": True')" \
  && bad "PC-B8 a quoted key with True was committed" || pass "PC-B8 a quoted key with True blocked"
mkdir -p .github/actions/lint
printf 'runs:\n  using: composite\n  steps:\n    - run: ./lint.sh\n      shell: bash\n      continue-on-error: true\n' > .github/actions/lint/action.yml
git add .github/actions/lint/action.yml
if git commit -q -m act 2>/dev/null; then bad "PC-B9 a composite action step that cannot fail was committed"; git reset -q; else pass "PC-B9 a composite action's continue-on-error: true blocked"; fi
rm -rf .github/actions
printf 'jobs:\n  scan:\n    steps:\n      - run: ./scan.sh\n        continue-on-error: true\n' > .github/workflows/gate.yml
mv .git/hooks/pre-commit .git/hooks/pre-commit.off
git add .github/workflows/gate.yml; git commit -qm 'an old repo, committed before the kit' >/dev/null 2>&1
mv .git/hooks/pre-commit.off .git/hooks/pre-commit
printf '      - run: echo more\n' >> .github/workflows/gate.yml; git add .github/workflows/gate.yml
if git commit -q -m touch 2>/dev/null; then pass "PC-B6 an untouched old continue-on-error does not block"; else bad "PC-B6 an untouched old continue-on-error BLOCKED an unrelated commit"; git reset -q; fi
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
  for s in impeccable frontend-design playwright-cli; do mkdir -p "$k/home/.claude/skills/$s"; : > "$k/home/.claude/skills/$s/SKILL.md"; done
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
  # K18: optional items (superpowers, ponytail, headroom) are for install.sh --check, never the reminder.
  cp "$KIT/hooks/recommended.json" "$k/home/.the-agent-kit/recommended.json"
  printf '# rules v2\n<!-- PROJECT-CONFIG:START -->\n**Platform / intent:** web - production\n<!-- PROJECT-CONFIG:END -->\n' > "$k/proj/AGENTS.md"
  mkdir -p "$k/home/.claude/plugins"; printf '{"plugins":{}}' > "$k/home/.claude/plugins/installed_plugins.json"; : > "$k/home/.codex/config.toml"
  o=$(kt claude "$k/proj"); o2=$(kt codex "$k/proj")
  has 'Context7' "$o" && has 'Context7' "$o2" && ! has 'superpowers' "$o$o2" && ! has 'ponytail' "$o$o2" && ! has 'headroom' "$o$o2" \
    && pass "K18 optional items are never in the session reminder" || bad "K18 an optional item was reminded: $o $o2"
  # K19: the reminder is ONE line that tells the agent to tell the user once, in one line, what is
  # missing and the command for each - not an invitation to a conversation about installing.
  has 'tell the user once, in one line' "$o" && has 'claude mcp add --transport http context7' "$o" && has 'claude mcp add chrome-devtools' "$o" \
    && [ "$(printf '%s\n' "$o" | wc -l | tr -d ' ')" = 1 ] \
    && pass "K19 one line, telling the agent to relay the missing tools and their commands once" || bad "K19 reminder wording or length wrong: $o"
  # K20-K27: Antigravity. It has no SessionStart event but a PreInvocation hook that fires before EVERY model
  # call and answers in JSON ({} for nothing, {"injectSteps":[{"ephemeralMessage":...}]} to speak) with the
  # conversation id and the workspace in the payload. The check must speak once per conversation, say
  # nothing otherwise, and be cheap on the calls it skips.
  ka() {  # $1 = conversation id (empty = none), $2 = workspace -> stdout
    printf '{"conversationId":"%s","invocationNum":1,"workspacePaths":["%s"]}' "$1" "$(wp "$2")" \
      | HOME="$KH" USERPROFILE="$KH" AGENT_KIT_REPO="$KS" $PY "$KIT/hooks/kit-check.py" --tool antigravity 2>/dev/null
  }
  msg() { printf '%s' "$1" | $PY -c "import json,sys; d=json.loads(sys.stdin.read()); print(d['injectSteps'][0]['ephemeralMessage'] if d else '')" 2>/dev/null; }
  rm -f "$k/home/.the-agent-kit/.ag-conversations" "$k/home/.the-agent-kit/.update-check"; printf 'abc1234\n' > "$k/home/.the-agent-kit/.kit-version"
  rm -f "$k/proj/AGENTS.md"
  o=$(ka conv-1 "$k/proj")
  has 'install.sh --update' "$(msg "$o")" && pass "K20 Antigravity: the first call of a conversation injects the note, as JSON" || bad "K20 no injected note: $o"
  o=$(ka conv-1 "$k/proj"); [ "$o" = '{}' ] && pass "K21 the same conversation's next call is silent: {}" || bad "K21 spoke twice in one conversation: $o"
  o=$(ka conv-2 "$k/proj"); has 'install.sh --update' "$(msg "$o")" && pass "K22 a new conversation gets the note again" || bad "K22 new conversation not served: $o"
  printf '%s\n' "$(printf '%s' "$latest" | cut -c1-7)" > "$k/home/.the-agent-kit/.kit-version"
  o=$(ka conv-3 "$k/proj"); [ "$o" = '{}' ] && pass "K23 nothing to say is a valid {} (Antigravity expects JSON)" || bad "K23 not {} when current: $o"
  o=$(ka "" "$k/proj"); o2=$(printf 'not json' | HOME="$KH" USERPROFILE="$KH" $PY "$KIT/hooks/kit-check.py" --tool antigravity 2>/dev/null); rc=$?
  [ "$o" = '{}' ] && [ "$o2" = '{}' ] && [ "$rc" = 0 ] && pass "K24 no conversation id, or a payload that is not JSON: {} and exit 0, never a note on every call" || bad "K24 unsafe on a bad payload: [$o] [$o2]"
  o=$(printf '{"conversationId":"conv-9","workspacePaths":[]}' | AGENT_KIT_NO_UPDATE_CHECK=1 HOME="$KH" USERPROFILE="$KH" $PY "$KIT/hooks/kit-check.py" --tool antigravity 2>/dev/null)
  [ "$o" = '{}' ] && pass "K25 AGENT_KIT_NO_UPDATE_CHECK=1: {}" || bad "K25 opt-out ignored for Antigravity: $o"
  # K26: a conversation already seen costs nothing: no network call (the cache file is never written) and no rules lookup.
  rm -f "$k/home/.the-agent-kit/.update-check"; printf 'abc1234\n' > "$k/home/.the-agent-kit/.kit-version"
  o=$(ka conv-1 "$k/proj")
  [ "$o" = '{}' ] && [ ! -e "$k/home/.the-agent-kit/.update-check" ] && pass "K26 a conversation already seen is answered before any network or git work" || bad "K26 a seen conversation still did work: $o"
  # K27: the ledger of seen conversations stays bounded.
  $PY - "$(wp "$k/home/.the-agent-kit/.ag-conversations")" <<'EOF'
import json, sys
json.dump({"ids": ["old-%d" % i for i in range(400)]}, open(sys.argv[1], "w"))
EOF
  ka conv-new "$k/proj" >/dev/null
  [ "$($PY -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d['ids']) <= 200 and d['ids'][-1] == 'conv-new')" "$(wp "$k/home/.the-agent-kit/.ag-conversations")")" = True ] \
    && pass "K27 the seen-conversations ledger is capped, keeping the newest" || bad "K27 ledger unbounded or lost the newest id"
  # K28: missing recommended tools reach an Antigravity conversation too, from its own config.
  cp "$KIT/hooks/recommended.json" "$k/home/.the-agent-kit/recommended.json"; rm -f "$k/home/.the-agent-kit/.tools-check"
  printf '%s\n' "$(printf '%s' "$latest" | cut -c1-7)" > "$k/home/.the-agent-kit/.kit-version"
  mkdir -p "$k/home/.gemini/config"; : > "$k/home/.gemini/config/mcp_config.json"
  o=$(ka conv-tools "$k/proj"); m=$(msg "$o")
  has 'tell the user once, in one line' "$m" && has 'Antigravity' "$m" && has 'agy mcp add' "$m" && [ "$(printf '%s\n' "$m" | wc -l | tr -d ' ')" = 1 ] \
    && pass "K28 Antigravity: the missing Context7 is named with its agy command, in one line" || bad "K28 Antigravity tool reminder wrong: $m"
  printf '{"mcpServers":{"context7":{"url":"https://mcp.context7.com/mcp"}}}' > "$k/home/.gemini/config/mcp_config.json"; rm -f "$k/home/.the-agent-kit/.tools-check"
  o=$(ka conv-tools2 "$k/proj"); [ "$o" = '{}' ] && pass "K29 Antigravity: Context7 present in mcp_config.json: silent" || bad "K29 spoke although Context7 is configured: $o"
  printf 'not json' > "$k/home/.gemini/config/mcp_config.json"; rm -f "$k/home/.the-agent-kit/.tools-check"
  o=$(ka conv-tools3 "$k/proj"); [ "$o" = '{}' ] && pass "K30 Antigravity: an unreadable mcp_config.json is 'cannot tell', not 'missing'" || bad "K30 reported missing from an unreadable config: $o"
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

# D13: a project that has the /tidy skill but whose machine has no tidy scripts is told, by name, what to run.
if [ -n "$PY" ]; then
  g=$(mktemp -d) || exit 2; u=$(mktemp -d) || exit 2
  G=$(cygpath -m "$g" 2>/dev/null || printf '%s' "$g")
  dr() { (cd "$u" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1); }
  git init -q "$u"; git -C "$u" config core.hooksPath .git/hooks
  mkdir -p "$u/.claude/skills/tidy" "$g/.the-agent-kit/hooks"; : > "$u/.claude/skills/tidy/SKILL.md"
  d=$(dr)
  has 'NOTE: /tidy is installed in this project but its scripts are missing; run install.sh --setup' "$d" \
    && pass "D13 /tidy in the project but no scripts on the machine: the note names the fix" || bad "D13 no /tidy note: $(printf '%s' "$d" | grep -i tidy)"
  : > "$g/.the-agent-kit/hooks/tidy-scan.py"; d=$(dr)
  has '/tidy is installed in this project' "$d" && bad "D13 note shown although the scripts are there" || pass "D13 no note once the scripts are installed"
  rm -rf "$u/.claude"; rm -f "$g/.the-agent-kit/hooks/tidy-scan.py"; d=$(dr)
  has '/tidy is installed in this project' "$d" && bad "D13 note shown in a project without /tidy" || pass "D13 no note in a project without /tidy"
  mkdir -p "$u/.agents/skills/tidy"; : > "$u/.agents/skills/tidy/SKILL.md"; d=$(dr)
  has '/tidy is installed in this project' "$d" && pass "D13 the Codex and Antigravity copy (.agents/skills/tidy) counts too" || bad "D13 .agents/skills/tidy not noticed"
  rm -rf "$g" "$u"
fi

# D14: the doctor lists the recommended tools missing for each tool installed on this machine, and the
# optional ones (the session reminder never carries those); a config it cannot read is "cannot tell",
# never "missing". A temp HOME stands in for the machine.
if [ -n "$PY" ]; then
  g=$(mktemp -d) || exit 2; u=$(mktemp -d) || exit 2
  G=$(cygpath -m "$g" 2>/dev/null || printf '%s' "$g")
  dr() { (cd "$u" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1); }
  git init -q "$u"; git -C "$u" config core.hooksPath .git/hooks
  mkdir -p "$g/.the-agent-kit/hooks"
  cp "$KIT/hooks/recommended.json" "$g/.the-agent-kit/recommended.json"; cp "$KIT/hooks/kit-check.py" "$g/.the-agent-kit/hooks/kit-check.py"
  mkdir -p "$g/.claude" "$g/.gemini/config"; printf '{"mcpServers":{}}' > "$g/.claude.json"; printf 'not json' > "$g/.gemini/config/mcp_config.json"
  d=$(dr)
  has 'Claude Code is missing Context7' "$d" && has 'optional.*Claude Code.*superpowers' "$d" && has 'claude mcp add' "$d" \
    && pass "D14 --check lists the missing recommended and optional tools, with their commands" || bad "D14 gaps not listed: $(printf '%s' "$d" | grep -i 'missing\|cannot')"
  has 'Antigravity is missing Context7' "$d" && bad "D14 an unreadable Antigravity config was reported as missing" \
    || { has 'cannot tell.*Antigravity' "$d" && pass "D14 an unreadable config is 'cannot tell', not 'missing'" || bad "D14 unreadable config not mentioned: $(printf '%s' "$d" | grep -i antigravity)"; }
  has 'Codex is missing' "$d" && bad "D14 reported Codex although it is not installed here" || pass "D14 a tool that is not on this machine is not checked"
  : > "$g/.gemini/config/mcp_config.json"; d=$(dr)
  has 'Antigravity is missing Context7' "$d" && has 'agy mcp add' "$d" \
    && pass "D14 an empty Antigravity MCP file is a readable, empty config: Context7 is missing" || bad "D14 empty Antigravity config misjudged: $(printf '%s' "$d" | grep -i antigravity)"
  rm -rf "$g" "$u"
fi

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
# S4: a skill is its whole folder. A SKILL.md routing to a references/ file that never shipped fails
# silently, so every kit file, nested ones included, must land in both tools' copies, and
# --update-rules must restore a stale one.
miss=""
for f in $(cd "$KIT/claude/skills" && find . -type f | sed 's|^\./||'); do
  for t in .claude/skills .agents/skills; do [ -f "$t/$f" ] || miss="$miss $t/$f"; done
done
nf=$(find "$KIT/claude/skills" -mindepth 3 -type f | head -1)
if [ -n "$nf" ]; then
  rel=${nf#"$KIT/claude/skills/"}; printf 'stale\n' > ".claude/skills/$rel"
  printf 'pre-0.5.0 copy\n' > .claude/skills/generating-reports/design.md
  sh "$KIT/install.sh" --update-rules >/dev/null 2>&1
  cmp -s "$nf" ".claude/skills/$rel" || miss="$miss (stale .claude/skills/$rel not refreshed)"
  [ -e .claude/skills/generating-reports/design.md ] && miss="$miss (pre-0.5.0 design.md not removed)"
fi
[ -z "$miss" ] && pass "S4 every skill file, nested ones too, reaches both tools and refreshes" \
  || bad "S4 skill files missing or stale:$miss"
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
  for s in generating-reports orchestrating-work writing-docs tidy web-security data-layer frontend-quality ci-cd; do
    [ -f "$u/.agents/skills/$s/SKILL.md" ] || m="$m $s"
  done
  x=""
  for s in code-correctness tests; do [ -e "$u/.agents/skills/$s" ] && x="$x $s"; done
  [ -z "$m" ] && [ -z "$x" ] && pass "U13 fresh install ships 8 Codex skills and withholds the 2 path-shaped rules" \
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
  # A1-A4: Antigravity. It already reads AGENTS.md and the .agents/skills Codex gets; the kit adds the
  # two path-shaped rules as glob rules and the guard as a workspace PreToolUse hook. Antigravity splits
  # a hook command on whitespace and ignores quotes (a quoted path with a space breaks the hook, and a
  # broken hook blocks every command), so the hook calls a launcher beside hooks.json by bare name.
  u=$(mktemp -d) && (cd "$u" && git init -q && mkdir -p .agents \
      && printf '{"mine":{"Stop":[{"command":"echo bye"}]}}\n' > .agents/hooks.json \
      && sh "$KIT/install.sh" >/dev/null 2>&1)
  m=""
  for n in code-correctness tests; do
    f="$u/.agents/rules/$n.md"
    body_a=$(awk 'fm<2 && /^---$/ {fm++; next} fm>=2 {print}' "$f" 2>/dev/null)
    body_r=$(awk 'fm<2 && /^---$/ {fm++; next} fm>=2 {print}' "$KIT/claude/rules/$n.md")
    { [ -f "$f" ] && grep -q '^trigger: glob$' "$f" && grep -q '^globs: ".*\*\*/\*\.' "$f" \
      && ! grep -q '^paths:' "$f" && [ "$body_a" = "$body_r" ]; } || m="$m $n"
  done
  x=""; for n in web-security data-layer frontend-quality ci-cd; do [ -e "$u/.agents/rules/$n.md" ] && x="$x $n"; done
  [ -z "$m" ] && [ -z "$x" ] \
    && pass "A1 Antigravity glob rules: the 2 path-shaped rules, bodies unchanged, the 4 skills not doubled" \
    || bad "A1 Antigravity rules wrong - bad:[$m] doubled:[$x]"
  hj=$(wp "$u/.agents/hooks.json")
  $PY -c "import json,sys; d=json.load(open(sys.argv[1])); h=d['the-agent-kit']['PreToolUse'][0]; c=h['hooks'][0]['command']; assert h['matcher']=='run_command' and 'mine' in d and c.endswith('agent-kit-guard.py --tool antigravity') and '\"' not in c" "$hj" 2>/dev/null \
    && [ -f "$u/.agents/agent-kit-guard.py" ] \
    && pass "A2 .agents/hooks.json wires the guard by bare name, keeps the user's own hooks" \
    || bad "A2 .agents/hooks.json missing the guard, quoting a path, or dropping the user's hooks"
  # A3: the launcher reaches the installed guard and answers in Antigravity's contract.
  ah=$(mktemp -d); mkdir -p "$ah/.the-agent-kit/hooks"; cp "$KIT/hooks/command-guard.py" "$ah/.the-agent-kit/hooks/"
  o=$(cd "$u/.agents" && printf '{"toolCall":{"name":"run_command","args":{"CommandLine":"git push --force"}}}' \
      | HOME="$ah" USERPROFILE="$(wp "$ah")" $PY agent-kit-guard.py --tool antigravity 2>/dev/null)
  printf '%s' "$o" | grep -q '"decision": "deny"' \
    && pass "A3 the launcher runs the installed guard: a force push is denied" \
    || bad "A3 the launcher did not deny a force push (got: $o)"
  rm -rf "$ah"
  # A4: --update-rules restores a stale launcher and glob rule, and re-adds a removed hook entry.
  printf 'stale\n' > "$u/.agents/agent-kit-guard.py"; printf 'stale\n' > "$u/.agents/rules/tests.md"
  printf '{"mine":{"Stop":[{"command":"echo bye"}]}}\n' > "$u/.agents/hooks.json"
  (cd "$u" && sh "$KIT/install.sh" --update-rules >/dev/null 2>&1)
  ! grep -q '^stale$' "$u/.agents/agent-kit-guard.py" && ! grep -q '^stale$' "$u/.agents/rules/tests.md" \
    && grep -q '"the-agent-kit"' "$u/.agents/hooks.json" && grep -q '"mine"' "$u/.agents/hooks.json" \
    && pass "A4 --update-rules refreshes the Antigravity launcher, rules and hook entry" \
    || bad "A4 --update-rules left the Antigravity files stale or missing"
  # A5: --check reports the Antigravity side - the guard answering in its contract, and the hook wired.
  o=$(cd "$u" && sh "$KIT/install.sh" --check 2>&1)
  printf '%s' "$o" | grep -q 'OK:   command-guard answers Antigravity' \
    && printf '%s' "$o" | grep -q 'OK:   Antigravity guard wired' \
    && pass "A5 --check reports the Antigravity guard and its wiring" \
    || bad "A5 --check says nothing (or the wrong thing) about Antigravity"
  rm -rf "$u"
  # A6-A8: the Antigravity files are written into a project the user may not control. A planted symlink
  # must never turn the kit's write into a write somewhere else, a hostile hooks.json must not pass the
  # doctor, and an interrupted merge must not leave a half-written hooks.json.
  u=$(mktemp -d) && vic=$(mktemp -d) && printf '{"keep":"me"}\n' > "$vic/victim.json"
  (cd "$u" && git init -q && mkdir -p .agents/rules && MSYS=winsymlinks:nativestrict ln -s "$vic/victim.json" .agents/hooks.json \
      && MSYS=winsymlinks:nativestrict ln -s "$vic/newfile" .agents/rules/tests.md.refresh.tmp 2>/dev/null \
      && MSYS=winsymlinks:nativestrict ln -s "$vic/launcher" .agents/agent-kit-guard.py 2>/dev/null \
      && sh "$KIT/install.sh" >/dev/null 2>&1; sh "$KIT/install.sh" --update-rules >/dev/null 2>&1)
  if [ -L "$u/.agents/hooks.json" ]; then
    [ "$(cat "$vic/victim.json")" = '{"keep":"me"}' ] && [ ! -e "$vic/newfile" ] && [ ! -e "$vic/launcher" ] \
      && pass "A6 symlinks in .agents/ are never written through" \
      || bad "A6 the installer wrote through a symlink: $(cat "$vic/victim.json") $(ls "$vic")"
  else pass "A6 (this platform cannot create symlinks; skipped)"; fi
  rm -rf "$u" "$vic"
  u=$(mktemp -d) && (cd "$u" && git init -q && mkdir -p .agents && printf '{"the-agent-kit":{"PreToolUse":[{"matcher":"run_command","hooks":[{"command":"echo hostile"}]}]}}\n' > .agents/hooks.json \
      && printf 'x\n' > .agents/agent-kit-guard.py && printf '# rules\n' > AGENTS.md)
  o=$(cd "$u" && sh "$KIT/install.sh" --check 2>&1)
  printf '%s' "$o" | grep -q 'OK:   Antigravity guard wired' \
    && bad "A7 --check calls a hostile hooks.json wired" \
    || { printf '%s' "$o" | grep -q 'Antigravity guard.*not the kit' && pass "A7 --check rejects a hooks.json whose guard command is not the kit's" \
         || bad "A7 --check says nothing about a hostile Antigravity hook"; }
  rm -rf "$u"
  # U21: global guidance includes Antigravity, but machine setup leaves its home files alone.
  g=$(mktemp -d) || exit 2
  o=$(HOME="$g" sh "$KIT/install.sh" --global 2>&1)
  has '~/.gemini/AGENTS.md' "$o" \
    && pass "U21 --global names Antigravity's global rules file" \
    || bad "U21 --global omits Antigravity's global rules file"
  has 'mklink /J' "$o" && has 'skills.json' "$o" && [ ! -e "$g/.agents" ] && [ ! -e "$g/.gemini" ] \
    && pass "U21b --global prints how to install the kit's skills once for all three tools, and writes none of it" \
    || bad "U21b --global omits the machine-wide skills steps, or wrote them"
  o=$(HOME="$g" AGENT_KIT_APPLY= sh "$KIT/install.sh" --setup </dev/null 2>&1)
  has "Antigravity's command guard is still wired per project" "$o" && [ ! -e "$g/.gemini" ] \
    && pass "U21 --setup says the Antigravity guard stays per project and, without consent or a ~/.gemini, writes nothing there" \
    || bad "U21 --setup omits Antigravity's per-project guard scope or writes ~/.gemini"
  rm -rf "$g"
  # U18: the machine-wide share must hold the rules with an EMPTY block too. The README tells users who
  # prefer global rules to append the share's AGENTS.md to ~/.claude/CLAUDE.md, so a leak here would put
  # this repo's branch rules into every project they own.
  g=$(mktemp -d) && HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
  if grep -q 'fill this in' "$g/.the-agent-kit/AGENTS.md" 2>/dev/null && ! grep -q 'the-agent-kit (rules and guardrails' "$g/.the-agent-kit/AGENTS.md" 2>/dev/null; then
    pass "U18 the machine-wide share gets an empty PROJECT-CONFIG, not the kit's own"
  else bad "U18 the machine-wide share inherited the kit repo's PROJECT-CONFIG"; fi
  # U19: the owner's git-ignored notes in docs/ never reach the share.
  made=""
  for n in lessons.md my-skills-and-plugins.md enhancements.md todo.md; do
    [ -f "$KIT/docs/$n" ] || { : > "$KIT/docs/$n"; made="$made $n"; }
  done
  HOME="$g" sh "$KIT/install.sh" --global >/dev/null 2>&1
  leaked=""
  for n in lessons.md my-skills-and-plugins.md enhancements.md todo.md; do
    [ -e "$g/.the-agent-kit/docs/$n" ] && leaked="$leaked $n"
  done
  [ -f "$g/.the-agent-kit/docs/project-setup-prompt.md" ] && [ -z "$leaked" ] \
    && pass "U19 git-ignored notes in docs/ stay out of the share" \
    || bad  "U19 the share received private notes from docs/:$leaked"
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

# ---------- MCP reaper: installer dispatch and Windows orphan lifecycle ----------
if [ -n "$PY" ]; then
  (
    orphan_tmp=$(mktemp -d) || exit 2
    # The Python fixture records only processes it starts. Cleanup runs even on failure.
    trap '$PY "$KIT/test/mcp_orphans_cases.py" --cleanup "$orphan_tmp"; rm -rf "$orphan_tmp"' 0
    trap 'exit 1' 1 2 15
    HOME="$orphan_tmp" sh "$KIT/install.sh" --tidy --json > "$orphan_tmp/tidy.json" || exit 1
    $PY -c 'import json,sys; assert isinstance(json.load(open(sys.argv[1])), list)' "$orphan_tmp/tidy.json" || exit 1
    HOME="$orphan_tmp" sh "$KIT/install.sh" --check > "$orphan_tmp/doctor.txt" 2>&1 || exit 1
    grep -Eq 'OK:   no orphaned MCP processes|WARN: [0-9]+ orphaned MCP processes' "$orphan_tmp/doctor.txt" || exit 1
    echo "PASS: MCP --tidy dispatches JSON dry run; --check reports orphans"
    case "$(uname -s)" in
      MINGW*|MSYS*|CYGWIN*) $PY "$KIT/test/mcp_orphans_cases.py" --live "$orphan_tmp" || exit 1 ;;
      *) echo "PASS: MCP Windows orphan lifecycle (non-Windows; skipped)" ;;
    esac
  ) || bad "MCP installer or Windows orphan lifecycle"
fi

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

# ---------- recommended tools list: refreshed by --setup, never re-adds what the user dismissed ----------
# The list is seeded once and then the user's, but a list that never learns about new upstream items goes
# stale (the machine this was found on still named the Playwright MCP the kit had retired). --setup, which
# --update runs, merges upstream items by id: new ones in, changed ones replaced, and an item the user
# removed or dismissed stays gone. Entries without an id are the user's own and are never touched.
echo "== recommended tools refresh =="
if [ -n "$PY" ]; then
  g=$(mktemp -d) || exit 2
  wq() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }
  G=$(wq "$g")
  su() { src=0; o=$(HOME="$g" USERPROFILE="$G" AGENT_KIT_APPLY=1 sh "$KIT/install.sh" --setup </dev/null 2>&1) || src=$?; }
  rj() { $PY -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print($1)" "$G/.the-agent-kit/recommended.json" 2>/dev/null; }
  RL="$g/.the-agent-kit/recommended.json"
  mkdir -p "$g/.the-agent-kit"
  # R1: a list from before ids existed (the stale one). Entries are matched by name; a retired name is
  # replaced; originals the user had deleted stay deleted; items added to the kit since are offered.
  cat > "$RL" <<'EOF'
{"items":[
 {"name":"Context7 MCP (library docs)","when":"always","claude":{"mcp":"context7","install":"old command"}},
 {"name":"Playwright MCP (drive the UI in a real browser)","when":"web","claude":{"mcp":"playwright","install":"claude mcp add playwright"}},
 {"name":"my own tool","when":"always","claude":{"mcp":"mine","install":"x"}}
]}
EOF
  su
  [ "$(rj "[i for i in d['items'] if i.get('id')=='context7'][0]['codex']['mcp']")" = context7 ] \
    && [ "$(rj "'old command' in open(sys.argv[1],encoding='utf-8').read()")" = False ] \
    && pass "R1 a changed upstream entry is replaced (Context7 gained its Codex and Antigravity keys)" || bad "R1 stale entry not refreshed: $o"
  [ "$(rj "any(i.get('claude',{}).get('mcp')=='playwright' for i in d['items'])")" = False ] \
    && [ "$(rj "any(i.get('id')=='playwright-cli' for i in d['items'])")" = True ] \
    && pass "R1 the retired Playwright MCP entry is replaced by the Playwright CLI one" || bad "R1 retired entry still listed"
  [ "$(rj "any(i.get('name')=='my own tool' for i in d['items'])")" = True ] \
    && pass "R1 the user's own entry is kept" || bad "R1 the user's own entry was lost"
  [ "$(rj "any(i.get('id') in ('chrome-devtools','impeccable','frontend-design') for i in d['items'])")" = False ] \
    && [ "$(rj "sorted(d['dismissed'])")" = "['chrome-devtools', 'frontend-design', 'impeccable']" ] \
    && pass "R1 originals the user had deleted stay deleted (recorded as dismissed)" || bad "R1 a deleted original came back: $(rj "[i.get('id') for i in d['items']]")"
  [ "$(rj "sorted(i['id'] for i in d['items'] if i.get('optional'))")" = "['headroom', 'ponytail', 'superpowers']" ] \
    && pass "R1 items added to the kit since are offered, flagged optional" || bad "R1 new upstream items not added"
  cp "$RL" "$g/after1.json"; su
  cmp -s "$RL" "$g/after1.json" && pass "R2 a second --setup leaves the list byte-identical" || bad "R2 re-run rewrote the list"
  # R3: from here the list carries its own record of what was offered. A removed item is dismissed,
  # an explicitly dismissed one never returns, and an item the list never saw is added.
  $PY - "$G/.the-agent-kit/recommended.json" <<'EOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p, encoding="utf-8"))
d["items"] = [i for i in d["items"] if i.get("id") not in ("ponytail", "superpowers", "headroom")]
d["seeded"] = [s for s in d["seeded"] if s != "superpowers"]
d["dismissed"].append("headroom")
json.dump(d, open(p, "w", encoding="utf-8"))
EOF
  su
  [ "$(rj "[i['id'] for i in d['items'] if i.get('id') in ('ponytail','superpowers','headroom')]")" = "['superpowers']" ] \
    && [ "$(rj "'ponytail' in d['dismissed'] and 'headroom' in d['dismissed']")" = True ] \
    && pass "R3 removed and dismissed items stay gone; an item the list never saw is added" || bad "R3 wrong merge: $(rj "[i.get('id') for i in d['items']]") dismissed=$(rj "d['dismissed']")"
  # R3b: an item the kit offered and has since retired goes; one of the user's own with an id of its own stays.
  $PY - "$G/.the-agent-kit/recommended.json" <<'EOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p, encoding="utf-8"))
d["items"] += [{"id": "old-thing", "name": "retired", "when": "always", "claude": {"mcp": "x", "install": "y"}},
               {"id": "mine-1", "name": "kept", "when": "always", "claude": {"mcp": "z", "install": "y"}}]
d["seeded"].append("old-thing")
json.dump(d, open(p, "w", encoding="utf-8"))
EOF
  su
  [ "$(rj "[i['id'] for i in d['items'] if i.get('id') in ('old-thing','mine-1')]")" = "['mine-1']" ] && has 'retired' "$o" \
    && ls "$g/.the-agent-kit/"recommended.json.bak-agent-kit-* >/dev/null 2>&1 \
    && pass "R3b a retired kit item is dropped, the user's own id kept, a backup left, and the run says what changed" || bad "R3b retired item handling wrong: $o"
  # R4: a list that cannot be parsed is left exactly as it is, and the run says so.
  printf '{ not json' > "$RL"
  su
  [ "$(cat "$RL")" = '{ not json' ] && has 'recommended.json' "$o" \
    && pass "R4 an unreadable list is left untouched and named" || bad "R4 unreadable list handled wrongly: $o"
  # R5: no list yet -> seeded from the kit, with the record the next merge needs.
  rm -f "$RL"; su
  [ "$(rj "len(d['items'])")" = 8 ] && [ "$(rj "sorted(d['seeded']) == sorted(i['id'] for i in d['items'])")" = True ] \
    && [ "$(rj "d['dismissed']")" = "[]" ] \
    && pass "R5 a fresh machine is seeded with every item and the record of them" || bad "R5 fresh seed wrong: $(cat "$RL" 2>/dev/null | head -c 200)"
  rm -rf "$g"
else
  bad "no python - the recommended list refresh NOT tested"
fi

# ---------- machine-wide skills: one real copy, linked into the other tools ----------
# The kit's four skills are installed once per machine: a real copy in ~/.agents/skills (Codex reads it),
# one directory link per skill in ~/.claude/skills (a junction on Windows, which needs no admin; a symlink
# elsewhere), and a skills.json entry for Antigravity. The installer creates and removes only what it
# owns: a folder of the user's with the same name is left alone and reported. Everything runs in a temp HOME.
echo "== machine-wide skills =="
if [ -n "$PY" ]; then
  wq() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }
  SK=$(ls "$KIT/claude/skills" | tr '\n' ' ')
  nsk=$(ls "$KIT/claude/skills" | wc -l | tr -d ' ')
  home_() { g=$(mktemp -d) || exit 2; G=$(wq "$g"); mkdir -p "$g/.claude" "$g/.gemini/config"; }
  su() {  # $1 = AGENT_KIT_APPLY ("" = no consent), $2 = link kind override ("" = platform default)
    src=0; o=$(env HOME="$g" USERPROFILE="$G" AGENT_KIT_APPLY="$1" AGENT_KIT_LINK_KIND="${2:-}" sh "$KIT/install.sh" --setup </dev/null 2>&1) || src=$?; }
  undo_() { src=0; o=$(env HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --undo </dev/null 2>&1) || src=$?; }
  lnk() {  # $1 = path -> "link ok" when it is a symlink or junction resolving to the same-named folder in ~/.agents/skills
    $PY - "$(wq "$1")" <<'EOF'
import os, sys
p = sys.argv[1]
st = os.lstat(p)
j = bool(getattr(st, "st_file_attributes", 0) & 0x400)
rp = os.path.realpath(p).replace("\\", "/").lower()
print("link" if (os.path.islink(p) or j) else "plain", "ok" if rp.endswith("/.agents/skills/" + os.path.basename(p).lower()) else "elsewhere")
EOF
  }
  sj_() { $PY -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print($2)" "$(wq "$1")" 2>/dev/null; }
  # W1-W3: a fresh machine with all three tools: copy, links, skills.json; a second run changes nothing.
  home_
  su ""
  [ ! -e "$g/.agents" ] && [ ! -e "$g/.gemini/config/skills.json" ] && has 'AGENT_KIT_APPLY' "$o" \
    && pass "W0 no consent: no skill copy, link or skills.json is written" || bad "W0 wrote skills without consent: $o"
  su 1
  m=""; for n in $SK; do [ -f "$g/.agents/skills/$n/SKILL.md" ] && [ "$(lnk "$g/.agents/skills/$n")" = "plain ok" ] || m="$m $n"; done
  [ -z "$m" ] && pass "W1 ~/.agents/skills holds one real copy of each of the $nsk kit skills (Codex reads it)" || bad "W1 canonical copies missing or linked:$m: $o"
  m=""; for n in $SK; do [ "$(lnk "$g/.claude/skills/$n")" = "link ok" ] && [ -f "$g/.claude/skills/$n/SKILL.md" ] || m="$m $n"; done
  [ -z "$m" ] && pass "W2 ~/.claude/skills/<name> is a directory link to the one copy, and the skill reads through it" || bad "W2 links wrong:$m: $o"
  [ "$(sj_ "$g/.gemini/config/skills.json" "d['entries'][0]['path']")" = '~/.agents/skills' ] \
    && [ "$(sj_ "$g/.gemini/config/skills.json" "sorted(d['entries'][0]['include_only']) == sorted('$SK'.split())")" = True ] \
    && pass "W3 skills.json points Antigravity at ~/.agents/skills, limited to the kit's skills" || bad "W3 skills.json wrong: $(cat "$g/.gemini/config/skills.json" 2>/dev/null)"
  cp "$g/.gemini/config/skills.json" "$g/sj.before"; before=$(ls -R "$g/.agents" "$g/.claude" "$g/.gemini" | md5sum); su 1
  [ "$(ls -R "$g/.agents" "$g/.claude" "$g/.gemini" | md5sum)" = "$before" ] && cmp -s "$g/.gemini/config/skills.json" "$g/sj.before" \
    && pass "W4 a second --setup changes nothing (no new file, backup or rewrite)" || bad "W4 re-run not idempotent: $o"
  # W5: the canonical copy is kit-owned: a drifted file is restored, and a link keeps working through it.
  printf 'drifted\n' > "$g/.agents/skills/tidy/SKILL.md"; su 1
  cmp -s "$g/.agents/skills/tidy/SKILL.md" "$KIT/claude/skills/tidy/SKILL.md" && [ "$(lnk "$g/.claude/skills/tidy")" = "link ok" ] \
    && pass "W5 a drifted kit copy is refreshed and its link still resolves" || bad "W5 drifted copy not refreshed: $o"
  # W6: undo removes what the installer made and nothing else.
  mkdir -p "$g/.agents/skills/mine" "$g/.claude/skills/theirs"; printf 'x\n' > "$g/.agents/skills/mine/SKILL.md"; printf 'y\n' > "$g/.claude/skills/theirs/SKILL.md"
  $PY - "$(wq "$g/.gemini/config/skills.json")" <<'EOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p, encoding="utf-8")); d["entries"].insert(0, {"path": "~/my-skills"})
json.dump(d, open(p, "w", encoding="utf-8"))
EOF
  undo_
  m=""; for n in $SK; do [ -e "$g/.claude/skills/$n" ] || [ -L "$g/.claude/skills/$n" ] || [ -e "$g/.agents/skills/$n" ] && m="$m $n"; done
  [ -z "$m" ] && [ -f "$g/.agents/skills/mine/SKILL.md" ] && [ -f "$g/.claude/skills/theirs/SKILL.md" ] \
    && [ "$(sj_ "$g/.gemini/config/skills.json" "[e['path'] for e in d['entries']]")" = "['~/my-skills']" ] \
    && pass "W6 --undo removes the kit's links, copies and skills.json entry, and leaves the user's own skills and entries" || bad "W6 undo wrong (left:$m): $o"
  rm -rf "$g"
  # W7-W9: what the installer does not own it does not touch, and it says so.
  home_
  mkdir -p "$g/.claude/skills/tidy" "$g/.agents/skills/writing-docs" "$g/elsewhere"
  printf 'mine\n' > "$g/.claude/skills/tidy/SKILL.md"; printf 'mine\n' > "$g/.agents/skills/writing-docs/SKILL.md"
  $PY - "$(wq "$g")" <<'EOF'
import os, subprocess, sys
g = sys.argv[1]
target = os.path.join(g, "elsewhere"); link = os.path.join(g, ".claude", "skills", "orchestrating-work")
if os.name == "nt":
    subprocess.run(["cmd", "/c", "mklink", "/J", os.path.normpath(link), os.path.normpath(target)], check=True, capture_output=True)
else:
    os.symlink(target, link)
EOF
  su 1
  [ "$(cat "$g/.claude/skills/tidy/SKILL.md")" = mine ] && [ "$(lnk "$g/.claude/skills/tidy")" = "plain elsewhere" ] && has 'tidy' "$(printf '%s' "$o" | grep -i 'WARN\|!')" \
    && pass "W7 a folder of the user's with a kit skill's name is left alone, with a warning" || bad "W7 user folder touched or not reported: $o"
  [ "$(cat "$g/.agents/skills/writing-docs/SKILL.md")" = mine ] && [ ! -e "$g/.claude/skills/writing-docs" ] \
    && pass "W8 a ~/.agents/skills folder that is not the kit's is left alone, and no link points at it" || bad "W8 foreign canonical folder touched or linked: $o"
  [ "$(lnk "$g/.claude/skills/orchestrating-work")" = "link elsewhere" ] \
    && pass "W9 a link of the user's pointing elsewhere is left alone" || bad "W9 foreign link replaced: $(lnk "$g/.claude/skills/orchestrating-work")"
  undo_
  [ -d "$g/elsewhere" ] && [ "$(lnk "$g/.claude/skills/orchestrating-work")" = "link elsewhere" ] && [ "$(cat "$g/.claude/skills/tidy/SKILL.md")" = mine ] \
    && [ "$(cat "$g/.agents/skills/writing-docs/SKILL.md")" = mine ] \
    && pass "W9b --undo leaves a foreign link, a foreign folder and the foreign target untouched" || bad "W9b undo removed something it does not own: $o"
  rm -rf "$g"
  # W10: an existing skills.json keeps every entry; the kit's entry is added, or extended when the user
  # already has one for ~/.agents/skills; one that exposes the whole folder already covers the kit.
  home_
  printf '{"entries":[{"path":"~/mine"},{"path":"~/.agents/skills","include_only":["other"]}],"inherits":[{"path":"/x/skills.json"}]}\n' > "$g/.gemini/config/skills.json"
  su 1
  [ "$(sj_ "$g/.gemini/config/skills.json" "d['entries'][0]['path'], sorted(d['entries'][1]['include_only']) == sorted('other $SK'.split()), len(d['entries']), d['inherits'][0]['path']")" = "~/mine True 2 /x/skills.json" ] \
    && ls "$g/.gemini/config/"skills.json.bak-agent-kit-* >/dev/null 2>&1 \
    && pass "W10 an existing skills.json keeps its entries and inherits; the user's own entry is extended; a backup is left" || bad "W10 skills.json merge wrong: $(cat "$g/.gemini/config/skills.json")"
  printf '{"entries":[{"path":"~/.agents/skills"}]}\n' > "$g/.gemini/config/skills.json"; cp "$g/.gemini/config/skills.json" "$g/sj.before"; su 1
  cmp -s "$g/.gemini/config/skills.json" "$g/sj.before" && pass "W10b an entry that already exposes all of ~/.agents/skills is left as it is" || bad "W10b whole-folder entry rewritten"
  printf '{ not json' > "$g/.gemini/config/skills.json"; su 1
  [ "$(cat "$g/.gemini/config/skills.json")" = '{ not json' ] && has 'skills.json' "$(printf '%s' "$o" | grep -i 'WARN\|!')" \
    && pass "W10c an unreadable skills.json is left untouched and named" || bad "W10c unreadable skills.json handled wrongly: $o"
  rm -rf "$g"
  # W11: a tool that is not installed is not set up: no ~/.claude or ~/.gemini is created for it, while
  # the one real copy still lands where Codex reads it.
  g=$(mktemp -d) || exit 2; G=$(wq "$g")
  su 1
  [ -f "$g/.agents/skills/tidy/SKILL.md" ] && [ ! -e "$g/.claude" ] && [ ! -e "$g/.gemini" ] \
    && pass "W11 without Claude Code or Antigravity on the machine, only the ~/.agents/skills copy is made" || bad "W11 created folders for absent tools: $(ls -A "$g")"
  rm -rf "$g"
  # W12: the symlink path (POSIX default; forced here so Windows exercises it too when it may make symlinks).
  home_
  su 1 symlink
  if [ "$(lnk "$g/.claude/skills/tidy")" = "link ok" ]; then
    $PY -c "import os,sys; sys.exit(0 if os.path.islink(sys.argv[1]) else 1)" "$(wq "$g/.claude/skills/tidy")" \
      && pass "W12 the symlink path makes real symlinks that resolve to the one copy" || bad "W12 AGENT_KIT_LINK_KIND=symlink did not make a symlink"
    undo_
    [ ! -e "$g/.claude/skills/tidy" ] && [ ! -L "$g/.claude/skills/tidy" ] && [ ! -e "$g/.agents/skills/tidy" ] \
      && pass "W12b --undo removes symlinks it made" || bad "W12b symlink not removed: $o"
  else
    case "$o" in *WARN*|*'!'*) pass "W12 (this platform may not create symlinks; the failure was reported, not hidden)" ;; *) bad "W12 symlink creation failed silently: $o" ;; esac
  fi
  rm -rf "$g"
  # W13: the doctor says when the machine-wide skills are not in place, and stops once they are.
  home_
  mkdir -p "$g/.the-agent-kit"; cp -r "$KIT/claude/skills" "$g/.the-agent-kit/skills"
  d=$(cd "$g" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1)
  has 'machine-wide skills.*install.sh --setup' "$d" && pass "W13 --check notes the kit's skills are not installed machine-wide" || bad "W13 --check silent about missing machine-wide skills"
  su 1; d=$(cd "$g" && HOME="$g" USERPROFILE="$G" sh "$KIT/install.sh" --check 2>&1)
  has 'machine-wide skills' "$d" && bad "W13 --check still notes it after setup" || pass "W13 --check is quiet once they are in place"
  rm -rf "$g"
else
  bad "no python - machine-wide skills NOT tested"
fi

# H1-H5: the eval harness's own oracles. Both were silently wrong until 2026-09-27: provider errors
# scored as ordinary FAILs, and a red-then-fix run scored as "edited before any failing test".
# The functions are lifted out of run.sh so the checks run offline, with no agent and no tokens.
(
  eval "$(sed -n '/^events_error() {/,/^}/p;/^trace_check() {/,/^}/p;/^ag_field() {/,/^}/p;/^agy_turn() {/,/^}/p' "$KIT/test/adherence/run.sh")"
  hf="$KIT/test/adherence/harness-fixtures"; spec='red-before-edit: (node --test|npm test)'
  case "$(events_error "$hf/codex-usage-limit.jsonl" codex)" in *"usage limit"*) pass "H1 codex usage limit read as a provider error" ;; *) bad "H1 codex usage limit NOT detected" ;; esac
  case "$(events_error "$hf/claude-session-limit.jsonl" claude)" in *"session limit"*) pass "H2 claude session limit read as a provider error" ;; *) bad "H2 claude session limit NOT detected" ;; esac
  case "$(trace_check "$hf/claude-red-then-edit.jsonl" claude "$spec")" in OK*) pass "H3 red run then source edit passes the trace" ;; *) bad "H3 red-then-edit FAILED the trace" ;; esac
  case "$(trace_check "$hf/claude-edit-after-green.jsonl" claude "$spec")" in FAIL*) pass "H4 edit after a green run ('# fail 0') fails the trace" ;; *) bad "H4 edit after a green run PASSED the trace" ;; esac
  case "$(trace_check "$hf/codex-piped-red.jsonl" codex "$spec")" in OK*) pass "H5 codex piped red run (exit 0) is read as red" ;; *) bad "H5 codex piped red run read as green" ;; esac
  # H6-H10: the Antigravity arm reads agy's stream-json, which carries no exit codes.
  ag="$hf/antigravity-edit-after-green.jsonl"
  case "$(trace_check "$ag" antigravity "$spec")" in FAIL*money.js*) pass "H6 antigravity edit after a green run fails the trace" ;; *) bad "H6 antigravity edit after a green run PASSED the trace" ;; esac
  case "$(trace_check "$hf/antigravity-red-then-edit.jsonl" antigravity "$spec")" in OK) pass "H7 antigravity piped red run then source edit passes the trace" ;; *) bad "H7 antigravity red-then-edit FAILED the trace" ;; esac
  m=$(ag_field "$ag" messages)
  if [ -z "$(events_error "$ag" antigravity)" ] && has 'run_command] rm -rf build -> ERROR: tool call denied by pre-tool hook' "$m" && has '^Fixed rounding in lib/money.js. The rm' "$m"; then
    pass "H8 antigravity denied tool call reaches the judge transcript and is not a provider error"
  else bad "H8 antigravity transcript or provider-error read wrong: $(events_error "$ag" antigravity) / $m"; fi
  u=$(ag_field "$ag" usage | tr '\t' ',')
  [ "$u" = "1,4,1,51234,812,40100,," ] && pass "H9 antigravity usage: turns, tool calls, edits, tokens in/out, cache read" || bad "H9 antigravity usage read as '$u'"
  [ "$(ag_field "$ag" thread)" = "0b7e5c1a-4f2d-4a8e-9c3b-2d1f6e8a9b10" ] && pass "H10 antigravity conversation id read for resuming later turns" || bad "H10 antigravity conversation id not read"
  # H11: agy can keep running after its final result event (seen live: a finished cell sat out the whole
  # 600 s budget and was scored TIMEOUT). The turn must end when the result arrives, and a genuinely
  # hung agy that never prints one must still be cut at the budget with the timeout's own exit code.
  fb=$(mktemp -d); mkdir "$fb/bin" "$fb/w"
  printf '#!/bin/sh\nprintf "%%s\\n" '"'"'{"event":"init","conversation_id":"c1"}'"'"' '"'"'{"event":"result","result":{"status":"SUCCESS","response":"done"}}'"'"'\nsleep 60\n' > "$fb/bin/agy"
  printf '#!/bin/sh\nsleep 60\n' > "$fb/bin/agy-hang"
  chmod +x "$fb/bin/agy" "$fb/bin/agy-hang"
  t0=$(date +%s); ( PATH="$fb/bin:$PATH"; TIMEOUT=40; mflag=""; eflag=""; cflag=""; err="$fb/err"; : > "$err"; : > "$fb/pf"
      agy_turn "$fb/w" "$fb/pf" "$fb/ev"; echo "$?" > "$fb/rc" ); t1=$(date +%s)
  [ "$(cat "$fb/rc")" = 0 ] && [ $((t1 - t0)) -lt 25 ] && grep -q '"event":"result"' "$fb/ev" \
    && pass "H11 an agy that lingers after its result is ended at once (took $((t1 - t0)) s), exit 0" \
    || bad "H11 a lingering agy was not ended promptly (rc=$(cat "$fb/rc" 2>/dev/null), $((t1 - t0)) s)"
  cp "$fb/bin/agy-hang" "$fb/bin/agy"
  t0=$(date +%s); ( PATH="$fb/bin:$PATH"; TIMEOUT=6; mflag=""; eflag=""; cflag=""; err="$fb/err"; : > "$fb/ev"
      agy_turn "$fb/w" "$fb/pf" "$fb/ev"; echo "$?" > "$fb/rc" ); t1=$(date +%s)
  [ "$(cat "$fb/rc")" = 124 ] && [ $((t1 - t0)) -lt 20 ] \
    && pass "H12 an agy that never answers is cut at the budget with the timeout exit code" \
    || bad "H12 a hung agy was not cut at the budget (rc=$(cat "$fb/rc" 2>/dev/null), $((t1 - t0)) s)"
  rm -rf "$fb"
  # H13: a case's cleanup.sh runs from scrub, in the sandbox, before the folder is removed; a failing one
  # neither aborts the cell nor stops the removal. Case 41 starts a real server, so this must hold.
  eval "$(sed -n '/^scrub() {/,/^}/p' "$KIT/test/adherence/run.sh")"
  cb=$(mktemp -d); mkdir "$cb/case" "$cb/w"
  printf 'pwd > "%s/ran"\nexit 1\n' "$cb" > "$cb/case/cleanup.sh"
  cdir="$cb/case"; KEEP=0; scrub "$cb/w"; src=$?
  [ -s "$cb/ran" ] && [ ! -d "$cb/w" ] && [ "$src" -eq 0 ] \
    && pass "H13 case cleanup.sh runs before the sandbox is removed, and its failure is ignored" \
    || bad "H13 cleanup.sh not run, or its failure broke scrub (rc=$src)"
  rm -rf "$cb"
  # H15: a case may widen the sandbox's command allowlist with an `allow` file (one pattern per line, `#`
  # comments), so a case about ports and processes can look at them. No file, no change.
  eval "$(sed -n '/^case_allow() {/,/^}/p' "$KIT/test/adherence/run.sh")"
  ca=$(mktemp -d); printf '# diagnostics only\nBash(netstat:*)\n\nBash(taskkill /PID:*)\n' > "$ca/allow"; mkdir "$ca/none"
  [ "$(case_allow "$ca")" = "Bash(netstat:*),Bash(taskkill /PID:*)" ] && [ -z "$(case_allow "$ca/none")" ] \
    && pass "H15 a case's allow file extends the allowlist; a case without one adds nothing" \
    || bad "H15 case_allow wrong: [$(case_allow "$ca")] / [$(case_allow "$ca/none")]"
  rm -rf "$ca"
  # H14: case 41's cleanup.sh must only remove the fixture's own server (a `node server.js`), never another
  # program that happens to listen in its port range, such as a developer's real service.
  if command -v node >/dev/null 2>&1; then
    cb=$(mktemp -d); bp=38421
    printf 'const s=require("http").createServer((q,r)=>r.end("bystander")); s.listen(%s,"127.0.0.1",()=>require("fs").writeFileSync(process.argv[2],String(process.pid))); setInterval(()=>{},1000);\n' "$bp" > "$cb/by.js"
    node "$cb/by.js" "$cb/by.pid" >/dev/null 2>&1 &
    n=0; while [ ! -s "$cb/by.pid" ] && [ $n -lt 50 ]; do sleep 0.2; n=$((n+1)); done
    sh "$KIT/test/adherence/cases/41-no-duplicate-servers/cleanup.sh" >/dev/null 2>&1
    sleep 1
    if node -e 'require("http").get({host:"127.0.0.1",port:+process.argv[1]},r=>{process.exit(0)}).on("error",()=>process.exit(1))' "$bp" 2>/dev/null; then
      pass "H14 case 41 cleanup leaves another program in its port range alone"
    else
      bad "H14 case 41 cleanup killed a bystander server on port $bp"
    fi
    bpid=$(cat "$cb/by.pid" 2>/dev/null); [ -n "$bpid" ] && { taskkill //F //PID "$bpid" >/dev/null 2>&1 || kill "$bpid" 2>/dev/null; }
    rm -rf "$cb"
  fi
) | tee "$w.h"; grep -q '^FAIL' "$w.h" 2>/dev/null && fail=1; rm -f "$w.h"

# H16-H23: the speed measurement. A true vanilla Claude arm (its own config folder), the duration columns,
# the last turn's telemetry, a rotating arm order and the panel file. Canned events only; no agent runs.
(
  eval "$(sed -n '/^claude_field() {/,/^}/p;/^record_row() {/,/^}/p;/^rotate_arms() {/,/^}/p;/^vanilla_check() {/,/^}/p;/^vanilla_reset() {/,/^}/p;/^vanilla_lock() {/,/^}/p;/^panel_ids() {/,/^}/p' "$KIT/test/adherence/run.sh")"
  hf="$KIT/test/adherence/harness-fixtures"
  u=$(claude_field "$hf/claude-vanilla-probe.jsonl" usage | tr '\t' ',')
  [ "$u" = "1,0,0,2,4,18182,6982,0.0316084,2883,2779,2858" ] \
    && pass "H16 claude usage: the usual eight columns, then duration_ms, duration_api_ms, ttft_ms" || bad "H16 claude usage read as '$u'"
  u=$(claude_field "$hf/claude-vanilla-probe.jsonl" usage "$hf/claude-resumed-turn2.jsonl" "$hf/no-such-turn.jsonl" | tr '\t' ',')
  [ "$u" = "3,1,1,6,210,52000,7300,0.0612,9120,8004,1900" ] \
    && pass "H17 a resumed case reads the LAST turn's result; tool calls and edits add up over every turn" || bad "H17 multi-turn usage read as '$u'"
  rb=$(mktemp -d); TSV="$rb/r.tsv"; TOOL=claude; MODEL=sonnet; EFFORT=medium; JUDGE=opus
  record_row 02-x vanilla 1 PASS 40 0 "$(printf '1\t2\t3\t4\t5\t6\t7\t8\t2883\t2779\t2858')" none
  TOOL=codex; record_row 02-x with 1 PASS 40 0 "$(printf '1\t2\t3\t4\t5\t6\t7\t8')" t1
  [ "$(awk -F'\t' '{print NF}' "$TSV" | sort -u)" = 22 ] \
    && [ "$(awk -F'\t' 'NR==1{print $19 "|" $20 "|" $21 "|" $22}' "$TSV")" = "none|2883|2779|2858" ] \
    && [ "$(awk -F'\t' 'NR==2{print $19 "|" $20 $21 $22}' "$TSV")" = "t1|" ] \
    && pass "H18 a TSV row ends with the three duration columns, empty for tools that report none" || bad "H18 record_row wrote: $(cat "$TSV")"
  rm -rf "$rb"
  [ "$(rotate_arms with,current,vanilla 1)|$(rotate_arms with,current,vanilla 2)|$(rotate_arms with,current,vanilla 3)|$(rotate_arms with,current,vanilla 4)|$(rotate_arms with,without 2)" \
    = "with current vanilla|current vanilla with|vanilla with current|with current vanilla|without with" ] \
    && pass "H19 the arm order rotates by run number and wraps" || bad "H19 rotate_arms wrong"
  vb=$(mktemp -d); vd="$vb/a dir/.claude-vanilla"; mkdir -p "$vd"
  m=$(vanilla_check "$vb/missing"); r1=$?
  m2=$(vanilla_check "$vd"); r2=$?
  printf '{}' > "$vd/.credentials.json"
  printf '{"disableClaudeAiConnectors":true,"syncClaudeAiSkills":false}' > "$vd/settings.json"
  m3=$(vanilla_check "$vd"); r3=$?
  printf '{"disableClaudeAiConnectors":true,"syncClaudeAiSkills":true,"syncClaudeAiPlugins":false}' > "$vd/settings.json"
  m4=$(vanilla_check "$vd"); r4=$?
  printf '{"disableClaudeAiConnectors":true,"syncClaudeAiSkills":false,"syncClaudeAiPlugins":false}' > "$vd/settings.json"
  before=$(find "$vd" | sort); m5=$(vanilla_check "$vd"); r5=$?; after=$(find "$vd" | sort)
  [ "$r1" -ne 0 ] && has 'AGENT_KIT_VANILLA_DIR' "$m" && [ "$r2" -ne 0 ] && has '.credentials.json' "$m2" \
    && [ "$r3" -ne 0 ] && has 'syncClaudeAiPlugins' "$m3" && [ "$r4" -ne 0 ] && has 'syncClaudeAiSkills' "$m4" \
    && [ "$r5" -eq 0 ] && [ -z "$m5" ] && [ "$before" = "$after" ] \
    && pass "H20 the vanilla folder is refused unless it has a login and the three claude.ai sync settings off; nothing is created" \
    || bad "H20 vanilla_check wrong: [$r1 $r2 $r3 $r4 $r5] $m / $m2 / $m3 / $m4 / $m5"
  mkdir -p "$vd/projects/p" "$vd/sessions" "$vd/plugins"; : > "$vd/history.jsonl"; : > "$vd/.claude.json"
  vanilla_reset "$vd"
  [ ! -e "$vd/projects" ] && [ ! -e "$vd/sessions" ] && [ ! -e "$vd/history.jsonl" ] \
    && [ -f "$vd/.credentials.json" ] && [ -f "$vd/settings.json" ] && [ -f "$vd/.claude.json" ] \
    && pass "H21 between cells projects/, sessions/ and history.jsonl go; the login and settings stay (path with a space)" \
    || bad "H21 vanilla_reset left or removed the wrong things: $(find "$vd" | sort | tr '\n' ' ')"
  vanilla_lock "$vd" >/dev/null 2>&1; l1=$?
  m=$(vanilla_lock "$vd" 2>&1); l2=$?
  rm -rf "$vd/.harness-lock"; mkdir "$vd/.harness-lock"; echo 999999 > "$vd/.harness-lock/pid"
  vanilla_lock "$vd" >/dev/null 2>&1; l3=$?
  [ "$l1" -eq 0 ] && [ "$l2" -ne 0 ] && has 'another' "$m" && [ "$l3" -eq 0 ] \
    && pass "H22 a second run cannot share the vanilla folder; a lock left by a dead run is taken over" \
    || bad "H22 vanilla_lock wrong: $l1 $l2 $l3 $m"
  rm -rf "$vb"
  pc=$(mktemp -d); mkdir "$pc/cases" "$pc/cases/02-a" "$pc/cases/16-b"
  printf '# a comment\n\n02-a  \n  16-b\n# 99-later\n' > "$pc/ok.txt"; printf '02-a\n77-typo\n' > "$pc/bad.txt"
  ids=$(panel_ids "$pc/ok.txt" "$pc/cases" | tr '\n' ','); m=$(panel_ids "$pc/bad.txt" "$pc/cases" 2>&1); rb=$?; panel_ids "$pc/none.txt" "$pc/cases" >/dev/null 2>&1; rn=$?
  [ "$ids" = "02-a,16-b," ] && [ "$rb" -ne 0 ] && has '77-typo' "$m" && [ "$rn" -ne 0 ] \
    && pass "H23 a panel file lists case ids; comments and blanks are skipped; an unknown id or a missing file stops the run" \
    || bad "H23 panel_ids wrong: [$ids] rc $rb/$rn $m"
  rm -rf "$pc"
) | tee "$w.h"; grep -q '^FAIL' "$w.h" 2>/dev/null && fail=1; rm -f "$w.h"

echo "---"
[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "FAILURES PRESENT"
exit "$fail"

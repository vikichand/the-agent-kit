#!/bin/sh
# the-agent-kit installer.
#
#   ./install.sh              per-project (self-contained): full rules (AGENTS.md + a CLAUDE.md that
#                             imports it, so nothing is duplicated) + git hooks in THIS repo
#   ./install.sh --extension  per-project (extends global): project-config stub + git hooks
#   ./install.sh --global     machine-wide: git hooks via core.hooksPath + printed tool snippets
#   ./install.sh --update     pull the latest kit from GitHub into ~/.the-agent-kit (no clone needed)
#   ./install.sh --update-rules  refresh THIS repo's AGENTS.md to the kit's current rules; the
#                             project's PROJECT-CONFIG block is preserved byte-for-byte
#   ./install.sh --check      doctor: verify the interpreter resolves and the guard actually fires
#
# Safe by design: never overwrites an existing CLAUDE.md / AGENTS.md / git hook, and never blindly
# rewrites your tool config - it prints snippets to merge. The tool-layer guard is NOT active until
# you merge those snippets; run --check to confirm what is actually live.
set -eu

KIT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MODE="${1:-project}"
# Where --update pulls from. Overridable so a fork (or the test suite) can point elsewhere.
KIT_REPO="${AGENT_KIT_REPO:-https://github.com/vikichand/the-agent-kit.git}"

say() { printf '%s\n' "$*"; }
hr()  { printf '%s\n' "------------------------------------------------------------"; }

detect_py() {  # print the first interpreter that ACTUALLY runs Python 3 (rejects the Windows Store stub); else empty
  # Probe order is by measured startup cost, because this runs on EVERY Bash call via the PreToolUse
  # hook and the cost is paid thousands of times a session. On Windows `python3` is usually the
  # WindowsApps alias and is the slowest of the three; the `py -3` launcher is markedly faster.
  # Measured on one Windows 11 box: py -3 = 140 ms/call, python3 = 237 ms/call.
  # On Linux `py` simply does not exist and the loop falls through to `python3` as before.
  # The probe reads the MAJOR VERSION rather than just "does it run", so a legacy `python` that is
  # Python 2 is rejected instead of being selected and then crashing the guard at runtime.
  for p in "python" "py -3" "python3"; do
    if [ "$(printf 'import sys;print(sys.version_info[0])' | $p - 2>/dev/null)" = "3" ]; then
      printf '%s' "$p"; return 0
    fi
  done
  printf ''
}

subst() {  # $1=kit share path  $2=python  $3=template -> stdout with __AGENT_KIT__/__PY__ filled
  awk -v kit="$1" -v py="$2" '
    BEGIN{ gsub(/[\\&]/,"\\\\&",kit); gsub(/[\\&]/,"\\\\&",py) }
    { gsub(/__AGENT_KIT__/,kit); gsub(/__PY__/,py); print }' "$3"
}

git_hooks_dir() {  # $1 = repo root -> absolute hooks dir (worktree/submodule safe) or empty
  d=$( (cd "$1" 2>/dev/null && git rev-parse --git-path hooks 2>/dev/null) ) || d=""
  [ -n "$d" ] || { printf ''; return; }
  case "$d" in /*|[A-Za-z]:*) : ;; *) d="$1/$d" ;; esac
  printf '%s' "$d"
}

install_git_hooks() {  # $1 = repo root
  hd=$(git_hooks_dir "$1")
  [ -n "$hd" ] || { say "  ! not a git repo - skipped the git hooks."; return; }
  mkdir -p "$hd"
  for h in commit-msg pre-commit pre-push; do
    if [ -e "$hd/$h" ]; then
      say "  = $h already exists in $hd - left untouched (Husky / commitlint / a scanner?). Merge by hand."
    else
      cp "$KIT/hooks/$h" "$hd/$h" && chmod +x "$hd/$h"
      say "  + installed git hook: $h"
    fi
  done
}

write_stub() {  # $1 = target file
  cat > "$1" <<'STUB'
<!-- The universal rules live in your global ~/.claude/CLAUDE.md (and ~/.codex/AGENTS.md); both tools
     read global + project files together, so this file EXTENDS them. Keep only project-specific config
     here - do NOT copy the universal rules in (that would double them in context). -->

<!-- PROJECT-CONFIG:START -->
<!-- Run the-agent-kit's docs/project-setup-prompt.md to fill this in (~15-30 lines, one screen). -->
<!-- PROJECT-CONFIG:END -->
STUB
}

write_claude_importer() {  # $1 = target CLAUDE.md - imports AGENTS.md instead of duplicating it
  cat > "$1" <<'IMP'
<!-- Claude Code reads CLAUDE.md, not AGENTS.md, so this file imports the rules instead of copying them.
     One source of truth, nothing to keep in sync. Put Claude-Code-only notes BELOW the import line. -->
@AGENTS.md
IMP
}

install_path_rules() {  # $1 = repo root. Path-scoped rules: the deep tier, free until a path matches.
  # These load ONLY when the agent opens a file matching their `paths:` globs. Measured on a 53 KiB
  # rule: 65,347 tokens of context with it present and not matching, versus 65,510 with no rule file
  # at all - i.e. free. The same file costs its full size the moment a path matches, which is the
  # point. `paths:` is read by Claude Code, VS Code Copilot and Cline; other tools ignore the folder
  # and still get the full universal floor from AGENTS.md.
  # Two possible homes: claude/rules in the repo, rules/ in the relocated ~/.the-agent-kit copy.
  src=""
  [ -d "$KIT/claude/rules" ] && src="$KIT/claude/rules"
  [ -z "$src" ] && [ -d "$KIT/rules" ] && src="$KIT/rules"
  [ -n "$src" ] || return 0
  mkdir -p "$1/.claude/rules"
  for r in "$src/"*.md; do
    [ -e "$r" ] || continue
    b=$(basename "$r")
    if [ -e "$1/.claude/rules/$b" ]; then
      say "  = .claude/rules/$b already exists - left untouched."
    else
      cp "$r" "$1/.claude/rules/$b"; say "  + wrote .claude/rules/$b (loads only on matching paths)"
    fi
  done
}

install_project() {   # self-contained: full rules + git hooks
  root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  say "Installing FULL rules + git hooks into: $root"
  # AGENTS.md holds the rules (the cross-tool standard: Codex, Cursor, Aider, Copilot...). Claude Code
  # reads CLAUDE.md only, so CLAUDE.md IMPORTS AGENTS.md rather than duplicating it - one source of
  # truth, no drift. (Anthropic's documented pattern; a symlink also works but needs admin on Windows.)
  if [ -e "$root/AGENTS.md" ]; then say "  = AGENTS.md already exists - left untouched."
  else cp "$KIT/AGENTS.md" "$root/AGENTS.md"; say "  + wrote AGENTS.md (full rules + empty project block)"; fi
  if [ -e "$root/CLAUDE.md" ]; then say "  = CLAUDE.md already exists - left untouched."
  else write_claude_importer "$root/CLAUDE.md"; say "  + wrote CLAUDE.md (imports AGENTS.md - single source of truth)"; fi
  install_path_rules "$root"
  install_git_hooks "$root"
  hr
  say "Tool-layer guard is machine-wide - run once:  ./install.sh --global   then:  ./install.sh --check"
}

install_extension() { # lean: project-config stub + git hooks
  root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  say "Installing project EXTENSION into: $root"
  if [ ! -e "$HOME/.claude/CLAUDE.md" ] && [ ! -e "$HOME/.codex/AGENTS.md" ]; then
    say "  ! WARNING: no global rules found (~/.claude/CLAUDE.md or ~/.codex/AGENTS.md). This stub carries NO"
    say "    universal rules - add the global rules first, or use plain './install.sh' for a self-contained file."
  fi
  if [ -e "$root/AGENTS.md" ]; then say "  = AGENTS.md already exists - left untouched."
  else write_stub "$root/AGENTS.md"; say "  + wrote AGENTS.md (project-config stub; extends your global rules)"; fi
  if [ -e "$root/CLAUDE.md" ]; then say "  = CLAUDE.md already exists - left untouched."
  else write_claude_importer "$root/CLAUDE.md"; say "  + wrote CLAUDE.md (imports AGENTS.md)"; fi
  install_path_rules "$root"
  install_git_hooks "$root"
}

install_global() {
  share="$HOME/.the-agent-kit"
  mkdir -p "$share/hooks" "$share/git-hooks" "$share/docs"
  # Copy the WHOLE kit, not just the hooks, so the clone you ran this from becomes disposable.
  # git-hooks/ is the core.hooksPath target (those three only); hooks/ is the full set, which is
  # what the relocated install.sh compares against in --check and copies from per project.
  for h in command-guard.py commit-msg pre-commit pre-push; do cp "$KIT/hooks/$h" "$share/hooks/$h"; done
  for h in commit-msg pre-commit pre-push; do cp "$KIT/hooks/$h" "$share/git-hooks/$h"; done
  cp "$KIT/AGENTS.md" "$KIT/CLAUDE.md" "$KIT/install.sh" "$share/"
  cp "$KIT/docs/"*.md "$share/docs/" 2>/dev/null || true
  mkdir -p "$share/rules"
  cp "$KIT/claude/rules/"*.md "$share/rules/" 2>/dev/null || cp "$KIT/rules/"*.md "$share/rules/" 2>/dev/null || true
  chmod +x "$share/hooks/"* "$share/git-hooks/"* "$share/install.sh"
  # Stamp the source commit so --update can tell "already current" from "a month behind", and show
  # you what actually changed. Absent (or "unknown") when installed from a non-git copy - not fatal.
  ver=$( (cd "$KIT" && git rev-parse --short HEAD 2>/dev/null) || true )
  printf '%s\n' "${ver:-unknown}" > "$share/.kit-version"
  say "Copied the kit to $share (rules + hooks + installer + docs)"
  say "  -> $share is now self-contained: the clone you ran this from can be deleted."

  py=$(detect_py)
  if [ -z "$py" ]; then
    hr; say "  ! WARNING: no working python found - the tool-layer guard will not run. Install Python 3"
    say "    and re-run, or fix the interpreter in the snippet below. ('./install.sh --check' verifies.)"; py="python3"
  fi

  hr
  say "GIT-LAYER HOOKS (every repo, via git core.hooksPath) - commit-msg + pre-commit + pre-push"
  existing=$(git config --global --get core.hooksPath 2>/dev/null || true)
  if [ -n "$existing" ]; then
    say "  core.hooksPath already set to: $existing"
    say "  -> copy $share/git-hooks/* into that dir (keep your own hooks alongside - never overwrite)."
  else
    say "  A global core.hooksPath makes git use ONLY that dir for EVERY repo, SHADOWING any repo's own"
    say "  .git/hooks (Husky, a secret scanner, ...). If you rely on those, prefer the per-project install."
    say "  To enable globally anyway:   git config --global core.hooksPath \"$share/git-hooks\""
  fi

  hr
  say "TOOL GUARD - Claude Code    merge into  ~/.claude/settings.json :"
  subst "$share" "$py" "$KIT/claude/settings.json"
  hr
  say "TOOL GUARD - Codex          merge into  ~/.codex/hooks.json  (+ see codex/config.toml) :"
  subst "$share" "$py" "$KIT/codex/hooks.json"
  hr
  say "CODEX SANDBOX / APPROVAL    merge into  ~/.codex/config.toml :"
  cat "$KIT/codex/config.toml"

  hr
  say "The tool guard is NOT active until you merge the snippet(s) above - then verify:  ./install.sh --check"
  say "Optional global rules (lets projects stay lean via --extension), review the merge first:"
  say "    cat \"$KIT/AGENTS.md\" >> ~/.claude/CLAUDE.md   ;   cat \"$KIT/AGENTS.md\" >> ~/.codex/AGENTS.md"
}

update_kit() {  # refresh ~/.the-agent-kit from GitHub, so the clone stays disposable
  share="$HOME/.the-agent-kit"
  command -v git >/dev/null 2>&1 || { say "  ! git not found - cannot update. Install git, or re-clone by hand."; exit 2; }
  old=$(cat "$share/.kit-version" 2>/dev/null || printf 'unknown')
  tmp=$(mktemp -d) || exit 2
  say "Fetching the latest kit from $KIT_REPO"
  if ! git clone --quiet --depth 50 "$KIT_REPO" "$tmp/kit" 2>/dev/null; then
    rm -rf "$tmp"; say "  ! clone failed (offline, or the repo moved) - NOTHING was changed."; exit 2
  fi
  # Never overwrite a working install from a surprise payload: prove the download is actually the kit
  # before it touches anything. A moved/renamed/hijacked repo fails here instead of half-installing.
  for f in install.sh AGENTS.md hooks/command-guard.py hooks/pre-commit; do
    [ -f "$tmp/kit/$f" ] || { rm -rf "$tmp"; say "  ! downloaded tree has no $f - that is not the kit. NOTHING was changed."; exit 2; }
  done
  new=$( (cd "$tmp/kit" && git rev-parse --short HEAD 2>/dev/null) || printf 'unknown' )
  if [ "$old" = "$new" ] && [ "$old" != "unknown" ]; then
    rm -rf "$tmp"; say "  = already at $new - nothing to update."; return 0
  fi
  say "  $old -> $new"
  # Shallow clones may not reach `old`, so this is best-effort context, never a gate.
  (cd "$tmp/kit" && git log --oneline "$old..$new" 2>/dev/null | sed 's/^/    /') || true
  hr
  # Run the DOWNLOADED installer, not this one: a newer kit can ship files an older installer does
  # not know to copy. It is code from the network, which is why the identity check above runs first.
  #
  # exec, and nothing after it, is load-bearing. You are usually running $share/install.sh, which
  # --global is about to overwrite - and sh reads a script lazily by byte offset, so a shell that
  # kept going here would resume at a stale offset inside the NEW file and execute whatever fragment
  # of a line landed there ("sac: command not found", observed). exec replaces this process, so not
  # one more byte is read from the file being replaced. Keep the tail below inside the handoff.
  exec sh -c '
    sh "$1/install.sh" --global || exit $?
    rm -rf "$2"
    printf "%s\n" "------------------------------------------------------------"
    printf "%s\n" "Machine-wide guards + ~/.the-agent-kit are now current. Then, per project:"
    printf "%s\n" "    ~/.the-agent-kit/install.sh --update-rules     # new rules in, your PROJECT-CONFIG kept"
  ' _ "$tmp/kit" "$tmp"
}

update_rules() {  # refresh the universal rules in this repo's AGENTS.md, preserving its PROJECT-CONFIG block
  root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  tgt="$root/AGENTS.md"
  if [ ! -e "$tgt" ]; then
    say "  ! no AGENTS.md in $root - nothing to update. Run './install.sh' to install the rules first."
    exit 2
  fi
  # An --extension stub carries no universal rules on purpose - they live in the global files.
  if grep -q 'universal rules live in your global' "$tgt" 2>/dev/null; then
    say "  = this AGENTS.md is an --extension stub: the universal rules live in your GLOBAL files"
    say "    (~/.claude/CLAUDE.md / ~/.codex/AGENTS.md) - update those; this file only holds project config."
    exit 0
  fi
  # Fail closed without both markers: there is no way to tell project config from rules, so replace nothing.
  if ! grep -q 'PROJECT-CONFIG:START' "$tgt" 2>/dev/null || ! grep -q 'PROJECT-CONFIG:END' "$tgt" 2>/dev/null; then
    say "  ! $tgt has no PROJECT-CONFIG markers - refusing to guess which part is yours."
    say "    Add the markers (see the kit's AGENTS.md) or update the file by hand."
    exit 2
  fi
  tmp="$tgt.update-rules.tmp"
  # Pass 1 saves the project's block (markers inclusive); pass 2 prints the kit's current rules with
  # the kit's placeholder block swapped for the saved one.
  awk '
    NR==FNR { if (/PROJECT-CONFIG:START/) c=1
              if (c) blk = blk $0 ORS
              if (/PROJECT-CONFIG:END/)  c=0
              next }
    /PROJECT-CONFIG:START/ { skip=1; printf "%s", blk }
    !skip { print }
    /PROJECT-CONFIG:END/   { skip=0 }
  ' "$tgt" "$KIT/AGENTS.md" > "$tmp"
  if [ ! -s "$tmp" ]; then rm -f "$tmp"; say "  ! update produced an empty file - aborted, nothing changed."; exit 2; fi
  if cmp -s "$tmp" "$tgt"; then
    rm -f "$tmp"; say "  = AGENTS.md already carries the current rules - nothing to do."
  else
    mv "$tmp" "$tgt"
    say "  + updated the universal rules in $tgt - your PROJECT-CONFIG block is untouched."
    say "    Anything else hand-edited OUTSIDE the markers was replaced; review:  git diff AGENTS.md"
  fi
}

doctor() {
  hr; say "the-agent-kit --check (doctor)"
  py=$(detect_py)
  if [ -z "$py" ]; then
    say "  FAIL: no working python (python3/python/py). On Windows 'python3' is often a no-op Store stub."
    say "        -> the tool-layer command-guard will NOT run. Install Python 3."
  else
    say "  OK:   python = $py"
    d=$(printf '%s' '{"tool_input":{"command":"git push"}}'         | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$d" in *'"ask"'*)  say "  OK:   command-guard fires on 'git push'" ;; *) say "  FAIL: command-guard emitted no decision for 'git push'" ;; esac
    f=$(printf '%s' '{"tool_input":{"command":"git push --force"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$f" in *'"deny"'*) say "  OK:   force-push is denied" ;; *) say "  FAIL: force-push not denied" ;; esac
    n=$(printf '%s' '{"tool_input":{"command":"git commit -an -m x"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$n" in *'"deny"'*) say "  OK:   bundled --no-verify (git commit -an) is denied" ;; *) say "  FAIL: bundled --no-verify (-an) NOT denied" ;; esac
    h=$(printf '%s' '{"tool_input":{"command":"git -c core.hooksPath=/x commit -m y"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$h" in *'"deny"'*) say "  OK:   -c core.hooksPath override is denied" ;; *) say "  FAIL: -c core.hooksPath NOT denied" ;; esac
    e=$(printf '%s' '{"tool_input":{"command":"nice -n 5 git commit --no-verify -m x"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$e" in *'"deny"'*) say "  OK:   wrapper-composed --no-verify is denied" ;; *) say "  FAIL: wrapper-composed --no-verify NOT denied" ;; esac
    g=$(printf '%s' '{"tool_input":{"command":"printf x >> .git/config"}}' | $py "$KIT/hooks/command-guard.py" --decision deny 2>/dev/null)
    case "$g" in *'"deny"'*) say "  OK:   direct .git/config write is flagged" ;; *) say "  FAIL: direct .git/config write NOT flagged" ;; esac
  fi
  for h in commit-msg pre-commit pre-push; do
    if [ -x "$KIT/hooks/$h" ]; then say "  OK:   hooks/$h present + executable"; else say "  WARN: hooks/$h missing or not executable"; fi
  done
  hd=$(git_hooks_dir "$(pwd)")
  if [ -z "$hd" ]; then
    say "  NOTE: not a git repo - no git-layer hooks to check here."
  else
    hp=$(git config core.hooksPath 2>/dev/null || true)
    if [ -n "$hp" ]; then
      say "  NOTE: core.hooksPath=$hp - git runs hooks from THERE, not .git/hooks (kit --global, Husky, lefthook?)."
    fi
    # Existence is not enough: another tool's hook in that slot means OUR guard is not running.
    # Three distinguishable states, reported separately so you know how strong the evidence is:
    #   byte-identical to the kit's hook -> proven
    #   mentions the kit (Husky/lefthook shim that calls it) -> text match only, eyeball it
    #   neither -> our guard is not running
    for h in commit-msg pre-commit pre-push; do
      if [ ! -e "$hd/$h" ]; then
        say "  NOTE: $h not installed here - run ./install.sh in this repo."
      elif cmp -s "$KIT/hooks/$h" "$hd/$h" 2>/dev/null; then
        say "  OK:   $h live in $hd (kit hook, byte-identical)"
      elif grep -q 'the-agent-kit' "$hd/$h" 2>/dev/null; then
        say "  OK:   $h in $hd calls the kit (shim) - text match only; open it to confirm it still runs."
      else
        say "  FAIL: $hd/$h is NOT the kit's - that guard is INACTIVE. Merge the kit's $h into it."
      fi
    done
  fi
  # Rules files. Both tools enforce a limit SILENTLY: Codex truncates AGENTS.md past
  # project_doc_max_bytes (32 KiB default, no warning); Claude Code loads CLAUDE.md in full but
  # adherence drops past ~200 lines. Block-level HTML comments are stripped before Claude's context,
  # so they cost nothing and are excluded from the line count below.
  if [ -e AGENTS.md ]; then
    ab=$(wc -c < AGENTS.md 2>/dev/null | tr -d ' ' || true)
    case "$ab" in ''|*[!0-9]*) ab=-1 ;; esac
    if [ "$ab" -lt 0 ]; then
      say "  WARN: AGENTS.md exists but could not be read to measure it (permissions? file lock?)."
    elif [ "$ab" -gt 32768 ]; then
      say "  FAIL: AGENTS.md is $ab bytes - Codex SILENTLY truncates past 32768 (project_doc_max_bytes)."
      say "        That cap applies to the COMBINED AGENTS.md chain read root-to-leaf, so nested files count too."
    else
      say "  OK:   AGENTS.md $ab bytes (Codex silently truncates the combined chain past 32768)"
    fi
    # Claude Code docs, Memory > Write effective instructions: "target under 200 lines per CLAUDE.md
    # file. Longer files consume more context and reduce adherence." Block-level HTML comments are
    # stripped before Claude's context, so they are excluded from this count.
    al=$(sed '/<!--/,/-->/d' AGENTS.md 2>/dev/null | grep -c . || true)
    case "$al" in ''|*[!0-9]*) al=-1 ;; esac
    if [ "$al" -lt 0 ]; then
      :
    elif [ "$al" -gt 200 ]; then
      say "  WARN: AGENTS.md is $al effective lines - Claude Code targets under 200; adherence drops past it."
    else
      say "  OK:   AGENTS.md $al effective lines (target: under 200; HTML comments excluded, they cost nothing)"
    fi
    # The single highest-value anti-hallucination content is this project's REAL commands. Shipping the
    # placeholder means the agent guesses how to build, test, and verify - so say so loudly.
    if grep -q 'PROJECT-CONFIG:START' AGENTS.md 2>/dev/null && grep -q 'fill this in' AGENTS.md 2>/dev/null; then
      say "  WARN: PROJECT-CONFIG is still the empty placeholder. Without it the agent GUESSES this project's"
      say "        build / test / lint commands. Fill it via docs/project-setup-prompt.md - biggest win available."
    fi
    # The depth tier. It is invisible by design - it loads only on matching paths - so if it silently
    # failed to install, nothing else would ever say so. The doctor is the only place that can.
    if [ -d .claude/rules ]; then
      rn=$(ls .claude/rules/*.md 2>/dev/null | wc -l | tr -d ' ')
      rbad=0
      for rf in .claude/rules/*.md; do
        [ -e "$rf" ] || continue
        grep -q '^paths:' "$rf" 2>/dev/null || rbad=$((rbad+1))
      done
      if [ "$rn" -eq 0 ]; then
        say "  WARN: .claude/rules exists but holds no rules - the depth tier is not installed here."
      elif [ "$rbad" -gt 0 ]; then
        say "  WARN: $rbad of $rn rules in .claude/rules lack 'paths:' frontmatter - those load on EVERY"
        say "        turn instead of only on matching files, which is the opposite of the intent."
      else
        say "  OK:   $rn path-scoped rules in .claude/rules (load only on matching paths, free otherwise)"
      fi
    else
      say "  NOTE: no .claude/rules here - the deep conditional rules are not installed. Run ./install.sh"
      say "        in this repo to add them (they cost nothing until a matching file is opened)."
    fi
    if [ -e CLAUDE.md ]; then
      if grep -q '@AGENTS.md' CLAUDE.md 2>/dev/null; then
        say "  OK:   CLAUDE.md imports AGENTS.md - one source of truth"
      else
        say "  WARN: CLAUDE.md does not import AGENTS.md - two copies of the rules will drift apart."
      fi
    else
      say "  WARN: no CLAUDE.md - Claude Code does NOT read AGENTS.md. Add a file containing '@AGENTS.md'."
    fi
  fi
  hr
}

USAGE="Usage: ./install.sh [--extension | --global | --update | --update-rules | --check]"
case "$MODE" in
  --global|global)              install_global ;;
  --extension|extension)        install_extension ;;
  --update|update)              update_kit ;;
  --update-rules|update-rules)  update_rules ;;
  --check|check|doctor)         doctor ;;
  ""|project|--project)         install_project ;;
  -h|--help)                    say "$USAGE" ;;
  *) say "Unknown mode: $MODE"; say "$USAGE"; exit 2 ;;
esac

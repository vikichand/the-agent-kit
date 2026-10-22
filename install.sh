#!/bin/sh
# the-agent-kit installer.
#
#   ./install.sh              per-project (self-contained): full rules (AGENTS.md + a CLAUDE.md that
#                             imports it, so nothing is duplicated) + git hooks in THIS repo
#   ./install.sh --extension  per-project (extends global): project-config stub + git hooks
#   ./install.sh --setup      machine-wide, all of it: copy the kit to ~/.the-agent-kit, turn on the git
#                             hooks, add the kit to your Claude Code and Codex settings, and install its
#                             skills once for all three tools and wire Antigravity's session-start check
#                             (asks first)
#   ./install.sh --undo       remove the machine-wide skill links, copies, skills.json names and the
#                             Antigravity check hook it made
#   ./install.sh --global     machine-wide, by hand: copy the kit and PRINT the snippets to merge yourself
#   ./install.sh --update     pull the latest kit from GitHub into ~/.the-agent-kit, then run --setup
#   ./install.sh --update-rules  refresh THIS repo's AGENTS.md to the kit's current rules; the
#                             project's PROJECT-CONFIG block is preserved byte-for-byte
#   ./install.sh --check      doctor: verify the interpreter resolves and the guard actually fires
#   ./install.sh --tidy       list orphaned MCP trees; add --kill to terminate them
#
# Safe by design: never overwrites an existing CLAUDE.md / AGENTS.md / git hook. Your tool settings are
# only ever ADDED to (bar rules the kit itself once added and has retired), after you say yes, with a
# backup first; --global prints them for a hand merge
# instead. Run --check to confirm what is actually live.
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
<!-- Run the setup prompt (~/.the-agent-kit/docs/project-setup-prompt.md) to fill this in (~15-30 lines, one screen). -->
<!-- PROJECT-CONFIG:END -->
STUB
}

write_rules() {  # $1 = target AGENTS.md - the kit's rules with an EMPTY project block
  # Never `cp` AGENTS.md: this repo fills its OWN PROJECT-CONFIG block (branches, gates, careful
  # zones), and copying it verbatim would ship the kit's project config into every project that
  # installs it. The rules above the markers are the floor; what sits between them belongs to the
  # project. --update-rules already swaps the kit's block for the target's, so only a fresh install
  # needed fixing.
  awk '
    /PROJECT-CONFIG:START/ { skip = 1
      print "<!-- PROJECT-CONFIG:START -->"
      print "<!-- Not configured yet. Run the setup prompt (~/.the-agent-kit/docs/project-setup-prompt.md) to fill this in. -->"
      print "<!-- PROJECT-CONFIG:END -->" }
    !skip { print }
    /PROJECT-CONFIG:END/   { skip = 0 }
  ' "$KIT/AGENTS.md" > "$1"
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

install_skills() {  # $1 = repo root. Task-shaped guidance: only the description sits in context.
  # Skills are matched against the TASK, not against file paths, which is why orchestration lives here
  # rather than in .claude/rules (path-triggered) or AGENTS.md (always-on and budget-capped).
  src=""
  [ -d "$KIT/claude/skills" ] && src="$KIT/claude/skills"
  [ -z "$src" ] && [ -d "$KIT/skills" ] && src="$KIT/skills"
  [ -n "$src" ] || return 0
  for sd in "$src"/*/; do
    [ -d "$sd" ] || continue
    b=$(basename "$sd")
    if [ -e "$1/.claude/skills/$b/SKILL.md" ]; then
      say "  = .claude/skills/$b already exists - left untouched."
    else
      mkdir -p "$1/.claude/skills/$b"
      # The whole folder, not just SKILL.md - skills route to reference files (references/design.md)
      # that the body points at, and a skill deployed without them is silently broken.
      cp -r "$sd." "$1/.claude/skills/$b/"
      say "  + wrote .claude/skills/$b (loads when a task matches it)"
    fi
  done
}

codex_skill_desc() {  # $1 = rule basename without .md -> the Codex skill description, or "" if not ported.
  # Codex has no path-scoped rules. It loads a skill when the TASK matches its description, keeping
  # only name + description in context until then, which is the closest thing it has to a rule that
  # costs nothing until it applies. Four of the six depth files are domain-shaped and get an honest
  # trigger below. code-correctness (any source file) and tests (any test file) are path-shaped: the
  # only true description is "use when writing code", which fires always or never, so they are NOT
  # ported - Codex gets their one-line versions from AGENTS.md and nothing more. Routing lives here,
  # in the adapter; the rule text stays single-sourced in claude/rules/.
  case "$1" in
    web-security)     printf '%s' "Use when adding or changing auth, sessions, API routes, middleware, webhooks, payments, uploads, rate limits, CORS, CSRF, security headers, or edge config (nginx, Caddy, vercel.json, wrangler.toml, fly.toml) - the server-side security defaults a senior engineer applies without being asked." ;;
    data-layer)       printf '%s' "Use when writing or changing migrations, models, schema, SQL, or anything that reads or stores data - staged schema changes, N+1 queries and indexes, money and time column types, and keeping personal data out of logs." ;;
    frontend-quality) printf '%s' "Use when building or changing user-facing UI: components, pages, screens, forms - accessibility, internationalisation, loading states, and restraint in visual polish." ;;
    ci-cd)            printf '%s' "Use when editing CI or delivery config: GitHub workflows, Dockerfiles, GitLab CI, Jenkinsfiles, Azure pipelines - pinned actions, least-privilege tokens, untrusted checkouts, secrets in logs, and gates that fail closed." ;;
    *)                printf '' ;;
  esac
}

rule_to_skill() {  # $1 = rule file  $2 = skill name  $3 = description  -> SKILL.md on stdout
  # Swap the `paths:` frontmatter for skill frontmatter; the body is byte-identical to the rule's.
  printf -- '---\nname: %s\ndescription: %s\n---\n' "$2" "$3"
  awk 'NR==1 && $0!="---" {all=1} all {print; next} fm<2 && /^---$/ {fm++; next} fm>=2 {print}' "$1"
}

install_codex_skills() {  # $1 = repo root. Everything Codex can load lazily, in the dir it reads for that.
  # .agents/skills is discovered by Codex from the repo root down (no trust prompt, unlike
  # .codex/skills) and is NOT read by Claude Code, so nothing here double-loads on Claude.
  ssrc=""; [ -d "$KIT/claude/skills" ] && ssrc="$KIT/claude/skills"
  [ -z "$ssrc" ] && [ -d "$KIT/skills" ] && ssrc="$KIT/skills"
  rsrc=""; [ -d "$KIT/claude/rules" ] && rsrc="$KIT/claude/rules"
  [ -z "$rsrc" ] && [ -d "$KIT/rules" ] && rsrc="$KIT/rules"
  [ -n "$ssrc$rsrc" ] || return 0
  if [ -n "$ssrc" ]; then
    for sd in "$ssrc"/*/; do
      [ -d "$sd" ] || continue
      b=$(basename "$sd")
      if [ -e "$1/.agents/skills/$b/SKILL.md" ]; then
        say "  = .agents/skills/$b already exists - left untouched."
      else
        mkdir -p "$1/.agents/skills/$b"
        cp -r "$sd." "$1/.agents/skills/$b/"
        say "  + wrote .agents/skills/$b (Codex and Antigravity: loads when a task matches it)"
      fi
    done
  fi
  skipped=""
  if [ -n "$rsrc" ]; then
    for r in "$rsrc"/*.md; do
      [ -e "$r" ] || continue
      n=$(basename "$r" .md); d=$(codex_skill_desc "$n")
      if [ -z "$d" ]; then skipped="$skipped $n"; continue; fi
      if [ -e "$1/.agents/skills/$n/SKILL.md" ]; then
        say "  = .agents/skills/$n already exists - left untouched."
      else
        mkdir -p "$1/.agents/skills/$n"
        rule_to_skill "$r" "$n" "$d" > "$1/.agents/skills/$n/SKILL.md"
        say "  + wrote .agents/skills/$n (Codex and Antigravity: the $n rule, matched by task instead of by path)"
      fi
    done
  fi
  [ -n "$skipped" ] && say "  = not ported to Codex skills:$skipped - path-shaped (any source / test file), no honest task trigger; Codex has their one-line versions in AGENTS.md."
  return 0
}

rule_to_glob() {  # $1 = rule file -> Antigravity glob rule on stdout: `paths:` list -> one `globs:` string
  awk 'NR==1 && $0=="---" {fm=1; next}
       fm==1 && /^---$/ {printf "---\ntrigger: glob\nglobs: \"%s\"\n---\n", g; fm=2; next}
       fm==1 { if (match($0, /^ *- *"[^"]*"/)) { p=$0; sub(/^ *- *"/, "", p); sub(/".*$/, "", p); g = g (g=="" ? "" : ", ") p }; next }
       {print}' "$1"
}

write_ag_launcher() {  # $1 = target. Antigravity splits a hook command on whitespace and ignores quotes,
  # so a guard path under a home folder with a space breaks the hook, and a broken hook blocks every
  # command. Hooks run from the folder holding hooks.json, so this launcher sits there, is called by
  # bare name, and hands the call to the machine-wide guard.
  cat > "$1" <<'LAUNCH'
# The Agent Kit: launcher for the command guard (see .agents/hooks.json). Kit-owned; --update-rules
# replaces it. Antigravity cannot pass a quoted path to a hook, so the guard is found from here.
import os, runpy, sys

guard = os.path.join(os.path.expanduser("~"), ".the-agent-kit", "hooks", "command-guard.py")
if not os.path.isfile(guard):
    sys.stderr.write("the-agent-kit: no guard at %s; run install.sh --setup. Command not checked.\n" % guard)
    sys.exit(0)
sys.argv = [guard] + sys.argv[1:]
runpy.run_path(guard, run_name="__main__")
LAUNCH
}

merge_ag_hooks() {  # $1 = .agents/hooks.json. Add-only: the user's own hook entries are never touched.
  py=$(detect_py)
  if [ -z "$py" ]; then say "  ! no Python 3 found - Antigravity guard hook not written (the guard needs it)."; return 0; fi
  r=$($py - "$1" "$py agent-kit-guard.py --tool antigravity" <<'MERGE'
import json, os, sys, tempfile
path, cmd = sys.argv[1], sys.argv[2]
data = {}
if os.path.islink(path):
    print("symlink"); sys.exit(0)
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError:
        print("unreadable"); sys.exit(0)
if not isinstance(data, dict):
    print("unreadable"); sys.exit(0)
if "the-agent-kit" in data:
    print("kept"); sys.exit(0)
data["the-agent-kit"] = {"PreToolUse": [{"matcher": "run_command", "hooks": [
    {"type": "command", "command": cmd, "timeout": 15}]}]}
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".hooks.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, indent=2); f.write("\n")
os.replace(tmp, path)   # a kill mid-write must never leave the user's hooks.json half written
print("added")
MERGE
)
  case "$r" in
    added)      say "  + wired the command guard into .agents/hooks.json (Antigravity)" ;;
    unreadable) say "  ! .agents/hooks.json is not a JSON object - left untouched; the Antigravity guard is NOT wired." ;;
    symlink)    say "  ! .agents/hooks.json is a symlink - left untouched; the Antigravity guard is NOT wired." ;;
  esac
}

install_antigravity() {  # $1 = repo root. Antigravity reads AGENTS.md and the .agents/skills Codex gets
  # (the three skills and four domain rules). What only it has: glob-triggered rules, for the two
  # path-shaped depth files Codex skips, and a workspace PreToolUse hook for the command guard. The four
  # domain rules stay skills only; writing them here too would load them twice.
  src=""
  [ -d "$KIT/claude/rules" ] && src="$KIT/claude/rules"
  [ -z "$src" ] && [ -d "$KIT/rules" ] && src="$KIT/rules"
  for n in code-correctness tests; do
    [ -n "$src" ] && [ -e "$src/$n.md" ] || continue
    if [ -e "$1/.agents/rules/$n.md" ] || [ -L "$1/.agents/rules/$n.md" ]; then say "  = .agents/rules/$n.md already exists - left untouched."
    else
      mkdir -p "$1/.agents/rules"; rule_to_glob "$src/$n.md" > "$1/.agents/rules/$n.md"
      say "  + wrote .agents/rules/$n.md (Antigravity: loads when a matching file is touched)"
    fi
  done
  mkdir -p "$1/.agents"
  [ -e "$1/.agents/agent-kit-guard.py" ] || [ -L "$1/.agents/agent-kit-guard.py" ] || write_ag_launcher "$1/.agents/agent-kit-guard.py"
  merge_ag_hooks "$1/.agents/hooks.json"
}

install_project() {   # self-contained: full rules + git hooks
  root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  say "Installing FULL rules + git hooks into: $root"
  # AGENTS.md holds the rules (the cross-tool standard: Codex, Cursor, Aider, Copilot...). Claude Code
  # reads CLAUDE.md only, so CLAUDE.md IMPORTS AGENTS.md rather than duplicating it - one source of
  # truth, no drift. (Anthropic's documented pattern; a symlink also works but needs admin on Windows.)
  if [ -e "$root/AGENTS.md" ]; then say "  = AGENTS.md already exists - left untouched."
  else write_rules "$root/AGENTS.md"; say "  + wrote AGENTS.md (full rules + empty project block)"; fi
  if [ -e "$root/CLAUDE.md" ]; then say "  = CLAUDE.md already exists - left untouched."
  else write_claude_importer "$root/CLAUDE.md"; say "  + wrote CLAUDE.md (imports AGENTS.md - single source of truth)"; fi
  install_path_rules "$root"
  install_skills "$root"
  install_codex_skills "$root"
  install_antigravity "$root"
  install_git_hooks "$root"
  hr
  say "Tool-layer guard is machine-wide - run once:  ./install.sh --setup   then:  ./install.sh --check"
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
  install_skills "$root"
  install_codex_skills "$root"
  install_antigravity "$root"
  install_git_hooks "$root"
}

merge_recommended() {  # $1 = the kit's list  $2 = the user's list (~/.the-agent-kit/recommended.json)  $3 = plan | apply (default)
  # plan only describes the change (exit 10 when there is one): --setup shows it and writes after consent.
  # Items are matched by id. New upstream items are added and changed ones replaced; an item the user
  # removed (it was offered before, so it is in `seeded`) or dismissed never comes back; entries without
  # an id are the user's own and are never touched. A list from before ids existed is matched by name,
  # and its missing originals count as deleted, which is what deleting an entry meant then.
  py=$(detect_py)
  [ -n "$py" ] || return 1
  $py - "$(nat "$1")" "$(nat "$2")" "${3:-apply}" <<'RECO'
import json, os, shutil, sys, tempfile, time
up_path, path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(up_path, encoding="utf-8-sig") as f:
        up = json.load(f)
    ups = [i for i in up["items"] if isinstance(i, dict) and i.get("id")]
except (OSError, ValueError, KeyError, TypeError):
    ups = []
if not ups:
    sys.exit(0)   # no usable list from the kit: nothing to merge, and nothing may be retired from a bad download
if os.path.islink(path):
    print("  ! recommended.json is a symlink - left untouched."); sys.exit(0)
fresh = not os.path.exists(path)
cur = {"items": []}
if not fresh:
    try:
        with open(path, encoding="utf-8-sig") as f:
            cur = json.load(f)
        if not isinstance(cur, dict) or not all(isinstance(cur.get(k, []), list) for k in ("items", "seeded", "dismissed")):
            raise ValueError
    except ValueError:
        print("  ! ~/.the-agent-kit/recommended.json is not valid JSON - left as it is, so the tool reminders use it unchanged. Fix or delete it.")
        sys.exit(0)
items = cur.get("items", [])
legacy = not fresh and "seeded" not in cur
seeded, dismissed = set(cur.get("seeded", [])), list(cur.get("dismissed", []))
added, updated, dropped = [], [], []
upstream_ids = {u["id"] for u in ups}
for n in range(len(items) - 1, -1, -1):   # a kit item that was offered and has since been retired goes
    i = items[n]
    if isinstance(i, dict) and i.get("id") in seeded and i["id"] not in upstream_ids:
        dropped.append(i.get("name", i["id"])); del items[n]
for u in ups:
    entry = {k: v for k, v in u.items() if k not in ("since", "replaces")}
    if u["id"] in dismissed:
        continue
    names = [u["name"]] + list(u.get("replaces", []))
    at = next((n for n, i in enumerate(items) if isinstance(i, dict) and (
        i.get("id") == u["id"] or (not i.get("id") and i.get("name") in names))), None)
    if at is not None:
        if items[at] != entry:
            items[at] = entry; updated.append(u["name"])
    elif u["id"] in seeded or (legacy and int(u.get("since", 1)) <= 1):
        dismissed.append(u["id"])   # offered before and gone from the list: the user removed it
    else:
        items.append(entry); added.append(u["name"])
new = {"_about": up.get("_about", cur.get("_about")), "items": items, "seeded": sorted(upstream_ids),
       "dismissed": list(dict.fromkeys(dismissed))}
new.update({k: v for k, v in cur.items() if k not in new})
if not fresh and json.dumps(new, sort_keys=True) == json.dumps(cur, sort_keys=True):
    sys.exit(0)
if mode == "plan" and not fresh:   # the list comes off the network on --update: show it, write only after a yes
    bits = [("add", added), ("update", updated), ("retire", dropped)]
    print("  + recommended tools: " + ("; ".join("%s %s" % (k, ", ".join(v)) for k, v in bits if v)
          if any(v for _, v in bits) else "bring the list up to date") + " (items you removed or dismissed stay gone)")
    sys.exit(10)
if not fresh:
    bak, n ="%s.bak-agent-kit-%s" % (path, time.strftime("%Y%m%d-%H%M%S")), 1
    while os.path.exists(bak):   # two runs in one second must not overwrite the first backup
        n += 1; bak = "%s.bak-agent-kit-%s-%d" % (path, time.strftime("%Y%m%d-%H%M%S"), n)
    shutil.copy2(path, bak)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".recommended.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
    json.dump(new, f, indent=2, ensure_ascii=False); f.write("\n")
os.replace(tmp, path)   # a kill mid-write must never leave the user's list half written
RECO
}

copy_share() {  # copy this kit into ~/.the-agent-kit, so the download it came from can be deleted
  share="$HOME/.the-agent-kit"
  mkdir -p "$share/hooks" "$share/git-hooks" "$share/docs" "$share/claude" "$share/codex" "$share/setup"
  # Copy the WHOLE kit, not just the hooks, so the clone you ran this from becomes disposable.
  # git-hooks/ is the core.hooksPath target (those three only); hooks/ is the full set, which is
  # what the relocated install.sh compares against in --check and copies from per project.
  for h in command-guard.py kit-check.py agent-kit-check.py mcp-orphans.py mcp-wrap.py tidy-procs.py tidy-scan.py commit-msg pre-commit pre-push; do
    case "$h" in mcp-*|tidy-*|agent-kit-*) [ -f "$KIT/hooks/$h" ] || continue ;; esac
    cp "$KIT/hooks/$h" "$share/hooks/$h"
  done
  for h in commit-msg pre-commit pre-push; do cp "$KIT/hooks/$h" "$share/git-hooks/$h"; done
  # The recommended-tools list is the user's once seeded. hooks/recommended.json beside it is the kit's
  # pristine copy, which --setup merges in by id (merge_recommended): a declined item stays declined.
  cp "$KIT/hooks/recommended.json" "$share/hooks/recommended.json" 2>/dev/null || true
  [ -f "$share/recommended.json" ] || merge_recommended "$KIT/hooks/recommended.json" "$share/recommended.json" \
    || cp "$KIT/hooks/recommended.json" "$share/recommended.json" 2>/dev/null || true
  # AGENTS.md goes through write_rules, never cp: this repo's file carries its OWN project block, and
  # the share is what --update-rules and the "prefer the rules global" append both read. A cp here put
  # this repo's branch rules into every user's global rules (Q3, found 2026-09-26 before it shipped).
  write_rules "$share/AGENTS.md"
  cp "$KIT/CLAUDE.md" "$KIT/install.sh" "$share/"
  # The installer prints these as merge snippets, so the relocated copy must carry them too.
  cp "$KIT/claude/settings.json" "$share/claude/" 2>/dev/null || true
  cp "$KIT/codex/config.toml" "$KIT/codex/hooks.json" "$share/codex/" 2>/dev/null || true
  cp "$KIT/setup/merge-settings.py" "$share/setup/" 2>/dev/null || true
  # Only docs git would publish: anything git ignores is the owner's private working notes (plans,
  # research, todo lists), never the kit's. A copy with no .git (a zip) has no ignored files to leak.
  for f in "$KIT/docs/"*.md; do
    [ -f "$f" ] || continue
    git -C "$KIT" check-ignore -q "$f" 2>/dev/null && continue
    cp "$f" "$share/docs/"
  done
  rm -f "$share/docs/lessons.md" "$share/docs/my-skills-and-plugins.md" "$share/docs/enhancements.md" "$share/docs/todo.md"   # left by earlier installs
  mkdir -p "$share/rules"
  cp "$KIT/claude/rules/"*.md "$share/rules/" 2>/dev/null || cp "$KIT/rules/"*.md "$share/rules/" 2>/dev/null || true
  # Replace the share's skills wholesale. `cp -r src dest` with dest already present copies INTO it,
  # which on the second --update left a nested skills/skills/ and a stale top level: projects updated
  # from that copy silently missed every skill added after the first install (observed 2026-09-18).
  rm -rf "$share/skills"; mkdir -p "$share/skills"
  if [ -d "$KIT/claude/skills" ]; then cp -r "$KIT/claude/skills/." "$share/skills/" 2>/dev/null || true
  elif [ -d "$KIT/skills" ]; then cp -r "$KIT/skills/." "$share/skills/" 2>/dev/null || true; fi
  # The optional performance profile ships in the share too, so the README's paths exist after --update.
  for pd in claude/performance codex/performance; do
    rm -rf "$share/$pd"
    [ -d "$KIT/$pd" ] && mkdir -p "$share/$pd" && cp -r "$KIT/$pd/." "$share/$pd/" 2>/dev/null
  done
  chmod +x "$share/hooks/"* "$share/git-hooks/"* "$share/install.sh"
  # Stamp the source commit so --update can tell "already current" from "a month behind", and show
  # you what actually changed. Absent (or "unknown") when installed from a non-git copy - not fatal.
  ver=$( (cd "$KIT" && git rev-parse --short HEAD 2>/dev/null) || true )
  printf '%s\n' "${ver:-unknown}" > "$share/.kit-version"
  say "Copied the kit to $share (rules + hooks + installer + docs)"
  say "  -> $share is now self-contained: the clone you ran this from can be deleted."
}

install_global() {  # copy the kit, then PRINT the settings snippets for a hand merge (--setup applies them)
  share="$HOME/.the-agent-kit"
  # Running the installed copy's own --global would copy every file onto itself and die under
  # set -e ("are the same file"). Refreshing the share is --update's job.
  if [ "$KIT" = "$share" ]; then
    say "This IS the installed copy - nothing to copy onto itself. To refresh it from GitHub:"
    say "    $share/install.sh --update"
    return 0
  fi
  copy_share

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
    say "  Run that in a NORMAL terminal, not inside an agent session: this kit denies"
    say "  'git config core.hooksPath' so an agent cannot point git away from the hooks,"
    say "  and that denial applies to you too while you are in one."
  fi

  hr
  say "TOOL GUARD - Claude Code    merge into  ~/.claude/settings.json :"
  subst "$share" "$py" "$KIT/claude/settings.json"
  hr
  say "TOOL GUARD - Codex          merge into  ~/.codex/hooks.json  (+ see codex/config.toml) :"
  subst "$(nat "$share")" "$py" "$KIT/codex/hooks.json"   # Codex on Windows runs hooks in cmd.exe
  hr
  say "CODEX SANDBOX / APPROVAL    merge into  ~/.codex/config.toml :"
  cat "$KIT/codex/config.toml"

  hr
  say "THE KIT'S SKILLS - one real copy for all three tools (--setup does this for you, after asking):"
  say "  copy each folder in $share/skills to ~/.agents/skills/<name>   (Codex reads it there)"
  say "  link ~/.claude/skills/<name> to that copy: ln -s on macOS and Linux; on Windows a junction, which needs no admin:"
  say "      cmd //c mklink /J <link> <target>      (remove it later with rmdir, never rm -rf)"
  say "  add {\"path\": \"~/.agents/skills\", \"include_only\": [<the skill names>]} to \"entries\" in ~/.gemini/config/skills.json (Antigravity)"

  hr
  say "ANTIGRAVITY SESSION-START CHECK - Antigravity has no SessionStart event, so it runs as a PreInvocation hook"
  say "  that acts on the first call of each conversation. Copy $share/hooks/agent-kit-check.py to"
  say "  ~/.gemini/config/, then add this under its own name to ~/.gemini/config/hooks.json (keep your other hooks):"
  say "    \"the-agent-kit\": {\"PreInvocation\": [{\"type\": \"command\", \"command\": \"$py agent-kit-check.py --tool antigravity\", \"timeout\": 10}]}"

  hr
  # $share, never $KIT. Under --update, $KIT is a temp clone this run deletes on its way out, so a
  # command printed with that path is already broken by the time anyone reads it. $share is where
  # the kit actually lives afterwards.
  say "The tool guard is NOT active until you merge the snippet(s) above - then verify:"
  say "    $share/install.sh --check"
  say "Optional global rules (lets projects stay lean via --extension), review the merge first:"
  say "    cat \"$share/AGENTS.md\" >> ~/.claude/CLAUDE.md   ;   cat \"$share/AGENTS.md\" >> ~/.codex/AGENTS.md"
  say "    mkdir -p ~/.gemini && cat \"$share/AGENTS.md\" >> ~/.gemini/AGENTS.md"
  say "Antigravity: the guard hook stays per project; run $share/install.sh inside each project."
}

nat() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }   # a path Python and git accept on every OS

merge_settings() {  # $1 = share, $2 = python, then extra flags -> runs the kit's settings merge
  ms_share=$1; ms_py=$2; shift 2
  $ms_py "$(nat "$ms_share/setup/merge-settings.py")" --home "$(nat "$HOME")" --share "$(nat "$ms_share")" \
    --share-cmd "$ms_share" --py "$ms_py" "$@"
}

confirm() {  # consent to write the user's settings: a terminal answer, or AGENT_KIT_APPLY=1
  # AGENT_KIT_APPLY is the only way without a terminal, and the kit's tool guard asks the user before any
  # agent command sets it: an agent cannot rewrite its own permissions without the human saying yes.
  [ "${AGENT_KIT_APPLY:-}" = 1 ] && return 0
  # Settings that just arrived with an update are applied only by an answer given after seeing them: in
  # a terminal, the question below; otherwise a separate --setup, run once the list above has been read.
  if [ -t 0 ]; then
    printf 'Apply these changes? [y/N] '
    read -r ans || ans=""
    case "$ans" in y|Y|yes|YES|Yes) return 0 ;; esac
    say "  Nothing changed."
    return 1
  fi
  say "  Nothing changed: there is no terminal to ask you in. To apply the changes listed above, run"
  say "  $HOME/.the-agent-kit/install.sh --setup in a terminal, or AGENT_KIT_APPLY=1 in front of it."
  return 1
}

wire_machine() {  # $1 = plan | apply | undo. The kit's own skills, installed once for all three tools.
  # plan prints what apply would do (exit 10 when there is something to do); undo removes what apply made.
  #   ~/.agents/skills/<name>        the one real copy (Codex reads it); the kit marks its copies
  #   ~/.claude/skills/<name>        a directory link to it (Claude Code has no setting for another folder)
  #   ~/.gemini/config/skills.json   Antigravity's entry for ~/.agents/skills, limited to the kit's names
  # Only what the kit made is ever changed or removed. A folder, link or entry of the user's with the same
  # name is left as it is and reported. A tool that is not on the machine (no ~/.claude, no
  # ~/.gemini/config) is not set up, and nothing is created for it.
  share="$HOME/.the-agent-kit"
  py=$(detect_py)
  [ -n "$py" ] || { say "  ! no working Python 3 found - the kit's skills were not installed machine-wide."; return 1; }
  $py - "$1" "$(nat "$HOME")" "$(nat "$share")" "$py" <<'WIRE'
import json, os, re, shutil, subprocess, sys, tempfile, time
mode, home, share, pycmd = sys.argv[1:5]
KIT_SKILLS = ("generating-reports", "orchestrating-work", "tidy", "writing-docs")
MARK = ".the-agent-kit"            # a file inside every skill folder the kit copied: that is what "ours" means
canon_root = os.path.join(home, ".agents", "skills")
claude_skills = os.path.join(home, ".claude", "skills")
cfg = os.path.join(home, ".gemini", "config")
sj_path = os.path.join(cfg, "skills.json")
SJ_PATH = "~/.agents/skills"
src_root = os.path.join(share, "skills")
names = sorted(n for n in (os.listdir(src_root) if os.path.isdir(src_root) else [])
               if os.path.isfile(os.path.join(src_root, n, "SKILL.md")))
if mode == "undo":
    names = sorted(set(names) | set(KIT_SKILLS))
# Antigravity's session-start check: a named PreInvocation hook in the global hooks.json, run through a
# launcher beside it (the hook command is split on whitespace and quotes are ignored, so no quoted path).
HOOK_KEY = "the-agent-kit-check"     # not "the-agent-kit": the project hook in .agents/hooks.json already has that name
hooks_path = os.path.join(cfg, "hooks.json")
launch_path = os.path.join(cfg, "agent-kit-check.py")
launch_src = os.path.join(share, "hooks", "agent-kit-check.py")
LAUNCH_SIG = b"# The Agent Kit: launcher for the session-start check"   # first line of every launcher the kit has shipped
CMD_RE = re.compile(r"(python3?|py -3) agent-kit-check\.py --tool antigravity")
stamp = time.strftime("%Y%m%d-%H%M%S")
actions, lines, rc = [], [], 0

def norm(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))

def is_link(p):                      # a symlink, or a Windows junction (os.path.islink is False for those)
    if os.path.islink(p):
        return True
    if os.name == "nt":
        try:
            st = os.lstat(p)
        except OSError:
            return False
        return bool(getattr(st, "st_file_attributes", 0) & 0x400) and getattr(st, "st_reparse_tag", 0) == 0xA0000003
    return False

def points_to(link, target):
    return norm(os.path.realpath(link)) == norm(os.path.realpath(target))

def make_link(link, target):
    # AGENT_KIT_LINK_KIND=symlink|junction overrides the platform default (symlink; junction on Windows,
    # which needs no admin rights and no Developer Mode). It exists so the other kind can be tested.
    kind = os.environ.get("AGENT_KIT_LINK_KIND") or ("junction" if os.name == "nt" else "symlink")
    if kind == "junction":
        if re.search(r'[&|<>^%!"]', link + target):   # cmd.exe would act on these, quoted or not
            raise OSError("a path contains a character cmd.exe interprets (& | < > ^ % ! \"); link it by hand")
        r = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.normpath(link), os.path.normpath(target)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout).strip() or "mklink /J failed")
    else:
        os.symlink(target, link, target_is_directory=True)

def drop_link(link):                 # never rmtree: that could follow the link into the one real copy
    if os.name == "nt":
        os.rmdir(link)               # removes a junction or directory symlink, not what it points at
    else:
        os.unlink(link)

def tree(p):
    out = {}
    for d, _, fs in os.walk(p):
        for f in fs:
            full = os.path.join(d, f)
            rel = os.path.relpath(full, p).replace(os.sep, "/")
            if rel != MARK:
                with open(full, "rb") as fh:
                    out[rel] = fh.read()
    return out

def owned_copy(p):
    return os.path.isfile(os.path.join(p, MARK)) and not is_link(p)

def copy_skill(n):
    src, dst = os.path.join(src_root, n), os.path.join(canon_root, n)
    tmp = dst + ".agent-kit-new"
    if os.path.lexists(tmp):         # re-checked here: we cannot tell who made it, so we never delete it
        raise OSError("%s already exists; left as it is" % tmp)
    shutil.copytree(src, tmp, symlinks=True)   # a link inside a kit skill is copied as a link, never followed
    with open(os.path.join(tmp, MARK), "w", encoding="utf-8") as f:
        f.write("This folder is a copy made by the-agent-kit's install.sh; --setup refreshes it and --undo removes it.\n")
    if os.path.lexists(dst):
        if not owned_copy(dst):      # re-checked here: it may have changed since the plan was made
            shutil.rmtree(tmp, ignore_errors=True)
            raise OSError("%s is no longer the kit's copy; left as it is" % dst)
        shutil.rmtree(dst)
    os.makedirs(canon_root, exist_ok=True)
    os.rename(tmp, dst)

def write_json(path, data):
    if os.path.exists(path):
        bak, n = "%s.bak-agent-kit-%s" % (path, stamp), 1
        while os.path.exists(bak):   # two runs in one second must not overwrite the first backup
            n += 1; bak = "%s.bak-agent-kit-%s-%d" % (path, stamp, n)
        shutil.copy2(path, bak)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".skills.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, path)            # a kill mid-write must never leave the user's skills.json half written

def kit_entry(e):
    return isinstance(e, dict) and isinstance(e.get("path"), str) and (
        e["path"].rstrip("/\\") == SJ_PATH or norm(os.path.expanduser(e["path"].replace("~/", home + "/", 1))) == norm(canon_root))

def warn(s):
    lines.append("  ! " + s)

def want_hook():
    return {"PreInvocation": [{"type": "command", "command": pycmd + " agent-kit-check.py --tool antigravity", "timeout": 10}]}

def kit_hook_shape(v):               # what an entry written by an earlier run looks like (any interpreter spelling)
    h = v.get("PreInvocation") if isinstance(v, dict) and list(v) == ["PreInvocation"] else None
    return (isinstance(h, list) and len(h) == 1 and isinstance(h[0], dict)
            and CMD_RE.fullmatch(str(h[0].get("command", ""))) is not None)

def read_launcher():
    with open(launch_src, "rb") as f:
        return f.read()

def write_launcher():
    fd, tmp = tempfile.mkstemp(dir=cfg, prefix=".agent-kit-check.", suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(read_launcher())
    os.replace(tmp, launch_path)

if mode in ("plan", "apply"):
    ok = []                          # skills whose one real copy is ours (made now or already)
    todo_copy, todo_refresh, todo_link = [], [], []
    for n in names:
        dst = os.path.join(canon_root, n)
        if not os.path.lexists(dst):
            todo_copy.append(n); ok.append(n)
        elif is_link(dst) or not owned_copy(dst):
            warn("~/.agents/skills/%s is not the kit's copy; left as it is, and nothing is linked to it" % n)
        else:
            ok.append(n)
            try:
                differs = tree(dst) != tree(os.path.join(src_root, n))
            except OSError:
                differs = True
            if differs:
                todo_refresh.append(n)
    for n in todo_copy + todo_refresh:   # copy_skill builds in <n>.agent-kit-new; one already there is not ours to delete
        if os.path.lexists(os.path.join(canon_root, n) + ".agent-kit-new"):
            warn("~/.agents/skills/%s.agent-kit-new already exists; left as it is, so %s is not copied or refreshed (remove it to retry)" % (n, n))
            todo_copy[:] = [x for x in todo_copy if x != n]
            todo_refresh[:] = [x for x in todo_refresh if x != n]
            if n in ok and not os.path.lexists(os.path.join(canon_root, n)):
                ok.remove(n)
    if todo_copy:
        lines.append("  + copy to ~/.agents/skills (the one real copy, read by Codex): " + ", ".join(todo_copy))
    if todo_refresh:
        lines.append("  + refresh in ~/.agents/skills (the kit's copy; edits made to it are replaced): " + ", ".join(todo_refresh))
    actions += [("copy " + n, (lambda n=n: copy_skill(n))) for n in todo_copy + todo_refresh]
    if os.path.isdir(os.path.join(home, ".claude")):
        for n in ok:
            link, dst = os.path.join(claude_skills, n), os.path.join(canon_root, n)
            if not os.path.lexists(link):
                todo_link.append(n)
            elif is_link(link) and points_to(link, dst):
                pass
            elif is_link(link):
                warn("~/.claude/skills/%s is a link to somewhere else; left as it is" % n)
            else:
                warn("~/.claude/skills/%s is a folder of yours; left as it is (it wins over the kit's skill of the same name)" % n)
        if todo_link:
            lines.append("  + link in ~/.claude/skills (a directory link to the one copy): " + ", ".join(todo_link))
            def do_links(todo=tuple(todo_link)):
                os.makedirs(claude_skills, exist_ok=True)
                for n in todo:
                    make_link(os.path.join(claude_skills, n), os.path.join(canon_root, n))
            actions.append(("link", do_links))
    if os.path.isdir(cfg) and ok:
        data, bad, why = {"entries": []}, False, "is not a JSON object with an entries list"
        if os.path.islink(sj_path):
            bad, why = True, "is a symlink"
        elif os.path.exists(sj_path):
            try:
                with open(sj_path, encoding="utf-8-sig") as f:
                    data = json.load(f)
                bad = not isinstance(data, dict) or not isinstance(data.get("entries", []), list)
            except ValueError:
                bad = True
        if bad:
            warn("~/.gemini/config/skills.json %s; left untouched, so Antigravity does not get the kit's skills from it" % why)
        else:
            entries = data.setdefault("entries", [])
            mine = next((e for e in entries if kit_entry(e)), None)
            if mine is None:
                entries.append({"path": SJ_PATH, "include_only": list(ok)})
                lines.append("  + add ~/.agents/skills (limited to the kit's skills) to ~/.gemini/config/skills.json for Antigravity")
                actions.append(("skills.json", lambda d=data: write_json(sj_path, d)))
            elif isinstance(mine.get("include_only"), list):
                missing = [n for n in ok if n not in mine["include_only"]]
                if missing:
                    mine["include_only"] += missing
                    lines.append("  + add the kit's skills to your ~/.agents/skills entry in ~/.gemini/config/skills.json: " + ", ".join(missing))
                    actions.append(("skills.json", lambda d=data: write_json(sj_path, d)))
    if os.path.isdir(cfg) and os.path.isfile(launch_src) and os.path.isfile(os.path.join(share, "hooks", "kit-check.py")):
        data, state = {}, "add"      # `data` is rebound above for skills.json: the writers bind their own copy (d=data)
        if os.path.islink(hooks_path):
            warn("~/.gemini/config/hooks.json is a symlink; left untouched, so the Antigravity session-start check is not wired")
            state = "blocked"
        elif os.path.exists(hooks_path):
            try:
                with open(hooks_path, encoding="utf-8-sig") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                warn("~/.gemini/config/hooks.json is not a JSON object; left untouched, so the Antigravity session-start check is not wired")
                state = "blocked"
        if state != "blocked":
            cur = data.get(HOOK_KEY)
            if cur is None:
                state = "add"
            elif cur == want_hook():
                state = "ok"
            elif kit_hook_shape(cur):
                state = "refresh"
            else:
                warn("the entry named %s in ~/.gemini/config/hooks.json is not the kit's; left as it is, so the session-start check is not wired" % HOOK_KEY)
                state = "blocked"
        if state != "blocked":
            have = None
            try:
                if os.path.isfile(launch_path) and not os.path.islink(launch_path):
                    with open(launch_path, "rb") as f:
                        have = f.read()
            except OSError:
                pass
            if os.path.islink(launch_path) or (os.path.lexists(launch_path) and (have is None or (
                    have != read_launcher() and not have.startswith(LAUNCH_SIG)))):
                warn("~/.gemini/config/agent-kit-check.py is a symlink or a file that is not the kit's launcher; left as it is, so the Antigravity session-start check is not wired")
            else:
                if have != read_launcher():
                    lines.append("  + write ~/.gemini/config/agent-kit-check.py (the launcher the hook calls; kit-owned)")
                    actions.append(("launcher", write_launcher))
                if state in ("add", "refresh"):
                    data[HOOK_KEY] = want_hook()
                    lines.append("  + %s the session-start check in ~/.gemini/config/hooks.json (a PreInvocation hook; your other hooks are kept)"
                                 % ("add" if state == "add" else "refresh"))
                    actions.append(("hooks.json", lambda d=data: write_json(hooks_path, d)))
    if mode == "apply":
        failed = set()
        for what, fn in actions:
            if what == "hooks.json" and "launcher" in failed:   # a hook that calls a missing launcher errors on every model call
                lines.append("  ! hooks.json not changed: the launcher it calls could not be written"); rc = 1
                continue
            try:
                fn()
            except (OSError, shutil.Error) as e:
                lines.append("  ! %s failed: %s" % (what, e)); rc = 1; failed.add(what)
        lines = [l for l in lines if l.startswith("  !")] + ["  done: " + ", ".join(w for w, _ in actions)] * bool(actions)
    elif actions:
        rc = 10
else:                                # undo
    gone = []
    mine_names = []                  # skills whose ~/.agents/skills folder was the kit's: the only names skills.json may lose
    for n in names:
        link, dst = os.path.join(claude_skills, n), os.path.join(canon_root, n)
        if os.path.lexists(link) and is_link(link) and points_to(link, dst) and (owned_copy(dst) or not os.path.lexists(dst)):
            try:
                drop_link(link); gone.append("~/.claude/skills/" + n)
            except OSError as e:
                lines.append("  ! could not remove ~/.claude/skills/%s: %s" % (n, e)); rc = 1
    for n in names:
        dst = os.path.join(canon_root, n)
        if os.path.lexists(dst) and owned_copy(dst):
            try:
                shutil.rmtree(dst); gone.append("~/.agents/skills/" + n); mine_names.append(n)
            except OSError as e:
                lines.append("  ! could not remove ~/.agents/skills/%s: %s" % (n, e)); rc = 1
    if os.path.exists(sj_path):
        try:
            if os.path.islink(sj_path):
                raise ValueError
            with open(sj_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            entries = data["entries"]
            mine = next((e for e in entries if kit_entry(e) and isinstance(e.get("include_only"), list)), None)
            if mine is not None:
                left = [n for n in mine["include_only"] if n not in mine_names]
                if left != mine["include_only"]:
                    if left:
                        mine["include_only"] = left
                    elif set(mine) <= {"path", "include_only"}:
                        entries.remove(mine)
                    else:            # an empty include_only may mean "everything", so keep the user's entry as it was
                        raise ValueError
                    write_json(sj_path, data); gone.append("the kit's skills in ~/.gemini/config/skills.json")
        except (ValueError, KeyError, TypeError, OSError):
            lines.append("  ! ~/.gemini/config/skills.json could not be read, is a symlink, or has an entry with other keys; left as it is")
    hook_left = False                # keep the launcher while an entry might still call it
    if os.path.exists(hooks_path):
        try:
            if os.path.islink(hooks_path):
                raise ValueError
            with open(hooks_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict) and kit_hook_shape(data.get(HOOK_KEY)):
                del data[HOOK_KEY]
                write_json(hooks_path, data); gone.append("the session-start check in ~/.gemini/config/hooks.json")
        except (ValueError, OSError):
            hook_left = True
            lines.append("  ! ~/.gemini/config/hooks.json could not be read or is a symlink; left as it is")
    if not hook_left and os.path.isfile(launch_path) and not os.path.islink(launch_path):
        try:
            with open(launch_path, "rb") as f:   # only the kit's own launcher, by its first line
                ours = f.read(len(LAUNCH_SIG)).startswith(LAUNCH_SIG)
        except OSError:
            ours = False
        if ours:
            os.remove(launch_path); gone.append("~/.gemini/config/agent-kit-check.py")
        else:
            lines.append("  ! ~/.gemini/config/agent-kit-check.py is not the kit's launcher; left as it is")
    lines.insert(0, "  - removed: " + (", ".join(gone) if gone else "nothing (the kit made none of it, or it is already gone)"))
print("\n".join(lines))
sys.exit(rc)
WIRE
}

setup_machine() {  # --setup: everything a machine needs, applied with the user's consent
  share="$HOME/.the-agent-kit"
  [ "$KIT" = "$share" ] || copy_share
  py=$(detect_py)
  [ -n "$py" ] || { say "  ! no working Python 3 found - the kit's guard and this setup both need it. Install it and re-run."; exit 2; }
  hr
  say "SETTINGS - the kit's entries are added to yours; only rules the kit once added and has retired are removed"
  mrc=0; plan=$(merge_settings "$share" "$py" 2>&1) || mrc=$?
  [ -n "$plan" ] && say "$plan"
  [ "$mrc" = 0 ] && [ -z "$plan" ] && say "  already current (or no Claude Code / Codex settings folder found)"
  say "GIT HOOKS - secret scan, protected branches and attribution stripping, in every repo"
  want=$(nat "$share/git-hooks"); hp=$(git config --global --get core.hooksPath 2>/dev/null || true); sethooks=0
  case "$(printf '%s' "$hp" | tr '\\' '/')" in
    */.the-agent-kit/git-hooks|*/.the-agent-kit/git-hooks/) say "  already on" ;;
    "") sethooks=1; say "  + turn on: core.hooksPath -> $want"
        say "    (git then runs the kit's hooks in every repo, instead of each repo's own .git/hooks)" ;;
    *) say "  left as it is: core.hooksPath is $hp (another tool owns it)."
       say "  To add the kit's hooks, copy $share/git-hooks/* into that folder." ;;
  esac
  hr
  # The kit's list may have just come off the network (--update), and its text ends up in the agent's
  # context, so it is shown first and merged only after the same yes as the settings.
  say "RECOMMENDED TOOLS - the list the session-start check reminds from (~/.the-agent-kit/recommended.json)"
  rrc=0; rplan=$(merge_recommended "$KIT/hooks/recommended.json" "$share/recommended.json" plan 2>&1) || rrc=$?
  if [ -n "$rplan" ]; then say "$rplan"; else say "  already current"; fi
  hr
  say "SKILLS AND THE ANTIGRAVITY CHECK -the kit's own skills installed once for all three tools, and the session-start check for Antigravity"
  wrc=0; wplan=$(wire_machine plan 2>&1) || wrc=$?
  if [ -n "$wplan" ]; then say "$wplan"; else say "  already in place"; fi
  say "Antigravity's command guard is still wired per project: run $share/install.sh inside each project."
  if [ "$mrc" != 10 ] && [ "$sethooks" = 0 ] && [ "$wrc" != 10 ] && [ "$rrc" != 10 ]; then
    [ "$mrc" = 1 ] && { say "Fix the file named above (it could not be read safely), then run this again."; exit 1; }
    say "Already set up: your settings and git hooks carry the kit."
    return 0
  fi
  if confirm; then
    arc=0
    [ "$mrc" = 10 ] && { AGENT_KIT_APPLY=1 merge_settings "$share" "$py" --apply >/dev/null 2>&1 || arc=$?; }
    [ "$sethooks" = 1 ] && git config --global core.hooksPath "$want"
    [ "$arc" = 0 ] || [ "$mrc" = 1 ] || { say "  ! the settings merge did not finish (exit $arc) - run $share/install.sh --check"; exit 1; }
    if [ "$rrc" = 10 ]; then
      merge_recommended "$KIT/hooks/recommended.json" "$share/recommended.json" apply || say "  ! the recommended-tools list could not be updated"
    fi
    if [ "$wrc" = 10 ]; then
      wout=$(wire_machine apply 2>&1) || say "  ! the skills step did not finish cleanly:"
      [ -n "$wout" ] && say "$wout"
    fi
    say "Done. Backups of changed files sit beside them as *.bak-agent-kit-<time>."
    say "Restart Claude Code and Codex: hooks load when a session starts."
    # Codex keeps a hash of each hook definition it was told to trust and skips any new or changed one.
    case "$plan" in *".codex/hooks.json"*)
      say "Codex runs a new or changed hook only once you trust it: in Codex, run /hooks and trust the kit's" ;
      say "  command-guard.py and kit-check.py entries. Until then Codex skips them without a warning." ;;
    esac
    say "Then in each project:   $share/install.sh     (and run the setup prompt once)"
  fi
  [ "$mrc" = 1 ] && exit 1
  return 0
}

update_kit() {  # refresh ~/.the-agent-kit from GitHub, so the clone stays disposable
  share="$HOME/.the-agent-kit"
  command -v git >/dev/null 2>&1 || { say "  ! git not found - cannot update. Install git, or re-clone by hand."; exit 2; }
  [ -n "${AGENT_KIT_REPO:-}" ] && say "  ! AGENT_KIT_REPO override active - updating from $KIT_REPO, NOT the official repo."
  old=$(cat "$share/.kit-version" 2>/dev/null || printf 'unknown')
  tmp=$(mktemp -d) || exit 2
  say "Fetching the latest kit from $KIT_REPO"
  if ! git clone --quiet --depth 50 "$KIT_REPO" "$tmp/kit" 2>/dev/null; then
    rm -rf "$tmp"; say "  ! clone failed (offline, or the repo moved) - NOTHING was changed."; exit 2
  fi
  # Never overwrite a working install from a surprise payload: prove the download is actually the kit
  # before it touches anything. A moved/renamed/hijacked repo fails here instead of half-installing.
  for f in install.sh AGENTS.md hooks/command-guard.py hooks/mcp-orphans.py hooks/mcp-wrap.py hooks/tidy-procs.py hooks/tidy-scan.py hooks/pre-commit; do
    case "$f" in hooks/mcp-*|hooks/tidy-*) [ -f "$tmp/kit/$f" ] || continue ;; esac
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
    AGENT_KIT_APPLY= sh "$1/install.sh" --setup || exit $?
    rm -rf "$2"
    printf "%s\n" "------------------------------------------------------------"
    printf "%s\n" "The kit in ~/.the-agent-kit is current. Then, in each project:"
    printf "%s\n" "    ~/.the-agent-kit/install.sh --update-rules     # new rules in, your PROJECT-CONFIG kept"
  ' _ "$tmp/kit" "$tmp"
}

refresh_kit_owned() {  # $1 = repo root. Kit-NAMED rules and skills are kit-owned: a fix to
  # web-security.md must reach installed projects, or every update silently under-delivers.
  # Files under other names are the user's and are never touched.
  src=""
  [ -d "$KIT/claude/rules" ] && src="$KIT/claude/rules"
  [ -z "$src" ] && [ -d "$KIT/rules" ] && src="$KIT/rules"
  if [ -n "$src" ]; then
    for r in "$src"/*.md; do
      [ -e "$r" ] || continue
      b=$(basename "$r"); tgt="$1/.claude/rules/$b"
      if [ -e "$tgt" ] && ! cmp -s "$r" "$tgt"; then
        cp -f "$r" "$tgt"; say "  ~ refreshed .claude/rules/$b (kit-owned; local edits to kit-named files are replaced)"
      fi
    done
  fi
  ssrc=""
  [ -d "$KIT/claude/skills" ] && ssrc="$KIT/claude/skills"
  [ -z "$ssrc" ] && [ -d "$KIT/skills" ] && ssrc="$KIT/skills"
  if [ -n "$ssrc" ]; then
    for sd in "$ssrc"/*/; do
      [ -d "$sd" ] || continue
      b=$(basename "$sd")
      # 0.5.0 moved generating-reports/design.md into references/; drop the old kit-owned copy.
      [ "$b" = generating-reports ] && [ -f "$sd/references/design.md" ] && for t in .claude/skills .agents/skills; do
        [ -f "$1/$t/$b/design.md" ] && rm -f "$1/$t/$b/design.md" && say "  - removed $t/$b/design.md (moved to references/)"
      done
      # Every file in the skill, nested ones (references/) included; $fn is the path inside it.
      for fn in $(cd "$sd" && find . -type f | sed 's|^\./||'); do
        sf="$sd$fn"
        # The Codex copy of the same skill is kit-owned on the same terms.
        for t in .claude/skills .agents/skills; do
          tgt="$1/$t/$b/$fn"
          [ -L "$tgt" ] && continue   # a symlink here is not the kit's file; never write through it
          if [ -e "$tgt" ] && ! cmp -s "$sf" "$tgt"; then
            cp -f "$sf" "$tgt"; say "  ~ refreshed $t/$b/$fn (kit-owned)"
          elif [ ! -e "$tgt" ] && [ -d "$1/$t/$b" ]; then
            mkdir -p "$(dirname "$tgt")"; cp "$sf" "$tgt"; say "  + added $t/$b/$fn (new kit file)"
          fi
        done
      done
    done
  fi
  # Generated Codex skills: regenerate from the current rule text and replace on any difference, so a
  # fix to web-security.md reaches Codex projects too, not only Claude ones.
  if [ -n "$src" ]; then
    for r in "$src"/*.md; do
      [ -e "$r" ] || continue
      n=$(basename "$r" .md); d=$(codex_skill_desc "$n"); [ -n "$d" ] || continue
      tgt="$1/.agents/skills/$n/SKILL.md"; [ -e "$tgt" ] && [ ! -L "$tgt" ] || continue
      tmp=$(mktemp "$tgt.XXXXXX") || continue; rule_to_skill "$r" "$n" "$d" > "$tmp"
      if cmp -s "$tmp" "$tgt"; then rm -f "$tmp"
      else mv -f "$tmp" "$tgt"; say "  ~ refreshed .agents/skills/$n/SKILL.md (kit-owned; regenerated from $n.md)"; fi
    done
  fi
  # Antigravity's glob rules and guard launcher are kit-owned on the same terms.
  if [ -n "$src" ]; then
    for n in code-correctness tests; do
      tgt="$1/.agents/rules/$n.md"; [ -e "$tgt" ] && [ ! -L "$tgt" ] && [ -e "$src/$n.md" ] || continue
      tmp=$(mktemp "$tgt.XXXXXX") || continue; rule_to_glob "$src/$n.md" > "$tmp"
      if cmp -s "$tmp" "$tgt"; then rm -f "$tmp"
      else mv -f "$tmp" "$tgt"; say "  ~ refreshed .agents/rules/$n.md (kit-owned; regenerated from $n.md)"; fi
    done
  fi
  tgt="$1/.agents/agent-kit-guard.py"
  if [ -e "$tgt" ] && [ ! -L "$tgt" ] && tmp=$(mktemp "$tgt.XXXXXX"); then
    write_ag_launcher "$tmp"
    if cmp -s "$tmp" "$tgt"; then rm -f "$tmp"
    else mv -f "$tmp" "$tgt"; say "  ~ refreshed .agents/agent-kit-guard.py (kit-owned)"; fi
  fi
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
  # Bringing a project up to date has to mean the WHOLE kit, not just this one file. A project set up
  # before the depth tier existed has no .claude/rules, and updating only AGENTS.md would leave it
  # silently missing every path-scoped rule while reporting success.
  refresh_kit_owned "$root"
  install_path_rules "$root"
  install_skills "$root"
  install_codex_skills "$root"
  install_antigravity "$root"
}

doctor() {
  dfail=0
  hr; say "the-agent-kit --check (doctor)"
  # The compatibility tuple: a measurement or a bug report means nothing without the tool versions.
  for cli in claude codex agy; do
    v=$($cli --version 2>/dev/null | head -1)
    [ -n "$v" ] && say "  OK:   $cli = $v" || say "  NOTE: $cli not on PATH"
  done
  py=$(detect_py)
  if [ -z "$py" ]; then
    dfail=1; say "  FAIL: no working python (python3/python/py). On Windows 'python3' is often a no-op Store stub."
    say "        -> the tool-layer command-guard will NOT run. Install Python 3."
  else
    say "  OK:   python = $py"
    d=$(printf '%s' '{"tool_input":{"command":"git push"}}'         | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$d" in *'"ask"'*)  say "  OK:   command-guard fires on 'git push'" ;; *) dfail=1; say "  FAIL: command-guard emitted no decision for 'git push'" ;; esac
    f=$(printf '%s' '{"tool_input":{"command":"git push --force"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$f" in *'"deny"'*) say "  OK:   force-push is denied" ;; *) dfail=1; say "  FAIL: force-push not denied" ;; esac
    n=$(printf '%s' '{"tool_input":{"command":"git commit -an -m x"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$n" in *'"deny"'*) say "  OK:   bundled --no-verify (git commit -an) is denied" ;; *) dfail=1; say "  FAIL: bundled --no-verify (-an) NOT denied" ;; esac
    h=$(printf '%s' '{"tool_input":{"command":"git -c core.hooksPath=/x commit -m y"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$h" in *'"deny"'*) say "  OK:   -c core.hooksPath override is denied" ;; *) dfail=1; say "  FAIL: -c core.hooksPath NOT denied" ;; esac
    e=$(printf '%s' '{"tool_input":{"command":"nice -n 5 git commit --no-verify -m x"}}' | $py "$KIT/hooks/command-guard.py" --decision ask 2>/dev/null)
    case "$e" in *'"deny"'*) say "  OK:   wrapper-composed --no-verify is denied" ;; *) dfail=1; say "  FAIL: wrapper-composed --no-verify NOT denied" ;; esac
    g=$(printf '%s' '{"tool_input":{"command":"printf x >> .git/config"}}' | $py "$KIT/hooks/command-guard.py" --decision deny 2>/dev/null)
    case "$g" in *'"deny"'*) say "  OK:   direct .git/config write is flagged" ;; *) dfail=1; say "  FAIL: direct .git/config write NOT flagged" ;; esac
    a=$(printf '%s' '{"toolCall":{"name":"run_command","args":{"CommandLine":"git push --force"}}}' | $py "$KIT/hooks/command-guard.py" --tool antigravity 2>/dev/null)
    case "$a" in *'"decision": "deny"'*) say "  OK:   command-guard answers Antigravity (force-push denied)" ;; *) dfail=1; say "  FAIL: command-guard gave Antigravity no decision for a force-push" ;; esac
  fi
  for h in commit-msg pre-commit pre-push; do
    if [ -x "$KIT/hooks/$h" ]; then say "  OK:   hooks/$h present + executable"; else say "  WARN: hooks/$h missing or not executable"; fi
  done
  # The session-start check is optional (it is wired only if you merged the SessionStart snippet), so
  # its absence is a NOTE, and opting out is reported as a choice rather than a fault.
  if [ ! -f "$KIT/hooks/kit-check.py" ]; then
    say "  NOTE: hooks/kit-check.py not in this kit copy - the session-start update check is unavailable"
  elif [ "${AGENT_KIT_NO_UPDATE_CHECK:-}" = 1 ]; then
    say "  NOTE: session-start update check is switched off (AGENT_KIT_NO_UPDATE_CHECK=1)"
  else
    say "  OK:   hooks/kit-check.py present (session-start update check; wired if you merged SessionStart)"
    # The recommended-tools gaps, optional ones included, which the session reminder never carries.
    # kit-check reads ~ through USERPROFILE on Windows, so hand it the same home this script uses.
    [ -n "$py" ] && HOME="$HOME" USERPROFILE="$(nat "$HOME")" $py "$KIT/hooks/kit-check.py" --doctor 2>/dev/null || true
  fi
  for h in mcp-orphans.py mcp-wrap.py tidy-procs.py tidy-scan.py; do
    if [ -f "$KIT/hooks/$h" ]; then say "  OK:   hooks/$h present"; else say "  NOTE: hooks/$h unavailable in this kit copy"; fi
  done
  # The /tidy skill is copied into each project but its scripts live on the machine: a project installed
  # before they shipped, or cloned onto another machine, has the skill and nothing for it to run.
  if { [ -d .claude/skills/tidy ] || [ -d .agents/skills/tidy ]; } && [ ! -f "$HOME/.the-agent-kit/hooks/tidy-scan.py" ]; then
    say "  NOTE: /tidy is installed in this project but its scripts are missing; run install.sh --setup"
  fi
  if [ -n "$py" ] && [ -d "$HOME/.the-agent-kit/skills" ]; then
    wrc=0; wire_machine plan >/dev/null 2>&1 || wrc=$?
    [ "$wrc" = 10 ] && say "  NOTE: the kit's machine-wide skills (one copy in ~/.agents/skills, linked for Claude Code and Antigravity) and the Antigravity session-start check are not all in place; run install.sh --setup"
  fi
  # The settings are where the tool guard and the session-start check are wired. Checking the scripts
  # alone reported all OK on a machine whose Codex had no guard at all (2026-09-29).
  share="$HOME/.the-agent-kit"
  if [ -n "$py" ] && [ -f "$share/setup/merge-settings.py" ]; then
    src=0; m=$(merge_settings "$share" "$py" --check 2>&1) || src=$?
    case "$src" in
      0) say "  OK:   $m" ;;
      10) say "  WARN: $m - run: $share/install.sh --setup" ;;
      *) say "  WARN: $m" ;;
    esac
  fi
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
        dfail=1; say "  FAIL: $hd/$h is NOT the kit's - that guard is INACTIVE. Merge the kit's $h into it."
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
      dfail=1; say "  FAIL: AGENTS.md is $ab bytes - Codex SILENTLY truncates past 32768 (project_doc_max_bytes)."
      say "        That cap applies to the COMBINED AGENTS.md chain read root-to-leaf, so nested files count too."
    elif [ "$ab" -gt 24000 ]; then
      say "  WARN: AGENTS.md is $ab bytes - Antigravity cuts each rules file at 24000 bytes."
    else
      say "  OK:   AGENTS.md $ab bytes (Codex truncates past 32768, Antigravity each file past 24000)"
    fi
    # Claude Code docs, Memory > Write effective instructions: "target under 200 lines per CLAUDE.md
    # file. Longer files consume more context and reduce adherence." Block-level HTML comments are
    # stripped before Claude's context, so they are excluded from this count.
    # Delete self-closed one-line comments FIRST, then true multi-line comment ranges. Order is
    # load-bearing: `<!-- PROJECT-CONFIG:START -->` holds both delimiters, so a bare `/<!--/,/-->/d`
    # opened a range there and closed it at `<!-- PROJECT-CONFIG:END -->`, silently excluding the
    # project's whole config from the budget it is supposed to be counted against. That under-reported
    # this repo by 7 lines and every filled install by the size of its block (found 2026-09-26).
    al=$(sed -e '/^[[:space:]]*<!--.*-->[[:space:]]*$/d' -e '/<!--/,/-->/d' AGENTS.md 2>/dev/null | grep -c . || true)
    case "$al" in ''|*[!0-9]*) al=-1 ;; esac
    if [ "$al" -lt 0 ]; then
      :
    elif [ "$al" -gt 200 ]; then
      say "  WARN: AGENTS.md is $al effective lines - Claude Code targets under 200; adherence drops past it."
    else
      say "  OK:   AGENTS.md $al effective lines (target: under 200; HTML comments excluded: Claude Code strips them, Codex and Antigravity read them)"
    fi
    # The single highest-value anti-hallucination content is this project's REAL commands. Shipping the
    # placeholder means the agent guesses how to build, test, and verify - so say so loudly.
    if grep -q 'PROJECT-CONFIG:START' AGENTS.md 2>/dev/null && grep -q 'fill this in' AGENTS.md 2>/dev/null; then
      say "  WARN: PROJECT-CONFIG is still the empty placeholder. Without it the agent GUESSES this project's"
      say "        build / test / lint commands. Fill it via ~/.the-agent-kit/docs/project-setup-prompt.md - biggest win."
    elif grep -q 'PROJECT-CONFIG:START' AGENTS.md 2>/dev/null && ! grep -q '^\*\*Branches:\*\*' AGENTS.md 2>/dev/null; then
      # A block filled before 2026-09-26 has no branch model, and --update-rules keeps the block byte for
      # byte, so without this the gap is invisible: the agent guesses which branch takes work.
      say "  WARN: this project's block has no **Branches:** line, so the agent guesses which branch takes work"
      say "        and whether one is release-only. Re-run ~/.the-agent-kit/docs/project-setup-prompt.md to add it."
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
    # Antigravity: the guard is a workspace hook, so it is per project, not machine-wide.
    hk="absent"
    if [ -n "$py" ] && [ -f .agents/hooks.json ]; then
      hk=$($py - .agents/hooks.json <<'HKCHK' 2>/dev/null
import json, re, sys
try:
    c = json.load(open(sys.argv[1], encoding="utf-8"))["the-agent-kit"]["PreToolUse"][0]["hooks"][0]["command"]
except Exception:
    print("absent"); sys.exit(0)
print("ok" if re.fullmatch(r"(python3?|py -3) agent-kit-guard\.py --tool antigravity", str(c)) else "other")
HKCHK
)
    fi
    if [ "$hk" = ok ] && [ -f .agents/agent-kit-guard.py ] && [ ! -L .agents/agent-kit-guard.py ]; then
      say "  OK:   Antigravity guard wired (.agents/hooks.json + .agents/agent-kit-guard.py)"
      if [ ! -f "$HOME/.the-agent-kit/hooks/command-guard.py" ]; then
        say "  WARN: the launcher has no guard to call (~/.the-agent-kit/hooks/command-guard.py missing): commands pass UNCHECKED. Run install.sh --setup."
      fi
    elif [ "$hk" = other ]; then
      say "  WARN: the Antigravity guard command in .agents/hooks.json is not the kit's - it is not wired, whatever else it runs."
    elif [ -d .agents ]; then
      say "  NOTE: Antigravity guard not wired in this project - run ./install.sh --update-rules here."
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
  orphan_line=""
  if [ -n "$py" ]; then
    orphan_line=$($py "$KIT/hooks/mcp-orphans.py" --json 2>/dev/null | $py -c '
import json, sys
trees = json.load(sys.stdin)
if not isinstance(trees, list):
    sys.exit(1)
count = sum(len(t["pids"]) for t in trees)
mb = sum(t["mb"] for t in trees)
print("  WARN: %d orphaned MCP processes (%.1f MB) - run: install.sh --tidy (add --kill after reading the list)" % (count, mb) if trees else "  OK:   no orphaned MCP processes")
' 2>/dev/null) || orphan_line=""
  fi
  say "${orphan_line:-  NOTE: orphan check unavailable}"
  # A doctor that prints FAIL and exits 0 is worse than no doctor: CI and scripts read the exit code,
  # and a green exit over red text is false confidence.
  [ "$dfail" -eq 0 ] || exit 1
}

# Library mode: the adherence harness sources this file for install_codex_skills, so the Codex arm
# of the eval is built by the same code as a real install and the two cannot drift. Nothing below
# this line runs when sourced that way.
if [ "${AGENT_KIT_LIB:-0}" = 1 ]; then return 0 2>/dev/null || exit 0; fi

USAGE="Usage: ./install.sh [--setup | --update | --update-rules | --undo | --check | --tidy [--kill] [reaper options] | --extension | --global]"
case "$MODE" in
  --setup|setup)                setup_machine ;;
  --global|global)              install_global ;;
  --extension|extension)        install_extension ;;
  --update|update)              update_kit ;;
  --update-rules|update-rules)  update_rules ;;
  --undo|undo)                  wire_machine undo ;;
  --check|check|doctor)         doctor ;;
  --tidy|tidy)
    shift
    py=$(detect_py)
    [ -n "$py" ] || { say "Python 3 unavailable - cannot run orphan check"; exit 1; }
    exec $py "$KIT/hooks/mcp-orphans.py" "$@"
    ;;
  ""|project|--project)         install_project ;;
  -h|--help)                    say "$USAGE" ;;
  *) say "Unknown mode: $MODE"; say "$USAGE"; exit 2 ;;
esac

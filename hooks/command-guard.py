#!/usr/bin/env python3
"""
Command guard for Claude Code AND Codex - a best-effort PROMPT-TIME nudge, NOT a boundary.

Two events: as a PreToolUse hook it classifies a Bash command (ask / deny / allow); as a
UserPromptSubmit hook (`--event userprompt`) it reads the user's own message and records which
git-writes it authorizes for that turn (see the turn-scoped grant note above classify()).

It parses shell text, which can never fully replicate git + GNU option parsing, so it is best-effort
for EVERYTHING it does - including the two hook-disable vectors below. `bash -c`, `eval`, `$(...)`,
aliases, MCP tools, and (critically) config written as a FILE rather than a CLI token all slip past.
The REAL boundary is elsewhere and is not optional:
  - git-layer hooks (pre-push, pre-commit, commit-msg) + server-side branch protection;
  - an OS sandbox / container (the only thing that actually contains `rm -rf`, `bash -c`, etc.);
  - denying the agent write access to `.git/config` / `GIT_CONFIG_*` (a text scan can't read a file
    it never sees - `printf '[core]\nhooksPath=..' >> .git/config` disables the hooks with no
    `core.hooksPath` token anywhere in the command).
Treat every "ask"/"deny" below as reducing the odds of a careless mistake, nothing more.

It does its best to flag: `--no-verify` / `core.hooksPath` set via the CLI (anywhere in the command);
direct `.git/config` / `GIT_CONFIG_GLOBAL` writes; force/delete push; and destructive commands
(`rm -rf`, `git reset --hard`, `git clean`, `curl|sh`). Needs python3.
"""
import sys, json, re, shlex, argparse, os, tempfile

WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "xargs", "sudo", "doas",
            "env", "command", "builtin", "bash", "sh", "zsh", "exec"}
PUSH_REASON = {
    "ask":  "git push needs your approval each time (per-run, not persistent). Approve only if you asked for this push.",
    "deny": "git push is guarded on this tool - run it yourself. The agent may commit freely; pushing is left to you.",
}
# One-time, turn-scoped grants (Claude ask-mode only). See capture_intent() / load_grants().
COMMIT_ASK = "git commit: approve here, or just ask me in chat to commit. It runs without a prompt only in the same turn you request a commit."
COMMIT_OK  = "git commit: authorized by your request this turn."
PUSH_OK    = "git push: authorized by your request this turn."
PR_ASK     = "gh pr create: approve here, or ask me in chat to open the PR."
PR_OK      = "gh pr create: authorized by your request this turn."
MERGE_ASK  = "gh pr merge always needs your approval - a merge is never authorized by a chat request."
HOOKSPATH_DENY = "core.hooksPath is being set - that points git's hooks elsewhere and disables the guards. Blocked."
NOVERIFY_DENY  = "`--no-verify` skips the git guard hooks (secret scan, attribution, push guard). Blocked."
FORCE_DENY     = "force/delete push is blocked - it rewrites or removes remote history. Use the pre-push override only if truly intended."
GITCFG_DENY    = "writing git config directly (.git/config or GIT_CONFIG_GLOBAL/SYSTEM) can disable the guard hooks - review carefully."

GIT_GLOBAL_VALUE = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
                    "--config-env", "--attr-source")   # git globals that consume the NEXT token as a value
PUSH_VALUE_FLAGS = ("-o", "--push-option", "--repo", "--receive-pack", "--exec", "--recurse-submodules")
COMMIT_VALUE_FLAGS = ("-m", "--message", "-F", "--file", "-C", "-c", "--reuse-message", "--reedit-message",
                      "--author", "--date", "-t", "--template", "--fixup", "--squash", "--trailer")
PROSE_FLAGS = ("-m", "--message", "-F", "--file", "--trailer", "--author", "--date", "-t", "--template")

_NOVERIFY = re.compile(r"^--no-veri(fy?)?$", re.I)   # --no-veri / --no-verif / --no-verify only (not --no-verbose, not --no-verify.txt)


def base(tok):
    t = tok.strip("(){}")
    t = re.split(r"[\\/]", t)[-1]
    return re.sub(r"\.(exe|cmd|bat)$", "", t, flags=re.I)


def verb_tokens(tokens):
    i = 0
    while i < len(tokens):
        raw = tokens[i]
        if base(raw).lower() in WRAPPERS:
            i += 1
            while i < len(tokens) and (re.match(r"^-?\d+[a-z]?$", tokens[i]) or tokens[i] == "-u"):
                i += 2 if tokens[i] == "-u" else 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", raw):
            i += 1
            continue
        break
    return tokens[i:]


def drop_values(tokens, value_flags):
    """Every token except the values of value-taking flags - separate (`-m x`) AND glued (`-mx`, `--message=x`)."""
    longs = tuple(f for f in value_flags if f.startswith("--"))
    shorts = tuple(f for f in value_flags if len(f) == 2 and f.startswith("-"))
    out = []
    skip = False
    for a in tokens:
        if skip:
            skip = False
            continue
        if a in value_flags:
            skip = True
            out.append(a)
            continue
        if any(a.startswith(l + "=") for l in longs):      # --message=... : drop the whole glued token
            continue
        if len(a) > 2 and any(a.startswith(s) for s in shorts):  # -mTEXT : drop the whole glued token
            continue
        out.append(a)
    return out


def flags_only(args, value_flags):
    return [a for a in drop_values(args, value_flags) if a.startswith("-")]


def short_has(flags, letter):
    lo = letter.lower()
    return any(re.match(r"^-[A-Za-z]+$", a) and lo in a[1:].lower() for a in flags)


# Build output is regenerable, and `rm -rf node_modules` is routine housekeeping. Prompting for it
# every time trains you to click through the prompt without reading it - which is how the prompts
# that DO matter stop working. So this list buys back the false positives, and nothing else.
REGENERABLE = {
    "node_modules", "dist", "build", "out", "coverage", "target",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".cache",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv",
}


def regenerable_path(p):
    """True only for a relative path whose last segment is regenerable build output.

    Fails closed on everything ambiguous: a glob (it can match far more than it reads as), an
    absolute or drive-qualified or ~ path (that is not this project's build dir), and any `..`
    (which escapes the project entirely). `rm -rf ../../node_modules` is not housekeeping.
    """
    if any(ch in p for ch in "*?["):
        return False
    q = p.replace("\\", "/").rstrip("/")
    if not q or q.startswith("/") or q.startswith("~") or re.match(r"^[A-Za-z]:", q):
        return False
    segs = [s for s in q.split("/") if s and s != "."]
    if not segs or ".." in segs:
        return False
    return segs[-1] in REGENERABLE


def is_no_verify(flags):                       # git-CONTEXT use (we already know it's a git commit/push)
    return any(a.lower().startswith("--no-v") for a in flags)


def sets_hookspath(tok):                        # a token that SETS core.hooksPath (not a filename that contains it)
    t = tok.lower()
    return "core.hookspath=" in t or "=core.hookspath" in t or t == "core.hookspath"


def is_force_push(args):
    flags = flags_only(args, PUSH_VALUE_FLAGS)
    if any(a.lower().startswith("--for") or a.lower().startswith("--de") or a == "-d" for a in flags):
        return True
    if short_has(flags, "f") or short_has(flags, "d"):
        return True
    operands = [a for a in drop_values(args, PUSH_VALUE_FLAGS) if not a.startswith("-")]
    return any(a.startswith(":") or a.startswith("+") for a in operands)


# ---------------------------------------------------------------------------------------------
# Turn-scoped git-write authorization (Claude Code, ask-mode only).
#
# The user's own words are the ONLY source of a grant. A UserPromptSubmit hook (which the agent
# cannot write to) reads each message and records which of commit / push / pr the user asked for,
# keyed to the session id. The PreToolUse guard then lets exactly those operations through with no
# prompt, for that turn only. Every new user message OVERWRITES the record, so a grant never
# survives into a later turn: the agent can never commit, push or open a PR on its own initiative,
# only in the same turn you asked, or by approving the normal prompt (which is it asking you).
#
# Detection is deliberately CONSERVATIVE and fails toward the prompt: it grants only on a clear
# request and vetoes on any nearby negation or noun usage ("the commit", "the push logs"). A missed
# phrasing costs one extra prompt; it can never silently authorize something you did not plainly ask
# for. This is a convenience layer on a best-effort guard, NOT a security boundary: the temp file is
# only as trustworthy as the machine, and the real boundary stays the git-layer hooks + branch
# protection. Codex (--decision deny) never consults grants; its behaviour is unchanged.

_NEG = r"(?:do\s*n['o]?t|don['o]?t|do not|never|no need(?:\s+to)?|without|hold\s*off(?:\s+on)?|not\s+yet|wait(?:\s+to)?|skip|avoid)"
_DET = r"(?:the|this|that|these|those|a|an|last|latest|previous|prior|earlier|first|second|next|initial|original|my|your|his|her|their|our|each|every|which|whose|another|same|broken|failing|bad|wrong|old|new)"


def _grant_path(session):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", session or "")[:64] or "nosession"
    return os.path.join(tempfile.gettempdir(), "agent-kit-grant-" + sid + ".json")


def load_grants(session):
    if not session:
        return frozenset()
    try:
        with open(_grant_path(session), "r") as f:
            return frozenset(json.load(f).get("authorized", []))
    except Exception:
        return frozenset()


def save_grants(session, grants):
    if not session:
        return
    try:
        with open(_grant_path(session), "w") as f:
            json.dump({"authorized": sorted(grants)}, f)
    except Exception:
        pass


def _asked(text, v):
    """True only when `text` reads as a request to run verb `v` (commit|push), unvetoed."""
    vg = v + r"(?:e?s|ed|ing)?"
    if re.search(_NEG + r"\s+(?:\w+\s+){0,3}?" + vg + r"\b", text):                       # "don't push", "hold off on pushing"
        return False
    if re.search(r"\b" + vg + r"\b\s+(?:\w+\s+){0,3}?(?:later|yet|tomorrow|afterwards?|once|after|when)\b", text):
        return False                                                                     # "push it later"
    if re.search(r"(?:later|eventually|afterwards?)\s+(?:\S+\s+){0,4}?" + vg + r"\b", text):
        return False                                                                     # "later we'll push"
    reqs = [                                                                             # verb right after an action cue
        r"(?:can|could|would|will)\s+you\s+(?:please\s+|now\s+|then\s+|also\s+)?" + vg + r"\b",
        r"(?:^|[.!?]\s+|\bplease\b|\bnow\b|\bthen\b|\balso\b|\band\b|\bfirst\b|go\s+ahead\s+and)\s*" + vg + r"\b",
        r"let'?s\s+" + vg + r"\b",
    ]
    if any(re.search(p, text) for p in reqs):
        return True
    obj = re.search(r"\b" + vg + r"\s+(?:it|this|that|these|those|the|my|all|everything|now|up|origin|them)\b", text)
    ser = re.search(r"\b" + vg + r"\b\s*(?:,|;|\.|!|\band\b|\bthen\b|$)", text)           # "commit, push, and ..."
    if obj or ser:
        return not re.search(_DET + r"\s+" + v + r"\b", text)                            # reject noun usage "the commit"
    return False


def _asked_pr(text):
    verb = r"(?:creat(?:e|ing)|open(?:ing)?|rais(?:e|ing)|mak(?:e|ing)|submit(?:ting)?|put\s+up|send)"
    noun = r"(?:pull[\s-]*requests?|prs?|mrs?|merge[\s-]*requests?)"
    if re.search(_NEG + r"\s+(?:\w+\s+){0,4}?" + noun + r"\b", text):
        return False
    return bool(re.search(r"\b" + verb + r"\s+(?:a\s+|an\s+|the\s+)?" + noun + r"\b", text))


def _strip_pasted(s):
    """Remove quoted/pasted content before reading intent: a git verb the user QUOTED from a log,
    an issue, or a teammate's message is data, not their instruction (AGENTS.md's untrusted-content
    invariant, applied to the grant itself). Fenced blocks, blockquote lines, and inline code go."""
    s = re.sub(r"```.*?```", " ", s, flags=re.S)
    s = re.sub(r"~~~.*?~~~", " ", s, flags=re.S)
    s = re.sub(r"(?m)^\s*>.*$", " ", s)
    s = re.sub(r"`[^`]*`", " ", s)
    return s


def detect_grants(prompt):
    text = " " + _strip_pasted(prompt or "").lower().strip() + " "
    g = set()
    if _asked(text, r"commit"):
        g.add("commit")
    if _asked(text, r"push"):
        g.add("push")
    if _asked_pr(text):
        g.add("pr")
    return g


def classify(tokens, decision, grants=frozenset()):
    toks = verb_tokens(tokens)
    if not toks:
        return None
    verb = base(toks[0]).lower()
    rest = toks[1:]

    if verb == "git":
        j = 0
        while j < len(rest):
            t = rest[j]
            if not t.startswith("-"):
                break
            if "=" in t:
                j += 1
            elif t in GIT_GLOBAL_VALUE:
                j += 2
            else:
                j += 1
        sub = rest[j] if j < len(rest) else ""
        args = rest[j + 1:]
        if sub == "push":
            if is_force_push(args):
                return "deny", FORCE_DENY
            if is_no_verify(flags_only(args, PUSH_VALUE_FLAGS)):
                return "deny", NOVERIFY_DENY
            if decision == "ask":                       # Claude: silent only if you asked this turn
                return ("allow", PUSH_OK) if "push" in grants else ("ask", PUSH_REASON["ask"])
            return decision, PUSH_REASON[decision]       # Codex (deny): push is left to the human
        if sub == "commit":
            if is_no_verify(flags_only(args, COMMIT_VALUE_FLAGS)) or short_has(flags_only(args, COMMIT_VALUE_FLAGS), "n"):
                return "deny", NOVERIFY_DENY
            if decision == "ask":                       # Claude: silent only if you asked this turn
                return ("allow", COMMIT_OK) if "commit" in grants else ("ask", COMMIT_ASK)
            return None                                  # Codex (deny): commit freely, as before
        if sub == "reset" and any(a.lower().startswith("--h") for a in args):
            return decision, "`git reset --hard` irreversibly discards changes."
        if sub == "clean" and (short_has(args, "f") or any(a.lower().startswith("--f") for a in args)):
            return decision, "`git clean -f` irreversibly deletes untracked files."
        if sub in ("checkout", "restore") and any(a in (".", "./") for a in args):
            return decision, "`git %s .` discards uncommitted changes irreversibly." % sub
        # The rules name "deleting branches" as needing approval, so the guard has to actually ask.
        # Only the FORCE form: -D (or -d --force) drops an UNMERGED branch and its commits become
        # unreachable. Plain -d already refuses on unmerged work, so git gates that itself and
        # flagging it would just add noise to routine cleanup. Case matters here (-d is not -D), and
        # short_has() is deliberately case-insensitive, so this checks the flags directly.
        if sub == "branch":
            fl = flags_only(args, ())
            shorts = [a[1:] for a in fl if re.match(r"^-[A-Za-z]+$", a)]
            forced = any("D" in s for s in shorts) or (
                (any("d" in s for s in shorts) or any(a.lower() == "--delete" for a in fl))
                and (any("f" in s for s in shorts) or any(a.lower() == "--force" for a in fl))
            )
            if forced:
                return decision, "`git branch -D` force-deletes an unmerged branch; its commits become unreachable."
        return None

    if verb == "gh":                                     # gh pr create is grantable; gh pr merge always asks
        # Scan for the pr subcommand rather than assuming position: a value-taking global flag
        # (`--repo o/r`) leaves its value sitting among the operands.
        ops = [a for a in rest if not a.startswith("-")]
        if decision == "ask":
            for k in range(len(ops) - 1):
                if ops[k].lower() == "pr":
                    act = ops[k + 1].lower()
                    if act == "create":
                        return ("allow", PR_OK) if "pr" in grants else ("ask", PR_ASK)
                    if act == "merge":
                        return "ask", MERGE_ASK
        return None

    if verb == "rm":
        ftoks = flags_only(rest, ())
        letters = "".join(a[1:] for a in ftoks if re.match(r"^-[A-Za-z]+$", a)).lower()
        recursive = "r" in letters or any(a.lower().startswith("--r") for a in ftoks)
        force = "f" in letters or any(a.lower().startswith("--f") for a in ftoks)
        if recursive and force:
            # Silent ONLY when every operand is regenerable build output. One stray target - an
            # absolute path, a glob, a source dir - and the whole command asks, as before.
            targets = [a for a in rest if not a.startswith("-")]
            if targets and all(regenerable_path(t) for t in targets):
                return None
            return decision, "`rm -rf` irreversibly deletes files."
    if verb in ("dd", "mkfs") or verb.startswith("mkfs"):
        return decision, "`%s` can irreversibly destroy data." % verb
    if verb == "chmod" and any(a == "777" or a.endswith("777") or "+s" in a for a in rest):
        return decision, "over-permissive / setuid chmod."
    return None


def split_ops(cmd):
    """Split a command line into segments on shell operators (&& || ; | & newline) that sit OUTSIDE
    quotes. Best-effort, like the rest of this file, but quote-aware so a metacharacter INSIDE a
    commit message (`-m "fix; ship"`) no longer chops the command and drops it past classification -
    which mattered less when a settings ask-rule was the commit gate, and matters now that the guard
    is."""
    parts, buf, i, n, q = [], [], 0, len(cmd), None
    while i < n:
        c = cmd[i]
        if q:
            buf.append(c)
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < n:
                buf.append(cmd[i + 1]); i += 2; continue
            i += 1; continue
        if c in ("'", '"'):
            q = c; buf.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:
            buf.append(c); buf.append(cmd[i + 1]); i += 2; continue
        if cmd[i:i + 2] in ("&&", "||"):
            parts.append("".join(buf)); buf = []; i += 2; continue
        if c in ";|&\n\r":
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c); i += 1
    parts.append("".join(buf))
    return parts


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}))
    sys.exit(0)


def capture_intent(data):
    """UserPromptSubmit: record which git-writes the user's OWN message authorizes, for this turn."""
    save_grants(data.get("session_id") or "", detect_grants(data.get("prompt", "")))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision", choices=("ask", "deny"), default="ask")
    ap.add_argument("--event", choices=("pretool", "userprompt"), default="pretool")
    args, _ = ap.parse_known_args()
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)
    if args.event == "userprompt":
        capture_intent(data)
        return
    cmd = data.get("tool_input", {}).get("command", "")
    if not cmd:
        sys.exit(0)
    # Grants only exist in Claude ask-mode; Codex (deny) never consults them.
    grants = load_grants(data.get("session_id") or "") if args.decision == "ask" else frozenset()

    if re.search(r"\|\s*(sudo\s+)?(ba|z)?sh\b", cmd, re.IGNORECASE):   # curl ... | sh / SH / bash / BASH
        emit(args.decision, "piping a download straight into a shell (curl | sh) runs unreviewed code.")

    # bar-raise (NOT a boundary): direct git-config writes can point hooks elsewhere; the sandbox is the real fix
    if re.search(r"(>>?|\btee\b)\s*\S*\.git[/\\]config\b", cmd) or re.search(r"\bGIT_CONFIG_(GLOBAL|SYSTEM)\b\s*=", cmd):
        emit(args.decision, GITCFG_DENY)

    try:
        whole = [s for s in (t.strip("(){}") for t in shlex.split(cmd)) if s]
    except ValueError:
        whole = re.findall(r"\S+", cmd)

    # best-effort hook-disable scan over CLI tokens (prose values excluded so a message can't false-trip)
    scan = drop_values(whole, PROSE_FLAGS)
    if any(sets_hookspath(t) for t in scan):
        emit("deny", HOOKSPATH_DENY)
    if any(_NOVERIFY.match(t) for t in scan):
        emit("deny", NOVERIFY_DENY)

    # One Bash call gets ONE decision, so the MOST RESTRICTIVE segment must win: deny > ask > allow.
    # Without this ranking a chained command silently downgrades - `git push && git commit` with only
    # commit granted would end on `allow` and run the ungranted push promptless.
    rank = {"allow": 0, "ask": 1, "deny": 2}
    best = None
    for part in split_ops(cmd):
        try:
            toks = [s for s in (x.strip("(){}") for x in shlex.split(part)) if s]
        except ValueError:
            continue
        res = classify(toks, args.decision, grants)
        if res:
            if res[0] == "deny":
                emit(*res)
            if best is None or rank[res[0]] > rank[best[0]]:
                best = res
    if best:
        emit(*best)
    sys.exit(0)


main()

#!/usr/bin/env python3
"""
PreToolUse command guard for Claude Code AND Codex - a best-effort PROMPT-TIME nudge, NOT a boundary.

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
import sys, json, re, shlex, argparse

WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "xargs", "sudo", "doas",
            "env", "command", "builtin", "bash", "sh", "zsh", "exec"}
PUSH_REASON = {
    "ask":  "git push needs your approval each time (per-run, not persistent). Approve only if you asked for this push.",
    "deny": "git push is guarded on this tool - run it yourself. The agent may commit freely; pushing is left to you.",
}
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


def classify(tokens, decision):
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
            return decision, PUSH_REASON[decision]
        if sub == "commit" and (is_no_verify(flags_only(args, COMMIT_VALUE_FLAGS)) or short_has(flags_only(args, COMMIT_VALUE_FLAGS), "n")):
            return "deny", NOVERIFY_DENY
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


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision", choices=("ask", "deny"), default="ask")
    args, _ = ap.parse_known_args()
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        sys.exit(0)
    if not cmd:
        sys.exit(0)

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

    best = None  # deny outranks ask
    for part in re.split(r"&&|\|\||;|\||&|\n|\r", cmd):
        try:
            toks = [s for s in (x.strip("(){}") for x in shlex.split(part)) if s]
        except ValueError:
            continue
        res = classify(toks, args.decision)
        if res:
            if res[0] == "deny":
                emit(*res)
            best = res
    if best:
        emit(*best)
    sys.exit(0)


main()

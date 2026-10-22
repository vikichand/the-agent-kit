#!/usr/bin/env python3
"""
Command guard for Claude Code AND Codex - a best-effort PROMPT-TIME nudge, NOT a boundary.

Two events: as a PreToolUse hook it classifies a Bash command (ask / deny / allow); as a
UserPromptSubmit hook (`--event userprompt`) it reads the user's own message and records which
git-writes it authorizes for that turn (see the turn-scoped grant note above classify()).

It parses shell text, which can never fully replicate git + GNU option parsing, so it is best-effort
for EVERYTHING it does - including the two hook-disable vectors below. `bash -c`, `eval`, `$(...)`,
aliases, MCP tools, and (critically) config written as a FILE rather than a CLI token all slip past.
So do a flag set by sourcing a file (`. env.sh`) rather than on the command line, and a tool that fakes a
terminal (`script`, `expect`, `winpty`) to answer an installer's question.
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
OVERRIDE_ASK   = ("this sets a guard override (AGENT_KIT_RELEASE / AGENT_KIT_ALLOW_FORCE / AGENT_KIT_APPLY): it lets a "
                  "push through the pre-push hook, or lets the installer write your Claude Code and Codex settings "
                  "without asking you in a terminal. A chat request never covers it - approve only if you meant it.")
MARKER_ASK     = ("this removes the variable that tells the pre-push hook an agent is pushing (or clears the whole "
                  "environment), so the hook would treat the push as yours. Approve only if you meant it.")

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


TIDY_ASK = ("this deletes branches, worktrees or files, or kills processes, and none of it can be undone. "
            "Approve only if you chose these items in /tidy.")


_LAUNCHER = re.compile(r"^(python[\d.]*|pythonw[\d.]*|py|pypy[\d.]*|uv|uvx|pipx)$")
# Launcher options that consume the NEXT token; its value (`-X pycache_prefix=a.py`, `--with-requirements r.py`)
# is not the script. Not exhaustive: an unlisted value flag whose value ends in .py still hides the script.
_VALUE_OPTS = {"-X", "-W", "-c", "-m", "-p", "-f", "--with", "--with-requirements", "--with-editable", "--python",
               "--project", "--directory", "--env-file", "--package", "--extra", "--group", "--index", "--spec",
               "--pip-args", "--find-links"}
_PS_CMD = re.compile(r"^-c(o(m(m(a(n(d)?)?)?)?)?)?$", re.I)


def has_word(rest, word):
    """`word` as its own token, or glued to a redirect/operator (`apply>out.txt` is one shlex token)."""
    return any(t == word or re.match(re.escape(word) + r"[<>|&;]", t) for t in rest)


def shell_payload(prog, toks):
    """Segments a Windows shell wrapper runs (`cmd /c ...`, `pwsh -Command ...`), as token lists, or None."""
    if prog == "cmd":
        i = next((k for k, t in enumerate(toks) if k and t.lower() in ("/c", "/k")), None)
    elif prog in ("pwsh", "powershell"):
        i = next((k for k, t in enumerate(toks) if k and _PS_CMD.match(t)), None)
    else:
        return None
    if i is None:
        return None
    rest = toks[i + 1:]
    out = []
    for part in split_ops(rest[0] if len(rest) == 1 else " ".join(rest)):   # a quoted payload is ONE token
        try:
            out.append([s for s in (x.strip("(){}") for x in shlex.split(part)) if s])
        except ValueError:
            out.append(part.split())
    return out


def kit_destructive(toks):
    """The kit's own cleanup scripts, in the step that removes things: tidy-scan/tidy-procs `apply` and
    mcp-orphans `--kill`. Only the command's own script counts: the program itself, or the
    first .py/.sh argument of a python launcher (`uv run python`, `py -3`) that is not an option or an
    option's value, or the payload of a `cmd /c` / `pwsh -Command` wrapper. A tidy name sitting in another
    command's arguments (`git push -o tidy-scan.py -o apply`) is not a tidy run. Matched by file name, so
    unquoted Windows paths (shlex eats their backslashes) are seen. A --dry-run is NOT exempt: a token that
    only reads like one (a redirect target: `apply ... > --dry-run`) would buy silence, and one extra
    prompt on a dry run is cheap."""
    prog = base(toks[0]).lower()
    inner = shell_payload(prog, toks)
    if inner is not None:
        return any(t and kit_destructive(verb_tokens(t) or [""]) for t in inner)
    if prog.endswith((".py", ".sh")):
        i = 0
    elif _LAUNCHER.match(prog):
        i, skip = None, False
        for k, t in enumerate(toks[1:], 1):
            if skip:
                skip = False
            elif t.startswith("-"):
                skip = t in _VALUE_OPTS
            elif "=" not in t and base(t).lower().endswith((".py", ".sh")):
                i = k
                break
        if i is None:
            return False
    else:
        return False
    name, rest = base(toks[i]).lower(), toks[i + 1:]
    if name.endswith(("tidy-scan.py", "tidy-procs.py")):
        return has_word(rest, "apply")
    if name.endswith("mcp-orphans.py"):
        return has_word(rest, "--kill")
    if name.endswith("install.sh"):                 # --tidy --kill execs mcp-orphans.py
        return has_word(rest, "--tidy") and has_word(rest, "--kill")
    return False


def classify(tokens, decision, grants=frozenset()):
    res = _classify(tokens, decision, grants)
    if res:
        return res                                   # every deny (and other ask) wins over the tidy prompt
    toks = verb_tokens(tokens)
    # Codex hooks cannot ask ("permissionDecision: ask ... parsed but not supported yet"), and a deny would
    # break /tidy there, so this is Claude and Antigravity only.
    if toks and decision == "ask" and kit_destructive(toks):
        return "ask", TIDY_ASK
    return None


def _classify(tokens, decision, grants):
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


# A heredoc that feeds `git commit -F -` or `git tag -F -` IS the commit message: prose that git stores
# and never runs. Tokenizing it as commands made a message that merely MENTIONED core.hooksPath get
# refused (observed 2026-09-21), and a body line reading "git push --force" would have been classified as
# a force push. Only the message form is stripped: `sh <<EOF`, `python <<EOF` and every other heredoc is
# code and keeps being scanned, and a real command after the terminator is scanned as usual.
# An UNQUOTED delimiter still expands the body, so `$(...)` and backticks in it run: such a body is
# stripped only when it has neither. A quoted delimiter ('EOF' or "EOF") makes the body inert.
_MSG_HEREDOC = re.compile(
    r"(\bgit\b[^\n]*?\b(?:commit|tag)\b[^\n]*?(?:-F\s*-(?=\s|$)|--file[=\s]-(?=\s|$))[^\n]*?"
    r"<<(-?)\s*(['\"]?)(\w+)\3[^\n]*\n)"          # 1: the header line, 2: '-' for <<-, 3: quote, 4: delimiter
    r"(.*?)"                                         # 5: the body
    r"(^\t*\4[ \t]*$)",                            # 6: the terminator (<<- may indent it with tabs)
    re.S | re.M)


def strip_message_heredocs(cmd):
    def strip(m):
        if not m.group(3) and ("$(" in m.group(5) or "`" in m.group(5)):
            return m.group(0)
        return m.group(1) + m.group(6)
    return _MSG_HEREDOC.sub(strip, cmd)


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


OVERRIDE_VAR = re.compile(r"AGENT_KIT_(?:RELEASE|ALLOW_FORCE|APPLY)$")
# The pre-push hook refuses AGENT_KIT_ALLOW_FORCE in a shell carrying one of these; an agent that removes
# its marker makes its push look like yours.
MARKER_VAR = re.compile(r"(?:CLAUDE_CODE_CHILD_SESSION|CODEX_THREAD_ID|ANTIGRAVITY_CONVERSATION_ID)$")
PS_ENV_SET = {"set-item", "si", "new-item", "ni", "set-content", "sc", "add-content", "ac"}
PS_ENV_WRITE = {"remove-item", "ri", "del", "erase", "rm", "rd", "rmdir", "clear-item", "cli",
                "clear-content", "clc"} | PS_ENV_SET
SHELL_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "time"}
_ASSIGN = re.compile(r"^([A-Za-z_]\w*)(?:\[[^\]]*\])?\+?=(.*)$", re.S)   # X=v, X+=v, X[0]=v


def _var_hit(name, removing=False):
    if MARKER_VAR.match(name):
        return "marker"
    return None if removing or not OVERRIDE_VAR.match(name) else "override"


def _assign_hit(tok):
    """A NAME=value word: setting an override, or emptying a marker (a non-empty marker still marks)."""
    m = _ASSIGN.match(tok)
    if not m:
        return None
    h = _var_hit(m.group(1))
    return h if h == "override" or (h == "marker" and not m.group(2)) else None


def env_tamper(cmd, depth=0):
    """'override' when a command sets a pre-push override, 'marker' when it removes an agent's marker,
    else None. Read per command, by its name and arguments, so a commit message, a grep pattern or an
    echo that only mentions a variable is not taken for setting it.
    ponytail: literal names only; indirection (unset ${x}_ID), string building ("AGENT_KIT_"+"RELEASE"),
    interpreters (os.environ.pop), wildcards (env:CODEX*), here-strings, tmux, git aliases and the registry
    get through. The force-push deny and the pre-push hook stay behind it."""
    for part in split_ops(cmd):
        try:
            toks = [s for s in (t.strip("(){}") for t in shlex.split(part)) if s]
        except ValueError:
            toks = part.split()
        hit = _tamper(toks, depth) if toks else None
        if hit:
            return hit
    return None


def _tamper(toks, depth):
    joined = " ".join(toks)
    m = re.search(r"SetEnvironmentVariable\(\s*([A-Za-z_]\w*)", joined, re.I)   # .NET, persists with 'User'
    if m and _var_hit(m.group(1)):
        return _var_hit(m.group(1))
    m = re.match(r"^\$\{?env:([A-Za-z_]\w*)\}?\s*(=)?", toks[0], re.I)            # PowerShell $env:X = v
    if m and (m.group(2) or (len(toks) > 1 and toks[1].startswith("="))):
        return _var_hit(m.group(1))
    i = 0
    while i < len(toks):                                                          # X=v, wrappers, env, sh -c
        t, b = toks[i], base(toks[i]).lower()
        if _ASSIGN.match(t):
            if _assign_hit(t):
                return _assign_hit(t)
        elif b == "env":
            return _env_tamper(toks[i + 1:], depth)
        elif b in ("sh", "bash", "zsh", "dash"):
            rest = toks[i + 1:]
            k = next((j for j, a in enumerate(rest) if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a)), -1)   # -c, -lc
            return env_tamper(rest[k + 1], depth + 1) if 0 <= k < len(rest) - 1 and depth < 3 else None
        elif b not in WRAPPERS and b not in SHELL_KEYWORDS and not re.match(r"^-?\d+[a-z]?$", t):
            break
        i += 1
    verb = toks[i:]
    if not verb:
        return None
    prog, rest = base(verb[0]).lower(), verb[1:]
    payload = shell_payload(prog, verb)
    if payload is not None:
        return next((h for h in (_tamper(p, depth + 1) for p in payload if p) if h), None) if depth < 3 else None
    if prog == "eval" and depth < 3:
        return env_tamper(" ".join(rest), depth + 1)
    if prog == "unset":
        return next((h for h in (_var_hit(a, removing=True) for a in rest) if h), None)
    if prog in ("export", "declare", "typeset", "readonly", "set"):
        if (prog == "set" and rest and rest[0] in ("-e", "--erase")) or "-n" in rest or "+x" in rest:
            # fish set -e X; export -n X and declare +x X stop passing X to the commands that follow
            return next((h for h in (_var_hit(a, removing=True) for a in rest if a[0] not in "-+") if h), None)
        words = [a for a in rest if not a.startswith("-")]
        for j, a in enumerate(words):                                             # X=v, fish set -x X v
            h = _assign_hit(a) if "=" in a else _var_hit(a) if prog == "set" and j + 1 < len(words) else None
            if h:
                return h
        return None
    if prog == "setx":
        names = [a for a in rest if not a.startswith("/")]
        return _var_hit(names[0]) if names else None
    if prog in PS_ENV_WRITE:
        for a in rest:
            m = re.match(r"^(?:-(?:literal)?path:)?env:\\?([A-Za-z_]\w*)$", a, re.I)
            if m:
                return _var_hit(m.group(1), removing=prog not in PS_ENV_SET)
        return None
    return None


def _env_tamper(rest, depth):
    """`env [-i|-] [-u X] [X=v] cmd ...`: removing a marker, setting an override, or clearing it all for a push."""
    clears, i = False, 0
    while i < len(rest):
        a = rest[i]
        if a in ("-i", "-", "--ignore-environment"):
            clears = True
        elif a in ("-u", "--unset") and i + 1 < len(rest):
            i += 1
            if _var_hit(rest[i], removing=True):
                return "marker"
        elif a.startswith("--unset=") or (a.startswith("-u") and len(a) > 2):
            if _var_hit(a.split("=", 1)[-1] if "=" in a else a[2:], removing=True):
                return "marker"
        elif _ASSIGN.match(a):
            if _assign_hit(a):
                return _assign_hit(a)
        elif not a.startswith("-"):
            inner = rest[i:]
            if clears and re.search(r"\bpush\b", " ".join(inner)):               # also env -i sh -c "git push"
                return "marker"
            return _tamper(inner, depth + 1) if depth < 3 else None
        i += 1
    return None


ANTIGRAVITY = False   # set by --tool antigravity: its PreToolUse contract differs from Claude's and Codex's


def emit(decision, reason):
    if ANTIGRAVITY:
        # Plain "ask" honours cached Always-Allow grants; force_ask makes each push its own question.
        print(json.dumps({"decision": "force_ask" if decision == "ask" else decision, "reason": reason}))
        sys.exit(0)
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
    ap.add_argument("--tool", choices=("claude", "codex", "antigravity"), default="claude")
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
    if args.tool == "antigravity":
        global ANTIGRAVITY
        ANTIGRAVITY = True
        args.decision = "ask"   # Antigravity can ask the user; there are no turn grants (no prompt hook)
        call = data.get("toolCall")
        call = call if isinstance(call, dict) and call.get("name") == "run_command" else {}
        cmd = (call.get("args") or {}).get("CommandLine", "")
    else:
        cmd = data.get("tool_input", {}).get("command", "")
    if not isinstance(cmd, str) or not cmd:
        sys.exit(0)
    cmd = strip_message_heredocs(cmd)   # a commit message is data, not commands (see _MSG_HEREDOC)
    # Grants only exist in Claude ask-mode; Codex (deny) never consults them.
    grants = load_grants(data.get("session_id") or "") if args.decision == "ask" else frozenset()

    # The pre-push overrides. Asked every time, never covered by a grant: a release push to a
    # release-only branch, or a forced push, is the owner's act, not something a chat request authorizes.
    # Matched with quotes and backslashes removed: A""GENT_KIT_RELEASE=1 is the same assignment to the shell.
    if re.search(r"(?:^|[\s;&|(])(?:export\s+)?AGENT_KIT_(?:RELEASE|ALLOW_FORCE|APPLY)\s*=",
                 re.sub(r"[\"'\\]", "", cmd)):
        emit(args.decision, OVERRIDE_ASK)
    tamper = env_tamper(cmd)   # PowerShell, .NET, setx, fish, wrappers; and removing an agent's marker
    if tamper == "override":
        emit(args.decision, OVERRIDE_ASK)
    if tamper == "marker":
        emit(args.decision, MARKER_ASK)

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

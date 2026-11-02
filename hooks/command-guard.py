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
import sys, json, re, shlex, argparse, os, posixpath

WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "xargs", "sudo", "doas",
            "env", "command", "builtin", "bash", "sh", "zsh", "exec"}
# Options of a wrapper that consume the NEXT token. Without them `timeout -s KILL 60 git push --force`
# read KILL as the command and the push went unseen.
WRAPPER_VALUE = {
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "env": {"-u", "--unset", "-C", "--chdir"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-R", "--user", "--group", "--chdir"},
    "doas": {"-u", "-C"},
    "xargs": {"-I", "-n", "-L", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter"},
    "time": {"-f", "-o", "--format", "--output"},
    "exec": {"-a"},
}
PUSH_REASON = {
    "ask":  "git push needs your approval each time (per-run, not persistent). Approve only if you asked for this push.",
    "deny": "git push is guarded on this tool: run it yourself. Pushing is left to you.",
}
# One-time, turn-scoped grants (Claude ask-mode only). See capture_intent() / load_grants().
PUSH_OK    = "git push: authorized by your request this turn."
PR_ASK     = "gh pr create: approve here, or ask me in chat to open the PR."
PR_OK      = "gh pr create: authorized by your request this turn."
PR_DENY    = "opening or merging a pull request is guarded on this tool: run it yourself, like a push."
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
        w = base(raw).lower()
        if w in WRAPPERS:
            i += 1
            while i < len(tokens) and (tokens[i].startswith("-") or re.match(r"^\d+[a-z]?$", tokens[i])):
                t = tokens[i]
                split = (tokens[i + 1] if t in ("-S", "--split-string") and i + 1 < len(tokens) else
                         t[2:] if t.startswith("-S") and len(t) > 2 else
                         t.split("=", 1)[1] if t.startswith("--split-string=") else None)
                if w == "env" and split is not None:
                    rest = tokens[i + (1 if t in ("-S", "--split-string") else 0) + 1:]
                    try:                                   # env -S 'git push --force': the value IS the command
                        return verb_tokens(shlex.split(split) + rest)
                    except ValueError:
                        return split.split() + rest
                i += 2 if tokens[i] in WRAPPER_VALUE.get(w, ()) else 1
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


# A recursive delete runs without a prompt when every target is inside the project (the session's
# working directory) or the temp folder. main() sets CWD, and turns RELATIVE_OK off when the command
# also changes directory to anywhere it cannot place inside them.
CWD = ""
CMD = ""
_KEEP = {".git", ".claude", ".codex", ".agents", ".gemini", ".ssh", ".gnupg", ".aws"}
SHELL_KEYWORDS = ("if", "then", "else", "elif", "do", "while", "until", "!", "time")
VARS = None
RELATIVE_OK = True
_ROOTS = []


def _norm(p):
    """An absolute path in one comparable form: forward slashes, Git Bash's /c/ as c:/, `..` resolved."""
    q = p.replace("\\", "/")
    if os.name == "nt":
        q = re.sub(r"^/([A-Za-z])(?=/|$)", r"\1:", q).lower()
    return posixpath.normpath(q)


def safe_roots():
    if not _ROOTS:
        import tempfile  # here, not at the top: it costs 12 ms and only a recursive delete needs it
        home = _norm(os.path.expanduser("~"))
        # No cwd from the host: only the temp folder. The hook's own working folder could be anywhere.
        for r in map(_norm, ([CWD] if CWD else []) + [tempfile.gettempdir(), "/tmp"]):
            # A session opened in home, a drive root or above home would make everything "the project".
            if r != home and not home.startswith(r + "/") and posixpath.dirname(r) != r \
                    and not re.fullmatch(r"[a-z]:/?", r, re.I):
                _ROOTS.append(r)
    return _ROOTS


def shell_vars():
    """Variables the command sets to one literal or to a plain `mktemp`, and the temp folder's own names.
    A name set twice to different values, or to anything else, stays unknown."""
    if VARS is None:
        import tempfile
        tmp = tempfile.gettempdir().replace("\\", "/")
        found = {"TEMP": tmp, "TMP": tmp, "TMPDIR": tmp}
        for m in re.finditer(r"(?:^|[\s;&|(])(?:export\s+)?([A-Za-z_]\w*)=(?:\"?\$\(\s*mktemp\b([^)]*)\)\"?"
                             r"|\"([^\"$`]*)\"|'([^']*)'|([^\s;&|$`'\"()]*))(?=$|[\s;&|)])", CMD):
            if m.group(2) is not None:   # mktemp -p DIR / --tmpdir=DIR can create anywhere
                val = None if re.search(r"(^|\s)(-p|--tmpdir)", m.group(2)) else tmp + "/mktemp"
            else:
                val = next(g for g in m.group(3, 4, 5) if g is not None)
                # Globs and braces expand, and a value with a space splits wherever $x is used unquoted.
                if re.search(r"[*?\[{},\\]", val) or (re.search(r"\s", val) and any(
                        CMD[:u.start()].count('"') % 2 == 0 for u in re.finditer(r"\$\{?%s\b" % m.group(1), CMD))):
                    val = None
            found[m.group(1)] = val if found.get(m.group(1), val) == val else None
        for name in found:   # set again some other way: `read x`, `for x in`, `unset x`, `x+=`, ...
            if re.search(r"\b(?:read|unset|declare|typeset|local|let|readonly|for|select|getopts|mapfile)\b"
                         r"[^;&|\n]*\b%s\b|\b%s\+=" % (name, name), CMD):
                found[name] = None
        globals()["VARS"] = found
    return VARS


def contained(p):
    """True when deleting p cannot reach outside the project or the temp folder, and p is neither."""
    if "{}" in CMD:     # find -exec / xargs -I fill in `{}`: the real target is unknown
        return False
    if "$" in p:
        v = shell_vars()
        p = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: v.get(m.group(1) or m.group(2)) or "\0", p)
    q = p.replace("\\", "/")
    # An unknown variable, ~, brace expansion or a PowerShell list (`x,D:\y`) can name anything.
    if not q or any(ch in q for ch in "\0$`~{},"):
        return False
    # A colon past a drive letter is a provider or another drive (HKCU:\, FileSystem::D:\, Cert:\).
    if ":" in (q[2:] if re.match(r"^[A-Za-z]:", q) else q):
        return False
    segs = q.split("/")
    # `...` or `.. ` can read as `..` on Windows; the kit's own folders and secrets always ask.
    if any(re.fullmatch(r"[. ]+", s) and s not in (".", "..") or s.lower() in _KEEP or s.lower().startswith(".env")
           for s in segs):
        return False
    if any(ch in q for ch in "*?["):
        # A glob only in the last segment, after a literal first character: `e2e-*` is a family of
        # entries, while `*` is everything and `.*` can reach `..`.
        head, _, last = q.rpartition("/")
        if not re.fullmatch(r"[\w-][^/]*", last) or any(ch in head for ch in "*?["):
            return False
        q = head + "/x" if head else "x"
    if q.startswith("/") or re.match(r"^[A-Za-z]:", q):
        n = _norm(q)
        return any(n.startswith(r + "/") for r in safe_roots())
    segs = [s for s in q.split("/") if s and s != "."]
    return RELATIVE_OK and bool(segs) and ".." not in segs and bool(CWD) and _norm(CWD) in safe_roots()


# PowerShell's delete commands and aliases. `rm` is not here: as a POSIX command it keeps the -rf rule above.
PS_REMOVE = {"remove-item", "ri", "del", "erase", "rd", "rmdir"}
PS_REMOVE_VALUE = ("-path", "-literalpath", "-filter", "-include", "-exclude")
# Commands that print a file's contents. A secret file read with one of them lands in the transcript.
READERS = {"cat", "type", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "bat", "nl", "xxd",
           "od", "strings", "base64", "awk", "sed", "cut", "sort", "get-content", "gc", "select-string", "sls",
           "findstr", "format-hex"}
_TEMPLATE = (".example", ".sample", ".template", ".dist", ".defaults", ".schema")


def secret_path(p):
    """The same files the Claude settings ask before reading: .env and its variants (templates excepted),
    keys and certificates, cloud and package-manager credentials, and anything under a secrets folder."""
    q = p.replace("\\", "/").strip("'\"").rstrip("/")
    segs = [x for x in q.lower().split("/") if x]
    if not segs:
        return False
    b = segs[-1]
    if b.endswith(".pub"):
        return False
    if b == ".env" or (b.startswith(".env.") and not b.endswith(_TEMPLATE)):
        return True
    if b.endswith((".pem", ".p12", ".pfx")) or b in ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
                                                    ".npmrc", ".netrc", ".pgpass", "credentials"):
        return b != "credentials" or ".aws" in segs
    return "secrets" in segs[:-1] or ".gnupg" in segs[:-1]


def is_no_verify(flags):                       # git-CONTEXT use (we already know it's a git commit/push)
    return any(a.lower().startswith("--no-v") for a in flags)


def sets_hookspath(tok):                        # a token that SETS core.hooksPath (not a filename that contains it)
    t = tok.lower()
    return "core.hookspath=" in t or "=core.hookspath" in t or t == "core.hookspath"


_SCOPE = r"(?:[ \t]+--(?:global|local|system|worktree|show-origin|no-includes))*"
_HP_READ = re.compile(r"[ \t]*git[ \t]+config" + _SCOPE + r"[ \t]+(?:--get|--get-all|get)" + _SCOPE + r"[ \t]+core\.hookspath[ \t\r\n]*", re.I)


def hookspath_read_only(cmd):                   # the whole command is one plain read: nothing chained can hide a write
    return bool(_HP_READ.fullmatch(cmd))


def is_force_push(args):
    flags = flags_only(args, PUSH_VALUE_FLAGS)
    if any(a.lower().startswith(("--for", "--de", "--mir", "--pru")) or a == "-d" for a in flags):
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
# survives into a later turn: the agent can never push or open a PR on its own initiative, only in
# the same turn you asked, or by approving the normal prompt (which is it asking you). A local commit
# needs no grant: it is undoable and never leaves the machine, so it runs without a prompt.
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
    import tempfile  # here, not at the top: it costs 12 ms on every guarded call and only grants need it
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
        # A write that fails must not leave the previous turn's grant live: no record means no grant.
        try:
            os.remove(_grant_path(session))
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


GRANT_ASK = "this names the kit's turn-grant file, which only the prompt hook should write. Approve only if you meant it."
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


SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}


def inner_commands(cmd):
    """The command strings that a shell, eval or Windows shell in `cmd` runs. `bash -c 'git push -f'` holds
    its command in one quoted word, which every check would otherwise read as a single name. Matched
    anywhere in a segment, so `echo bash -c '...'` is read too: the cost is a prompt, never a miss."""
    out = []
    for part in split_ops(cmd):
        try:
            toks = shlex.split(part)
        except ValueError:
            continue
        for i, t in enumerate(toks):
            prog = base(t).lower()
            if prog == "eval":
                out.append(" ".join(toks[i + 1:]))
            elif prog in ("cmd", "pwsh", "powershell"):
                out += [shlex.join(s) for s in shell_payload(prog, toks[i:]) or ()]
            elif prog in SHELLS:
                j = i + 1
                while j < len(toks) and toks[j][:1] in "-+":
                    if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", toks[j]):      # -c, -lc, -xc
                        if j + 1 < len(toks):
                            out.append(toks[j + 1])
                        break
                    j += 2 if toks[j] in ("-o", "+o", "-O", "+O") else 1   # set -o pipefail takes a value
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
    if toks and decision == "ask":
        pkg = added_dependency(toks)
        if pkg:
            return "ask", DEP_ASK % pkg
    return None


# Package managers and the subcommands that add a package when they name one. A bare or flags-only
# install (`npm install`, `pnpm install --frozen-lockfile`) installs what the lockfile declares.
_ADDERS = {"npm": ("install", "i", "add", "in"), "pnpm": ("install", "i", "add"), "yarn": ("add",),
           "bun": ("install", "i", "add", "a"), "pip": ("install",), "pip3": ("install",), "uv": ("add",),
           "cargo": ("add", "install"), "go": ("install", "get"), "gem": ("install",), "poetry": ("add",),
           "pipx": ("install", "run"), "bundle": ("add",), "deno": ("add", "install"), "dotnet": ("package",)}
# Not -w: npm's takes a workspace name but pnpm's is a switch, so it stays a token and npm's
# `-w ws` reads `ws` as the package. That over-asks; it never lets a package through unasked.
_DEP_VALUE = ("-r", "--requirement", "-c", "--constraint", "--workspace", "--filter", "-C", "--dir", "--cwd",
              "--prefix", "--path", "--registry", "--target", "-t")
DEP_ASK = ("this adds a dependency (%s). Approve after checking it is the real, maintained package you want: "
           "typo-squatted names are a live attack.")


def added_dependency(toks):
    """The package a command adds, or None. `uv pip install` and `python -m pip install` count as pip."""
    verb = base(toks[0]).lower()
    rest = toks[1:]
    if _LAUNCHER.match(verb) and rest[:2] == ["-m", "pip"]:
        verb, rest = "pip", rest[2:]
    if re.fullmatch(r"pip\d*(?:\.\d+)?", verb):
        verb = "pip"
    if verb == "uv" and rest[:1] in (["pip"], ["tool"]):        # uv pip install / uv tool install
        verb, rest = ("pip" if rest[0] == "pip" else "pipx"), rest[1:]
    if verb == "dotnet" and rest[:1] == ["add"]:                 # dotnet add [project] package x
        rest = rest[1:]
        rest = rest[rest.index("package"):] if "package" in rest else []
    ops, skip = [], False
    for a in drop_values(rest, _DEP_VALUE):
        redirect = re.match(r"^\d*(?:>>?|<)(.*)$", a)   # `2>&1`, `> log.txt`, `>/dev/null`
        if skip or redirect:
            skip = bool(redirect) and not redirect.group(1)
            continue
        if not a.startswith("-"):
            ops.append(a)
    if verb not in _ADDERS or not ops or ops[0] not in _ADDERS[verb]:
        return None
    # A local path (`./packages/ui`, `file:./CMS`) is the project's own code, not a registry package.
    pkgs = [a for a in ops[1:] if not re.match(r"^(?:file:|link:|portal:)?(?:\.{1,2}(?:/|$)|/)", a)]
    return pkgs[0] if pkgs else None


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
            return None                                  # local and undoable: no prompt on any tool
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
        if decision == "deny":                           # Codex: no grants and no ask, so like a push
            for k in range(len(ops) - 1):
                if ops[k].lower() == "pr" and ops[k + 1].lower() in ("create", "merge"):
                    return "deny", PR_DENY
            return None
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
            # Silent only when every operand is build output or sits inside the project or the temp
            # folder. One target that could reach outside them and the whole command asks.
            targets = [a for a in rest if not a.startswith("-")]
            if targets and all(regenerable_path(t) or contained(t) for t in targets):
                return None
            return decision, "`rm -rf` irreversibly deletes files."
    if verb in PS_REMOVE or (POWERSHELL and verb == "rm"):   # in PowerShell, rm is Remove-Item
        fl = [a.lower().split(":")[0] for a in rest if a.startswith("-")]      # -Recurse:$true
        cmd_s = verb in ("rd", "rmdir", "del", "erase") and any(a.lower() == "/s" for a in rest)
        if cmd_s or any(len(a) > 1 and "-recurse".startswith(a) for a in fl):
            targets = [a for a in drop_values(rest, PS_REMOVE_VALUE)
                       if not a.startswith("-") and not re.match(r"^/[A-Za-z]$", a)]
            if targets and all(regenerable_path(t) or contained(t) for t in targets):
                return None
            return decision, "`%s -Recurse` irreversibly deletes a folder and everything in it." % toks[0]
    if verb in READERS:
        hit = next((a for a in rest if not a.startswith("-") and secret_path(a)), None)
        if hit:
            return decision, "this reads `%s`, a file that holds secrets. Approve only if you meant to show it." % hit
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
        line = m.string[m.string.rfind("\n", 0, m.start()) + 1:m.end(1)]
        if line.count("<<") > 1:                         # `bash <<B; git commit -F - <<A`: B's body runs first
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
POWERSHELL = False    # set for Claude Code's PowerShell tool, where rm is Remove-Item


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
    try:
        grants = detect_grants(data.get("prompt", ""))
    except Exception:
        grants = frozenset()   # a crash here must fail towards "nothing authorized", never keep the last turn's grant
    save_grants(data.get("session_id") or "", grants)
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
        ti = data.get("tool_input")
        cmd = ti.get("command", "") if isinstance(ti, dict) else ""
    if not isinstance(cmd, str) or not cmd:
        sys.exit(0)
    if data.get("tool_name") == "PowerShell":
        global POWERSHELL
        POWERSHELL = True
        # PowerShell's escape is the backtick (`--force is --force, a trailing ` continues the line) and its
        # backslash is a path separator, which the POSIX parsing below would eat: .\.env must stay .env.
        cmd = re.sub(r"`(.)", r"\1", re.sub(r"`\r?\n", "", cmd)).replace("\\", "/")
    cmd = strip_message_heredocs(cmd)   # a commit message is data, not commands (see _MSG_HEREDOC)
    cmd = re.sub(r"\\\r?\n", "", cmd)    # the shell joins a backslash-newline: `push \<newline>--force` is one word list
    # What `bash -c`, eval, `cmd /c` and `pwsh -Command` run is checked as its own lines, three levels deep.
    todo = [cmd]
    for _ in range(3):
        todo = [c for s in todo for c in inner_commands(s)]
        if not todo:
            break
        cmd += "\n" + "\n".join(todo)
    # The grant file is written by the prompt hook. A command that names it could forge a grant. This
    # raises the bar for an accident only: the agent's shell can write any file this hook can.
    if re.search(r"agent-kit-grant", cmd, re.I):
        emit(args.decision, GRANT_ASK)
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

    # curl ... | sh / SH / bash / BASH, and PowerShell's iwr ... | iex. Only a download feeding the shell:
    # `grep "a|sh.exe"` and `printf y | sh install.sh` run nothing fetched.
    if re.search(r"\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod|downloadstring|net\.webclient)\b[^\n;]*"
                 r"\|\s*(?:(sudo\s+)?(ba|z)?sh|iex|invoke-expression)\b", cmd, re.IGNORECASE):
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
    # `git config --get core.hooksPath` only reads it. Only that exact command passes, alone: one extra
    # operand or flag (`--comment --get core.hooksPath /x`) or a chained, quote-split write can set it.
    if not hookspath_read_only(cmd) and any(sets_hookspath(t) for t in scan):
        emit("deny", HOOKSPATH_DENY)
    if any(_NOVERIFY.match(t) for t in scan):
        emit("deny", NOVERIFY_DENY)

    # One Bash call gets ONE decision, so the MOST RESTRICTIVE segment must win: deny > ask > allow.
    # Without this ranking a chained command silently downgrades - `git push && git commit` with only
    # commit granted would end on `allow` and run the ungranted push promptless.
    global CWD, CMD, RELATIVE_OK
    CWD = data.get("cwd") if isinstance(data.get("cwd"), str) else ""
    CMD = cmd
    for part in split_ops(cmd):                      # `cd / && rm -rf usr` is not a delete inside the project
        try:
            raw = [s for s in (x.strip("(){}") for x in shlex.split(part)) if s]
        except ValueError:
            RELATIVE_OK = False                      # unreadable: it may change directory
            continue
        while raw and raw[0] in SHELL_KEYWORDS:
            raw = raw[1:]                            # `if true; then cd /; rm -rf x; fi`
        if any(a in ("-C", "--chdir", "--cd") or a.startswith(("--chdir=", "--cd=")) for a in raw):
            RELATIVE_OK = False                      # `env -C / rm -rf x`, `wsl --cd /`
        t = verb_tokens(raw)
        if t and base(t[0]).lower() in ("cd", "pushd", "popd", "chdir", "set-location", "sl", "push-location"):
            dest = [a for a in t[1:] if not a.startswith("-")]
            if not dest or not contained(dest[0].rstrip("/\\") + "/x"):   # the folder itself, or inside
                RELATIVE_OK = False
    rank = {"allow": 0, "ask": 1, "deny": 2}
    best = None
    for part in split_ops(cmd):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()     # unbalanced quotes: read the words anyway, never skip the segment
        # An option keeps its braces: stripping `xargs -I{}` to `-I` made it take `git` as its value.
        toks = [s for s in (x.strip("()" if x.startswith("-") else "(){}") for x in words) if s]
        while toks and toks[0] in SHELL_KEYWORDS:       # `for i in 1; do rm -rf /; done`
            toks = toks[1:]
        res = classify(toks, args.decision, grants)
        if res:
            if res[0] == "deny":
                emit(*res)
            if best is None or rank[res[0]] > rank[best[0]]:
                best = res
    if best:
        emit(*best)
    sys.exit(0)


try:
    main()
except SystemExit:
    raise
except Exception:
    # Fail closed on a host without onFailure: an unexpected crash asks (Codex, which cannot ask, denies).
    emit("deny" if "deny" in sys.argv else "ask", "the command guard could not read this command, so it stops it for you to check.")

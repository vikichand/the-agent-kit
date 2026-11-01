#!/usr/bin/env python3
"""Install, update or uninstall the-agent-kit's entries on a machine, from one install record.

Run by install.sh, never by an agent on its own: the installer asks the user first.

  machine.py install|uninstall|check --home H --share S --share-cmd C --py P [--apply]

Everything the kit puts in a place it shares with the user (settings files, git's global config, the
skill folders, Antigravity's config) is an ENTRY, and ~/.the-agent-kit/.install-record.json lists every
entry the kit installed, with the value it wrote. Every install is an uninstall of the old kit followed
by an install of the new one:
  1. an entry in the record that the current kit no longer ships is removed, unless its value is no
     longer the one the kit wrote: then it is the user's, left and reported
  2. each entry the current kit ships, by the three-way rule (dpkg conffiles): absent -> added; still
     what the kit recorded -> updated to the current kit's value; changed by the user -> left and
     reported. A kit-owned folder or file (a skill copy, its link, Antigravity's launcher) is the
     kit's whatever is in it, so drift there is replaced, never left
  3. the record is rewritten to what is installed now
uninstall is step 1 with nothing shipped. check plans and reports without writing. Nothing that is not
the kit's is removed or changed: a folder without the kit's mark, a link pointing elsewhere, a hook whose
command merely mentions a kit script, a core.hooksPath another tool set.

A machine set up before records existed has none: that one run counts as the kit's what an older kit is
known to have written (legacy_owned) and writes the first record.

Exit: 0 nothing to change (or applied), 10 changes pending (not applied), 1 something could not be done.
Standard library only; Codex's config.toml needs Python 3.11 or later (tomllib).
"""
import argparse, copy, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

RECORD = ".install-record.json"
ABSENT = object()

# Kit-owned means the whole command IS the kit script: an optional interpreter, then the script, then
# plain flags. A user's own command that merely mentions the script (a wrapper, a chain) is the user's.
KIT_HOOK = re.compile(r'^\s*(?:\S+\s+(?:-3\s+)?)?(?:"[^"]*|\S*)\.the-agent-kit[\\/]+hooks[\\/]+([\w.-]+\.py)"?'
                      r'(?:\s+--?[\w-]+(?:\s+[\w-]+)?)*\s*$')
# Rules older kits shipped and this one does not, per list: always removed (a rule identical to one the
# kit shipped in that list is the kit's, whoever typed it), and the only rules besides the current
# template's a record entry may name. When the template drops a rule, add it here;
# test/shipped_history.py fails a release that forgets.
# Write(...) rules: Claude Code ignores them, warning on every start, since Edit rules cover all
# file-editing tools (code.claude.com/docs/en/permissions). The tool-runner and package-install rules
# prompted on everyday commands in every mode, with no time limit, so unattended runs stalled on them.
# The git add/commit/push asks became the command guard's turn grants.
RETIRED = {
    "ask": ("Write(**/AGENTS.md)", "Write(**/CLAUDE.md)",
            "Bash(npx *)", "Bash(bunx *)", "Bash(pnpm dlx *)", "Bash(uvx *)",
            "Bash(npm install)", "Bash(npm ci)", "Bash(npm ci *)", "Bash(yarn install)", "Bash(bun install)",
            "Bash(pnpm install)", "Bash(npm install *)", "Bash(npm i *)", "Bash(npm add *)", "Bash(pnpm add *)",
            "Bash(pnpm install *)", "Bash(yarn add *)", "Bash(bun add *)", "Bash(bun install *)",
            "Bash(pip install *)", "Bash(pip3 install *)", "Bash(python -m pip install *)",
            "Bash(python3 -m pip install *)", "Bash(uv add *)", "Bash(uv pip install *)", "Bash(cargo install *)",
            "Bash(cargo add *)", "Bash(go install *)", "Bash(gem install *)",
            "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)"),
    # The secret-file reads were denies until 2026-08-20, then became asks (still in the template): a
    # deny left behind overrides the ask, so the agent cannot read a secret even when you approve it.
    "deny": ("Write(**/.git/config)", "Write(**/.git/hooks/**)",
             "Read(./.env)", "Read(**/.env)", "Read(**/.env.local)", "Read(**/.env.*.local)",
             "Read(**/.env.production)", "Read(**/.env.production.*)", "Read(**/*.pem)", "Read(**/id_rsa)",
             "Read(**/id_ed25519)", "Read(**/.ssh/id_*)", "Read(**/.aws/credentials)", "Read(**/.gnupg/**)",
             "Read(**/.npmrc)", "Read(**/.netrc)", "Read(**/secrets/**)"),
}
# Hook matchers older kits shipped, keyed by the current one (legacy_owned only). The guard first matched
# only Bash, which left Claude Code's PowerShell tool unguarded.
OLD_MATCHERS = {"Bash|PowerShell": ("Bash",)}
# Every settings key and config.toml key any kit has shipped. A record entry may only name one of these
# (or one the current templates ship): the record lives in a folder an agent can write to, so it is never
# trusted to say what else is the kit's. Add a key here when the templates gain one; keep it when they drop it.
KIT_KEYS = ("attribution", "includeGitInstructions", "worktree")
KIT_TOML = (("", "approval_policy"), ("", "sandbox_mode"), ("sandbox_workspace_write", "network_access"))
NAME = re.compile(r"^(?!\.)[\w.-]+$")   # a skill name: never "." or "..", never hidden
# The skills older kits shipped, before the record: only these names may be taken as an older kit's copy.
LEGACY_SKILLS = ("generating-reports", "orchestrating-work", "tidy", "writing-docs")
MARK = ".the-agent-kit"            # a file inside every skill folder the kit copied
MARK_TEXT = "This folder is a copy made by the-agent-kit's install.sh; install refreshes it and uninstall removes it.\n"
SJ_PATH = "~/.agents/skills"       # Antigravity's skills.json entry for the one real copy
HOOK_KEY = "the-agent-kit-check"   # Antigravity's global hooks.json entry (the project one is "the-agent-kit")
LAUNCH_SIG = b"# The Agent Kit: launcher for the session-start check"   # first line of every launcher shipped
AG_CMD = re.compile(r"(python3?|py -3) agent-kit-check\.py --tool antigravity")


# ---- small helpers ---------------------------------------------------------------------------------

def canon(cmd):
    """One spelling for the same command: a hand merge may write `C:\\x` or `c:/x` for `C:/x`. Comparing
    raw strings rewrote working files over spelling. A Git Bash `/c/x` is not folded in: under
    MSYS_NO_PATHCONV=1 Python gets it unconverted, so that hook never starts and is rewritten."""
    c = (cmd or "").replace("\\", "/")
    return re.sub(r'(^|[\s"\'])([A-Z]):/', lambda m: m.group(1) + m.group(2).lower() + ":/", c)


def kit_script(cmd):
    m = KIT_HOOK.match(cmd or "") if isinstance(cmd, str) else None
    return m.group(1) if m else None


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
    os.makedirs(os.path.dirname(link), exist_ok=True)
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


def tree_hash(p):
    """A digest of every file under p except the kit's mark, so a copy compares equal to its source."""
    h = hashlib.sha256()
    for d, dirs, fs in sorted(os.walk(p)):
        dirs.sort()
        for f in sorted(fs):
            full = os.path.join(d, f)
            rel = os.path.relpath(full, p).replace(os.sep, "/")
            if rel == MARK:
                continue
            h.update(rel.encode() + b"\0")
            with open(full, "rb") as fh:
                h.update(fh.read() + b"\0")
    return h.hexdigest()


def file_hash(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def mark_for(n):
    return MARK_TEXT + "skill: %s\n" % n


def marked(p):
    """The kit's mark is inside, and p is a real folder (a link to a folder is never the kit's copy)."""
    return os.path.isfile(os.path.join(p, MARK)) and not is_link(p)


def write_atomic(path, data, stamp, binary=False):
    """Back the file up beside itself, then replace it in one rename: a kill mid-write never leaves it half
    written. Two runs in one second never overwrite the first backup."""
    if os.path.exists(path):
        bak, n = "%s.bak-agent-kit-%s" % (path, stamp), 1
        while os.path.exists(bak):
            n += 1; bak = "%s.bak-agent-kit-%s-%d" % (path, stamp, n)
        shutil.copy2(path, bak)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".agent-kit.", suffix=".tmp")
    with os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8", "newline": "\n"})) as f:
        f.write(data)
    os.replace(tmp, path)


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    raise ValueError("unsupported value in the kit's config.toml: %r" % (v,))


# ---- the machine -----------------------------------------------------------------------------------

class Machine:
    def __init__(self, home, share, share_cmd, py):
        self.home, self.share, self.share_cmd, self.py = home, share, share_cmd, py
        self.claude = os.path.join(home, ".claude")
        self.codex = os.path.join(home, ".codex")
        self.cfg = os.path.join(home, ".gemini", "config")
        self.canon_root = os.path.join(home, ".agents", "skills")
        self.claude_skills = os.path.join(self.claude, "skills")
        self.files = {}              # path -> parsed content (dict for JSON, text for TOML), loaded once
        self.errors = {}             # path -> why it cannot be read safely: its entries are skipped
        self.dirty = set()           # paths whose content changed and must be written
        self.notes = []              # things left as they are, reported
        self.warnings = []           # what could not be installed because something of the user's is in the way
        self.ops = []                # (label, description, thunk) for files and folders outside the JSON/TOML ones
        self.removed = []            # record entries this run takes out
        self.left = set()            # idents of kit entries left as they are because the user changed them

    # -- loading -------------------------------------------------------------------------------------
    def load(self, path, kind):
        if path in self.files or path in self.errors:
            return self.files.get(path)
        try:
            if os.path.islink(path):
                raise ValueError("it is a symlink")
            text = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8-sig") as f:
                    text = f.read()
            if kind == "toml":
                import tomllib
                tomllib.loads(text)
                self.files[path] = text
            else:
                data = json.loads(text) if text.strip() else {}
                if not isinstance(data, dict):
                    raise ValueError("the top level is not an object")
                self.files[path] = data
        except ImportError:
            self.errors[path] = "needs Python 3.11+ to merge (tomllib); copy the kit's codex/config.toml settings by hand"
        except Exception as e:   # a file we cannot read safely is reported and left exactly as it was
            self.errors[path] = str(e) or e.__class__.__name__
        return self.files.get(path)

    def template(self, rel, cmd_path):
        with open(os.path.join(self.share, rel), encoding="utf-8") as f:
            # Escaped as JSON string content: a native Windows path carries backslashes.
            esc = lambda s: json.dumps(s)[1:-1]
            return json.loads(f.read().replace("__AGENT_KIT__", esc(cmd_path)).replace("__PY__", esc(self.py)))

    # -- what the current kit ships ------------------------------------------------------------------
    def desired(self):
        out = []
        if os.path.isdir(self.claude):
            f = os.path.join(self.claude, "settings.json")
            t = self.template(os.path.join("claude", "settings.json"), self.share_cmd)
            for lst in ("ask", "deny"):
                out += [{"kind": "rule", "file": f, "list": lst, "value": r} for r in t.get("permissions", {}).get(lst, [])]
            out += self.hook_entries(f, t)
            out += [{"kind": "key", "file": f, "key": k, "value": v} for k, v in t.items() if k not in ("permissions", "hooks")]
        if os.path.isdir(self.codex):
            # Codex runs a hook on Windows through cmd.exe, where /c/x is not C:/x: the native path (--share).
            f = os.path.join(self.codex, "hooks.json")
            out += self.hook_entries(f, self.template(os.path.join("codex", "hooks.json"), self.share))
            try:
                import tomllib
                with open(os.path.join(self.share, "codex", "config.toml"), "rb") as fh:
                    kit = tomllib.load(fh)
                f = os.path.join(self.codex, "config.toml")
                for k, v in kit.items():
                    if isinstance(v, dict):
                        out += [{"kind": "toml", "file": f, "table": k, "key": kk, "value": vv} for kk, vv in v.items()]
                    else:
                        out.append({"kind": "toml", "file": f, "table": "", "key": k, "value": v})
            except ImportError:
                self.notes.append("~/.codex/config.toml: needs Python 3.11+ to merge; copy the kit's codex/config.toml settings by hand")
        out.append({"kind": "git", "key": "core.hooksPath", "value": os.path.join(self.share, "git-hooks").replace("\\", "/")})
        src = os.path.join(self.share, "skills")
        names = sorted(n for n in (os.listdir(src) if os.path.isdir(src) else []) if os.path.isfile(os.path.join(src, n, "SKILL.md")))
        for n in names:
            out.append({"kind": "dir", "path": os.path.join(self.canon_root, n), "src": os.path.join(src, n),
                        "name": n, "value": tree_hash(os.path.join(src, n))})
            if os.path.isdir(self.claude):
                out.append({"kind": "link", "path": os.path.join(self.claude_skills, n), "value": os.path.join(self.canon_root, n)})
            if os.path.isdir(self.cfg):
                out.append({"kind": "listitem", "file": os.path.join(self.cfg, "skills.json"), "value": n})
        launch_src = os.path.join(self.share, "hooks", "agent-kit-check.py")
        if os.path.isdir(self.cfg) and os.path.isfile(launch_src) and os.path.isfile(os.path.join(self.share, "hooks", "kit-check.py")):
            out.append({"kind": "file", "path": os.path.join(self.cfg, "agent-kit-check.py"), "src": launch_src, "value": file_hash(launch_src)})
            out.append({"kind": "agentry", "file": os.path.join(self.cfg, "hooks.json"), "key": HOOK_KEY,
                        "value": {"PreInvocation": [{"type": "command", "command": self.py + " agent-kit-check.py --tool antigravity", "timeout": 10}]}})
        return out

    def hook_entries(self, f, t):
        return [{"kind": "hook", "file": f, "event": ev, "script": kit_script(h.get("command")),
                 "value": {"matcher": b.get("matcher"), "hook": h}}
                for ev, blocks in t.get("hooks", {}).items() for b in blocks for h in b.get("hooks", [])]

    # -- identity and current value ------------------------------------------------------------------
    @staticmethod
    def ident(e):
        k = e["kind"]
        if k == "rule":
            return (k, norm(e["file"]), e["list"], e["value"])
        if k == "hook":
            return (k, norm(e["file"]), e["event"], e["script"])
        if k in ("key", "agentry"):
            return (k, norm(e["file"]), e["key"])
        if k == "toml":
            return (k, norm(e["file"]), e["table"], e["key"])
        if k == "git":
            return (k, e["key"])
        if k == "listitem":
            return (k, norm(e["file"]), e["value"].casefold())
        return (k, norm(e["path"]).casefold() if os.name == "nt" else norm(e["path"]))

    def find_hook(self, data, e):
        """(block, hook) of the kit's hook for e's script in e's event, or None."""
        for b in (data.get("hooks", {}) or {}).get(e["event"], []) or []:
            if isinstance(b, dict):
                for h in b.get("hooks", []) or []:
                    if isinstance(h, dict) and kit_script(h.get("command")) == e["script"]:
                        return b, h
        return None

    def hook_value(self, e, b, h):
        exact = norm(e["file"]) == norm(os.path.join(self.codex, "hooks.json"))
        hv = dict(h)
        if not exact:
            hv["command"] = canon(hv.get("command"))
        return {"matcher": b.get("matcher") if len(b.get("hooks", [])) == 1 else e["value"]["matcher"], "hook": hv}

    def command(self, e, v):
        if e["kind"] == "hook":
            c = v["hook"].get("command")
            return c if norm(e["file"]) == norm(os.path.join(self.codex, "hooks.json")) else canon(c)
        return v["PreInvocation"][0].get("command")

    def same(self, e, cur, val):
        if e["kind"] == "hook" and cur is not ABSENT:
            exact = norm(e["file"]) == norm(os.path.join(self.codex, "hooks.json"))
            v = copy.deepcopy(val)
            if not exact:
                v["hook"]["command"] = canon(v["hook"].get("command"))
            return cur == v
        if e["kind"] == "git" and cur is not ABSENT:
            return canon(cur).rstrip("/") == canon(val).rstrip("/")
        return cur == val

    def current(self, e):
        """The entry's value as it is now, ABSENT, or None when its file cannot be read (skip it)."""
        k = e["kind"]
        if k in ("rule", "hook", "key", "listitem", "agentry"):
            data = self.load(e["file"], "json")
            if data is None:
                return None
            if k == "rule":
                lst = (data.get("permissions") or {}).get(e["list"]) or []
                return e["value"] if e["value"] in lst else ABSENT
            if k == "hook":
                found = self.find_hook(data, e)
                return ABSENT if found is None else self.hook_value(e, *found)
            if k == "key":
                return data[e["key"]] if e["key"] in data else ABSENT
            if k == "agentry":
                if e["key"] not in data:
                    return ABSENT
                v = data[e["key"]]
                h = v.get("PreInvocation") if isinstance(v, dict) and list(v) == ["PreInvocation"] else None
                ok = (isinstance(h, list) and len(h) == 1 and isinstance(h[0], dict)
                      and AG_CMD.fullmatch(str(h[0].get("command", ""))) is not None)
                return v if ok else "not-the-kit's"
            mine = self.sj_entry(data)
            if mine is not None and "include_only" not in mine:
                return e["value"]        # the entry exposes the whole folder: the kit's skills are already in it
            names = mine.get("include_only") if mine else None
            return e["value"] if isinstance(names, list) and e["value"] in names else ABSENT
        if k == "toml":
            text = self.load(e["file"], "toml")
            if text is None:
                return None
            import tomllib
            d = tomllib.loads(text)
            d = d if not e["table"] else d.get(e["table"])
            return d[e["key"]] if isinstance(d, dict) and e["key"] in d else ABSENT
        if k == "git":
            r = subprocess.run(["git", "config", "--global", "--get", e["key"]], capture_output=True, text=True)
            return r.stdout.strip() or ABSENT
        if k == "dir":
            p = e["path"]
            if not os.path.lexists(p):
                return ABSENT
            return tree_hash(p) if marked(p) else "not-the-kit's"
        if k == "link":
            p = e["path"]
            if not os.path.lexists(p):
                return ABSENT
            return e["value"] if is_link(p) and points_to(p, e["value"]) else "not-the-kit's"
        if k == "file":
            p = e["path"]
            if not os.path.lexists(p):
                return ABSENT
            if os.path.islink(p):
                return "not-the-kit's"
            with open(p, "rb") as f:
                head = f.read()
            return hashlib.sha256(head).hexdigest() if head.startswith(LAUNCH_SIG) else "not-the-kit's"
        return None

    def sj_entry(self, data):
        home = self.home
        for e in data.get("entries", []) if isinstance(data.get("entries"), list) else []:
            if isinstance(e, dict) and isinstance(e.get("path"), str) and (
                    e["path"].rstrip("/\\") == SJ_PATH
                    or norm(os.path.expanduser(e["path"].replace("~/", home + "/", 1))) == norm(self.canon_root)):
                return e
        return None

    # -- changing an entry ---------------------------------------------------------------------------
    def set(self, e):
        k = e["kind"]
        if k in ("rule", "hook", "key", "listitem", "agentry"):
            data = self.files[e["file"]]
            if k == "rule":
                lst = data.setdefault("permissions", {}).setdefault(e["list"], [])
                if e["value"] not in lst:
                    lst.append(e["value"])
            elif k == "hook":
                self.set_hook(data, e)
            elif k in ("key", "agentry"):
                data[e["key"]] = copy.deepcopy(e["value"])
            else:
                if not isinstance(data.get("entries"), list):
                    data["entries"] = []
                mine = self.sj_entry(data)
                if mine is None:
                    data["entries"].append({"path": SJ_PATH, "include_only": [e["value"]]})
                elif isinstance(mine.get("include_only"), list) and e["value"] not in mine["include_only"]:
                    mine["include_only"].append(e["value"])
            self.dirty.add(e["file"])
        elif k == "toml":
            self.set_toml(e)
        elif k == "git":
            self.ops.append(("git", lambda: subprocess.run(["git", "config", "--global", e["key"], e["value"]], check=True)))
        elif k == "dir":
            self.ops.append(("copy " + e["name"], lambda: self.copy_dir(e)))
        elif k == "link":
            self.ops.append(("link " + os.path.basename(e["path"]), lambda: self.relink(e)))
        elif k == "file":
            self.ops.append(("write " + os.path.basename(e["path"]), lambda: self.write_file(e)))

    def remove(self, e):
        k = e["kind"]                    # a listitem is removed with the others in its file: drop_listitems
        if k in ("rule", "hook", "key", "agentry"):
            data = self.files[e["file"]]
            if k == "rule":
                lst = (data.get("permissions") or {}).get(e["list"]) or []
                lst[:] = [r for r in lst if r != e["value"]]
            elif k == "hook":
                found = self.find_hook(data, e)
                if found:
                    b, h = found
                    b["hooks"].remove(h)
                    blocks = data["hooks"][e["event"]]
                    if not b["hooks"]:
                        blocks.remove(b)
                    if not blocks:
                        del data["hooks"][e["event"]]
            else:
                data.pop(e["key"], None)
            self.dirty.add(e["file"])
        elif k == "toml":
            self.drop_toml(e)
        elif k == "git":
            self.ops.append(("git", lambda: subprocess.run(["git", "config", "--global", "--unset", e["key"]], check=True)))
        elif k == "dir":
            self.ops.append(("remove " + os.path.basename(e["path"]), lambda: self.rm_dir(e)))
        elif k == "link":
            self.ops.append(("unlink " + os.path.basename(e["path"]), lambda: self.unlink(e)))
        elif k == "file":
            self.ops.append(("remove " + os.path.basename(e["path"]), lambda: self.rm_file(e)))

    def drop_listitems(self, f, names, changes, why):
        data = self.files.get(f)
        mine = self.sj_entry(data) if isinstance(data, dict) else None
        if mine is None or not isinstance(mine.get("include_only"), list):
            return
        left = [n for n in mine["include_only"] if n not in names]
        if left == mine["include_only"]:
            return
        if not left and set(mine) - {"path", "include_only"}:
            # An empty include_only may mean "everything", and the entry carries the user's own keys.
            self.warnings.append("%s: the ~/.agents/skills entry carries settings of yours; left as it is, with"
                                 " the kit's skill names in it (remove them by hand)" % self.where({"kind": "listitem", "file": f}))
            return
        if left:
            mine["include_only"] = left
        else:
            data["entries"].remove(mine)
        self.dirty.add(f)
        for n in names:
            changes.append((self.where({"kind": "listitem", "file": f}), "-", "remove skills.json name %s%s" % (n, why)))

    def set_hook(self, data, e):
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError('"hooks" is not an object')
        want = copy.deepcopy(e["value"]["hook"])
        found = self.find_hook(data, e)
        if found:
            b, h = found
            if len(b.get("hooks", [])) == 1:   # the kit's own block: update it in place, matcher too
                h.clear(); h.update(want)
                if e["value"]["matcher"] is not None:
                    b["matcher"] = e["value"]["matcher"]
                return
            b["hooks"].remove(h)               # a block shared with the user's hooks keeps their matcher
        nb = {"matcher": e["value"]["matcher"]} if e["value"]["matcher"] is not None else {}
        nb["hooks"] = [want]
        hooks.setdefault(e["event"], []).append(nb)

    def fill_hook(self, e):
        """A kit hook the user changed keeps their values; a field the kit added later (onFailure, timeout)
        still reaches it. To opt out of a field, set it to the value you want."""
        data = self.files[e["file"]]
        found = self.find_hook(data, e)
        if not found:
            return []
        b, h = found
        done = []
        missing = {k: v for k, v in e["value"]["hook"].items() if k not in h}
        if missing:
            h.update(copy.deepcopy(missing)); self.dirty.add(e["file"])
            done.append("added " + ", ".join(sorted(missing)))
        want = e["value"]["matcher"]
        if len(b.get("hooks", [])) == 1 and b.get("matcher") in OLD_MATCHERS.get(want, ()):
            done.append("matcher %s to %s" % (b["matcher"], want))
            b["matcher"] = want; self.dirty.add(e["file"])
        return done

    # TOML: changed only as text, one plain `key = value` line at a time, and the result must parse to
    # exactly the settings expected, so nothing of the user's can change.
    def toml_edit(self, e, new_line):
        import tomllib
        text = self.files[e["file"]]
        before = tomllib.loads(text)
        lines, cur, at, header = text.split("\n"), "", None, None
        for i, line in enumerate(lines):
            m = re.match(r"\s*\[\s*([^\]\[]+?)\s*\]\s*(#.*)?$", line)
            if m:
                cur = m.group(1)
                if cur == e["table"]:
                    header = i
                continue
            if re.match(r"\s*\[\[", line):
                cur = None; continue
            if cur == e["table"] and re.match(r"\s*%s\s*=" % re.escape(e["key"]), line):
                if at is not None:
                    return False
                at = i
        if at is not None:
            lines[at:at + 1] = [new_line] if new_line is not None else []
        elif new_line is None:
            return True
        elif not e["table"]:
            lines[0:0] = ["# the-agent-kit", new_line]   # top-level keys must come before the first [table]
        elif header is not None:
            lines[header + 1:header + 1] = [new_line]
        else:
            lines += ["", "# the-agent-kit", "[%s]" % e["table"], new_line]
        new = "\n".join(lines)
        if new and not new.endswith("\n"):
            new += "\n"
        expect = copy.deepcopy(before)
        sect = expect if not e["table"] else expect.setdefault(e["table"], {})
        if new_line is None:
            sect.pop(e["key"], None)
        else:
            sect[e["key"]] = e["value"]
        try:
            ok = tomllib.loads(new) == expect
        except tomllib.TOMLDecodeError:
            ok = False
        if ok:
            self.files[e["file"]] = new; self.dirty.add(e["file"])
        return ok

    def set_toml(self, e):
        if not self.toml_edit(e, "%s = %s" % (e["key"], toml_value(e["value"]))):
            self.notes.append("left %s in ~/.codex/config.toml: not one plain line to change; set it by hand" % self.label(e))

    def drop_toml(self, e):
        if not self.toml_edit(e, None):
            self.notes.append("left %s in ~/.codex/config.toml: not one plain line to remove" % self.label(e))

    # Folders and files outside the settings: done in order, after the plan is agreed.
    def copy_dir(self, e):
        dst, src = e["path"], e["src"]
        tmp = dst + ".agent-kit-new"
        if os.path.lexists(tmp):         # we cannot tell who made it, so we never delete it
            raise OSError("%s already exists; left as it is (remove it to retry)" % tmp)
        shutil.copytree(src, tmp, symlinks=True)   # a link inside a kit skill is copied as a link, never followed
        with open(os.path.join(tmp, MARK), "w", encoding="utf-8") as f:
            f.write(mark_for(e["name"]))
        old = None
        if os.path.lexists(dst):
            if not marked(dst):          # re-checked here: it may have changed since the plan was made
                shutil.rmtree(tmp, ignore_errors=True)
                raise OSError("%s is no longer the kit's copy; left as it is" % dst)
            old = dst + ".agent-kit-old"
            if os.path.lexists(old):     # left by an interrupted run: removed only when it is the kit's copy
                if not marked(old):
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise OSError("%s already exists and is not the kit's; left as it is (remove it to retry)" % old)
                shutil.rmtree(old)
            os.rename(dst, old)          # aside first: a failed swap puts the old copy back, never loses it
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.rename(tmp, dst)
        except OSError:
            if old:
                os.rename(old, dst)
            raise
        if old:
            shutil.rmtree(old)

    def rm_dir(self, e):
        p = e["path"]
        if os.path.lexists(p) and marked(p):   # re-checked: it may have changed since the plan
            shutil.rmtree(p)

    def relink(self, e):
        p = e["path"]
        if os.path.lexists(p):           # planned only where nothing was: something appeared since
            raise OSError("%s appeared since the plan; left as it is" % p)
        make_link(p, e["value"])

    def unlink(self, e):
        p = e["path"]
        if os.path.lexists(p) and is_link(p) and points_to(p, e["value"]):   # only a link to the kit's copy
            drop_link(p)

    def write_file(self, e):
        p = e["path"]
        if os.path.lexists(p):           # replace only the kit's own launcher
            if os.path.islink(p) or not os.path.isfile(p):
                raise OSError("%s is not the kit's launcher; left as it is" % p)
            with open(p, "rb") as f:
                if not f.read(len(LAUNCH_SIG)).startswith(LAUNCH_SIG):
                    raise OSError("%s is not the kit's launcher; left as it is" % p)
        with open(e["src"], "rb") as f:
            data = f.read()
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".agent-kit.", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)

    def rm_file(self, e):
        p = e["path"]
        if os.path.isfile(p) and not os.path.islink(p):
            with open(p, "rb") as f:
                ours = f.read(len(LAUNCH_SIG)).startswith(LAUNCH_SIG)
            if ours:                     # closed first: Windows will not delete a file that is open
                os.remove(p)

    def valid(self, e, desired):
        """Does this record entry point at one of the kit's own places? Anything else (another file,
        another git key, a folder outside ~/.agents/skills, the permissions or hooks objects) is refused."""
        if not isinstance(e, dict) or not isinstance(e.get("kind"), str):
            return False
        claude = os.path.join(self.claude, "settings.json")
        same = lambda a, b: isinstance(a, str) and norm(a) == norm(b)
        k = e["kind"]
        try:
            if k == "rule":
                rules = set(RETIRED.get(e["list"], ())) | {d["value"] for d in desired if d["kind"] == "rule" and d["list"] == e["list"]}
                return same(e["file"], claude) and e["list"] in ("ask", "deny") and e["value"] in rules
            if k == "hook":
                return ((same(e["file"], claude) or same(e["file"], os.path.join(self.codex, "hooks.json")))
                        and isinstance(e["event"], str) and isinstance(e["script"], str)
                        and re.match(r"^[\w.-]+\.py$", e["script"]) is not None
                        and (e["value"] is None or isinstance(e["value"], dict)))
            if k == "key":
                keys = set(KIT_KEYS) | {d["key"] for d in desired if d["kind"] == "key"}
                return same(e["file"], claude) and e["key"] in keys and e["key"] not in ("permissions", "hooks")
            if k == "toml":
                keys = set(KIT_TOML) | {(d["table"], d["key"]) for d in desired if d["kind"] == "toml"}
                return same(e["file"], os.path.join(self.codex, "config.toml")) and (e["table"], e["key"]) in keys
            if k == "git":
                return (e["key"] == "core.hooksPath" and isinstance(e["value"], str)
                        and canon(e["value"]).rstrip("/").endswith("/.the-agent-kit/git-hooks"))
            if k == "dir":
                return (isinstance(e["name"], str) and NAME.match(e["name"]) is not None
                        and same(e["path"], os.path.join(self.canon_root, e["name"])))
            if k == "link":
                n = os.path.basename(e["path"]) if isinstance(e["path"], str) else ""
                return (NAME.match(n) is not None and same(e["path"], os.path.join(self.claude_skills, n))
                        and same(e["value"], os.path.join(self.canon_root, n)))
            if k == "listitem":
                return (same(e["file"], os.path.join(self.cfg, "skills.json")) and isinstance(e["value"], str)
                        and NAME.match(e["value"]) is not None)
            if k == "agentry":
                return same(e["file"], os.path.join(self.cfg, "hooks.json")) and e["key"] == HOOK_KEY
            if k == "file":
                return same(e["path"], os.path.join(self.cfg, "agent-kit-check.py"))
        except (KeyError, TypeError, ValueError):
            return False
        return False

    # -- ownership on a machine with no record -------------------------------------------------------
    def legacy_owned(self, e, cur):
        """With no record, is this present value what an older kit wrote? Only what the kit is known to
        have written counts; anything else is the user's."""
        k = e["kind"]
        if k in ("hook", "agentry"):
            return cur != "not-the-kit's"   # its whole command is the kit's script (KIT_HOOK, AG_CMD)
        if k in ("rule", "listitem"):
            return True                  # identical to what the kit ships: whoever typed it, it is the kit's
        if k in ("key", "toml"):
            return self.same(e, cur, e["value"])
        if k == "git":
            return canon(cur).rstrip("/").endswith("/.the-agent-kit/git-hooks")
        if k == "dir":
            return cur != "not-the-kit's" and (e.get("name") in LEGACY_SKILLS or marked(e["path"]))
        if k in ("link", "file"):
            return cur != "not-the-kit's"
        return False

    def legacy_record(self):
        """What an older kit left that this one no longer ships: its retired rules and any hook whose
        command runs a kit script this kit does not ship for that event."""
        out = []
        f = os.path.join(self.claude, "settings.json")
        data = self.load(f, "json") if os.path.isdir(self.claude) else None
        if data is not None:
            for lst, retired in RETIRED.items():
                for r in (data.get("permissions") or {}).get(lst) or []:
                    if r in retired:
                        out.append({"kind": "rule", "file": f, "list": lst, "value": r})
        for d, f in ((self.claude, os.path.join(self.claude, "settings.json")), (self.codex, os.path.join(self.codex, "hooks.json"))):
            data = self.load(f, "json") if os.path.isdir(d) else None
            if not isinstance(data, dict):
                continue
            for ev, blocks in (data.get("hooks") or {}).items() if isinstance(data.get("hooks"), dict) else []:
                for b in blocks if isinstance(blocks, list) else []:
                    for h in (b.get("hooks") or []) if isinstance(b, dict) else []:
                        s = kit_script(h.get("command")) if isinstance(h, dict) else None
                        if s:
                            e = {"kind": "hook", "file": f, "event": ev, "script": s, "value": None}
                            out.append(e)
        return out

    @staticmethod
    def label(e):
        k = e["kind"]
        if k == "rule":
            return "%s rule %s" % (e["list"], e["value"])
        if k == "hook":
            return "%s hook %s" % (e["event"], e["script"])
        if k in ("key", "agentry"):
            return e["key"]
        if k == "toml":
            return ("[%s] " % e["table"] if e["table"] else "") + e["key"]
        if k == "git":
            return e["key"]
        if k == "listitem":
            return "skills.json name %s" % e["value"]
        return os.path.basename(e["path"])

    def where(self, e):
        p = e.get("file") or e.get("path") or ""
        if e["kind"] == "git":
            return "git config --global"
        return "~/" + os.path.relpath(os.path.dirname(p) if e["kind"] in ("dir", "link") else p, self.home).replace("\\", "/")


def plan(m, action, record):
    """(changes, new_record_entries). Each change is (where, sign, text) and is already applied to the
    in-memory files and queued in m.ops; nothing is written until apply().

    What the kit owns comes from two sources: the record (what this kit wrote last time), and what any
    kit is known to have written (legacy_record: the ask rules it retired, and every hook whose whole
    command is a kit script). A machine with no record has only the second."""
    desired = [] if action == "uninstall" else m.desired()
    want = {Machine.ident(e): e for e in desired}
    legacy = record is None
    rec_by = {Machine.ident(e): e for e in (record["entries"] if record else [])}
    changes, keep, seen, drop_names = [], [], set(), []
    why = "" if action == "uninstall" else " (the kit no longer ships it)"

    def take_out(e):
        m.removed.append(e)
        if e["kind"] == "listitem":      # decided together per file, below
            drop_names.append(e); return
        m.remove(e); changes.append((m.where(e), "-", "remove %s%s" % (m.label(e), why)))

    # 1. what the kit put in and does not ship now
    for e in list(rec_by.values()) + m.legacy_record():
        i = Machine.ident(e)
        if i in want or i in seen:
            continue
        seen.add(i)
        cur = m.current(e)
        if cur is None or cur is ABSENT or cur == "not-the-kit's":
            continue
        r = rec_by.get(i)
        if e["kind"] in ("dir", "link", "file") or r is None or m.same(e, cur, r["value"]) \
                or (e["kind"] == "hook" and m.command(e, cur) != m.command(e, r["value"])):
            take_out(e)
        else:
            m.notes.append("%s: left %s as it is: the kit no longer ships it, but you changed it" % (m.where(e), m.label(e)))
            m.left.add(i); keep.append(e)
    if action == "uninstall" and legacy:
        # No record: what the current kit would install counts, where it is still the kit's.
        foreign = set()
        for e in m.desired():
            if Machine.ident(e) in seen:
                continue
            if e["kind"] in ("link", "listitem") and os.path.basename(e["value"]).casefold() in foreign:
                continue                 # the skill folder of that name is the user's: so is what names it
            cur = m.current(e)
            if cur is None or cur is ABSENT:
                continue
            if not m.legacy_owned(e, cur):
                if e["kind"] == "dir":
                    foreign.add(e["name"].casefold())
                continue
            take_out(e)
    for f in sorted({e["file"] for e in drop_names}):
        m.drop_listitems(f, [e["value"] for e in drop_names if e["file"] == f], changes, why)

    # 2. what the current kit ships, by the three-way rule
    new_entries, foreign = [], set()
    for e in desired:
        i = Machine.ident(e)
        k = e["kind"]
        if k in ("link", "listitem") and os.path.basename(e["value"]).casefold() in foreign:
            continue                     # the skill folder of that name is the user's: nothing points at it
        if k == "agentry" and "launcher" in foreign:
            continue                     # it would run a file that is not the kit's launcher
        cur = m.current(e)
        if cur is None:
            continue                     # its file cannot be read: reported, left alone
        r = rec_by.get(i)
        if cur is ABSENT:
            m.set(e); changes.append((m.where(e), "+", "add %s" % m.label(e)))
            new_entries.append(e); continue
        if m.same(e, cur, e["value"]):
            new_entries.append(e); continue
        if cur == "not-the-kit's":
            if k == "file":
                foreign.add("launcher")
                m.warnings.append("%s is not the kit's launcher: left as it is, and the Antigravity session-start"
                                  " check is not wired to it" % m.where(e))
            elif k == "agentry":
                m.warnings.append("%s: the entry named %s is not the kit's: left as it is, so the session-start"
                                  " check is not wired" % (m.where(e), e["key"]))
            else:
                m.warnings.append("%s: %s is not the kit's (a folder or link of yours): left as it is, and the"
                                  " kit's %s skill is not installed there" % (m.where(e), m.label(e), m.label(e)))
                if k == "dir":
                    foreign.add(e["name"].casefold())
            continue
        if k == "git" and not legacy_git_ok(m, cur, r):
            m.notes.append("git config --global: left core.hooksPath as it is: it is %s, which another tool owns."
                           " To add the kit's hooks, copy %s/* into that folder" % (cur, e["value"]))
            continue
        if k in ("dir", "link", "file"):
            ours = True                  # kit-owned: drift is replaced
        elif k in ("hook", "agentry"):
            # Its whole command is the kit's script. A different command (path, interpreter, flags) is an
            # older kit's spelling: updated. The same command with other values changed is the user's.
            ours = m.command(e, cur) != m.command(e, e["value"]) or (r is not None and m.same(e, cur, r["value"]))
        else:
            ours = m.same(e, cur, r["value"]) if r else m.legacy_owned(e, cur)
        if ours:
            m.set(e); changes.append((m.where(e), "~", "update %s" % m.label(e)))
        else:
            done = m.fill_hook(e) if k == "hook" else []
            if done:
                changes.append((m.where(e), "~", "update %s (%s)" % (m.label(e), "; ".join(done))))
            m.notes.append("%s: left %s as it is: you changed it" % (m.where(e), m.label(e)))
            m.left.add(i)
        new_entries.append(e)
    return changes, keep + new_entries


def legacy_git_ok(m, cur, r):
    """core.hooksPath set to something else is another tool's (Husky, lefthook), unless the record says
    the kit set exactly this value, or it is an older spelling of the kit's own folder."""
    if r is not None:
        return m.same({"kind": "git"}, cur, r["value"])
    return canon(cur).rstrip("/").endswith("/.the-agent-kit/git-hooks")


def summary(changes):
    """The plan as the user reads it: grouped by file, and a run of rules in one list as one line."""
    by_where, out = {}, []
    for w, sign, text in changes:
        by_where.setdefault(w, []).append((sign, text))
    for w in sorted(by_where):
        out.append("  " + w)
        rules = {}
        for sign, text in by_where[w]:
            m = re.match(r"(add|remove) (ask|deny) rule (.+?)( \(the kit no longer ships it\))?$", text)
            if m:
                rules.setdefault((sign, m.group(1), m.group(2), m.group(4) or ""), []).append(m.group(3))
                continue
            out.append("    %s %s" % (sign, text))
        for (sign, verb, lst, why), names in sorted(rules.items()):
            out.append("    %s %s %d %s rule(s)%s: %s" % (sign, verb, len(names), lst, why, ", ".join(names)))
    return out


def apply(m, stamp):
    errors = []
    for path in sorted(m.dirty):
        data = m.files[path]
        try:
            text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            write_atomic(path, text, stamp)
        except OSError as e:
            errors.append("%s: not written - %s" % (path, e))
    for what, fn in m.ops:
        try:
            fn()
        except Exception as e:           # one failed step never stops the rest; the record reads back what happened
            errors.append("%s failed: %s" % (what, e))
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("install", "uninstall", "check"))
    ap.add_argument("--home", required=True)
    ap.add_argument("--share", required=True)
    ap.add_argument("--share-cmd", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--brief", action="store_true", help="check: one line, for install.sh check")
    ap.add_argument("--expect", help="with --apply: a file holding the plan the user agreed to; refuse if it changed")
    a = ap.parse_args()
    # Consent lives here too, not only in install.sh: otherwise running this script directly would be a
    # way to write the user's settings that no guard sees. The tool guard asks before any agent command
    # sets AGENT_KIT_APPLY; install.sh sets it only after the user answered yes in a terminal.
    if a.apply and os.environ.get("AGENT_KIT_APPLY") != "1":
        print("refused: changing your settings needs your consent (answer yes to install.sh, or set AGENT_KIT_APPLY=1)")
        return 1
    rec_path = os.path.join(a.share, RECORD)
    record = None
    if os.path.exists(rec_path):
        try:
            with open(rec_path, encoding="utf-8") as f:
                record = json.load(f)
            if not isinstance(record, dict) or not isinstance(record.get("entries"), list):
                raise ValueError("not a record")
        except (OSError, ValueError) as e:
            print("  ! %s cannot be read (%s): nothing changed. Move it aside to set up as if new." % (rec_path, e))
            return 1
    m = Machine(a.home, a.share, a.share_cmd, a.py)
    if record is not None:
        desired = m.desired()
        ok = [e for e in record["entries"] if m.valid(e, desired)]
        if len(ok) != len(record["entries"]):
            m.warnings.append("ignored %d entr%s in the install record that point outside the kit's own places"
                              " (the record is never trusted to say what else is the kit's)"
                              % (len(record["entries"]) - len(ok), "y" if len(record["entries"]) - len(ok) == 1 else "ies"))
        record = dict(record, entries=ok)
    action = "install" if a.action == "check" else a.action
    changes, entries = plan(m, action, record)
    errors = ["~/%s: not changed - %s" % (os.path.relpath(p, a.home).replace("\\", "/"), why) for p, why in sorted(m.errors.items())]
    if a.brief:
        if errors:
            print("the kit's machine-wide entries: " + "; ".join(errors))
        elif changes:
            print("the kit's machine-wide entries: %d change(s) pending in %s" % (len(changes), ", ".join(sorted({w for w, _, _ in changes}))))
        else:
            print("the kit's machine-wide entries: installed and current (%d recorded%s)" % (
                len(entries), "" if record else "; no install record yet"))
        return 1 if errors else (10 if changes else 0)
    shown = summary(changes) + ["  = " + n for n in m.notes] + ["  ! " + w for w in m.warnings] + ["  ! " + e for e in errors]
    if a.apply and a.expect:
        # Consent was given to the plan install.sh showed. If anything changed since (a file, the record),
        # this is not that plan: nothing is applied, and the user is asked again.
        try:
            with open(a.expect, encoding="utf-8") as f:
                agreed = [l.rstrip() for l in f.read().splitlines() if l.strip()]
        except OSError:
            agreed = None
        if agreed != [l.rstrip() for l in shown if l.strip()]:
            print("  ! the plan changed since you said yes: nothing changed. Run it again to see the new plan.")
            return 1
    for line in shown:
        print(line)
    if a.action == "check":
        return 1 if errors else (10 if changes else 0)
    if not a.apply:   # a file that cannot be read never holds back the rest: pending wins, it is applied
        return 10 if changes else (1 if errors else 0)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    errs = apply(m, stamp)
    for e in errs:
        print("  ! " + e)
    if m.dirty:
        print("  Backups: each changed file saved beside itself as <file>.bak-agent-kit-%s" % stamp)
    # The record says what is installed now, read back from the machine, not taken from the plan: a step
    # that failed leaves its entry out (an add) or in (a removal). An entry whose file could not be read
    # keeps its old record entry; an uninstall that left nothing deletes the record.
    unread = {norm(p) for p in m.errors}
    after = Machine(a.home, a.share, a.share_cmd, a.py)
    def there(e):
        cur = after.current(e)
        if cur in (None, ABSENT, "not-the-kit's"):
            return False
        return Machine.ident(e) in m.left or after.same(e, cur, e["value"])
    kept = [e for e in (record["entries"] if record else []) if norm(e.get("file") or e.get("path") or "") in unread]
    out = [e for e in entries if norm(e.get("file") or e.get("path") or "") not in unread and there(e)]
    out += [e for e in m.removed if e.get("value") is not None
            and after.current(e) not in (None, ABSENT, "not-the-kit's")] + kept   # a removal that failed stays
    clean = [{k: v for k, v in e.items() if k != "src"} for e in out]
    if clean:
        write_atomic(rec_path, json.dumps({"version": 1, "entries": clean}, indent=1) + "\n", stamp)
        bak = [f for f in os.listdir(a.share) if f.startswith(RECORD + ".bak-agent-kit-")]
        for f in bak:                    # the record is the kit's own state: no backups of it pile up
            os.remove(os.path.join(a.share, f))
    elif os.path.exists(rec_path):
        os.remove(rec_path)
    return 1 if (m.errors or errs) else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Install, update or uninstall the-agent-kit in one project, from the project's install record.

Run by install.sh inside a repo, never by an agent on its own.

  project.py install|uninstall|check --root R --kit K --kit-time T --py P [--lean] [--apply]

Everything the kit writes into a project is an ENTRY in `.agents/the-agent-kit.json`, committed with the
project, with a fingerprint of what the kit wrote. Every install is an uninstall of the old kit followed
by an install of the new one, as on the machine (setup/machine.py):
  - a file the kit wrote and no longer ships is removed, unless it was edited since: then it is the
    user's, left and reported
  - each file the kit ships is written; one it wrote before is replaced even if it was edited (a kit
    file is the kit's: git holds the edit), and a symlink is never written through
  - AGENTS.md: the text outside the PROJECT-CONFIG block is the kit's rules and is replaced; the block is
    the project's and is never touched. Without the markers the file is left as it is, and named
  - CLAUDE.md and a --lean AGENTS.md are written once, for the project to own
  - the Antigravity guard entry in .agents/hooks.json is added, or brought current when its command is
    not the kit's shape; any interpreter spelling of the kit's command is left as it is, so teammates
    on different machines do not rewrite each other's file
A project recorded by a newer kit than the one running is left alone: update the kit first. Git hooks
(.git/hooks, per clone and never committed) stay with install.sh.

Exit: 0 nothing to change (or applied), 10 changes pending (not applied), 1 something could not be done.
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from machine import is_link   # a symlink, or a Windows junction (os.path.islink misses those)

RECORD = os.path.join(".agents", "the-agent-kit.json")
START, END = "PROJECT-CONFIG:START", "PROJECT-CONFIG:END"
# Codex has no path-scoped rules: it loads a skill when the TASK matches its description. The four
# domain-shaped depth files get an honest trigger; code-correctness and tests are path-shaped (any source
# file, any test file), so Codex gets their one-line versions from AGENTS.md and nothing more.
CODEX_DESC = {
    "web-security": "Use when adding or changing auth, sessions, API routes, middleware, webhooks, payments, uploads, rate limits, CORS, CSRF, security headers, or edge config (nginx, Caddy, vercel.json, wrangler.toml, fly.toml) - the server-side security defaults a senior engineer applies without being asked.",
    "data-layer": "Use when writing or changing migrations, models, schema, SQL, or anything that reads or stores data - staged schema changes, N+1 queries and indexes, money and time column types, and keeping personal data out of logs.",
    "frontend-quality": "Use when building or changing user-facing UI: components, pages, screens, forms - accessibility, internationalisation, loading states, and restraint in visual polish.",
    "ci-cd": "Use when editing CI or delivery config: GitHub workflows, Dockerfiles, GitLab CI, Jenkinsfiles, Azure pipelines - pinned actions, least-privilege tokens, untrusted checkouts, secrets in logs, and gates that fail closed.",
}
# Antigravity has glob-triggered rules: the two path-shaped depth files Codex skips go there. The four
# domain rules stay skills only; writing them here too would load them twice.
AG_GLOB = ("code-correctness", "tests")
# Kit files a later kit dropped, as paths in the kit (claude/rules, claude/skills). The only files besides
# the current kit's a record entry may name; test/shipped_history.py fails a release that forgets one.
RETIRED_FILES = ("claude/skills/generating-reports/design.md",)   # 0.5.0 moved it to references/
AG_HOOK_KEY = "the-agent-kit"
AG_GUARD = re.compile(r"(python3?|py -3) agent-kit-guard\.py --tool antigravity")

STUB = """<!-- The universal rules live in your global ~/.claude/CLAUDE.md (and ~/.codex/AGENTS.md); both tools
     read global + project files together, so this file EXTENDS them. Keep only project-specific config
     here - do NOT copy the universal rules in (that would double them in context). -->

<!-- PROJECT-CONFIG:START -->
<!-- Run the setup prompt (~/.the-agent-kit/docs/project-setup-prompt.md) to fill this in (~15-30 lines, one screen). -->
<!-- PROJECT-CONFIG:END -->
"""
IMPORTER = """<!-- Claude Code reads CLAUDE.md, not AGENTS.md, so this file imports the rules instead of copying them.
     One source of truth, nothing to keep in sync. Put Claude-Code-only notes BELOW the import line. -->
@AGENTS.md
"""
# Antigravity splits a hook command on whitespace and ignores quotes, so a guard path under a home folder
# with a space breaks the hook, and a broken hook blocks every command. Hooks run from the folder holding
# hooks.json, so this launcher sits there, is called by bare name, and hands the call to the machine guard.
LAUNCHER = """# The Agent Kit: launcher for the command guard (see .agents/hooks.json). Kit-owned; --update-rules
# replaces it. Antigravity cannot pass a quoted path to a hook, so the guard is found from here.
import os, runpy, sys

guard = os.path.join(os.path.expanduser("~"), ".the-agent-kit", "hooks", "command-guard.py")
if not os.path.isfile(guard):
    sys.stderr.write("the-agent-kit: no guard at %s; run install.sh --setup. Command not checked.\\n" % guard)
    sys.exit(0)
sys.argv = [guard] + sys.argv[1:]
runpy.run_path(guard, run_name="__main__")
"""
PLACEHOLDER = ["<!-- PROJECT-CONFIG:START -->",
               "<!-- Not configured yet. Run the setup prompt (~/.the-agent-kit/docs/project-setup-prompt.md) to fill this in. -->",
               "<!-- PROJECT-CONFIG:END -->"]


# ---- the generators: byte-identical to the shell versions they replace ------------------------------

def lines(text):
    """awk's view of a file: its lines, without the newline, a final unterminated line included."""
    out = text.split("\n")
    return out[:-1] if out and out[-1] == "" else out


def rules_text(kit_agents):
    """The kit's AGENTS.md with an EMPTY project block: the kit repo fills its own block, and copying it
    would ship the kit's project config into every project."""
    out, skip = [], False
    for ln in lines(kit_agents):
        if START in ln:
            skip = True; out += PLACEHOLDER
        if not skip:
            out.append(ln)
        if END in ln:
            skip = False
    return "".join(l + "\n" for l in out)


def with_block(kit_agents, project_agents):
    """The kit's current rules around the project's own PROJECT-CONFIG block, markers included."""
    blk, c = [], False
    for ln in lines(project_agents):
        if START in ln:
            c = True
        if c:
            blk.append(ln)
        if END in ln:
            c = False
    out, skip = [], False
    for ln in lines(kit_agents):
        if START in ln:
            skip = True; out += blk
        if not skip:
            out.append(ln)
        if END in ln:
            skip = False
    return "".join(l + "\n" for l in out)


def rule_to_skill(rule, name, desc):
    """A depth rule as a Codex skill: the `paths:` frontmatter swapped for skill frontmatter."""
    out, ls = ["---", "name: %s" % name, "description: %s" % desc, "---"], lines(rule)
    if ls and ls[0] != "---":
        return "".join(l + "\n" for l in out + ls)
    fm = 0
    for ln in ls:
        if fm < 2 and ln == "---":
            fm += 1; continue
        if fm >= 2:
            out.append(ln)
    return "".join(l + "\n" for l in out)


def rule_to_glob(rule):
    """A depth rule as an Antigravity glob rule: its `paths:` list becomes one `globs:` string."""
    out, fm, g = [], 0, ""
    for i, ln in enumerate(lines(rule)):
        if i == 0 and ln == "---":
            fm = 1; continue
        if fm == 1 and ln == "---":
            out.append('---\ntrigger: glob\nglobs: "%s"\n---' % g); fm = 2; continue
        if fm == 1:
            m = re.match(r' *- *"([^"]*)"', ln)
            if m:
                g = g + (", " if g else "") + m.group(1)
            continue
        out.append(ln)
    return "".join(l + "\n" for l in out)


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def read_agents(path):
    """(text with LF, crlf?) or (None, reason)."""
    raw = read_bytes(path)
    try:
        text = raw.decode("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
    except UnicodeDecodeError:
        return None, "it is not UTF-8"
    return text.replace("\r\n", "\n"), b"\r\n" in raw


def one_block(text):
    """Exactly one PROJECT-CONFIG:START line, then exactly one END line after it."""
    ls = lines(text)
    st = [i for i, l in enumerate(ls) if START in l]
    en = [i for i, l in enumerate(ls) if END in l]
    return len(st) == 1 and len(en) == 1 and st[0] < en[0]


def is_stub(text):
    return "universal rules live in your global" in text


# ---- the project -----------------------------------------------------------------------------------

class Project:
    def __init__(self, root, kit, py, lean):
        self.root, self.kit, self.py, self.lean = root, kit, py, lean
        self.rules_src = next((d for d in (os.path.join(kit, "claude", "rules"), os.path.join(kit, "rules")) if os.path.isdir(d)), None)
        self.skills_src = next((d for d in (os.path.join(kit, "claude", "skills"), os.path.join(kit, "skills")) if os.path.isdir(d)), None)
        self.notes, self.warnings, self.errors = [], [], []
        self.writes, self.deletes, self.json_edits = {}, [], {}   # rel -> bytes; [rel]; rel -> object
        self.json_read = {}
        self.backups = set()
        self.git, self.held = False, set()
        self.launcher_foreign = False

    def p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    # -- what the current kit ships -----------------------------------------------------------------
    def desired(self):
        """[(entry, bytes or None)]: each entry with the content the kit writes for it now."""
        out = []
        with open(os.path.join(self.kit, "AGENTS.md"), encoding="utf-8") as f:
            self.kit_agents = f.read()
        if self.lean:
            out.append(({"kind": "seed", "path": "AGENTS.md"}, STUB.encode()))
        else:
            out.append(({"kind": "rules", "path": "AGENTS.md"}, None))
        out.append(({"kind": "seed", "path": "CLAUDE.md"}, IMPORTER.encode()))
        for src, files in self.kit_files():
            data = read_bytes(src)
            for rel, content in files(data):
                out.append(({"kind": "file", "path": rel, "src": src}, content))
        out.append(({"kind": "file", "path": ".agents/agent-kit-guard.py"}, LAUNCHER.encode()))
        out.append(({"kind": "agentry", "path": ".agents/hooks.json", "key": AG_HOOK_KEY}, None))
        return out

    def kit_files(self):
        """(source file, function bytes -> [(project path, content)]) for every rule and skill file."""
        out = []
        if self.rules_src:
            for f in sorted(os.listdir(self.rules_src)):
                if f.endswith(".md"):
                    out.append((os.path.join(self.rules_src, f), lambda d, n=f[:-3]: self.rule_targets(n, d)))
        if self.skills_src:
            for s in sorted(os.listdir(self.skills_src)):
                sd = os.path.join(self.skills_src, s)
                if not os.path.isfile(os.path.join(sd, "SKILL.md")):
                    continue
                for d, dirs, fs in sorted(os.walk(sd)):
                    dirs.sort()
                    for f in sorted(fs):
                        rel = os.path.relpath(os.path.join(d, f), sd).replace(os.sep, "/")
                        out.append((os.path.join(d, f), lambda b, s=s, rel=rel: self.skill_targets(s, rel, b)))
        return out

    @staticmethod
    def rule_targets(n, data):
        text = data.decode("utf-8")
        t = [(".claude/rules/%s.md" % n, data)]
        if n in CODEX_DESC:
            t.append((".agents/skills/%s/SKILL.md" % n, rule_to_skill(text, n, CODEX_DESC[n]).encode("utf-8")))
        if n in AG_GLOB:
            t.append((".agents/rules/%s.md" % n, rule_to_glob(text).encode("utf-8")))
        return t

    @staticmethod
    def skill_targets(s, rel, data):
        return [(".claude/skills/%s/%s" % (s, rel), data), (".agents/skills/%s/%s" % (s, rel), data)]

    def allowed_paths(self, desired):
        """Every project path a record entry may name: the current kit's, and those of RETIRED_FILES."""
        ok = {e["path"] for e, _ in desired}
        for kp in RETIRED_FILES:
            parts = kp.split("/")
            if parts[:2] == ["claude", "skills"]:
                ok |= {p for p, _ in self.skill_targets(parts[2], "/".join(parts[3:]), b"")}
            elif parts[:2] == ["claude", "rules"]:
                n = parts[2][:-3]
                ok |= {".claude/rules/%s.md" % n, ".agents/skills/%s/SKILL.md" % n, ".agents/rules/%s.md" % n}
        return ok

    # -- reading the project ------------------------------------------------------------------------
    def escapes(self, rel):
        """Does rel reach outside the project? Any folder on the way (or the file) being a symlink or a
        junction counts: a cloned repo can ship `.claude` as a link to the user's real ~/.claude."""
        q = self.root
        for part in rel.split("/"):
            q = os.path.join(q, part)
            if os.path.lexists(q) and is_link(q):
                return True
        real, top = os.path.realpath(self.p(rel)), os.path.realpath(self.root)
        try:
            return os.path.commonpath([real, top]) != top
        except ValueError:               # another drive on Windows: outside, whatever the reason
            return True

    def scan_unsaved(self):
        """What git can give back: the paths it tracks with no uncommitted change. An existing file is
        replaced or removed only when it is one of these, or exactly what the kit last wrote. An ignored
        or untracked file is in no commit, so it counts as unsaved."""
        r = subprocess.run(["git", "-C", self.root, "ls-files", "-z"], capture_output=True)
        self.git = r.returncode == 0
        self.held = set()
        if not self.git:
            return
        tracked = {t.replace("\\", "/") for t in r.stdout.decode("utf-8", "replace").split("\0") if t}
        r = subprocess.run(["git", "-C", self.root, "status", "--porcelain=v1", "-z", "--untracked-files=no"],
                           capture_output=True)
        changed, items = set(), r.stdout.decode("utf-8", "replace").split("\0")
        i = 0
        while i < len(items):
            item = items[i]
            if len(item) > 3:
                changed.add(item[3:].replace("\\", "/"))
                if item[0] in "RC":      # a rename or copy: the next field is its old path, with no status
                    i += 1
                    if i < len(items) and items[i]:
                        changed.add(items[i].replace("\\", "/"))
            i += 1
        self.held = tracked - changed

    def may_replace(self, rel, kit_sha):
        """May the kit overwrite or remove the file at rel? kit_sha is what the kit last wrote there. Always,
        and nothing is lost: what git holds (tracked, committed, clean) it can give back; anything else (an
        uncommitted edit, an ignored or untracked file, no git at all) is copied beside the file first.
        Refusing instead would leave a project that ignores .claude/ never updated."""
        cur = self.current(rel)
        if cur is None or (kit_sha and cur == kit_sha):
            return True
        if not self.git or rel not in self.held:
            self.backups.add(rel)
        return True

    def current(self, rel):
        """sha of the file, None when absent, "link" when it or a folder on its way is a link (never
        written through)."""
        p = self.p(rel)
        if self.escapes(rel):
            return "link"
        if not os.path.isfile(p):
            return None
        return sha(read_bytes(p))

    def load_json(self, rel):
        if rel in self.json_edits:
            return self.json_edits[rel]
        p = self.p(rel)
        if self.escapes(rel):
            self.warnings.append("%s is, or is inside, a link; left untouched, so the Antigravity guard is not wired" % rel); return None
        data = {}
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8-sig") as f:
                    data = json.load(f)
            except ValueError:
                data = None
            if not isinstance(data, dict):
                self.warnings.append("%s is not a JSON object; left untouched, so the Antigravity guard is not wired" % rel)
                return None
        self.json_edits[rel] = data
        self.json_read[rel] = json.loads(json.dumps(data))   # a copy, to tell a change from a read
        return data

    def ag_entry(self):
        return {"PreToolUse": [{"matcher": "run_command", "hooks": [
            {"type": "command", "command": self.py + " agent-kit-guard.py --tool antigravity", "timeout": 15}]}]}

    @staticmethod
    def ag_shaped(v):
        try:
            h = v["PreToolUse"][0]["hooks"][0]
            return (list(v) == ["PreToolUse"] and len(v["PreToolUse"]) == 1 and v["PreToolUse"][0].get("matcher") == "run_command"
                    and len(v["PreToolUse"][0]["hooks"]) == 1 and AG_GUARD.fullmatch(str(h.get("command", ""))) is not None)
        except (KeyError, IndexError, TypeError, AttributeError):
            return False


def plan(pj, action, record):
    """(changes, new record entries, ok). Changes are (sign, text); the content to write is queued on pj."""
    desired = [] if action == "uninstall" else pj.desired()
    if action == "uninstall":
        pj.desired()                     # loads the kit's AGENTS.md, for the AGENTS.md uninstall check
    want = {e["path"]: (e, c) for e, c in desired}
    rec = {e["path"]: e for e in (record or {}).get("entries", [])}
    changes, entries = [], []

    # 1. what the kit wrote and does not ship now
    old = dict(rec)
    # A file at a path an older kit shipped (RETIRED_FILES) is the kit's, record or not: the record only
    # knows what this kit's line of installs wrote. Its content is unknown, so it goes as it is.
    for rel in sorted(pj.allowed_paths([]) - set(want) - set(rec)):
        if pj.current(rel) not in (None, "link"):
            old[rel] = {"kind": "file", "path": rel, "sha": None}
    if action == "uninstall" and record is None:
        for e, c in pj.desired():
            if e["kind"] == "file" and pj.current(e["path"]) not in (None, "link"):
                old[e["path"]] = {"kind": "file", "path": e["path"], "sha": sha(c)}
            elif e["kind"] in ("seed", "rules", "agentry"):
                old[e["path"]] = dict(e, sha=sha(c) if c else None)
    for rel, e in sorted(old.items()):
        if rel in want:
            continue
        k = e["kind"]
        if k in ("file", "seed"):
            cur = pj.current(rel)
            if cur is None or cur == "link":
                continue
            if (e.get("sha") is None or cur == e["sha"]) and pj.may_replace(rel, e.get("sha")):
                pj.deletes.append(rel); changes.append(("-", "remove %s%s" % (rel, "" if action == "uninstall" else " (the kit no longer ships it)")))
            else:
                pj.notes.append("left %s as it is: the kit wrote it, but it was edited since" % rel)
                entries.append(e)
        elif k == "rules":
            cur = pj.current(rel)
            if cur is None or cur == "link":
                continue
            text, _ = read_agents(pj.p(rel))
            if text == rules_text(pj.kit_agents) and pj.may_replace(rel, e.get("sha")):   # nothing of the project's
                pj.deletes.append(rel); changes.append(("-", "remove %s" % rel))
            else:
                pj.notes.append("left %s as it is: its PROJECT-CONFIG block or text is the project's; remove it by hand" % rel)
        elif k == "agentry":
            data = pj.load_json(rel)
            if data is not None and AG_HOOK_KEY in data and Project.ag_shaped(data[AG_HOOK_KEY]):
                del data[AG_HOOK_KEY]; changes.append(("-", "remove the command guard from %s" % rel))
                pj.json_edits[rel] = data

    # 2. what the current kit ships
    for e, content in desired:
        rel, k = e["path"], e["kind"]
        cur = pj.current(rel) if k != "agentry" else None
        if cur == "link":
            pj.warnings.append("%s is, or is inside, a link; left as it is (the kit never writes through one)" % rel)
            if rel == ".agents/agent-kit-guard.py":
                pj.launcher_foreign = True   # the hook would run whatever the link points at
            continue
        if k == "file":
            if cur is None:
                pj.writes[rel] = content; changes.append(("+", "add %s" % rel))
            elif cur != sha(content):
                if not pj.may_replace(rel, (rec.get(rel) or {}).get("sha")):
                    if (rec.get(rel) or {}).get("sha"):
                        entries.append(rec[rel])
                    continue
                pj.writes[rel] = content; changes.append(("~", "update %s" % rel))
            entries.append({"kind": "file", "path": rel, "sha": sha(content)})
        elif k == "seed":
            if cur is None:
                pj.writes[rel] = content; changes.append(("+", "add %s" % rel))
                entries.append({"kind": "seed", "path": rel, "sha": sha(content)})
            elif rel in rec:
                entries.append(rec[rel])  # written once for the project to own: never updated
        elif k == "rules":
            if cur is None:
                text = rules_text(pj.kit_agents)
                pj.writes[rel] = text.encode("utf-8"); changes.append(("+", "add AGENTS.md (the rules, with an empty project block)"))
                entries.append({"kind": "rules", "path": rel, "sha": sha(text)}); continue
            text, crlf = read_agents(pj.p(rel))
            if text is None:
                pj.warnings.append("AGENTS.md: %s; left as it is" % crlf); continue
            if is_stub(text):
                pj.notes.append("AGENTS.md is a --lean stub: the universal rules live in your global files; left as it is")
                continue
            if START not in text or END not in text:
                pj.warnings.append("AGENTS.md has no PROJECT-CONFIG markers, so the kit cannot tell your text from its"
                                   " rules; left as it is. Add the markers (see the kit's AGENTS.md) to have it updated")
                continue
            if not one_block(text):
                pj.warnings.append("AGENTS.md has more than one PROJECT-CONFIG block, or its END comes first, so the kit"
                                   " cannot tell your text from its rules; left as it is")
                continue
            new = with_block(pj.kit_agents, text)
            if not new.strip():
                pj.errors.append("updating AGENTS.md produced an empty file; left as it is"); continue
            if new != text:
                if not pj.may_replace(rel, (rec.get(rel) or {}).get("sha")):
                    continue
                pj.writes[rel] = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
                changes.append(("~", "update the rules in AGENTS.md (your PROJECT-CONFIG block is kept; anything else"
                                     " edited outside it is replaced: review with git diff AGENTS.md)"))
            else:
                pj.notes.append("AGENTS.md already carries the current rules")
            out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
            entries.append({"kind": "rules", "path": rel, "sha": sha(out)})
        elif k == "agentry":
            if pj.launcher_foreign:
                pj.warnings.append("the Antigravity guard is not wired: .agents/agent-kit-guard.py is not the kit's file")
                continue
            data = pj.load_json(rel)
            if data is None:
                continue
            v = data.get(AG_HOOK_KEY)
            if v is None:
                data[AG_HOOK_KEY] = pj.ag_entry(); changes.append(("+", "wire the command guard into %s (Antigravity)" % rel))
            elif not Project.ag_shaped(v):
                pj.warnings.append("the entry named %s in %s is not the kit's; left as it is, so the Antigravity guard"
                                   " is not wired" % (AG_HOOK_KEY, rel)); continue
            entries.append({"kind": "agentry", "path": rel, "key": AG_HOOK_KEY})
    return changes, entries


def valid(pj, e, allowed):
    if not isinstance(e, dict) or not isinstance(e.get("path"), str):
        return False
    rel = e["path"]
    if "\\" in rel or rel.startswith("/") or any(part in ("", ".", "..") for part in rel.split("/")):
        return False
    k = e.get("kind")
    if k == "file":
        return rel in allowed and isinstance(e.get("sha"), str)
    if k == "seed":
        return rel in ("CLAUDE.md", "AGENTS.md") and isinstance(e.get("sha"), str)
    if k == "rules":
        return rel == "AGENTS.md" and (e.get("sha") is None or isinstance(e.get("sha"), str))
    if k == "agentry":
        return rel == ".agents/hooks.json" and e.get("key") == AG_HOOK_KEY
    return False


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    mode = os.stat(path).st_mode & 0o777 if os.path.isfile(path) else 0o644   # mkstemp makes 0600
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".agent-kit.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("install", "uninstall", "check"))
    ap.add_argument("--root", required=True)
    ap.add_argument("--kit", required=True)
    ap.add_argument("--kit-time", type=int, default=0, help="commit time of the kit, to refuse a project a newer kit installed")
    ap.add_argument("--py", required=True)
    ap.add_argument("--lean", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    pj = Project(os.path.abspath(a.root), os.path.abspath(a.kit), a.py, a.lean)
    rec_path = pj.p(RECORD.replace(os.sep, "/"))
    record = None
    if os.path.lexists(rec_path):
        try:
            if os.path.islink(rec_path):
                raise ValueError("it is a symlink")
            with open(rec_path, encoding="utf-8") as f:
                record = json.load(f)
            if not isinstance(record, dict) or not isinstance(record.get("entries"), list):
                raise ValueError("not a record")
        except (OSError, ValueError) as e:
            # Anyone who can commit could otherwise block every update with a broken file: it is set aside,
            # and this run works as on a project without one (files at the kit's own paths are the kit's).
            pj.warnings.append("%s cannot be read (%s): treated as missing, and rewritten" % (RECORD.replace(os.sep, "/"), e))
            record = None
    rec_time = record.get("kit_time") if isinstance(record, dict) else None
    if not isinstance(rec_time, int) or rec_time > time.time():
        if isinstance(rec_time, int):    # a time in the future is no kit's: it would block every update
            pj.warnings.append("ignored the record's kit time, which is in the future")
        rec_time = 0
    if record is not None:
        if a.kit_time and rec_time > a.kit_time and os.environ.get("AGENT_KIT_FORCE") != "1":
            # The record is the project's, so anyone who can commit can set it: the refusal is said, and
            # one variable gets past it.
            print("  ! this project was installed by a newer kit than this one: nothing changed. Update the kit"
                  " first (install.sh --update), then run this again; or, to install this kit anyway,"
                  " AGENT_KIT_FORCE=1 in front of the same command.")
            return 1
        desired = pj.desired()
        allowed = pj.allowed_paths(desired)
        ok = [e for e in record["entries"] if valid(pj, e, allowed)]
        if len(ok) != len(record["entries"]):
            pj.warnings.append("ignored %d entr%s in %s that name something outside the kit's own files (the record"
                               " is never trusted to say what else is the kit's)"
                               % (len(record["entries"]) - len(ok), "y" if len(record["entries"]) - len(ok) == 1 else "ies",
                                  RECORD.replace(os.sep, "/")))
        record = dict(record, entries=ok)
    pj.scan_unsaved()
    action = "install" if a.action == "check" else a.action
    changes, entries = plan(pj, action, record)
    for sign, text in changes:
        print("  %s %s" % (sign, text))
    for n in pj.notes:
        print("  = " + n)
    for w in pj.warnings:
        print("  ! " + w)
    for e in pj.errors:
        print("  ! " + e)
    if a.action == "check" or not a.apply:
        return 1 if pj.errors and not changes else (10 if changes else 0)
    errs = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for rel in sorted(pj.backups):       # git does not hold it: the old text is kept beside the file
        if rel not in pj.writes and rel not in pj.deletes:
            continue
        try:
            if os.path.isfile(pj.p(rel)) and not pj.escapes(rel):
                with open(pj.p(rel) + ".bak-agent-kit-" + stamp, "xb") as f:   # never through a planted link
                    f.write(read_bytes(pj.p(rel)))
                print("  = saved your copy of %s as %s.bak-agent-kit-%s (git did not hold it)" % (rel, rel, stamp))
        except OSError as e:
            errs.append("backup of %s failed, so it is left as it is: %s" % (rel, e))
            pj.deletes = [d for d in pj.deletes if d != rel]; pj.writes.pop(rel, None)
    # The kit's own top folders are never removed, even empty: they may be the project's too.
    stop = {pj.root, pj.p(".claude"), pj.p(".agents")}
    for rel in pj.deletes:
        try:
            if pj.escapes(rel):          # re-checked: a link may have appeared since the plan
                raise OSError("it is, or is inside, a link")
            os.remove(pj.p(rel))
            d = os.path.dirname(pj.p(rel))
            while d not in stop and os.path.isdir(d) and not is_link(d) and not os.listdir(d):   # a folder the removal emptied
                os.rmdir(d); d = os.path.dirname(d)
        except OSError as e:
            errs.append("remove %s failed: %s" % (rel, e))
    for rel, data in sorted(pj.writes.items()):
        try:
            if pj.escapes(rel):
                raise OSError("it is, or is inside, a link")
            write_atomic(pj.p(rel), data)
        except OSError as e:
            errs.append("write %s failed: %s" % (rel, e))
    for rel, data in sorted(pj.json_edits.items()):
        if data is None or data == pj.json_read.get(rel):
            continue                     # read only to look: unchanged files are never rewritten
        try:
            if pj.escapes(rel):
                raise OSError("it is, or is inside, a link")
            write_atomic(pj.p(rel), (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError as e:
            errs.append("write %s failed: %s" % (rel, e))
    for e in errs:
        print("  ! " + e)
    # The record is read back from the project, like the machine's: a file that failed to land is left out.
    kept = [e for e in entries if e["kind"] in ("rules", "agentry")
            or (pj.current(e["path"]) is not None and pj.current(e["path"]) != "link")]
    if pj.escapes(RECORD.replace(os.sep, "/")):
        print("  ! %s is, or is inside, a link: the record was not written" % RECORD.replace(os.sep, "/"))
        return 1
    if kept:
        rec = {"version": 1, "kit_time": a.kit_time or rec_time, "entries": kept}
        write_atomic(rec_path, (json.dumps(rec, indent=1) + "\n").encode("utf-8"))
    elif os.path.exists(rec_path):
        os.remove(rec_path)
    return 1 if (pj.errors or errs) else 0


if __name__ == "__main__":
    sys.exit(main())

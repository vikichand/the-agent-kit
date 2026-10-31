#!/usr/bin/env python3
"""Cases for setup/project.py: the project install record, and its generators against the shell ones
they replaced (byte for byte, over every rule the kit ships).

  python3 test/project_cases.py [path/to/project.py]
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(KIT, "setup", "project.py")
spec = importlib.util.spec_from_file_location("project", PROJECT)
pj = importlib.util.module_from_spec(spec); spec.loader.exec_module(pj)
RULES = sorted(f[:-3] for f in os.listdir(os.path.join(KIT, "claude", "rules")) if f.endswith(".md"))
SKILLS = sorted(n for n in os.listdir(os.path.join(KIT, "claude", "skills")) if os.path.isfile(os.path.join(KIT, "claude", "skills", n, "SKILL.md")))
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(p, mode="r"):
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


# ---- the generators, against the shell ones ---------------------------------------------------------
# rule_to_skill, rule_to_glob and write_rules come live from install.sh (the eval harness still builds its
# arms with them), so a change to either side fails here. The block swap left install.sh; its awk is kept
# below as the reference the Python port must match.
with open(os.path.join(KIT, "install.sh"), encoding="utf-8") as f:
    _install = f.read()


def shell_fn(name):
    a = _install.index("\n%s() {" % name) + 1
    return _install[a:_install.index("\n}\n", a) + 3]


SHELL = shell_fn("rule_to_skill") + shell_fn("rule_to_glob") + shell_fn("write_rules") + r'''
wr() { KIT=$(dirname "$1"); t=$(mktemp); write_rules "$t"; cat "$t"; rm -f "$t"; }
update_rules() {
  awk '
    NR==FNR { if (/PROJECT-CONFIG:START/) c=1
              if (c) blk = blk $0 ORS
              if (/PROJECT-CONFIG:END/)  c=0
              next }
    /PROJECT-CONFIG:START/ { skip=1; printf "%s", blk }
    !skip { print }
    /PROJECT-CONFIG:END/   { skip=0 }
  ' "$1" "$2"
}
'''


def sh(call, *args):
    # A script file, not `bash -c`: on Windows a newline inside a command-line argument does not reach bash.
    fd, script = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(SHELL + '\n' + call + ' "$@"\n')
    # The full path: on Windows a bare "bash" is looked up in System32 first, which is WSL's, not Git's.
    r = subprocess.run([shutil.which("bash") or "bash", script.replace("\\", "/")] + list(args), capture_output=True)
    os.remove(script)
    return r.stdout


diff = []
for n in RULES:
    src = os.path.join(KIT, "claude", "rules", n + ".md")
    text = read(src)
    if n in pj.CODEX_DESC and sh("rule_to_skill", src, n, pj.CODEX_DESC[n]) != pj.rule_to_skill(text, n, pj.CODEX_DESC[n]).encode():
        diff.append("rule_to_skill " + n)
    if sh("rule_to_glob", src) != pj.rule_to_glob(text).encode():
        diff.append("rule_to_glob " + n)
agents = os.path.join(KIT, "AGENTS.md")
if sh("wr", agents) != pj.rules_text(read(agents)).encode():
    diff.append("write_rules")
tmp = tempfile.mkdtemp()
proj = os.path.join(tmp, "AGENTS.md")
with open(proj, "w", encoding="utf-8", newline="\n") as f:
    f.write("# old rules\n<!-- PROJECT-CONFIG:START -->\n**Stack:** mine\n<!-- PROJECT-CONFIG:END -->\nold tail\n")
if sh("update_rules", proj, agents) != pj.with_block(read(agents), read(proj)).encode():
    diff.append("update_rules")
shutil.rmtree(tmp)
check("the Python generators match the shell ones byte for byte (every rule, AGENTS.md, the block swap)", not diff, ", ".join(diff))


# ---- a project ------------------------------------------------------------------------------------
class Repo:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="project-cases-")
        subprocess.run(["git", "init", "-q", self.root])

    def p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def run(self, action="install", apply=True, lean=False, kit_time=100, py="python3"):
        args = [sys.executable, PROJECT, action, "--root", self.root, "--kit", KIT, "--kit-time", str(kit_time), "--py", py]
        args += ["--lean"] * lean + ["--apply"] * apply
        r = subprocess.run(args, capture_output=True, text=True)
        self.out, self.rc = r.stdout + r.stderr, r.returncode
        return self.rc

    def record(self):
        try:
            return json.loads(read(self.p(".agents/the-agent-kit.json")))
        except OSError:
            return None

    def put_record(self, rec):
        with open(self.p(".agents/the-agent-kit.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f)

    def files(self):
        out = {}
        for d, dirs, fs in os.walk(self.root):
            if ".git" in d.split(os.sep):
                continue
            for f in fs:
                full = os.path.join(d, f)
                out[os.path.relpath(full, self.root).replace(os.sep, "/")] = read(full, "rb")
        return out

    def commit(self):
        """What the project has committed is what git can give back: the kit replaces only that."""
        g = ["git", "-C", self.root, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "core.hooksPath=/dev/null"]
        subprocess.run(g + ["add", "-A"], capture_output=True)
        subprocess.run(g + ["commit", "-q", "-m", "x", "--allow-empty"], capture_output=True)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


r = Repo()
r.run(apply=False)
check("plan without --apply: exit 10, nothing written", r.rc == 10 and not os.path.exists(r.p("AGENTS.md")), r.out)
r.run()
f = r.files()
check("install writes the rules, the importer, every rule and skill for each tool, the launcher and the guard hook",
      r.rc == 0 and "PROJECT-CONFIG:START" in f.get("AGENTS.md", b"").decode() and f.get("CLAUDE.md") == pj.IMPORTER.encode()
      and all(".claude/rules/%s.md" % n in f for n in RULES)
      and all(".claude/skills/%s/SKILL.md" % s in f and ".agents/skills/%s/SKILL.md" % s in f for s in SKILLS)
      and all(".agents/skills/%s/SKILL.md" % n in f for n in pj.CODEX_DESC)
      and all(".agents/rules/%s.md" % n in f for n in pj.AG_GLOB)
      and ".agents/agent-kit-guard.py" in f and "the-agent-kit" in json.loads(f[".agents/hooks.json"]), r.out)
rec = r.record()
check("install writes the record, with the kit's time", rec and rec.get("kit_time") == 100 and len(rec["entries"]) > 20, json.dumps(rec)[:200] if rec else "none")
before = r.files()
r.run()
check("a second install changes nothing", r.rc == 0 and r.files() == before, r.out)
r.run("check", apply=False)
check("check after install: exit 0", r.rc == 0, r.out)

# the project's block survives an update of the rules around it
a = read(r.p("AGENTS.md")).replace("<!-- Not configured yet.", "**Stack:** ours\n<!-- Not configured yet.")
a = a.replace("# AGENTS.md", "# AGENTS.md (edited outside the block)", 1)
with open(r.p("AGENTS.md"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write(a)
before = read(r.p("AGENTS.md"))
r.run()
first = r.out
baks = [n for n in os.listdir(r.root) if n.startswith("AGENTS.md.bak-agent-kit-")]
check("uncommitted edits to AGENTS.md are saved beside it before the update, and the run says so",
      baks and read(r.p(baks[0])) == before and "git did not hold" in r.out, r.out)
for n in baks:
    os.remove(r.p(n))
a = read(r.p("AGENTS.md"))
check("the rules around PROJECT-CONFIG are brought back to the kit's; the block is kept",
      "**Stack:** ours" in a and "(edited outside the block)" not in a and "review with git diff AGENTS.md" in first, first)
r.commit()
before = read(r.p("AGENTS.md"))
r.run()
check("a committed AGENTS.md already current is left as it is, and no copy is saved",
      read(r.p("AGENTS.md")) == before and not [n for n in os.listdir(r.root) if ".bak-agent-kit-" in n], r.out)

# an edited kit file is the kit's: replaced (git holds the edit)
with open(r.p(".claude/rules/tests.md"), "a", encoding="utf-8") as fh:
    fh.write("my edit\n")
r.commit()
r.run()
check("an edited kit file is replaced on install", read(r.p(".claude/rules/tests.md"), "rb") == read(os.path.join(KIT, "claude", "rules", "tests.md"), "rb"), r.out)

# what the kit no longer ships: an unchanged file goes, an edited one stays
for rel in (".claude/skills/generating-reports/design.md", ".agents/skills/generating-reports/design.md"):
    os.makedirs(os.path.dirname(r.p(rel)), exist_ok=True)
with open(r.p(".claude/skills/generating-reports/design.md"), "w", newline="\n") as fh:
    fh.write("kit text\n")
with open(r.p(".agents/skills/generating-reports/design.md"), "w", newline="\n") as fh:
    fh.write("kit text, then edited\n")
rec = r.record()
rec["entries"] += [{"kind": "file", "path": ".claude/skills/generating-reports/design.md", "sha": pj.sha("kit text\n")},
                   {"kind": "file", "path": ".agents/skills/generating-reports/design.md", "sha": pj.sha("kit text\n")}]
r.put_record(rec)
r.commit()
r.run()
check("a retired kit file is removed when unchanged, and left (and named) when edited",
      not os.path.exists(r.p(".claude/skills/generating-reports/design.md"))
      and os.path.exists(r.p(".agents/skills/generating-reports/design.md")) and "edited since" in r.out, r.out)
os.remove(r.p(".agents/skills/generating-reports/design.md"))

# a tampered record cannot name the user's own files
os.makedirs(r.p(".claude/rules"), exist_ok=True)
with open(r.p(".claude/rules/mine.md"), "w") as fh:
    fh.write("mine\n")
with open(r.p("src.py"), "w") as fh:
    fh.write("code\n")
rec = r.record()
rec["entries"] += [{"kind": "file", "path": ".claude/rules/mine.md", "sha": pj.sha("mine\n")},
                   {"kind": "file", "path": "src.py", "sha": pj.sha("code\n")},
                   {"kind": "file", "path": "../outside.txt", "sha": None},
                   {"kind": "seed", "path": "README.md", "sha": "x"}]
r.put_record(rec)
r.commit()
r.run()
check("a tampered record cannot remove the user's own files", os.path.exists(r.p(".claude/rules/mine.md"))
      and os.path.exists(r.p("src.py")) and "ignored 4 entries" in r.out, r.out)

# Antigravity's guard entry in another machine's spelling is left alone
h = json.loads(read(r.p(".agents/hooks.json")))
h["the-agent-kit"]["PreToolUse"][0]["hooks"][0]["command"] = "py -3 agent-kit-guard.py --tool antigravity"
with open(r.p(".agents/hooks.json"), "w") as fh:
    json.dump(h, fh)
before = read(r.p(".agents/hooks.json"))
r.run(py="python")
check("the guard entry in a teammate's interpreter spelling is not rewritten", read(r.p(".agents/hooks.json")) == before, r.out)

# a newer kit's record is not touched by an older kit
before = r.files()
r.run(kit_time=50)
check("an older kit refuses to change a project a newer kit installed", r.rc == 1 and r.files() == before and "newer kit" in r.out
      and "AGENT_KIT_FORCE=1" in r.out, r.out)
os.environ["AGENT_KIT_FORCE"] = "1"; r.run(kit_time=50); del os.environ["AGENT_KIT_FORCE"]
check("AGENT_KIT_FORCE=1 gets past the refusal", r.rc == 0 and r.record()["kit_time"] == 50, r.out)
r.run()

# uninstall: the kit's files go; the project's own, and AGENTS.md with its block, stay
r.commit()
r.run("uninstall")
f = r.files()
check("uninstall removes the kit's files and the guard entry, keeps the project's own and its AGENTS.md",
      not any(k.startswith(".claude/skills/") or k.startswith(".agents/skills/") or k.startswith(".agents/rules/") for k in f)
      and ".claude/rules/mine.md" in f and "src.py" in f and "AGENTS.md" in f and "CLAUDE.md" not in f
      and "the-agent-kit" not in json.loads(f.get(".agents/hooks.json", b"{}")) and "PROJECT-CONFIG block" in r.out, r.out)
r.close()

# a fresh install then uninstall leaves nothing of the kit's
r = Repo(); r.run(); r.run("uninstall")
left = [k for k in r.files() if k != ".agents/hooks.json"]
check("install then uninstall on an untouched project leaves nothing but an empty hooks.json", not left, str(left))
r.close()

# a cloned repo whose .claude is a link to the user's real folder: nothing is written through it
r = Repo()
outside = tempfile.mkdtemp(prefix="outside-")
linked = False
if os.name == "nt":
    linked = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.normpath(r.p(".claude")), os.path.normpath(outside)],
                            capture_output=True).returncode == 0
else:
    try:
        os.symlink(outside, r.p(".claude")); linked = True
    except OSError:
        pass
if linked:
    r.run()
    check("a .claude that is a link (or junction) to elsewhere gets nothing written through it",
          os.listdir(outside) == [] and "link" in r.out, r.out)
    os.rmdir(r.p(".claude")) if os.name == "nt" else os.unlink(r.p(".claude"))
shutil.rmtree(outside, ignore_errors=True)
r.close()

# a record that claims a kit time in the future, or does not parse, cannot block updates
r = Repo(); r.run()
rec = r.record(); rec["kit_time"] = 99999999999; r.put_record(rec)
os.remove(r.p(".claude/rules/tests.md"))
r.run()
check("a record with a kit time in the future does not block the install", r.rc == 0
      and os.path.exists(r.p(".claude/rules/tests.md")) and "future" in r.out, r.out)
with open(r.p(".agents/the-agent-kit.json"), "w") as fh:
    fh.write("{ not json")
os.remove(r.p(".claude/rules/tests.md"))
r.run()
check("an unreadable record does not block the install, and is rewritten", r.rc == 0
      and os.path.exists(r.p(".claude/rules/tests.md")) and r.record() is not None, r.out)
r.close()

# a kit file in a folder git ignores is in no commit: an edit to it is saved before the update
r = Repo()
with open(r.p(".gitignore"), "w") as fh:
    fh.write(".claude/\n")
r.run(); r.commit()
with open(r.p(".claude/rules/tests.md"), "a") as fh:
    fh.write("my edit\n")
r.run()
baks = [n for n in os.listdir(r.p(".claude/rules")) if n.startswith("tests.md.bak-agent-kit-")]
check("an edited kit file that git ignores is updated, with the edit saved beside it",
      read(r.p(".claude/rules/tests.md"), "rb") == read(os.path.join(KIT, "claude", "rules", "tests.md"), "rb")
      and baks and read(os.path.join(r.p(".claude/rules"), baks[0])).endswith("my edit\n"), r.out)
r.close()

# AGENTS.md with two blocks, or CRLF line endings
r = Repo()
with open(r.p("AGENTS.md"), "w", newline="\n") as fh:
    fh.write("x\n<!-- PROJECT-CONFIG:START -->\na\n<!-- PROJECT-CONFIG:END -->\nmine\n<!-- PROJECT-CONFIG:START -->\nb\n<!-- PROJECT-CONFIG:END -->\n")
before = read(r.p("AGENTS.md"))
r.commit(); r.run()
check("an AGENTS.md with two PROJECT-CONFIG blocks is left as it is, with a warning",
      read(r.p("AGENTS.md")) == before and "more than one" in r.out, r.out)
with open(r.p("AGENTS.md"), "wb") as fh:
    fh.write(b"old\r\n<!-- PROJECT-CONFIG:START -->\r\n**Stack:** crlf\r\n<!-- PROJECT-CONFIG:END -->\r\n")
r.commit(); r.run()
raw = read(r.p("AGENTS.md"), "rb")
check("an AGENTS.md with CRLF line endings keeps them", b"**Stack:** crlf\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), r.out)
r.close()

# AGENTS.md without markers is never guessed at
r = Repo()
with open(r.p("AGENTS.md"), "w") as fh:
    fh.write("# our own rules\n")
r.run()
check("an AGENTS.md without PROJECT-CONFIG markers is left as it is, with a warning",
      read(r.p("AGENTS.md")) == "# our own rules\n" and "no PROJECT-CONFIG markers" in r.out, r.out)
r.close()

# --lean: the stub, and the stub is never rewritten into rules
r = Repo(); r.run(lean=True)
check("--lean writes the stub AGENTS.md", pj.is_stub(read(r.p("AGENTS.md"))), r.out)
r.run()
check("a full install leaves an existing --lean stub as it is", pj.is_stub(read(r.p("AGENTS.md"))) and "--lean stub" in r.out, r.out)
r.close()

# a project installed before records existed: kit-named files are the kit's; the 0.5.0 design.md goes
r = Repo()
for rel in (".claude/skills/generating-reports/design.md", ".claude/rules/tests.md"):
    os.makedirs(os.path.dirname(r.p(rel)), exist_ok=True)
    with open(r.p(rel), "w") as fh:
        fh.write("old\n")
r.commit()                               # an older install is committed in the project
r.run()
check("no record: the old kit's retired file goes and an old kit file is refreshed",
      not os.path.exists(r.p(".claude/skills/generating-reports/design.md"))
      and read(r.p(".claude/rules/tests.md"), "rb") == read(os.path.join(KIT, "claude", "rules", "tests.md"), "rb"), r.out)
r.close()

failed = [x for x in results if not x[1]]
for name, ok, detail in results:
    print("%s %s" % ("ok  " if ok else "FAIL", name))
    if not ok and detail:
        print("     " + detail.replace("\n", "\n     ")[:1500])
print("project: %d/%d passed" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)

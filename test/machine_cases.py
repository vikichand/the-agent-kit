#!/usr/bin/env python3
"""Cases for setup/machine.py: the install record that makes every install an uninstall of the old kit
followed by an install of the new one. Each case builds a throwaway home and share, runs machine.py the
way install.sh does, and checks the files it leaves behind.

  python3 test/machine_cases.py [path/to/machine.py]

Exit 0 when every case passes. Seconds per run; the full suite (test/run-tests.sh) is the integration gate.
"""
import json, os, shutil, subprocess, sys, tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MACHINE = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(KIT, "setup", "machine.py")
SKILLS = sorted(n for n in os.listdir(os.path.join(KIT, "claude", "skills"))
                if os.path.isfile(os.path.join(KIT, "claude", "skills", n, "SKILL.md")))
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


class Box:
    """A home with Claude Code, Codex and Antigravity folders, a share like ~/.the-agent-kit, and its own
    global git config, so nothing on the real machine is read or written."""

    def __init__(self, tools=("claude", "codex", "antigravity")):
        self.root = tempfile.mkdtemp(prefix="machine-cases-")
        self.home = os.path.join(self.root, "home")
        self.share = os.path.join(self.home, ".the-agent-kit")
        for t, d in (("claude", ".claude"), ("codex", ".codex"), ("antigravity", os.path.join(".gemini", "config"))):
            if t in tools:
                os.makedirs(os.path.join(self.home, d))
        os.makedirs(os.path.join(self.share, "hooks"))
        shutil.copytree(os.path.join(KIT, "claude"), os.path.join(self.share, "claude"),
                        ignore=shutil.ignore_patterns("skills", "rules", "performance"))
        shutil.copytree(os.path.join(KIT, "codex"), os.path.join(self.share, "codex"),
                        ignore=shutil.ignore_patterns("performance"))
        shutil.copytree(os.path.join(KIT, "claude", "skills"), os.path.join(self.share, "skills"))
        for h in ("command-guard.py", "kit-check.py", "agent-kit-check.py"):
            shutil.copy(os.path.join(KIT, "hooks", h), os.path.join(self.share, "hooks", h))
        os.makedirs(os.path.join(self.share, "git-hooks"))
        self.gitcfg = os.path.join(self.root, "gitconfig")
        open(self.gitcfg, "w").close()

    def p(self, *parts):
        return os.path.join(self.home, *parts)

    def run(self, action="install", apply=True, consent=True, share=None):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=self.gitcfg, GIT_CONFIG_NOSYSTEM="1",
                   AGENT_KIT_APPLY="1" if consent else "")
        args = [sys.executable, MACHINE, action, "--home", self.home, "--share", share or self.share,
                "--share-cmd", (share or self.share).replace("\\", "/"), "--py", "python3"]
        if apply:
            args.append("--apply")
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        self.out, self.rc = r.stdout + r.stderr, r.returncode
        return self.rc

    def json(self, *parts):
        with open(self.p(*parts), encoding="utf-8") as f:
            return json.load(f)

    def put_json(self, data, *parts):
        with open(self.p(*parts), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record(self):
        try:
            with open(os.path.join(self.share, ".install-record.json"), encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return None

    def put_record(self, rec):
        with open(os.path.join(self.share, ".install-record.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f)

    def git(self, key):
        r = subprocess.run(["git", "config", "--file", self.gitcfg, "--get", key], capture_output=True, text=True)
        return r.stdout.strip()

    def snapshot(self):
        out = {}
        for d, _, fs in os.walk(self.home):
            for f in fs:
                full = os.path.join(d, f)
                try:
                    with open(full, "rb") as fh:
                        out[os.path.relpath(full, self.home)] = fh.read()
                except OSError:
                    out[os.path.relpath(full, self.home)] = None
        return out

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def commands(settings, event):
    return [h.get("command", "") for b in settings.get("hooks", {}).get(event, []) for h in b.get("hooks", [])]


def toml(path):
    import tomllib
    with open(path, "rb") as f:
        return tomllib.load(f)


def tpl_claude():
    with open(os.path.join(KIT, "claude", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


# ---- a fresh machine ------------------------------------------------------------------------------
b = Box()
b.run(apply=False)
check("plan without --apply exits 10 and writes nothing", b.rc == 10 and b.record() is None
      and not os.path.exists(b.p(".claude", "settings.json")) and not b.git("core.hooksPath"), b.out)
b.run(consent=False)
check("--apply without AGENT_KIT_APPLY=1 refuses and writes nothing", b.rc == 1 and "consent" in b.out
      and not os.path.exists(b.p(".claude", "settings.json")), b.out)
b.run()
s = b.json(".claude", "settings.json"); t = tpl_claude()
check("install: every Claude rule, hook and key is in place", b.rc == 0
      and all(r in s["permissions"]["ask"] for r in t["permissions"]["ask"])
      and all(r in s["permissions"]["deny"] for r in t["permissions"]["deny"])
      and any("command-guard.py" in c for c in commands(s, "PreToolUse"))
      and any("kit-check.py" in c for c in commands(s, "SessionStart"))
      and s.get("includeGitInstructions") is False, b.out)
c = b.json(".codex", "hooks.json")
check("install: Codex hooks and config.toml keys are in place",
      any("command-guard.py" in x for x in commands(c, "PreToolUse"))
      and toml(b.p(".codex", "config.toml")).get("approval_policy") == "on-request", b.out)
check("install: git core.hooksPath points at the share's git-hooks",
      b.git("core.hooksPath").replace("\\", "/").endswith(".the-agent-kit/git-hooks"), b.git("core.hooksPath"))
check("install: one real copy of each kit skill, a Claude link to it, and Antigravity's skills.json entry",
      all(os.path.isfile(b.p(".agents", "skills", n, "SKILL.md")) for n in SKILLS)
      and all(os.path.isfile(b.p(".claude", "skills", n, "SKILL.md")) for n in SKILLS)
      and sorted(b.json(".gemini", "config", "skills.json")["entries"][0]["include_only"]) == SKILLS, b.out)
check("install: Antigravity's session-start hook and its launcher",
      "the-agent-kit-check" in b.json(".gemini", "config", "hooks.json")
      and os.path.isfile(b.p(".gemini", "config", "agent-kit-check.py")), b.out)
rec = b.record()
check("install: the record lists what was installed", rec is not None and rec.get("version") == 1
      and len(rec.get("entries", [])) > 30, json.dumps(rec)[:300] if rec else "no record")
before = b.snapshot()
b.run()
check("a second install changes nothing and backs nothing up", b.rc == 0 and b.snapshot() == before, b.out)
b.run("check", apply=False)
check("check after install: exit 0", b.rc == 0, b.out)

# ---- what the old kit put in and the new one no longer ships ---------------------------------------
# A new kit release drops two settings keys and a config.toml key it used to ship: the share's templates
# are edited the way that release would edit them. The user had changed one of the dropped keys.
claude_file = b.p(".claude", "settings.json")
s = b.json(".claude", "settings.json")
s["permissions"]["ask"] += ["Bash(npx *)", "Bash(mine *)"]
s["attribution"] = {"commit": "mine"}
s["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [
    {"type": "command", "command": 'python3 "%s/hooks/retired.py"' % b.share.replace("\\", "/")}]})
b.put_json(s, ".claude", "settings.json")
tpl = os.path.join(b.share, "claude", "settings.json")
with open(tpl, encoding="utf-8") as f:
    t = json.load(f)
for k in ("worktree", "attribution"):
    t.pop(k)
with open(tpl, "w", encoding="utf-8") as f:
    json.dump(t, f)
ctpl = os.path.join(b.share, "codex", "config.toml")
with open(ctpl, encoding="utf-8") as f:
    ct = f.read()
with open(ctpl, "w", encoding="utf-8") as f:
    f.write(ct.replace('sandbox_mode = "workspace-write"', ""))
shutil.copytree(b.p(".agents", "skills", SKILLS[0]), b.p(".agents", "skills", "old-kit-skill"))
rec = b.record()
rec["entries"] += [
    {"kind": "rule", "file": claude_file, "list": "ask", "value": "Bash(npx *)"},
    {"kind": "hook", "file": claude_file, "event": "PreToolUse", "script": "retired.py",
     "value": {"matcher": "Bash", "hook": {"type": "command", "command": 'python3 "%s/hooks/retired.py"' % b.share.replace("\\", "/")}}},
]
b.put_record(rec)
b.run("check", apply=False)
check("check flags what the kit no longer ships: exit 10", b.rc == 10, b.out)
b.run()
s = b.json(".claude", "settings.json")
check("retired rule, key and hook are removed; the user's own rule is kept",
      "Bash(npx *)" not in s["permissions"]["ask"] and "Bash(mine *)" in s["permissions"]["ask"]
      and "worktree" not in s and not any("retired.py" in x for x in commands(s, "PreToolUse"))
      and any("command-guard.py" in x for x in commands(s, "PreToolUse")), b.out)
check("a retired key the user changed is left, and named",
      s.get("attribution") == {"commit": "mine"} and "attribution" in b.out, b.out)
check("a retired config.toml key is removed; the kit's own keys stay",
      "sandbox_mode" not in toml(b.p(".codex", "config.toml"))
      and toml(b.p(".codex", "config.toml")).get("approval_policy") == "on-request", b.out)
check("a folder that only looks like a retired kit skill (copied mark, not in the record) is left",
      os.path.isdir(b.p(".agents", "skills", "old-kit-skill")), b.out)
shutil.rmtree(b.p(".agents", "skills", "old-kit-skill"))
shutil.copy(os.path.join(KIT, "claude", "settings.json"), tpl)        # back to the current kit
shutil.copy(os.path.join(KIT, "codex", "config.toml"), ctpl)
b.run()

# ---- the three-way rule ----------------------------------------------------------------------------
rec = b.record()
for e in rec["entries"]:   # pretend the kit installed an older timeout last time
    if e["kind"] == "hook" and e["file"] == claude_file and e["script"] == "command-guard.py" and e["event"] == "PreToolUse":
        e["value"]["hook"]["timeout"] = 5
b.put_record(rec)
s = b.json(".claude", "settings.json")
for bl in s["hooks"]["PreToolUse"]:
    for h in bl["hooks"]:
        if "command-guard.py" in h["command"]:
            h["timeout"] = 5
b.put_json(s, ".claude", "settings.json")
b.run()
tmo = [h.get("timeout") for bl in b.json(".claude", "settings.json")["hooks"]["PreToolUse"] for h in bl["hooks"] if "command-guard.py" in h["command"]]
check("a kit entry the user did not change takes the new kit's value", tmo == [15], "%s | %s" % (tmo, b.out))
s = b.json(".claude", "settings.json")
for bl in s["hooks"]["PreToolUse"]:
    for h in bl["hooks"]:
        if "command-guard.py" in h["command"]:
            h["timeout"] = 99
b.put_json(s, ".claude", "settings.json")
b.run()
tmo = [h.get("timeout") for bl in b.json(".claude", "settings.json")["hooks"]["PreToolUse"] for h in bl["hooks"] if "command-guard.py" in h["command"]]
check("a kit entry the user changed keeps the user's value", tmo == [99], "%s | %s" % (tmo, b.out))
b.run("check", apply=False)
check("check: a user's change is not a failure", b.rc == 0, b.out)

# ---- kit-owned folders: the kit's version wins ----------------------------------------------------
with open(b.p(".agents", "skills", SKILLS[0], "SKILL.md"), "w") as f:
    f.write("drifted\n")
b.run()
with open(b.p(".agents", "skills", SKILLS[0], "SKILL.md"), "rb") as f, \
        open(os.path.join(KIT, "claude", "skills", SKILLS[0], "SKILL.md"), "rb") as g:
    check("a drifted kit skill copy is refreshed", f.read() == g.read(), b.out)

# ---- uninstall ------------------------------------------------------------------------------------
s = b.json(".claude", "settings.json")
s["permissions"]["deny"].append("Bash(user-deny *)")
s["myOwnKey"] = True
b.put_json(s, ".claude", "settings.json")
os.makedirs(b.p(".agents", "skills", "mine")); open(b.p(".agents", "skills", "mine", "SKILL.md"), "w").close()
b.run("uninstall")
s = b.json(".claude", "settings.json")
t = tpl_claude()
check("uninstall removes the kit's rules, hooks and keys, and keeps the user's",
      not any(r in s.get("permissions", {}).get("ask", []) for r in t["permissions"]["ask"])
      and "Bash(user-deny *)" in s["permissions"]["deny"] and s.get("myOwnKey") is True
      and not any("kit-check.py" in x for x in commands(s, "SessionStart")), b.out)
check("uninstall keeps a kit entry the user changed, and names it",
      any("command-guard.py" in x for x in commands(s, "PreToolUse")) and "command-guard.py" in b.out, b.out)
check("uninstall removes the skill copies, links, skills.json names and Antigravity hook; the user's skill stays",
      not any(os.path.exists(b.p(".agents", "skills", n)) for n in SKILLS)
      and not any(os.path.lexists(b.p(".claude", "skills", n)) for n in SKILLS)
      and os.path.isfile(b.p(".agents", "skills", "mine", "SKILL.md"))
      and "the-agent-kit-check" not in b.json(".gemini", "config", "hooks.json")
      and not os.path.exists(b.p(".gemini", "config", "agent-kit-check.py")), b.out)
check("uninstall turns git's core.hooksPath back off", b.git("core.hooksPath") == "", b.git("core.hooksPath"))
check("uninstall removes the kit's config.toml keys", "approval_policy" not in toml(b.p(".codex", "config.toml")), b.out)
rec = b.record()
left = sorted((e["kind"], e.get("script") or e.get("key")) for e in rec["entries"]) if rec else None
check("uninstall: the record keeps only what was left (the guard hook and the key the user changed)",
      left == [("hook", "command-guard.py"), ("key", "attribution")], json.dumps(rec)[:300] if rec else "none")
b.close()

# ---- the record is never trusted to say what else is the kit's -------------------------------------
b = Box()
b.run()
s = b.json(".claude", "settings.json")
subprocess.run(["git", "config", "--file", b.gitcfg, "core.sshCommand", "ssh -i mykey"])
other = b.p(".claude.json"); b.put_json({"mcpServers": {"mine": {}}}, ".claude.json")
os.makedirs(b.p("precious")); open(b.p("precious", ".the-agent-kit"), "w").close(); open(b.p("precious", "data.txt"), "w").close()
rec = b.record()
rec["entries"] += [
    {"kind": "key", "file": b.p(".claude", "settings.json"), "key": "permissions", "value": s["permissions"]},
    {"kind": "git", "key": "core.sshCommand", "value": "ssh -i mykey"},
    {"kind": "key", "file": other, "key": "mcpServers", "value": {"mine": {}}},
    {"kind": "dir", "path": b.p("precious"), "name": "precious", "value": "x"},
    {"kind": "rule"},                                   # malformed: must not crash the run
    {"kind": "rule", "file": b.p(".claude", "settings.json"), "list": "deny", "value": "Bash(user-own *)"},
    {"kind": "dir", "path": b.p(".agents"), "name": "..", "value": "x"},
    {"kind": "git", "key": "core.hooksPath", "value": "/somewhere/husky"},
]
b.put_record(rec)
b.run()
check("a tampered record cannot remove the user's permissions, another git key, another file's keys or a folder elsewhere",
      b.rc == 0 and b.json(".claude", "settings.json").get("permissions", {}).get("deny")
      and b.git("core.sshCommand") == "ssh -i mykey" and b.json(".claude.json") == {"mcpServers": {"mine": {}}}
      and os.path.isfile(b.p("precious", "data.txt")) and "ignored 8 entries" in b.out, b.out)

# ---- an update interrupted between its two renames leaves a marked .agent-kit-old: the next run clears it
shutil.copytree(b.p(".agents", "skills", SKILLS[0]), b.p(".agents", "skills", SKILLS[0] + ".agent-kit-old"))
with open(b.p(".agents", "skills", SKILLS[0], "SKILL.md"), "a") as f:
    f.write("drift\n")
b.run()
check("a leftover .agent-kit-old of the kit's is cleared and the skill refreshed", b.rc == 0
      and not os.path.exists(b.p(".agents", "skills", SKILLS[0] + ".agent-kit-old")), b.out)

# ---- consent is to the plan that was shown ---------------------------------------------------------
s = b.json(".claude", "settings.json"); s["permissions"]["ask"].remove("Read(./.env)"); b.put_json(s, ".claude", "settings.json")
stale = os.path.join(b.root, "plan.txt")
with open(stale, "w") as f:
    f.write("  ~/.claude/settings.json\n    + add something else entirely\n")
before = b.snapshot()
env = dict(os.environ, GIT_CONFIG_GLOBAL=b.gitcfg, GIT_CONFIG_NOSYSTEM="1", AGENT_KIT_APPLY="1")
r = subprocess.run([sys.executable, MACHINE, "install", "--home", b.home, "--share", b.share, "--share-cmd",
                    b.share.replace("\\", "/"), "--py", "python3", "--apply", "--expect", stale], capture_output=True, text=True, env=env)
check("a plan that changed since the user said yes is not applied", r.returncode == 1 and b.snapshot() == before
      and "plan changed" in r.stdout, r.stdout)
b.run(apply=False)
with open(stale, "w") as f:
    f.write(b.out)
r = subprocess.run([sys.executable, MACHINE, "install", "--home", b.home, "--share", b.share, "--share-cmd",
                    b.share.replace("\\", "/"), "--py", "python3", "--apply", "--expect", stale], capture_output=True, text=True, env=env)
check("the plan the user said yes to is applied", r.returncode == 0
      and "Read(./.env)" in b.json(".claude", "settings.json")["permissions"]["ask"], r.stdout)
b.close()

# ---- a machine set up by an older kit, before records existed -------------------------------------
b = Box()
sh = b.share.replace("\\", "/")
b.put_json({"permissions": {"ask": ["Write(**/AGENTS.md)", "Bash(npx *)", "Bash(foo *)"], "deny": []},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": 'python3 "%s/hooks/command-guard.py"' % sh}]},
                                     {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/wrap.sh && python3 ~/.the-agent-kit/hooks/command-guard.py --decision ask", "timeout": 99}]}]}},
           ".claude", "settings.json")
os.makedirs(b.p(".agents", "skills", "tidy")); open(b.p(".agents", "skills", "tidy", "SKILL.md"), "w").close()
with open(b.p(".agents", "skills", "tidy", ".the-agent-kit"), "w") as f:
    f.write("This folder is a copy made by the-agent-kit's install.sh; --setup refreshes it and --undo removes it.\n")
os.makedirs(b.p(".agents", "skills", "mine-tidy")); open(b.p(".agents", "skills", "mine-tidy", "SKILL.md"), "w").close()
b.run()
s = b.json(".claude", "settings.json")
guards = [h for bl in s["hooks"]["PreToolUse"] for h in bl["hooks"] if h["command"].strip().endswith("--decision ask") and "wrap.sh" not in h["command"]]
check("first run with no record: retired rules go, the user's rule stays",
      "Write(**/AGENTS.md)" not in s["permissions"]["ask"] and "Bash(npx *)" not in s["permissions"]["ask"]
      and "Bash(foo *)" in s["permissions"]["ask"], b.out)
check("first run with no record: the older kit hook is updated in place, not duplicated",
      len(guards) == 1 and sum("command-guard.py" in h["command"] and "wrap.sh" not in h["command"]
                               for bl in s["hooks"]["PreToolUse"] for h in bl["hooks"]) == 1, json.dumps(s["hooks"]))
check("first run with no record: a user's wrapper that mentions a kit script is untouched",
      any("wrap.sh" in h["command"] and h.get("timeout") == 99 for bl in s["hooks"]["PreToolUse"] for h in bl["hooks"]), b.out)
check("first run with no record: an older kit's marked skill copy is refreshed",
      os.path.getsize(b.p(".agents", "skills", "tidy", "SKILL.md")) > 0, b.out)
b.close()

# ---- what is not the kit's is never touched --------------------------------------------------------
b = Box()
os.makedirs(b.p(".agents", "skills", SKILLS[0])); open(b.p(".agents", "skills", SKILLS[0], "SKILL.md"), "w").close()
subprocess.run(["git", "config", "--file", b.gitcfg, "core.hooksPath", "/somewhere/husky"])
b.run()
check("a skill folder of the user's with a kit skill's name is left, with a warning",
      os.path.getsize(b.p(".agents", "skills", SKILLS[0], "SKILL.md")) == 0 and SKILLS[0] in b.out, b.out)
check("a core.hooksPath another tool owns is left, with a note", b.git("core.hooksPath") == "/somewhere/husky"
      and "hooksPath" in b.out, b.out)
b.close()

b = Box(tools=("codex",))
b.run()
check("a tool that is not on the machine gets nothing", not os.path.exists(b.p(".claude"))
      and not os.path.exists(b.p(".gemini")) and os.path.isfile(b.p(".codex", "hooks.json")), b.out)
b.close()

b = Box()
with open(b.p(".claude", "settings.json"), "w") as f:
    f.write("{ not json")
b.run()
with open(b.p(".claude", "settings.json")) as f:
    left = f.read()
check("an unreadable settings file is left exactly as it is, the others still install, exit 1",
      left == "{ not json" and b.rc == 1 and os.path.isfile(b.p(".codex", "hooks.json")), b.out)
b.close()

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print("%s %s" % ("ok  " if ok else "FAIL", name))
    if not ok and detail:
        print("     " + detail.replace("\n", "\n     ")[:1500])
print("machine: %d/%d passed" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)

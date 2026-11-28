#!/usr/bin/env python3
"""the-agent-kit session-start check: is the kit current, and are this project's rules current?

Runs once when a session starts (Claude Code and Codex both call SessionStart hooks; matcher
`startup|resume`, so a reopened session is covered). Whatever it prints becomes context for the agent, so it prints NOTHING when everything is
current - the common case costs zero tokens - and one line per thing you can act on otherwise.
With `--tool antigravity` this runs as Antigravity's SessionStart hook (an older kit wired it to
PreInvocation, which fires before every model call), acts only on the first call of each conversation
id either way, and always answers in the JSON those hooks expect: {} to say nothing,
{"injectSteps": [{"ephemeralMessage": ...}]} to speak:

  1. A newer release of the kit is on `main`. Checked with `git ls-remote` (no clone, no download) at
     most once a day, with a 3-second limit; the answer is cached in ~/.the-agent-kit so the other
     sessions that day need no network at all.
  2. This project's rules (AGENTS.md above the PROJECT-CONFIG block) differ from the installed kit's.
     `install.sh update` brings every project in ~/.the-agent-kit/.projects current, and this check adds
     the project a session starts in to that list when it holds the kit (.agents/the-agent-kit.json).

  3. A tool the user's recommended list names is missing for the agent that started the session
     (`--tool claude|codex|antigravity`, set by the hook command). The list is ~/.the-agent-kit/recommended.json,
     which install.sh merges the kit's list into by id. The agent is asked to offer them as a checklist:
     a recommended item again a week after it was last offered, an "optional" one once. What the user
     declines the agent records with `kit-check.py --dismiss <id>` (the "dismissed" list), and it is never
     offered again. Items marked "web" only count in a project whose AGENTS.md block marks a web or
     user-facing platform. Read from local files only, and a file it cannot read counts as "cannot
     tell", never as "missing". A headless `claude -p` run is never asked.
  4. The kit's rules are not loaded for that tool: its global rules file exists without them, and the
     project's AGENTS.md and CLAUDE.md (with what it imports) carry none either.
  5. The copy of the rules between AGENT-KIT markers in that global file is from an older kit release.

It never updates or installs anything itself. Running downloaded code on session start, unasked, is exactly the
supply-chain shape the kit's own rules forbid; this only says what to run. It exits 0 on every path,
including every error, so it can never block a session.

Opt out entirely:  AGENT_KIT_NO_UPDATE_CHECK=1  (the adherence harness sets it, so the with-arm of an
eval never receives an instruction the control arm does not).
"""
import glob, json, os, re, shutil, subprocess, sys, time

REPO = os.environ.get("AGENT_KIT_REPO") or "https://github.com/vikichand/the-agent-kit.git"
SHARE = os.path.join(os.path.expanduser("~"), ".the-agent-kit")
CACHE = os.path.join(SHARE, ".update-check")
DAY = 24 * 3600
WEEK = 7 * DAY
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MARK = "PROJECT-CONFIG:START"


def run(args, timeout, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")   # never stop to ask for credentials
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
    return r.stdout if r.returncode == 0 else ""


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().replace("\r\n", "\n")
    except OSError:
        return None


def floor(text):
    """The universal rules: everything above the project block."""
    i = text.find(MARK)
    if i < 0:
        return None
    return text[:text.rfind("\n", 0, i) + 1]


def latest_release():
    """The sha at the tip of `main`, from a same-day cache or from one `git ls-remote`."""
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if time.time() - float(c.get("checked", 0)) < DAY:
            return c.get("latest") or ""
    except (OSError, ValueError, TypeError):
        pass
    try:
        out = run(["git", "ls-remote", "--heads", REPO, "main"], timeout=3)
    except (OSError, subprocess.SubprocessError):
        out = ""
    sha = out.split()[0] if out.split() else ""
    if sha:   # only a real answer is cached; an offline session tries again next time
        try:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump({"checked": time.time(), "latest": sha}, f)
        except OSError:
            pass
    return sha


def load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def installed_antigravity(kind, name, top, home):
    """Antigravity's global root is ~/.gemini/config (built-in docs agy-customizations: SKILL.md,
    skills.md, mcp_servers.md, json_configs.md). A skill is found in its skills folder, in a folder named
    by a skills.json entry, in a plugin, or in the project's .agents/skills; an MCP server in
    mcp_config.json (global or a plugin's)."""
    cfg = os.path.join(home, ".gemini", "config")
    if kind == "skill":
        roots = [os.path.join(cfg, "skills")] + glob.glob(os.path.join(cfg, "plugins", "*", "skills"))
        if top:
            roots.append(os.path.join(top, ".agents", "skills"))
        unreadable = False
        sj = os.path.join(cfg, "skills.json")
        if os.path.exists(sj):
            d = load_json(sj)
            unreadable = not isinstance(d, dict)
            for e in (d.get("entries") or []) if isinstance(d, dict) else []:
                p = e.get("path") if isinstance(e, dict) else None
                if not isinstance(p, str) or (e.get("include_only") and name not in e["include_only"]):
                    continue
                roots.append(os.path.join(home, p[2:]) if p.startswith("~/") else
                             p if os.path.isabs(p) or not top else os.path.join(top, p))
        if any(os.path.isfile(os.path.join(r, name, "SKILL.md")) for r in roots):
            return True
        return None if unreadable else False
    if kind == "mcp":
        names = set()
        for path in [os.path.join(cfg, "mcp_config.json")] + glob.glob(os.path.join(cfg, "plugins", "*", "mcp_config.json")):
            text = read(path) if os.path.exists(path) else ""
            if text is None:
                return None
            if text.strip():   # an empty file is a readable, empty config
                try:
                    d = json.loads(text.lstrip("﻿"))
                except ValueError:
                    return None
                if not isinstance(d, dict):
                    return None
                names |= set(d.get("mcpServers") or {})
        return name in names
    if kind == "plugin":
        return os.path.isdir(os.path.join(cfg, "plugins", name))
    return None


def installed(tool, kind, name, top):
    """True / False, or None when this machine's config cannot be read (never nag on a guess)."""
    home = os.path.expanduser("~")
    if kind == "command":   # a program on PATH, the same for every agent
        return shutil.which(name) is not None
    if tool == "antigravity":
        return installed_antigravity(kind, name, top, home)
    if kind == "skill":
        roots = ([os.path.join(home, ".claude", "skills")] if tool == "claude" else
                 [os.path.join(home, ".agents", "skills"), os.path.join(home, ".codex", "skills")])
        if top:
            roots.append(os.path.join(top, ".claude" if tool == "claude" else ".agents", "skills"))
        return any(os.path.isfile(os.path.join(r, name, "SKILL.md")) for r in roots)
    if tool == "claude":
        if kind == "mcp":
            path = os.path.join(home, ".claude.json")   # absent = nothing configured; unreadable = cannot tell
            cfg = load_json(path) if os.path.exists(path) else {}
            if not isinstance(cfg, dict):
                return None
            names = set(cfg.get("mcpServers") or {})
            if top:
                names |= set(((cfg.get("projects") or {}).get(top) or {}).get("mcpServers") or {})
                names |= set((load_json(os.path.join(top, ".mcp.json")) or {}).get("mcpServers") or {})
            return name in names
        if kind == "plugin" and name.endswith("@builtin"):
            # Shipped inside Claude Code, so never in installed_plugins.json: present when a settings file
            # enables it (code.claude.com/docs/en/plugins/loading: "<name>@<marketplace>": true under enabledPlugins).
            paths = [os.path.join(home, ".claude", "settings.json")]
            if top:
                paths += [os.path.join(top, ".claude", f) for f in ("settings.json", "settings.local.json")]
            found = [load_json(p) for p in paths if os.path.exists(p)]
            on = [s.get("enabledPlugins", {}) for s in found if isinstance(s, dict)]
            if any(isinstance(e, dict) and e.get(name) is True for e in on):
                return True
            return None if len(on) < len(found) or any(not isinstance(e, dict) for e in on) else False
        if kind == "plugin":   # undocumented file: if its shape changes, say nothing rather than guess
            d = load_json(os.path.join(home, ".claude", "plugins", "installed_plugins.json"))
            return name in (d.get("plugins") or {}) if isinstance(d, dict) else None
    if tool == "codex":
        path = os.path.join(home, ".codex", "config.toml")
        text = read(path) if os.path.exists(path) else ""
        if text is None:
            return None
        table = {"mcp": "mcp_servers", "plugin": "plugins"}.get(kind)
        if table is None:
            return None
        pattern = r'^\[%s\.(?:"%s"|%s)\]' % (table, re.escape(name), re.escape(name))
        return re.search(pattern, text, re.M) is not None
    return None


def is_web_project(top):
    text = read(os.path.join(top, "AGENTS.md")) if top else None
    if not text or MARK not in text:
        return False
    block = text[text.find(MARK):]
    return bool(re.search(r"\*\*Quality bars:\*\*", block) or
                re.search(r"(?im)^\*\*[^*\n]*platform[^*\n]*:\*\*[^\n]*\b(web|mobile|desktop|tv)\b", block))


WHO = {"claude": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}
GLOBAL_RULES = {"claude": "~/.claude/CLAUDE.md", "codex": "~/.codex/AGENTS.md", "antigravity": "~/.gemini/AGENTS.md"}
RULES_MARK = "## Safety invariants"   # the first heading of the kit's rules


def carries_rules(path, hops=4):
    """True when the file, or a file it imports with a line-start `@path` (Claude Code's import), holds the
    kit's rules. Hops are bounded, so an import cycle ends."""
    text = read(path)
    if text is None:
        return False
    if RULES_MARK in text:
        return True
    for m in re.finditer(r"(?m)^@(\S+)", text) if hops else ():
        p = m.group(1)
        p = os.path.expanduser(p) if p.startswith("~") else os.path.join(os.path.dirname(path), p)
        if carries_rules(p, hops - 1):
            return True
    return False


def marked_version(path):
    """The x.y.z in a file's `<!-- AGENT-KIT:START x.y.z -->` marker, as a tuple, or None."""
    m = re.search(r"<!-- AGENT-KIT:START (\d+)\.(\d+)\.(\d+) -->", read(path) or "")
    return tuple(int(x) for x in m.groups()) if m else None


def stale_global(tool):
    """One line when the marked copy of the rules in the tool's global file is from an older kit than the
    installed one. An unmarked copy is never judged: nothing could refresh it safely."""
    have = marked_version(os.path.expanduser(GLOBAL_RULES.get(tool, "")))
    kit = marked_version(os.path.join(SHARE, "AGENTS.global.md"))
    if not have or not kit or have >= kit:
        return None
    return ("the-agent-kit: the kit's rules in %s are from %s, older than the installed kit (%s). To refresh "
            "them, run ~/.the-agent-kit/install.sh: it asks first, keeps a backup and changes only what is "
            "between the AGENT-KIT markers." % (GLOBAL_RULES[tool], ".".join(map(str, have)), ".".join(map(str, kit))))


def rules_not_loaded(tool, top):
    """What to say when the tool's global rules file exists without the kit's rules and the project has none
    either: the hooks run, but no rule does. A machine with no global file at all is not judged, so a repo
    that never took the kit stays quiet there."""
    g = os.path.expanduser(GLOBAL_RULES.get(tool, ""))
    if not os.path.isfile(g) or carries_rules(g):
        return None
    base = top or os.getcwd()
    if any(carries_rules(os.path.join(base, f)) for f in ("AGENTS.md", "CLAUDE.md")):
        return None
    return ("the kit's rules are not loaded here (%s has none, and neither has this project): run "
            "~/.the-agent-kit/install.sh in this project, or append ~/.the-agent-kit/AGENTS.global.md to %s."
            % (GLOBAL_RULES[tool], GLOBAL_RULES[tool]))


def one_line(text, limit):
    return " ".join(str(text).split())[:limit]


def recommended_items():
    d = load_json(os.path.join(SHARE, "recommended.json"))
    d = d if isinstance(d, dict) else {}
    items, gone = d.get("items"), d.get("dismissed")
    gone = gone if isinstance(gone, list) else []
    return [i for i in items if isinstance(i, dict) and i.get("id") not in gone] if isinstance(items, list) else []


def check_items(tool, top, optional):
    """[(item, state, install command)] for what the list recommends this tool (optional items only when
    asked for); state is False (missing) or None (this machine's config cannot be read)."""
    web = is_web_project(top)
    out = []
    for it in recommended_items():
        spec = it.get(tool)
        if not isinstance(spec, dict) or bool(it.get("optional")) != optional or (it.get("when") == "web" and not web):
            continue
        kind = next((k for k in ("mcp", "plugin", "skill", "command") if spec.get(k)), None)
        state = installed(tool, kind, spec[kind], top) if kind else True
        if state is not True:
            cmd = (spec.get("install_windows") if os.name == "nt" else None) or \
                spec.get("install", "see the environment setup prompt")
            out.append((it, state, cmd))
    return out


def doctor(top):
    """What `install.sh check` prints about the recommended list: every tool installed on this machine,
    its missing recommended and optional items, and entries that are not the kit's."""
    home = os.path.expanduser("~")
    lines, checked = [], []
    for tool, d in (("claude", ".claude"), ("codex", ".codex"), ("antigravity", ".gemini")):
        if not (os.path.isdir(os.path.join(home, d)) or (tool == "claude" and os.path.isfile(os.path.join(home, ".claude.json")))):
            continue
        checked.append(WHO[tool])
        unloaded = rules_not_loaded(tool, top)
        if unloaded:
            lines.append("  WARN: %s: %s" % (WHO[tool], unloaded))
        for optional in (False, True):
            for it, state, cmd in check_items(tool, top, optional):
                label = "%s%s" % ("optional, " if optional else "", WHO[tool])
                name = it.get("name", it.get("id", "?"))
                if state is None:
                    lines.append("  NOTE: cannot tell whether %s has %s: its config could not be read" % (label, name))
                else:
                    lines.append("  NOTE: %s is missing %s: %s" % (label, name, cmd))
    # The kit's own list sits beside this script (hooks/ in the repo, ~/.the-agent-kit/hooks/ once installed).
    kit = (load_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), "recommended.json")) or {}).get("items")
    kit_names = {n for k in (kit if isinstance(kit, list) else []) if isinstance(k, dict)
                 for n in [k.get("name")] + list(k.get("replaces") or [])}
    for it in recommended_items():
        if not it.get("id") and it.get("name") not in kit_names:   # one the kit knows by name is merged by install.sh
            lines.append("  NOTE: recommended.json entry \"%s\" has no kit id: it is yours, or the kit retired it" % it.get("name", "?"))
    if not os.path.isfile(os.path.join(SHARE, "recommended.json")):
        lines.append("  NOTE: no recommended-tools list yet; install.sh creates ~/.the-agent-kit/recommended.json")
    elif checked and not lines:
        lines.append("  OK:   recommended tools present for %s" % ", ".join(checked))
    return lines


def missing_tools(tool, top):
    """One line asking the agent to offer what the user's list names for this tool and is not installed.
    A recommended item is offered again a week after it was last offered; an optional one is offered
    once. What the user declines is recorded with --dismiss and never offered again."""
    if tool == "claude" and os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli":
        return None   # `claude -p` (seen on 2.1.327; undocumented): nobody is there to answer, so do not spend the offer
    marker = os.path.join(SHARE, ".tools-check")
    seen = load_json(marker)
    asked = seen.get("asked") if isinstance(seen, dict) else None
    asked = asked if isinstance(asked, dict) else {}   # a marker from an older kit ({tool: date}) starts afresh
    mine = asked.get(tool) if isinstance(asked.get(tool), dict) else {}
    now, due = time.time(), {False: [], True: []}
    for optional in (False, True):
        for it, state, cmd in check_items(tool, top, optional):
            key = str(it.get("id") or "")
            # The agent pastes the id into a shell command and reads the rest as text: an id that is not a
            # plain token is never offered, and names and commands are flattened to one bounded line. An
            # entry without an id is the user's own: offered by name, and stopped by deleting it.
            if state is not False or (key and not ID.fullmatch(key)):
                continue
            label = "[%s]" % key if key else "(your own entry, no id)"
            key = key or "name:" + one_line(it.get("name", "?"), 60)
            if key in mine:
                try:
                    age = now - time.mktime(time.strptime(str(mine[key]), "%Y-%m-%d"))
                except (ValueError, OverflowError, OSError):
                    age = WEEK
                if optional or age < WEEK:
                    continue
            due[optional].append("%s %s: %s" % (one_line(it.get("name", key), 120), label, one_line(cmd, 400)))
            mine[key] = time.strftime("%Y-%m-%d")
    if not (due[False] or due[True]):
        return None
    asked[tool] = mine
    tmp = marker + ".tmp%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"asked": asked}, f)
        os.replace(tmp, marker)
    except OSError:
        return None   # an offer that cannot be recorded would repeat every session
    lists = ". ".join(filter(None, [
        due[False] and "Recommended: " + "; ".join(due[False]),
        due[True] and "Optional (leave unticked unless they ask): " + "; ".join(due[True])]))
    me = '"%s" "%s"' % (sys.executable.replace("\\", "/"), os.path.abspath(__file__).replace("\\", "/"))
    return ("the-agent-kit: once you have dealt with the user's first request, offer them these tools, which are "
            "not installed for %s. Ask with your multi-select question tool if you have one (AskUserQuestion on "
            "Claude Code, four options a question at most, so use more questions if needed), otherwise as a "
            "numbered list. %s. For each tool they pick, show the command and run it, except one that needs a key "
            "or holds a <placeholder>, which they run themselves. For the tools they decline, run once %s --dismiss "
            "<each id in brackets> (in PowerShell put & in front) so they are not offered again. A tool they neither pick nor decline is offered "
            "again in a week. A new MCP server, plugin or skill loads in the next session. If no user is "
            "there to answer, skip this." % (WHO[tool], lists, me))


def dismiss(ids):
    """--dismiss <id>...: record in the user's list that these were declined. Nothing is deleted."""
    path = os.path.join(SHARE, "recommended.json")
    d = load_json(path)
    ids = [i for i in ids if ID.fullmatch(i)]
    if os.path.islink(path) or not isinstance(d, dict) or not isinstance(d.get("dismissed", []), list) or not ids:
        print("the-agent-kit: nothing dismissed (no valid id, or %s cannot be read)" % path)
        return 1
    d["dismissed"] = list(dict.fromkeys([i for i in d.get("dismissed", []) if isinstance(i, str)] + ids))
    tmp = path + ".tmp%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as e:
        print("the-agent-kit: could not write %s: %s" % (path, e))
        return 1
    print("the-agent-kit: will not offer again: %s. To undo, remove the id from \"dismissed\" in %s" % (", ".join(ids), path))
    return 0


def first_invocation(data):
    """True once per Antigravity conversation id; the ids seen so far are kept in a small bounded file.
    No id, or a ledger that cannot be written, means False: staying silent beats a note on every call."""
    cid = data.get("conversationId") if isinstance(data, dict) else None
    if not isinstance(cid, str) or not cid:
        return False
    cid = cid[:128]   # the ledger is bounded by count above and by id length here
    path = os.path.join(SHARE, ".ag-conversations")
    d = load_json(path)
    seen = d.get("ids") if isinstance(d, dict) else None
    ids =[i for i in seen if isinstance(i, str)] if isinstance(seen, list) else []
    if cid in ids:
        return False
    tmp = path + ".tmp%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ids": (ids + [cid])[-200:]}, f)
        os.replace(tmp, path)   # a failed or killed write must not leave a half-written ledger
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    return True


def repo_top(cwd):
    try:
        return run(["git", "rev-parse", "--show-toplevel"], timeout=2, cwd=cwd).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def register(top):
    """Add a project that holds the kit to the list `install.sh update` works through, so a project
    installed before the list existed lists itself. update checks every line again before using it."""
    if not os.path.isfile(os.path.join(top, ".agents", "the-agent-kit.json")):
        return
    path, line = os.path.join(SHARE, ".projects"), top.replace("\\", "/")
    if any(ord(c) < 32 or ord(c) == 127 for c in line):   # one path, one line: a folder name cannot add a second
        return
    try:
        if line not in (read(path) or "").split("\n"):
            with open(path, "a", encoding="utf-8", newline="\n") as f:   # appended, never rewritten: sessions start side by side
                f.write(line + "\n")
    except OSError:
        pass


def main():
    if "--dismiss" in sys.argv:
        sys.exit(dismiss(sys.argv[sys.argv.index("--dismiss") + 1:]))
    if "--doctor" in sys.argv:   # asked for by install.sh check: local files only, nothing throttled
        print("\n".join(doctor(repo_top(os.getcwd()))))
        return
    tool = sys.argv[sys.argv.index("--tool") + 1] if "--tool" in sys.argv[:-1] else None
    if os.environ.get("AGENT_KIT_NO_UPDATE_CHECK") == "1" or not os.path.isdir(SHARE):
        if tool == "antigravity":
            print("{}")   # an Antigravity hook must always answer in JSON
        return
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        data = {}
    if tool == "antigravity":
        # SessionStart runs once per conversation, but an older kit's PreInvocation entry fires before EVERY
        # model call until the next install moves it, so a served conversation is answered here, before any
        # git or network work.
        if not first_invocation(data):
            print("{}")
            return
        cwd = next((p for p in (data.get("workspacePaths") or []) if isinstance(p, str)), None) or os.getcwd()
    else:
        cwd = (data.get("cwd") if isinstance(data, dict) else None) or os.getcwd()
    notes = []

    installed = (read(os.path.join(SHARE, ".kit-version")) or "").strip()
    if installed and installed != "unknown":
        latest = latest_release()
        if latest and not latest.startswith(installed):
            notes.append(f"the-agent-kit: a newer release is on main (installed {installed}, latest "
                         f"{latest[:7]}). To update: ~/.the-agent-kit/install.sh update")

    top = repo_top(cwd)
    if top:
        is_kit_repo = os.path.isfile(os.path.join(top, "hooks", "kit-check.py")) and \
            os.path.isfile(os.path.join(top, "install.sh"))
        if not is_kit_repo:
            register(top)
        project = read(os.path.join(top, "AGENTS.md"))
        share = read(os.path.join(SHARE, "AGENTS.md"))
        # Skip: the kit's own repo (its rules are the source, so "update" would overwrite new work with
        # the older installed copy), a --lean stub (its rules live in the global files), and any
        # repo without the markers (nothing the updater could safely do).
        if (project and share and not is_kit_repo
                and "universal rules live in your global" not in project):
            fp, fs = floor(project), floor(share)
            if fp is not None and fs is not None and fp != fs:
                notes.append("the-agent-kit: this project's rules (AGENTS.md above the PROJECT-CONFIG block) "
                             "differ from your installed kit. To bring them current, run here: "
                             "~/.the-agent-kit/install.sh  (it keeps the project block and "
                             "replaces anything hand-edited above it; review with git diff AGENTS.md).")

    if tool in WHO:
        line = rules_not_loaded(tool, top)
        if line:
            notes.append("the-agent-kit: tell the user in one line that " + line)
        line = stale_global(tool)
        if line:
            notes.append(line)
        try:
            line = missing_tools(tool, top)
        except Exception:   # an odd list or marker must not cost the notes already gathered
            line = None
        if line:
            notes.append(line)

    if tool == "antigravity":   # the documented hook output: {} to stay silent, injectSteps to speak
        print(json.dumps({"injectSteps": [{"ephemeralMessage": "\n".join(notes)}]} if notes else {}))
    elif notes:
        print("\n".join(notes))


if __name__ == "__main__":
    try:
        main()
    except Exception:   # never block a session: a broken check is silent, not fatal
        if "antigravity" in sys.argv:
            print("{}")
    sys.exit(0)

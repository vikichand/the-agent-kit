#!/usr/bin/env python3
"""the-agent-kit session-start check: is the kit current, and are this project's rules current?

Runs once when a session starts (Claude Code and Codex both call SessionStart hooks; matcher
`startup`). Whatever it prints becomes context for the agent, so it prints NOTHING when everything is
current - the common case costs zero tokens - and one line per thing you can act on otherwise.
Antigravity has no SessionStart event; with `--tool antigravity` this runs as a PreInvocation hook
(before every model call), acts only on the first call of each conversation id, and always answers in
the JSON that hook expects: {} to say nothing, {"injectSteps": [{"ephemeralMessage": ...}]} to speak:

  1. A newer release of the kit is on `main`. Checked with `git ls-remote` (no clone, no download) at
     most once a day, with a 3-second limit; the answer is cached in ~/.the-agent-kit so the other
     sessions that day need no network at all.
  2. This project's rules (AGENTS.md above the PROJECT-CONFIG block) differ from the installed kit's.
     `install.sh --update` refreshes the machine and never touches a project, so without this a repo
     keeps the rules it was given until someone remembers to run `--update-rules` inside it.

  3. A tool the user's recommended list names is missing for the agent that started the session
     (`--tool claude|codex|antigravity`, set by the hook command). The list is ~/.the-agent-kit/recommended.json,
     which install.sh --setup merges the kit's list into by id: delete an entry (or list its id under
     "dismissed") to stop a reminder. Items marked "optional" are never reminded. Items marked
     "web" only count in a project whose AGENTS.md block marks a web or user-facing platform. At most
     one reminder a day per tool, read from local files only, and a file it cannot read counts as
     "cannot tell", never as "missing".

It never updates or installs anything itself. Running downloaded code on session start, unasked, is exactly the
supply-chain shape the kit's own rules forbid; this only says what to run. It exits 0 on every path,
including every error, so it can never block a session.

Opt out entirely:  AGENT_KIT_NO_UPDATE_CHECK=1  (the adherence harness sets it, so the with-arm of an
eval never receives an instruction the control arm does not).
"""
import glob, json, os, re, subprocess, sys, time

REPO = os.environ.get("AGENT_KIT_REPO") or "https://github.com/vikichand/the-agent-kit.git"
SHARE = os.path.join(os.path.expanduser("~"), ".the-agent-kit")
CACHE = os.path.join(SHARE, ".update-check")
DAY = 24 * 3600
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


def recommended_items():
    items = (load_json(os.path.join(SHARE, "recommended.json")) or {}).get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def check_items(tool, top, optional):
    """[(item, state, install command)] for what the list recommends this tool (optional items only when
    asked for); state is False (missing) or None (this machine's config cannot be read)."""
    web = is_web_project(top)
    out = []
    for it in recommended_items():
        spec = it.get(tool)
        if not isinstance(spec, dict) or bool(it.get("optional")) != optional or (it.get("when") == "web" and not web):
            continue
        kind = next((k for k in ("mcp", "plugin", "skill") if spec.get(k)), None)
        state = installed(tool, kind, spec[kind], top) if kind else True
        if state is not True:
            cmd = (spec.get("install_windows") if os.name == "nt" else None) or \
                spec.get("install", "see the environment setup prompt")
            out.append((it, state, cmd))
    return out


def doctor(top):
    """What `install.sh --check` prints about the recommended list: every tool installed on this machine,
    its missing recommended and optional items, and entries that are not the kit's."""
    home = os.path.expanduser("~")
    lines, checked = [], []
    for tool, d in (("claude", ".claude"), ("codex", ".codex"), ("antigravity", ".gemini")):
        if not (os.path.isdir(os.path.join(home, d)) or (tool == "claude" and os.path.isfile(os.path.join(home, ".claude.json")))):
            continue
        checked.append(WHO[tool])
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
        if not it.get("id") and it.get("name") not in kit_names:   # one the kit knows by name is merged by --setup
            lines.append("  NOTE: recommended.json entry \"%s\" has no kit id: it is yours, or the kit retired it" % it.get("name", "?"))
    if not os.path.isfile(os.path.join(SHARE, "recommended.json")):
        lines.append("  NOTE: no recommended-tools list yet; install.sh --setup creates ~/.the-agent-kit/recommended.json")
    elif checked and not lines:
        lines.append("  OK:   recommended tools present for %s" % ", ".join(checked))
    return lines


def missing_tools(tool, top):
    """One line naming what the user's list recommends for this tool and is not installed."""
    gaps = ["%s (%s)" % (it.get("name", it.get("id", "?")), cmd)
            for it, state, cmd in check_items(tool, top, False) if state is False]
    if not gaps:
        return None
    marker = os.path.join(SHARE, ".tools-check")
    seen = load_json(marker) or {}
    today = time.strftime("%Y-%m-%d")
    if seen.get(tool) == today:
        return None
    seen[tool] = today
    try:
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(seen, f)
    except OSError:
        pass
    return ("the-agent-kit: tell the user once, in one line, that these recommended tools are not installed "
            "for %s, with the command to install each: %s. Install nothing without their yes, and let them "
            "run any command that needs a key. To stop a reminder, list its id under \"dismissed\" in "
            "~/.the-agent-kit/recommended.json." % (WHO[tool], "; ".join(gaps)))


def first_invocation(data):
    """True once per Antigravity conversation id; the ids seen so far are kept in a small bounded file.
    No id, or a ledger that cannot be written, means False: staying silent beats a note on every call."""
    cid = data.get("conversationId") if isinstance(data, dict) else None
    if not isinstance(cid, str) or not cid:
        return False
    path = os.path.join(SHARE, ".ag-conversations")
    d = load_json(path)
    seen = d.get("ids") if isinstance(d, dict) else None
    ids =[i for i in seen if isinstance(i, str)] if isinstance(seen, list) else []
    if cid in ids:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ids": (ids + [cid])[-200:]}, f)
    except OSError:
        return False
    return True


def repo_top(cwd):
    try:
        return run(["git", "rev-parse", "--show-toplevel"], timeout=2, cwd=cwd).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    if "--doctor" in sys.argv:   # asked for by install.sh --check: local files only, nothing throttled
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
        # PreInvocation fires before EVERY model call and blocks the loop while it runs, so a conversation
        # that has already been served is answered here, before any git or network work.
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
                         f"{latest[:7]}). To update the machine: ~/.the-agent-kit/install.sh --update")

    top = repo_top(cwd)
    if top:
        is_kit_repo = os.path.isfile(os.path.join(top, "hooks", "kit-check.py")) and \
            os.path.isfile(os.path.join(top, "install.sh"))
        project = read(os.path.join(top, "AGENTS.md"))
        share = read(os.path.join(SHARE, "AGENTS.md"))
        # Skip: the kit's own repo (its rules are the source, so "update" would overwrite new work with
        # the older installed copy), an --extension stub (its rules live in the global files), and any
        # repo without the markers (nothing the updater could safely do).
        if (project and share and not is_kit_repo
                and "universal rules live in your global" not in project):
            fp, fs = floor(project), floor(share)
            if fp is not None and fs is not None and fp != fs:
                notes.append("the-agent-kit: this project's rules (AGENTS.md above the PROJECT-CONFIG block) "
                             "differ from your installed kit. To bring them current, run here: "
                             "~/.the-agent-kit/install.sh --update-rules  (it keeps the project block and "
                             "replaces anything hand-edited above it; review with git diff AGENTS.md).")

    if tool in WHO:
        line = missing_tools(tool, top)
        if line:
            notes.append(line)

    if tool == "antigravity":   # the documented PreInvocation output: {} to stay silent, injectSteps to speak
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

#!/usr/bin/env python3
"""the-agent-kit session-start check: is the kit current, and are this project's rules current?

Runs once when a session starts (Claude Code and Codex both call SessionStart hooks; matcher
`startup`). Whatever it prints becomes context for the agent, so it prints NOTHING when everything is
current - the common case costs zero tokens - and one line per thing you can act on otherwise:

  1. A newer release of the kit is on `main`. Checked with `git ls-remote` (no clone, no download) at
     most once a day, with a 3-second limit; the answer is cached in ~/.the-agent-kit so the other
     sessions that day need no network at all.
  2. This project's rules (AGENTS.md above the PROJECT-CONFIG block) differ from the installed kit's.
     `install.sh --update` refreshes the machine and never touches a project, so without this a repo
     keeps the rules it was given until someone remembers to run `--update-rules` inside it.

  3. A tool the user's recommended list names is missing for the agent that started the session
     (`--tool claude|codex`, set by the settings snippet). The list is ~/.the-agent-kit/recommended.json,
     seeded from the kit once and then the user's: delete an entry to stop a reminder. Items marked
     "web" only count in a project whose AGENTS.md block marks a web or user-facing platform. At most
     one reminder a day per tool, read from local files only, and a file it cannot read counts as
     "cannot tell", never as "missing".

It never updates or installs anything itself. Running downloaded code on session start, unasked, is exactly the
supply-chain shape the kit's own rules forbid; this only says what to run. It exits 0 on every path,
including every error, so it can never block a session.

Opt out entirely:  AGENT_KIT_NO_UPDATE_CHECK=1  (the adherence harness sets it, so the with-arm of an
eval never receives an instruction the control arm does not).
"""
import json, os, re, subprocess, sys, time

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


def installed(tool, kind, name, top):
    """True / False, or None when this machine's config cannot be read (never nag on a guess)."""
    home = os.path.expanduser("~")
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


def missing_tools(tool, top):
    """One line naming what the user's list recommends for this tool and is not installed."""
    items = (load_json(os.path.join(SHARE, "recommended.json")) or {}).get("items") or []
    web = is_web_project(top)
    gaps = []
    for it in items:
        spec = it.get(tool) if isinstance(it, dict) else None
        if not isinstance(spec, dict) or (it.get("when") == "web" and not web):
            continue
        kind = next((k for k in ("mcp", "plugin", "skill") if spec.get(k)), None)
        if kind and installed(tool, kind, spec[kind], top) is False:
            gaps.append("%s (%s)" % (it.get("name", spec[kind]), spec.get("install", "see the environment setup prompt")))
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
    who = "Claude Code" if tool == "claude" else "Codex"
    return ("the-agent-kit: recommended for %s but not installed: %s. Mention this to the user once and "
            "offer to install; install only what they approve, and let them run any command that needs a "
            "key. To stop a reminder, remove its entry from ~/.the-agent-kit/recommended.json."
            % (who, "; ".join(gaps)))


def main():
    if os.environ.get("AGENT_KIT_NO_UPDATE_CHECK") == "1" or not os.path.isdir(SHARE):
        return
    tool = sys.argv[sys.argv.index("--tool") + 1] if "--tool" in sys.argv[:-1] else None
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        data = {}
    cwd = (data.get("cwd") if isinstance(data, dict) else None) or os.getcwd()
    notes = []

    installed = (read(os.path.join(SHARE, ".kit-version")) or "").strip()
    if installed and installed != "unknown":
        latest = latest_release()
        if latest and not latest.startswith(installed):
            notes.append(f"the-agent-kit: a newer release is on main (installed {installed}, latest "
                         f"{latest[:7]}). To update the machine: ~/.the-agent-kit/install.sh --update")

    try:
        top = run(["git", "rev-parse", "--show-toplevel"], timeout=2, cwd=cwd).strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
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

    if tool in ("claude", "codex"):
        line = missing_tools(tool, top)
        if line:
            notes.append(line)

    if notes:
        print("\n".join(notes))


if __name__ == "__main__":
    try:
        main()
    except Exception:   # never block a session: a broken check is silent, not fatal
        pass
    sys.exit(0)

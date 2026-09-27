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

It never updates anything itself. Running downloaded code on session start, unasked, is exactly the
supply-chain shape the kit's own rules forbid; this only says what to run. It exits 0 on every path,
including every error, so it can never block a session.

Opt out entirely:  AGENT_KIT_NO_UPDATE_CHECK=1  (the adherence harness sets it, so the with-arm of an
eval never receives an instruction the control arm does not).
"""
import json, os, subprocess, sys, time

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


def main():
    if os.environ.get("AGENT_KIT_NO_UPDATE_CHECK") == "1" or not os.path.isdir(SHARE):
        return
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

    if notes:
        print("\n".join(notes))


if __name__ == "__main__":
    try:
        main()
    except Exception:   # never block a session: a broken check is silent, not fatal
        pass
    sys.exit(0)

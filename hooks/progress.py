#!/usr/bin/env python3
"""Progress updates: while work runs longer than a few minutes, tell the agent to update the user.

No timer runs while the agent works. The user's message stamps a small per-session file; each finished
tool call compares the clock with it and, once the interval has passed, hands the agent a note asking
for an update. Only the session the user types in is nudged: subagents, headless runs and sessions
another agent started are workers, and their lead reports for them.

  --event prompt   UserPromptSubmit: stamp the clock (a task notification does not count as the user)
  --event tool     PostToolUse: say nothing, or emit the note as additionalContext
  --event stop     Stop, run with asyncRewake (Claude Code): when the turn ends with background work
                   still running, wait for the interval and wake the agent with the note (exit 2)
  --event invocation   Antigravity's PreInvocation, which runs before every model call and carries the
                   user's latest message: it does the work of both prompt and tool there

AGENT_KIT_UPDATE_MINUTES sets the interval (default 8, 0 turns it off).
"""
import json
import math
import os
import re
import sys
import time

DEFAULT_MINUTES = 8
MAX_MINUTES = 55   # the waiter's hook timeout is one hour; a longer wait would be killed without a word
# A background task that never ends (a dev server) would wake the agent for ever, each wake a paid turn.
MAX_WAKES = 30     # about four hours at the default interval
QUIET = "no work in progress"
STALE_DAYS = 7     # state files of sessions long gone are swept when a new session starts

AGENT_MARKERS = ("CLAUDE_CODE_CHILD_SESSION", "CODEX_THREAD_ID", "ANTIGRAVITY_CONVERSATION_ID")
OWN = {"claude": ("CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"),
       "codex": ("CODEX_THREAD_ID",), "antigravity": ("ANTIGRAVITY_CONVERSATION_ID",)}


def interval():
    try:
        m = float(os.environ.get("AGENT_KIT_UPDATE_MINUTES", DEFAULT_MINUTES))
    except ValueError:
        m = DEFAULT_MINUTES
    return min(m, MAX_MINUTES) * 60 if m > 0 else 0


def worker(tool, data):
    """True when nobody reads this session directly. The same signals as the guard's started_by_agent()."""
    e = os.environ
    if data.get("agent_id"):
        return True
    if e.get("CLAUDE_CODE_SESSION_ATTENDED") == "0" or e.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk"):
        return True
    return any(e.get(v) for v in AGENT_MARKERS + OWN["claude"] if v not in OWN[tool])


def state_dir():
    # Under the user's own kit folder, not the temp folder: on a shared machine /tmp is writable by
    # everyone, and a file planted there under a known name could be followed or block the hook.
    return os.path.join(os.path.expanduser("~"), ".the-agent-kit", "progress")


def state_path(session):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", session)[:64]
    return os.path.join(state_dir(), sid + ".json") if sid else None


def sweep(now):
    d = state_dir()
    for n in os.listdir(d):
        p = os.path.join(d, n)
        try:
            if now - os.path.getmtime(p) > STALE_DAYS * 86400:
                os.remove(p)
        except OSError:
            pass   # another session's sweep got there first


def load(path):
    try:
        with open(path) as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None
    ok = isinstance(s, dict) and all(type(s.get(k)) in (int, float) and math.isfinite(s[k])
                                     for k in ("last", "start", "gen", "wakes"))
    return s if ok else None


def save(path, s):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(s, f)
    put(tmp, path)


def put(src, dst):
    # Windows refuses to replace a file another hook has open for reading, so try again for a moment.
    for attempt in range(10):
        try:
            return os.replace(src, dst)
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02)


def clock(t):
    return time.strftime("%I:%M%p", time.localtime(t)).lstrip("0").lower()


def note(s, now, waiting=False, last=False):
    mins = max(1, int(round((now - s["start"]) / 60)))
    text = ("Progress update due (the-agent-kit). It is now %s and this request has been running for %d minute%s. "
            % (clock(now), mins, "" if mins == 1 else "s"))
    text += ("You are waiting on background work: check the output of each background task and each agent "
             "you delegated to, then " if waiting else
             "Before your next step, check the output of any background task or agent you delegated to, then ")
    text += ("give the user one short update: done (with pass counts), running now, what's left. End it with "
             "\"Estimated ETA: <time remaining, e.g. '53 mins' or '1 hour, 23 mins'> | <finish time on the "
             "clock, e.g. '8:20am'>\", worked out from %s." % clock(now))
    if waiting:
        text += (" If nothing is still working on the user's request (only a server left running, say), "
                 "reply with one line that says so and contains the words \"%s\"; the updates then stop." % QUIET)
    if last:
        text += " This is the last automatic update for this request: tell the user the updates have stopped."
    return text


def on_prompt(path, data, now):
    s = load(path)
    if not s:
        os.makedirs(state_dir(), mode=0o700, exist_ok=True)
        sweep(now)
        s = {"last": now, "start": now, "gen": 0, "wakes": 0}
    s["gen"] += 1   # any new turn retires a waiter left from the last one
    # A turn the tool starts itself (a finished background task, the waiter's own wake-up) reaches this
    # hook like a message. It must not reset the clock or the wake count, or the cap would never bite.
    woke = s.pop("woke", 0)
    own = type(woke) in (int, float) and 0 <= now - woke < 60
    if not own and not str(data.get("prompt") or "").lstrip().startswith("<task-notification>"):
        s.update(last=now, start=now, wakes=0, quiet=False)
    save(path, s)
    return 0


def due(path, now, wait):
    """The update note when the interval has passed, and the clock restarted; otherwise None."""
    s = load(path)
    if not s or now - s["last"] < wait:
        return None
    # Tool calls that finish together all get here. Creating the lock file is the claim: one create
    # wins, and the winner reads the state again in case an earlier winner has already reset the clock.
    lock = path + ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        try:
            if now - os.path.getmtime(lock) > 60:   # left by a hook that died: clear it for the next call
                os.remove(lock)
        except OSError:
            pass
        return None
    try:
        s = load(path)
        if s and now - s["last"] >= wait:
            text = note(s, now)
            s["last"] = now
            save(path, s)
            return text
    finally:
        os.close(fd)
        os.remove(lock)
    return None


def on_invocation(path, data, now, wait):
    import hashlib
    msg = hashlib.sha256(str(data.get("lastUserInput") or "").encode("utf-8", "replace")).hexdigest()[:16]
    s = load(path)
    if s and s.get("msg") == msg:
        return due(path, now, wait)
    # ponytail: the same message sent twice in a row does not restart the clock; compare the transcript's
    # entry time as the guard's antigravity_grants() does if that ever matters.
    on_prompt(path, {}, now)
    s = load(path)
    s["msg"] = msg
    save(path, s)
    return None


def on_stop(path, data, wait):
    s = load(path)
    if not s:
        return 0
    s["gen"] += 1
    mine = s["gen"]
    if QUIET in str(data.get("last_assistant_message") or "").lower():
        s["quiet"] = True
    tasks = data.get("background_tasks")
    running = isinstance(tasks, list) and any(isinstance(t, dict) and t.get("status") == "running" for t in tasks)
    save(path, s)
    if not running or s.get("quiet") or s["wakes"] >= MAX_WAKES:
        return 0
    give_up = time.monotonic() + wait + 60   # a clock set backwards must not hold the waiter for its full timeout
    while True:
        time.sleep(min(5, wait / 4))
        s = load(path)
        if not s or s["gen"] != mine or time.monotonic() > give_up:
            return 0
        now = time.time()
        if now - s["last"] >= wait:
            break
    s["wakes"] += 1
    s["last"] = s["woke"] = now
    save(path, s)
    sys.stderr.write(note(s, now, waiting=True, last=s["wakes"] >= MAX_WAKES) + "\n")
    return 2


def run(tool, event):
    """(exit code, note for the agent or None)."""
    wait = interval()
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0, None
    if not wait or not isinstance(data, dict) or worker(tool, data):
        return 0, None
    path = state_path(str(data.get("conversationId" if tool == "antigravity" else "session_id") or ""))
    if not path:
        return 0, None
    if event == "prompt":
        return on_prompt(path, data, time.time()), None
    if event == "tool":
        return 0, due(path, time.time(), wait)
    if event == "invocation":
        return 0, on_invocation(path, data, time.time(), wait)
    if event == "stop":
        return on_stop(path, data, wait), None
    return 0, None


def main(argv):
    tool = argv[argv.index("--tool") + 1]
    event = argv[argv.index("--event") + 1]
    if tool != "antigravity":
        rc, text = run(tool, event)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
        return rc
    out = {}
    try:
        text = run(tool, event)[1]
        if text:
            out = {"injectSteps": [{"ephemeralMessage": text}]}
    finally:
        print(json.dumps(out))   # an Antigravity hook must always answer in JSON, a failing one included
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

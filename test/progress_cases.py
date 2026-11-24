#!/usr/bin/env python3
"""Cases for hooks/progress.py. Usage: python test/progress_cases.py hooks/progress.py

Each case runs the hook as a tool would: JSON on stdin, a clean environment, and a home folder of its own
for the state file. Time is moved by writing an old `last` into the state, never by sleeping for minutes."""
import json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

HOOK = os.path.abspath(sys.argv[1])
MARKERS = ("CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ATTENDED",
           "CODEX_THREAD_ID", "ANTIGRAVITY_CONVERSATION_ID", "AGENT_KIT_UPDATE_MINUTES")
fails = 0
count = 0


def check(name, ok, detail=""):
    global fails, count
    count += 1
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  [" + str(detail)[:300] + "]"))


class Box:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="progress-")

    def env(self, extra):
        e = {k: v for k, v in os.environ.items() if k not in MARKERS}
        e.update({"HOME": self.tmp, "USERPROFILE": self.tmp, "CLAUDE_CODE_ENTRYPOINT": "cli"})
        e.update(extra or {})
        return e

    def start(self, event, data, tool="claude", env=None):
        e = self.env(env)
        if tool == "codex" and "CLAUDE_CODE_ENTRYPOINT" not in (env or {}):
            del e["CLAUDE_CODE_ENTRYPOINT"]   # to Codex, any Claude Code variable means Claude started it
        p = subprocess.Popen([sys.executable, HOOK, "--tool", tool, "--event", event], env=e,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p.stdin.write(data if isinstance(data, str) else json.dumps(data)); p.stdin.close()
        return p

    def run(self, event, data, tool="claude", env=None, timeout=30):
        p = self.start(event, data, tool, env)
        p.wait(timeout)
        return p.returncode, p.stdout.read(), p.stderr.read()

    def path(self, sid="s1"):
        return os.path.join(self.tmp, ".the-agent-kit", "progress", sid + ".json")

    def state(self, sid="s1"):
        with open(self.path(sid)) as f:
            return json.load(f)

    def age(self, seconds, sid="s1", **more):
        s = self.state(sid)
        s["last"] -= seconds
        s["start"] -= seconds
        s.update(more)
        with open(self.path(sid), "w") as f:
            json.dump(s, f)


def note(out):
    try:
        h = json.loads(out)["hookSpecificOutput"]
        return h["additionalContext"] if h["hookEventName"] == "PostToolUse" else ""
    except (ValueError, KeyError, TypeError):
        return ""


USER = {"session_id": "s1", "prompt": "run the suite"}
TOOL = {"session_id": "s1", "tool_name": "Bash"}
RUNNING = {"session_id": "s1", "last_assistant_message": "started",
           "background_tasks": [{"id": "a", "type": "shell", "status": "running"}]}
FAST = {"AGENT_KIT_UPDATE_MINUTES": "0.02"}   # 1.2 seconds

# -- the tool-call check ---------------------------------------------------------------------------
b = Box()
b.run("prompt", USER)
rc, out, err = b.run("tool", TOOL)
check("nothing is said before the interval has passed", rc == 0 and out == "" and os.path.isfile(b.path()), out + err)

b.age(600)
rc, out, err = b.run("tool", TOOL)
check("after 8 minutes the next tool call carries the update note, with the ETA line",
      rc == 0 and "Estimated ETA:" in note(out) and "10 minutes" in note(out), out + err)
rc, out, err = b.run("tool", TOOL)
check("the note resets the clock: the next tool call says nothing", rc == 0 and out == "", out + err)

b.age(600)
rc, out, err = b.run("tool", TOOL, tool="codex")
check("Codex gets the same note in the same shape", "Estimated ETA:" in note(out), out + err)

b.age(600)
rc, out, err = b.run("tool", TOOL, env={"AGENT_KIT_UPDATE_MINUTES": "0"})
rc2, out2, err2 = b.run("tool", TOOL, env={"AGENT_KIT_UPDATE_MINUTES": "20"})
rc3, out3, err3 = b.run("tool", TOOL, env={"AGENT_KIT_UPDATE_MINUTES": "soon"})
check("AGENT_KIT_UPDATE_MINUTES: 0 turns it off, 20 waits longer, a bad value means the default",
      out == "" and out2 == "" and "Estimated ETA:" in note(out3), out + out2 + out3 + err3)

# -- who gets it: only the session the user types in ------------------------------------------------
b = Box()
b.run("prompt", USER); b.age(600)
rc, out, err = b.run("tool", dict(TOOL, agent_id="sub1", agent_type="Explore"))
rc2, out2, err2 = b.run("tool", TOOL, env={"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
rc3, out3, err3 = b.run("tool", TOOL, tool="codex", env={"CLAUDECODE": "1"})
rc4, out4, err4 = b.run("tool", TOOL, env={"CODEX_THREAD_ID": "t1"})
check("a subagent, a headless run and a session another agent started are never nudged",
      out == out2 == out3 == out4 == "" and rc == rc2 == rc3 == rc4 == 0, out + out2 + out3 + out4)
b2 = Box()
b2.run("prompt", USER, env={"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
b2.run("prompt", {"prompt": "no session id"})
check("a headless run, or input with no session id, keeps no state", os.listdir(b2.tmp) == [], os.listdir(b2.tmp))

# -- notifications are not the user -----------------------------------------------------------------
b = Box()
b.run("prompt", USER); b.age(600, wakes=2)
before = b.state()
b.run("prompt", {"session_id": "s1", "prompt": "<task-notification>\n<status>completed</status>\n</task-notification>"})
mid = b.state()
b.run("prompt", USER)
after = b.state()
check("a task notification keeps the clock running; the user's own message resets it",
      mid["last"] == before["last"] and mid["wakes"] == 2 and mid["gen"] > before["gen"]
      and after["wakes"] == 0 and after["last"] > mid["last"], (before, mid, after))

# -- malformed and hostile input ---------------------------------------------------------------------
b = Box()
os.makedirs(os.path.dirname(b.path()))
with open(b.path(), "w") as f:
    f.write("{ not json")
rc, out, err = b.run("tool", TOOL)
with open(b.path(), "w") as f:
    json.dump({"last": "yesterday", "gen": [], "wakes": None}, f)
rc2, out2, err2 = b.run("tool", TOOL)
rc3, out3, err3 = b.run("stop", RUNNING, env=FAST, timeout=10)
with open(b.path(), "w") as f:
    f.write('{"last": 1, "start": Infinity, "gen": 1, "wakes": NaN}')
rc4, out4, err4 = b.run("tool", TOOL)
check("an unreadable or oddly shaped state file means no note and no waiter, not a crash",
      (rc, out, rc2, out2, rc3, rc4, out4) == (0, "", 0, "", 0, 0, ""), (rc, out, err, rc2, out2, err2, rc3, err3, rc4, err4))
rc, out, err = b.run("tool", "not json at all")
check("input that is not JSON is ignored quietly", rc == 0 and out == "", (rc, out, err))
b = Box()
b.run("prompt", {"session_id": "../../../evil/..\\x", "prompt": "hi"})
found = [os.path.relpath(os.path.join(d, f), b.tmp).replace("\\", "/") for d, _, fs in os.walk(b.tmp) for f in fs]
check("a session id cannot steer the state file out of the kit's own folder",
      found == [".the-agent-kit/progress/evilx.json"], found)
old = os.path.join(os.path.dirname(b.path()), "gone.json")
open(old, "w").close(); os.utime(old, (time.time() - 9 * 86400,) * 2)
b.run("prompt", {"session_id": "s2", "prompt": "hi"})
check("a new session sweeps state files left by sessions more than a week old",
      sorted(os.listdir(os.path.dirname(b.path()))) == ["evilx.json", "s2.json"], os.listdir(os.path.dirname(b.path())))

# -- parallel tool calls -----------------------------------------------------------------------------
b = Box()
b.run("prompt", USER)
rounds = []
for _ in range(5):   # the race this guards against showed up in about one run in five
    b.age(600)
    with ThreadPoolExecutor(12) as ex:
        outs = list(ex.map(lambda _: b.run("tool", TOOL), range(12)))
    rounds.append((sum(1 for rc, out, err in outs if "Estimated ETA:" in note(out)), [err for rc, out, err in outs if rc]))
check("twelve tool calls finishing together give one note, not twelve, five times over",
      rounds == [(1, [])] * 5 and b.state()["gen"] >= 1, rounds)

# -- Antigravity: one hook before every model call ------------------------------------------------------
def ag(box, text, env=None, raw=None):
    e = {"CLAUDE_CODE_ENTRYPOINT": ""}
    e.update(env or {})
    rc, out, err = box.run("invocation", raw or {"conversationId": "s1", "lastUserInput": text}, tool="antigravity", env=e)
    try:
        steps = json.loads(out).get("injectSteps") or []
    except ValueError:
        return rc, None
    return rc, " ".join(str(x.get("ephemeralMessage", "")) for x in steps)


b = Box()
first = ag(b, "build it")
b.age(600)
due_now = ag(b, "build it")
again = ag(b, "build it")
b.age(600)
new_msg = ag(b, "now the docs")
check("Antigravity: the first model call stamps the clock, a later one past the interval carries the note once",
      first == (0, "") and due_now[0] == 0 and "Estimated ETA:" in due_now[1] and again == (0, ""), (first, due_now, again))
check("Antigravity: a new message from the user restarts the clock", new_msg == (0, ""), new_msg)
b.age(600)
worker_run = ag(b, "now the docs", env={"CLAUDECODE": "1"})
garbage = ag(b, "", raw="not json")
off = ag(b, "now the docs", env={"AGENT_KIT_UPDATE_MINUTES": "0"})
check("Antigravity: a worker, bad input and the off switch all still answer in JSON, with no note",
      worker_run == garbage == off == (0, ""), (worker_run, garbage, off))

# -- the waiter: waking an idle lead ------------------------------------------------------------------
b = Box()
b.run("prompt", USER)
t = time.time()
rc, out, err = b.run("stop", {"session_id": "s1", "background_tasks": []}, env=FAST, timeout=10)
rc2, out2, err2 = b.run("stop", {"session_id": "s1", "background_tasks": [{"id": "a", "status": "completed"}]}, env=FAST, timeout=10)
check("with nothing running in the background, no waiter stays behind", rc == 0 and rc2 == 0 and err == "" and time.time() - t < 8, (rc, rc2, err))

rc, out, err = b.run("stop", RUNNING, env=FAST, timeout=20)
check("with background work running, the waiter wakes the agent at the interval with the update note",
      rc == 2 and "Estimated ETA:" in err and "background" in err and b.state()["wakes"] == 1, (rc, out, err))
b.run("prompt", {"session_id": "s1", "prompt": "Stop hook feedback: Progress update due"})
kept = b.state()["wakes"]
b.run("prompt", {"session_id": "s1", "prompt": "thanks, carry on"})
check("the turn the wake-up starts does not reset the wake count, whatever it looks like; the user's next message does",
      kept == 1 and b.state()["wakes"] == 0, (kept, b.state()))

b.run("prompt", USER)
w = b.start("stop", RUNNING, env={"AGENT_KIT_UPDATE_MINUTES": "0.1"})   # 6 seconds
time.sleep(1.5)
b.run("prompt", USER)
rc = w.wait(10)
check("a new message from the user ends the waiter early and quietly", rc == 0 and w.stderr.read() == "", rc)

b.run("prompt", USER)
w1 = b.start("stop", RUNNING, env={"AGENT_KIT_UPDATE_MINUTES": "0.05"})  # 3 seconds
time.sleep(1)
w2 = b.start("stop", RUNNING, env={"AGENT_KIT_UPDATE_MINUTES": "0.05"})
r1, r2 = w1.wait(15), w2.wait(15)
check("one waiter per session: a newer one replaces the older", (r1, r2) == (0, 2), (r1, r2))

b.run("prompt", USER); b.age(0, wakes=1)
rc, out, err = b.run("stop", dict(RUNNING, last_assistant_message="Only the dev server is left. No work in progress."), env=FAST, timeout=10)
rc2, out2, err2 = b.run("stop", RUNNING, env=FAST, timeout=10)
b.run("prompt", USER)
rc3, out3, err3 = b.run("stop", RUNNING, env=FAST, timeout=20)
check("\"no work in progress\" stops the wake-ups until the user's next message", (rc, rc2, rc3) == (0, 0, 2), (rc, rc2, rc3, err3))

b.run("prompt", USER); b.age(0, wakes=29)
rc, out, err = b.run("stop", RUNNING, env=FAST, timeout=20)
rc2, out2, err2 = b.run("stop", RUNNING, env=FAST, timeout=10)
check("the wake-ups are capped: the last one says so, and no waiter follows it",
      rc == 2 and "last automatic update" in err and rc2 == 0, (rc, err, rc2))

rc, out, err = b.run("stop", RUNNING, env={"AGENT_KIT_UPDATE_MINUTES": "0"}, timeout=10)
rc2, out2, err2 = b.run("stop", RUNNING, env=dict(FAST, CLAUDE_CODE_ENTRYPOINT="sdk-cli"), timeout=10)
check("turned off, or in a headless run, no waiter starts", (rc, rc2) == (0, 0), (rc, rc2))

print("%d cases, %d failed" % (count, fails))
sys.exit(1 if fails else 0)

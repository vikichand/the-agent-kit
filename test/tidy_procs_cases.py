"""Offline selection tests for tidy-procs; the pure cases kill nothing. The Windows live case starts and
kills only throwaway node servers it spawned itself."""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

path = pathlib.Path(__file__).resolve().parents[1] / "hooks/tidy-procs.py"
if not path.exists():
    print("FAIL: tidy-procs implementation missing")
    print("tidy-procs: 0/1 passed")
    sys.exit(1)
spec = importlib.util.spec_from_file_location("tidy", path)
tidy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tidy)

NOW = 100000.0
NEXT = r"node C:\proj\node_modules\next\dist\bin\next dev"


def proc(pid, ppid, command, age=9000, mb=1, name=None):
    return dict(pid=pid, ppid=ppid, command=command, created=NOW - age, mb=mb,
                name=name or command.split()[0])


PARENT = proc(1, 0, "bash", age=50000)


def net(listen=None, est=None):
    return {"listen": listen or {}, "established": est or {}}


def S(procs, n=None, cpu=None, self_pid=9999, min_age=300, idle=4 * 3600, patterns=None):
    # cpu: {pid: (before, after)} for the fake probe; missing pids are simply unsampled.
    probe = lambda pids: {p: cpu[p] for p in pids if cpu and p in cpu}
    return tidy.scan(procs, NOW, patterns or tidy.reaper.DEFAULT_PATTERNS, min_age, idle,
                     self_pid, n, probe)


def groups(result):
    return sorted((i["group"], i["pids"][0]) for i in result[0])


cases = []


def check(name, assertion):
    cases.append((name, assertion))


# strays
orphan = proc(10, 9, "node mcp-server --x")
r = S([orphan, proc(11, 10, "node worker")])
check("stray listed", lambda r=r: groups(r) == [("processes.strays", 10)] and r[0][0]["pids"] == [10, 11])
check("stray fields", lambda r=r: r[0][0]["confidence"] == "high" and r[0][0]["action"] == "kill"
      and r[0][0]["id"] == f"proc:10:{int(NOW - 9000)}" and r[0][0]["size_bytes"] == 2 * 1048576
      and all(isinstance(e, str) for e in r[0][0]["evidence"]))
check("id format", lambda r=r: all(re.fullmatch(r"proc:\d+:\d+", i["id"]) for i in r[0]))
check("young stray not listed", lambda: not S([proc(10, 9, "node mcp-server", age=10)])[0])

# MCP servers with live parents are never duplicates
sessions = [PARENT, proc(2, 1, "claude", 8000), proc(3, 1, "claude", 7000),
            proc(10, 2, r"node C:\proj\node_modules\@playwright\mcp\cli.js", 6000),
            proc(11, 3, r"node C:\proj\node_modules\@playwright\mcp\cli.js", 5000)]
check("mcp servers of live sessions are not duplicates", lambda: not S(sessions, net({11: [1]}))[0])

# duplicates
A, B = proc(20, 1, NEXT + " -p 3000", 9000), proc(21, 1, NEXT + " -p 3001", 8000)
r = S([PARENT, A, B], net({21: [3001]}))
check("duplicate: older non-listening flagged, listening newer kept", lambda r=r: groups(r) == [("processes.duplicates", 20)])
check("duplicate evidence and confidence", lambda r=r: r[0][0]["confidence"] == "medium"
      and "same command and project as pid 21, which is newer" in r[0][0]["evidence"])
r = S([PARENT, A, B], net({20: [3000]}))
check("duplicate: listening older kept, newer flagged", lambda r=r: groups(r) == [("processes.duplicates", 21)])
check("duplicate: none listens keeps newest", lambda r=r: groups(S([PARENT, A, B], net()))== [("processes.duplicates", 20)])
check("duplicate without net info keeps newest", lambda r=r: groups(S([PARENT, A, B], None)) == [("processes.duplicates", 20)])
other = proc(21, 1, NEXT.replace(r"C:\proj", r"C:\other"), 8000)
check("same command in two projects is not grouped", lambda: not S([PARENT, A, other], net())[0])
check("unknown project root is never grouped", lambda: not S([PARENT, proc(20, 1, "node next dev"), proc(21, 1, "node next dev", 8000)], net())[0])
check("global node_modules is not a project root", lambda: not S([PARENT, proc(20, 1, r"node C:\Users\v\AppData\Roaming\npm\node_modules\nodemon\bin\nodemon.js"),
      proc(21, 1, r"node C:\Users\v\AppData\Roaming\npm\node_modules\nodemon\bin\nodemon.js", 8000)], net())[0])
check("parent and child with the same command are not duplicates", lambda: not S([PARENT, A, proc(22, 20, NEXT + " -p 3000", 8500)], net())[0])
check("young duplicate is not listed", lambda: not S([PARENT, proc(20, 1, NEXT, 10), B], net({21: [1]}))[0])
check("own ancestor is not listed", lambda: not S([PARENT, A, proc(30, 20, "uv run python tidy-procs.py", 100), B], net({21: [1]}), self_pid=30)[0])
check("project root rules", lambda: tidy.project_root(NEXT) == "c:/proj"
      and tidy.project_root(r"python C:\srv\app\main.py --reload") == "c:/srv/app"
      and tidy.project_root("python manage.py runserver") is None and tidy.project_root("uvicorn app:app") is None)
check("port is removed from the key", lambda: tidy.normalise("next dev -p 3000") == tidy.normalise("next dev --port=3001")
      == tidy.normalise("next dev") and tidy.normalise("vite --host 0.0.0.0:5173") == tidy.normalise("vite --host 0.0.0.0")
      and tidy.normalise("python -m http.server 8000") == tidy.normalise("python -m http.server"))
for command, expected in [("npm run dev", True), ("node ...\\vitest run", False), ("php -S localhost:8000", True),
                          ("php -s", False), ("python -m http.server 8000", True), ("node server.js", False)]:
    check("dev command " + command, lambda c=command, e=expected: bool(tidy.is_dev(c)) == e)

# idle
IDLE = proc(40, 1, NEXT, age=27000)
LISTEN = net({40: [38417]})
CPU = {40: (1.0, 1.0)}
r = S([PARENT, IDLE], LISTEN, CPU)
check("idle listed", lambda r=r: groups(r) == [("processes.idle", 40)] and r[0][0]["confidence"] == "low")
check("idle evidence states the facts", lambda r=r: all(s in r[0][0]["evidence"] for s in
      ("no connection to port 38417", "no CPU in 3 s", "started 7.5 h ago")))
check("idle needs no connection", lambda r=r: not S([PARENT, IDLE], net({40: [38417]}, {38417: 1}), CPU)[0])
check("idle needs no cpu", lambda r=r: not S([PARENT, IDLE], LISTEN, {40: (1.0, 2.5)})[0])
check("idle needs an unsampled-cpu refusal", lambda r=r: not S([PARENT, IDLE], LISTEN, {})[0])
check("idle needs listening", lambda r=r: not S([PARENT, IDLE], net(), CPU)[0])
check("idle needs age", lambda r=r: not S([PARENT, proc(40, 1, NEXT, age=3600)], LISTEN, CPU)[0])
check("idle needs net info", lambda r=r: not S([PARENT, IDLE], None, CPU)[0])
check("idle uses the listening child", lambda r=r: groups(S([PARENT, proc(39, 1, "npm run dev", 27100), IDLE.copy() | dict(ppid=39)],
      LISTEN, {40: (1, 1), 39: (1, 1)})) == [("processes.idle", 39)])
check("idle mcp server is not listed", lambda r=r: not S([PARENT, proc(40, 1, "node mcp-server", 27000)], LISTEN, CPU)[0])

# priority: one process, one group
r = S([orphan, proc(11, 10, NEXT), proc(20, 1, NEXT + " -p 3001", 8000), PARENT], net({20: [1]}))
check("stray beats duplicate", lambda r=r: groups(r) == [("processes.strays", 10)])
D = proc(41, 1, NEXT + " -p 3002", 27000)
r = S([PARENT, D, proc(42, 1, NEXT + " -p 3003", 8000)], net({41: [3002], 42: [3003]}), {41: (1, 1)})
check("duplicate beats idle", lambda r=r: groups(r) == [("processes.duplicates", 41)])

# lister parsers
LSOF = ("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
        "node 40 v 21u IPv4 0x1 0t0 TCP *:3000 (LISTEN)\n"
        "node 40 v 22u IPv4 0x2 0t0 TCP 127.0.0.1:3000->127.0.0.1:5000 (ESTABLISHED)\n"
        "node 41 v 23u IPv6 0x3 0t0 TCP [::1]:3001 (LISTEN)\n")
SS = ("State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
      'LISTEN 0 511 0.0.0.0:3000 0.0.0.0:* users:(("node",pid=40,fd=21))\n'
      "ESTAB 0 0 127.0.0.1:3000 127.0.0.1:5000\n"
      "TIME-WAIT 0 0 127.0.0.1:3000 127.0.0.1:5001\n")
check("lsof parsed", lambda: tidy.build_net(tidy.parse_lsof(LSOF)) == {"listen": {40: [3000], 41: [3001]}, "established": {3000: 1}})
check("ss parsed", lambda: tidy.build_net(tidy.parse_ss(SS)) == {"listen": {40: [3000]}, "established": {3000: 1}})
check("cputime parsed", lambda: tidy.parse_cputime("1-02:03:04.5") == 93784.5 and tidy.parse_cputime("0:01.25") == 1.25)

# apply, with a fake kill: nothing real can die here
ITEMS = S([PARENT, IDLE], LISTEN, CPU)[0]
good = ITEMS[0]["id"]


def applied(ids, items=ITEMS, survivors=()):
    calls = []
    report, left = tidy.apply_ids(ids, items, lambda trees: calls.append(trees) or list(survivors))
    return calls, report, left


check("apply kills exactly the id", lambda: [[p["pid"] for p in t["processes"]] for t in applied([good])[0][0]] == [[40]])
check("apply refuses a different creation time", lambda: not applied(["proc:40:%d" % (int(NOW - 9000))])[0])
check("apply refuses an unknown pid and a malformed id", lambda: not applied(["proc:41:1", "garbage"])[0])
check("apply reports skipped ids", lambda: len(applied(["proc:40:1"])[1]) == 1 and "no longer" in applied(["proc:40:1"])[1][0])
check("apply reports survivors", lambda: applied([good], survivors=[40])[2] == [40])

passed = 0
for name, assertion in cases:
    try:
        assert assertion()
        passed += 1
    except Exception as exc:
        print(f"FAIL: {name}: {exc!r}")


def live():
    if os.name != "nt" or not shutil.which("node"):
        print("PASS: tidy-procs Windows live idle/apply (skipped: needs Windows and node)")
        return True
    root = pathlib.Path(tempfile.mkdtemp(prefix="tidyprocs_"))
    started = []
    try:
        for name in ("a", "b"):
            d = root / name
            d.mkdir()
            (d / "server.js").write_text(
                "const s=require('net').createServer(()=>{});"
                "s.listen(0,'127.0.0.1',()=>require('fs').writeFileSync(process.argv[2],process.pid+':'+s.address().port));"
                "setInterval(()=>{},1000);\n")
            # The trailing 'nodemon' argument makes this throwaway server look like a dev server to the matcher.
            p = subprocess.Popen(["node", "server.js", str(d / "pid.txt"), "nodemon"], cwd=d,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started.append(p)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not all((root / n / "pid.txt").exists() for n in "ab"):
            time.sleep(0.2)
        pid_a, pid_b = (int((root / n / "pid.txt").read_text().split(":")[0]) for n in "ab")
        assert (pid_a, pid_b) == (started[0].pid, started[1].pid), "unexpected node pids"
        flags = ["--idle-hours", "0", "--min-age-minutes", "0"]
        env = dict(os.environ, AGENT_KIT_MCP_PATTERNS_ONLY="1")
        out = subprocess.run([sys.executable, str(path), "scan", "--json"] + flags, env=env,
                             capture_output=True, text=True, check=True, timeout=90).stdout
        items = json.loads(out)["items"]
        mine = [i for i in items if i["pids"][0] == pid_a]
        assert mine and mine[0]["group"] == "processes.idle", f"throwaway server not listed idle: {out[:300]}"
        assert not any(i["pids"][0] == pid_b and i["group"] != "processes.idle" for i in items)
        subprocess.run([sys.executable, str(path), "apply", "--ids", mine[0]["id"]] + flags, env=env,
                       capture_output=True, text=True, check=True, timeout=90)
        alive = {p["pid"] for p in tidy.reaper.list_processes()}
        assert pid_a not in alive, "target survived apply"
        assert pid_b in alive, "apply killed a process it was not given"
        print("PASS: tidy-procs Windows live idle server listed, apply killed only that id")
        return True
    except Exception as exc:
        print(f"FAIL: windows live: {exc!r}")
        return False
    finally:
        for p in started:
            subprocess.run([tidy.reaper.TASKKILL, "/F", "/PID", str(p.pid)], capture_output=True, timeout=15)
        shutil.rmtree(root, ignore_errors=True)


total = len(cases) + 1
passed += live()
print(f"tidy-procs: {passed}/{total} passed")
sys.exit(passed != total)

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
# Without socket info the "newest" copy may be the idle one and the older one the server the browser is on,
# so the item is never offered in "remove all".
check("duplicate without net info is low and says why", lambda: (lambda x: x[0][0]["confidence"] == "low"
      and "socket state unknown: TCP connections could not be listed" in x[0][0]["evidence"])(S([PARENT, A, B], None)))
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


def dry(ids):
    calls = []
    report, left = tidy.apply_ids(ids, ITEMS, lambda trees: calls.append(trees) or [], dry_run=True)
    return calls, report, left


check("apply --dry-run kills nothing and says what it would", lambda: not dry([good])[0] and any(
    "would kill" in line for line in dry([good])[1]) and dry([good])[2] == [])
check("apply --dry-run still skips an id that no longer matches", lambda: not dry(["proc:41:1"])[0] and any(
    "skipped" in line for line in dry(["proc:41:1"])[1]))
check("apply kills exactly the id", lambda: [[p["pid"] for p in t["processes"]] for t in applied([good])[0][0]] == [[40]])
check("apply refuses a different creation time", lambda: not applied(["proc:40:%d" % (int(NOW - 9000))])[0])
check("apply refuses an unknown pid and a malformed id", lambda: not applied(["proc:41:1", "garbage"])[0])
check("apply reports skipped ids", lambda: len(applied(["proc:40:1"])[1]) == 1 and "no longer" in applied(["proc:40:1"])[1][0])
check("apply reports survivors", lambda: applied([good], survivors=[40])[2] == [40])

# security findings
r = S([PARENT, A, B], net({20: [3000], 21: [3001]}))
check("listening duplicate is low with its port in the evidence", lambda r=r: groups(r) == [("processes.duplicates", 20)]
      and r[0][0]["confidence"] == "low" and "also listening on port 3000" in r[0][0]["evidence"])
check("non-listening duplicate stays medium without a listening note", lambda: (lambda x: x[0][0]["confidence"] == "medium"
      and not any("also listening" in e for e in x[0][0]["evidence"]))(S([PARENT, A, B], net({21: [3001]}))))
HOSTILE = NEXT.replace(r"C:\proj", "C:\\pr\x1b[31moj\x07X")
r = S([PARENT, proc(20, 1, HOSTILE + " -p 3000", 9000), proc(21, 1, HOSTILE + " -p 3001", 8000)], net({21: [1]}))
check("process evidence and label carry no control characters", lambda r=r: r[0] and not any(
    re.search(r"[\x00-\x1f\x7f]", t) for i in r[0] for t in i["evidence"] + [i["label"]]) and any(
    "[31m" in e for e in r[0][0]["evidence"]))
check("clean replaces control characters", lambda: tidy.clean("a\x1b\nb") == "a  b")
check("clean strips C1, bidi and line-separator characters", lambda: all(
    tidy.clean(f"a{c}b") == "a b" for c in "\x9b\x85‮⁦⁩‎‏  "))


# repo scope: only processes working inside the repository (or a linked worktree) are ever listed
BASE = os.path.join(os.path.realpath(tempfile.gettempdir()), "tidyprocs-scope")  # a short 8.3 temp name would not match
RA, RB = os.path.join(BASE, "a"), os.path.join(BASE, "b")
WT_A = os.path.join(BASE, "a-wt")  # a linked worktree of repo A
SCOPE = sorted({tidy.norm(RA), tidy.norm(WT_A)})


def SC(procs, folders, n=None, cpu=None, patterns=None):
    """Scoped scan; folders is {pid: working folder}, a missing pid is an unreadable one."""
    probe = lambda pids: {p: cpu[p] for p in pids if cpu and p in cpu}
    return tidy.scan(procs, NOW, patterns or tidy.reaper.DEFAULT_PATTERNS, 300, 4 * 3600, 9999, n, probe,
                     scope=SCOPE, cwds=lambda pids: {p: folders[p] for p in pids if p in folders})


SERVER = proc(40, 1, "npm run dev", age=27000)
r = SC([PARENT, SERVER], {40: RA}, LISTEN, CPU)
check("cwd-in-repo dev server listed", lambda r=r: groups(r) == [("processes.idle", 40)])
check("cwd in a linked worktree is in the repo", lambda: groups(SC([PARENT, SERVER], {40: WT_A}, LISTEN, CPU)) == [("processes.idle", 40)])
check("cwd in another repo is not listed", lambda: not SC([PARENT, SERVER], {40: RB}, LISTEN, CPU)[0])
check("a sibling folder with the same prefix is not inside", lambda: not SC([PARENT, SERVER], {40: RA + "-other"}, LISTEN, CPU)[0])
check("argv path in the repo is listed when the cwd is unreadable", lambda: groups(SC(
    [PARENT, proc(40, 1, f'node "{os.path.join(RA, "node_modules", ".bin", "vite")}"', age=27000)], {}, LISTEN, CPU)) == [("processes.idle", 40)])
check("argv path in another repo with an unreadable cwd is not listed", lambda: not SC(
    [PARENT, proc(40, 1, f'node "{os.path.join(RB, "node_modules", ".bin", "vite")}"', age=27000)], {}, LISTEN, CPU)[0])
r = SC([PARENT, SERVER], {}, LISTEN, CPU)
check("unknown cwd is never listed and is counted in a note", lambda r=r: not r[0]
      and "1 processes with an unreadable working folder were skipped" in r[1])
check("a readable cwd outside the repo is final, a parent inside does not pull it in", lambda: not SC(
    [PARENT, proc(39, 1, "bash", 27100), proc(40, 39, "npm run dev", 27000)], {39: RA, 40: RB}, LISTEN, CPU)[0])
check("an unreadable child inherits an in-repo parent", lambda: groups(SC(
    [PARENT, proc(39, 1, "bash", 27100), proc(40, 39, "npm run dev", 27000)], {39: RA}, LISTEN, CPU)) == [("processes.idle", 40)])
OTHER = proc(20, 1, f"node {os.path.join(RB, 'node_modules', 'next', 'dist', 'bin', 'next')} dev -p 3000", 9000)
OTHER2 = proc(21, 1, f"node {os.path.join(RB, 'node_modules', 'next', 'dist', 'bin', 'next')} dev -p 3001", 8000)
check("out-of-repo duplicate is not listed", lambda: not SC([PARENT, OTHER, OTHER2], {20: RB, 21: RB}, net({21: [3001]}))[0])
check("the same duplicate inside the repo is listed", lambda: groups(SC(
    [PARENT, OTHER, OTHER2], {20: RA, 21: RA}, net({21: [3001]}))) == [("processes.duplicates", 20)])
STRAY = [orphan, proc(11, 10, "node worker")]
check("in-repo stray is listed high", lambda: (lambda x: groups(x) == [("processes.strays", 10)]
      and x[0][0]["confidence"] == "high")(SC(STRAY, {10: RA, 11: RA})))
check("stray tree is in scope when any member is", lambda: groups(SC(STRAY, {11: RA})) == [("processes.strays", 10)])
r = SC(STRAY, {10: RB, 11: RB})
check("out-of-repo stray becomes one note", lambda r=r: not r[0] and len(r[1]) == 1
      and "1 orphaned MCP trees elsewhere" in r[1][0] and "install.sh --tidy" in r[1][0])
check("a listening stray is low", lambda: (lambda x: x[0][0]["confidence"] == "low"
      and "listening on port 8080" in x[0][0]["evidence"])(SC(STRAY, {10: RA}, net({10: [8080]}))))
check("editor exe is never listed", lambda: not SC([PARENT, proc(40, 1, r"C:\Apps\Code.exe --ext vite", 27000, name="Code.exe")],
      {40: RA}, LISTEN, CPU)[0])
CLAUDE = r"C:\Users\v\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\cli.js"
check("an agent CLI is never listed, found by its script", lambda: not SC(
    [PARENT, proc(40, 1, f"node {CLAUDE} --resume vite", 27000, name="node.exe")], {40: RA}, LISTEN, CPU)[0])
check("node.exe itself is not excluded: a dev server on node is listed", lambda: groups(SC(
    [PARENT, proc(40, 1, "node server.js nodemon", 27000, name="node.exe")], {40: RA}, LISTEN, CPU)) == [("processes.idle", 40)])
for command, expected in [("claude", True), (r"C:\bin\claude.exe --x", True), (CLAUDE, True), ("node /x/@openai/codex/bin/codex.js", True),
                          ("agy chat", True), ("node C:/code/codex/server.js", False), ("node C:/code/claude/node_modules/.bin/vite", False),
                          ("npm run dev", False)]:
    check("agent cli " + command, lambda c=command, e=expected: tidy.agent_cli(c) == e)
check("under() compares whole path segments", lambda: tidy.under(tidy.norm(RA), SCOPE) and tidy.under(tidy.norm(os.path.join(RA, "x", "y")), SCOPE)
      and not tidy.under(tidy.norm(RA + "x"), SCOPE))
# apply: the fresh scan is scoped too, so an id from another repo no longer matches
ITEMS_B = SC([PARENT, SERVER], {40: RB}, LISTEN, CPU)[0]
ITEMS_A = SC([PARENT, SERVER], {40: RA}, LISTEN, CPU)[0]
check("apply refuses an id whose process is outside the scope", lambda: (lambda c, rep, left: not c and "skipped" in rep[0])(
    *applied([good], items=ITEMS_B)))
check("apply kills an id whose process is in scope", lambda: [t["pid"] for t in applied([good], items=ITEMS_A)[0][0]] == [40])


def child_cwd():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="tidyprocs_cwd_"))
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp)
    try:
        time.sleep(1)
        got = tidy.read_cwds([p.pid, 2 ** 22 + 1]).get(p.pid)
        if got is None and os.name != "nt" and not pathlib.Path("/proc/self").exists() and not tidy.which("lsof"):
            return True  # ponytail: no /proc and no lsof here, so cwd is unknown by design
        return got is not None and tidy.norm(got) == tidy.norm(str(tmp)) and (2 ** 22 + 1) not in tidy.read_cwds([2 ** 22 + 1])
    finally:
        p.kill()
        p.wait()
        shutil.rmtree(tmp, ignore_errors=True)


check("a child's working folder is read back exactly", child_cwd)
check("a scope that is the home folder or a filesystem root is refused", lambda: all(subprocess.run(
    [sys.executable, str(path), "scan", "--root", r], capture_output=True, text=True).returncode == 2
    for r in (os.path.expanduser("~"), os.path.abspath(os.sep))))
check("--root is required", lambda: subprocess.run([sys.executable, str(path), "scan"], capture_output=True,
                                                   text=True).returncode == 2)


def which_ignores_cwd():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="tidyprocs_which_"))
    old_cwd, old_path = os.getcwd(), os.environ["PATH"]
    try:
        for n in ("ss.cmd", "ss.exe", "ss"):
            (tmp / n).write_text("x")
        os.chdir(tmp)
        os.environ["PATH"] = "." + os.pathsep + str(tmp / "nope")
        return tidy.which("ss") is None and os.environ.get("NoDefaultCurrentDirectoryInExePath") == "1"
    finally:
        os.chdir(old_cwd)
        os.environ["PATH"] = old_path
        shutil.rmtree(tmp, ignore_errors=True)


check("which never resolves through the cwd", which_ignores_cwd)
src = path.read_text()
check("no bare executable names or shutil.which", lambda: not re.search(r'\["(?:ss|lsof|ps)"', src) and "shutil.which" not in src)
check("nan and negative ages are rejected", lambda: all(subprocess.run(
    [sys.executable, str(path), "scan", "--root", str(path.parent), flag, v], capture_output=True, text=True).returncode == 2
    for flag in ("--idle-hours", "--min-age-minutes") for v in ("nan", "-1", "inf")))

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

        def scan_in(folder):
            out = subprocess.run([sys.executable, str(path), "scan", "--json", "--root", str(folder)] + flags, env=env,
                                 capture_output=True, text=True, check=True, timeout=90).stdout
            return json.loads(out)["items"]

        # Repo A is the scope: A's server is listed, B's (same command, other folder) is not.
        items_a, items_b = scan_in(root / "a"), scan_in(root / "b")
        mine = [i for i in items_a if i["pids"][0] == pid_a]
        assert mine and mine[0]["group"] == "processes.idle", f"throwaway server not listed idle: {items_a}"
        assert not any(i["pids"][0] == pid_b for i in items_a), "scope A listed B's server"
        theirs = [i for i in items_b if i["pids"][0] == pid_b]
        assert theirs and not any(i["pids"][0] == pid_a for i in items_b), "scope B did not isolate B"
        # An id from repo B is refused while the scope is A.
        refused = subprocess.run([sys.executable, str(path), "apply", "--ids", theirs[0]["id"], "--root", str(root / "a")]
                                 + flags, env=env, capture_output=True, text=True, check=True, timeout=90).stdout
        assert "skipped" in refused and pid_b in {p["pid"] for p in tidy.reaper.list_processes()}, f"B id not refused: {refused}"
        subprocess.run([sys.executable, str(path), "apply", "--ids", mine[0]["id"], "--root", str(root / "a")] + flags,
                       env=env, capture_output=True, text=True, check=True, timeout=90)
        alive = {p["pid"] for p in tidy.reaper.list_processes()}
        assert pid_a not in alive, "target survived apply"
        assert pid_b in alive, "apply killed a process it was not given"
        print("PASS: tidy-procs Windows live: A's idle server listed, B's not, a B id refused, apply killed only A's")
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

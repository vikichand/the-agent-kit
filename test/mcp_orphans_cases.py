"""Offline selection tests; no process is killed by this corpus."""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

path = pathlib.Path(__file__).resolve().parents[1] / "hooks/mcp-orphans.py"
if not path.exists():
    print("FAIL: reaper implementation missing")
    print("mcp-orphans: 0/1 passed")
    sys.exit(1)
spec = importlib.util.spec_from_file_location("reaper", path)
reaper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reaper)


def cleanup(directory):
    marker_path = directory / "marker.txt"
    if os.name != "nt" or not marker_path.exists():
        return
    marker = marker_path.read_text()
    assert marker.startswith("AGENTKITORPHAN_") and len(marker) == 47
    import ctypes
    from ctypes import wintypes
    recorded = directory / "owned.json"
    owned = json.loads(recorded.read_text()) if recorded.exists() else []
    # PID files are written by the fixture children, even if CIM becomes unavailable.
    for name in ("cmd.pid", "node.pid"):
        pid_file = directory / name
        if pid_file.exists():
            pid = int(pid_file.read_text())
            if not any(p["pid"] == pid for p in owned):
                owned.append(dict(pid=pid, earliest=marker_path.stat().st_mtime,
                                  latest=pid_file.stat().st_mtime))
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for p in owned:
        handle = kernel.OpenProcess(0x1001, False, p["pid"])
        if not handle:
            continue
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            created = ((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime) / 10000000 - 11644473600
            matches = (abs(created - p["created"]) <= 0.002 if "created" in p else
                       p["earliest"] <= created <= p["latest"])
            if not matches:
                continue
            result = subprocess.run(["taskkill", "/F", "/PID", str(p["pid"])],
                                    capture_output=True, timeout=15)
            # Keep the verified process handle open so fallback cannot hit a reused PID.
            if result.returncode:
                code = wintypes.DWORD()
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                # Already exited (the reaper killed it): nothing to do. Only a live process needs the fallback.
                if kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259                         and not kernel.TerminateProcess(handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)


def live(directory):
    # Fail before spawning anything if this environment denies process enumeration.
    reaper.list_processes()
    marker = "AGENTKITORPHAN_" + uuid.uuid4().hex
    (directory / "marker.txt").write_text(marker)
    dummy = directory / "dummy.js"
    dummy.write_text("require('fs').writeFileSync(process.argv[2], String(process.pid)); setTimeout(() => process.exit(0), 120000); setInterval(() => {}, 1000);\n")
    node_pid_path = directory / "node.pid"
    client_code = (
        "import pathlib,subprocess,sys,time; "
        "child = subprocess.Popen(['cmd','/c','node',sys.argv[1],sys.argv[2],sys.argv[3]]); "
        "pathlib.Path(sys.argv[4]).write_text(str(child.pid)); "
        "time.sleep(120)"
    )
    client = subprocess.Popen([sys.executable, "-c", client_code, str(dummy), str(node_pid_path), marker, str(directory / "cmd.pid")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while not node_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert node_pid_path.exists(), "node failed to start"
        node_pid = int(node_pid_path.read_text())
        owned = [p for p in reaper.list_processes() if marker in p["command"]
                 and p["name"].lower() in ("python.exe", "python3.exe", "cmd.exe", "node.exe")]
        assert any(p["pid"] == node_pid for p in owned), "cannot verify node identity"
        (directory / "owned.json").write_text(json.dumps(owned))
        stopped = subprocess.run(["taskkill", "/F", "/PID", str(client.pid)],
                                 capture_output=True, text=True, timeout=15)
        assert stopped.returncode == 0, f"client taskkill failed: {stopped.stderr}"
        client.wait(timeout=10)
        time.sleep(3)
        env = dict(os.environ, AGENT_KIT_MCP_PATTERNS=marker,
                   AGENT_KIT_MCP_PATTERNS_ONLY="1")
        command = [sys.executable, str(path), "--min-age-minutes", "0", "--json"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True, timeout=60)
        trees = json.loads(result.stdout)
        assert trees and any(node_pid in t["pids"] for t in trees), "orphan node not listed"
        assert all(marker in t["command"] for t in trees), "unexpected tree; refusing kill"
        assert any(p["pid"] == node_pid and marker in p["command"] for p in reaper.list_processes()), "dry run killed node"
        result = subprocess.run(command + ["--kill"], env=env, capture_output=True, text=True, check=True, timeout=90)
        assert any(node_pid in t["pids"] for t in json.loads(result.stdout)), "kill did not report node"
        assert not any(p["pid"] == node_pid and marker in p["command"] for p in reaper.list_processes()), "node survived"
        print("PASS: MCP Windows live orphan listed, dry run preserves node, --kill removes node")
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(timeout=10)
        cleanup(directory)


if len(sys.argv) > 1 and sys.argv[1] in ("--live", "--cleanup"):
    directory = pathlib.Path(sys.argv[2]).resolve()
    (live if sys.argv[1] == "--live" else cleanup)(directory)
    sys.exit(0)


def proc(pid, ppid, command="node mcp-server", created=100, mb=2):
    return dict(pid=pid, ppid=ppid, command=command, created=created,
                name=command.split()[0], mb=mb)


def find(procs, self_pid=999, patterns=None, init_pids=()):
    return reaper.find_orphans(procs, 1000, patterns or reaper.DEFAULT_PATTERNS, 300, self_pid, init_pids)


cases = []


def check(name, assertion):
    cases.append((name, assertion))


tree = [proc(10, 9, "cmd /c npx -y @playwright/mcp"), proc(11, 10, "node worker"), proc(12, 11, "child")]
check("dead parent and descendants", lambda: find(tree)[0]["pids"] == [10, 11, 12])
check("tree memory", lambda: find(tree)[0]["mb"] == 6)
check("live parent", lambda: not find([proc(9, 0, "client", 50)] + tree))
check("pid reuse", lambda: find([proc(9, 0, "client", 200)] + tree)[0]["pid"] == 10)
check("plain dev server", lambda: not find([proc(10, 9, "next dev")]))
check("young root", lambda: not find([proc(10, 9, created=900)]))
check("own ancestors", lambda: not find(tree, self_pid=12))
check("self", lambda: not find(tree, self_pid=10))
check("custom environment patterns", lambda: bool(find([proc(10, 9, "node CUSTOM-server")], patterns=reaper.patterns_from_env({"AGENT_KIT_MCP_PATTERNS": " , custom-server, "}))))
check("patterns only excludes defaults", lambda: not reaper.find_orphans([proc(10, 9)], 1000, reaper.patterns_from_env({"AGENT_KIT_MCP_PATTERNS": "AGENTKITORPHAN_", "AGENT_KIT_MCP_PATTERNS_ONLY": "1"}), 300, 999))
check("patterns only matches custom", lambda: bool(find([proc(10, 9, "node AGENTKITORPHAN_test")], patterns=reaper.patterns_from_env({"AGENT_KIT_MCP_PATTERNS": "AGENTKITORPHAN_", "AGENT_KIT_MCP_PATTERNS_ONLY": "1"}))))
check("case insensitive", lambda: bool(find([proc(10, 9, "NODE MCP-SERVER")])) )
check("npx conjunction", lambda: bool(find([proc(10, 9, "node npx-cli.js cool-mcp")])) and not find([proc(10, 9, "node npx-cli.js vite")]))
check("uvx conjunction", lambda: bool(find([proc(10, 9, "uvx cool-mcp")])) and not find([proc(10, 9, "uvx tool")]))
check("reused descendant excluded", lambda: find([proc(10, 9, created=200), proc(11, 10, "worker", 100)])[0]["pids"] == [10])
check("kill refuses reused raw descendant", lambda: not reaper.tree_unchanged(find(tree)[0], tree + [proc(13, 10, "unrelated", 50)]))
check("kill refuses new descendant", lambda: not reaper.tree_unchanged(find(tree)[0], tree + [proc(13, 10, "new worker", 200)]))
check("kill accepts original tree", lambda: reaper.tree_unchanged(find(tree)[0], tree))
for value, expected in [("05:12", 312), ("1:02:03", 3723), ("2-03:04:05", 183845)]:
    check("etime " + value, lambda v=value, e=expected: reaper.parse_etime(v) == e)

NOW = 1000.0
PS_OK = "  10     1 05:12  2048 node mcp-server --x\n  11    10 00:30   512 child proc\n"
check("ps parses", lambda: [(p["pid"], p["ppid"], p["name"], p["mb"], p["created"]) for p in reaper.parse_ps_output(PS_OK, NOW)]
      == [(10, 1, "node", 2.0, NOW - 312), (11, 10, "child", 0.5, NOW - 30)])


def ps_raises(text):
    try:
        reaper.parse_ps_output(text, NOW)
    except ValueError:
        return True
    return False


check("ps forged duplicate pid raises", lambda: ps_raises(PS_OK + "  10     1 00:01  1 forged\n"))
check("ps garbage line raises", lambda: ps_raises(PS_OK + "garbage line\n"))
check("ps pid zero raises", lambda: ps_raises("  0     1 00:01  1 x\n"))
check("posix orphan reparented to init", lambda: bool(find([proc(1, 0, "init", 1), proc(10, 1)], init_pids=(0, 1))))
check("init_pids empty skips init child", lambda: not find([proc(1, 0, "init", 1), proc(10, 1)]))
check("clean strips control chars", lambda: reaper.clean("a\x1b[31mb\nc\x7fd\x00") == "a [31mb c d ")
check("non-interpreter root not flagged", lambda: not find([proc(10, 9, "mcp-server-foo --x")]))
check("interpreter root flagged", lambda: bool(find([proc(10, 9, "node mcp-server-foo --x")])))
check("interpreter root with .exe flagged", lambda: bool(find([proc(10, 9, "Node.EXE mcp-server")])))

passed = 0
for name, assertion in cases:
    try:
        assert assertion()
        passed += 1
    except Exception as exc:
        print(f"FAIL: {name}: {exc}")
print(f"mcp-orphans: {passed}/{len(cases)} passed")
sys.exit(passed != len(cases))

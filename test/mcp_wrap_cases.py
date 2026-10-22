#!/usr/bin/env python3
"""Tests for hooks/mcp-wrap.py. Run:  uv run python test/mcp_wrap_cases.py [path/to/mcp-wrap.py]
Windows cases prove the wrapper leaves no orphans when the client is killed. The POSIX case is for Linux/macOS."""
import os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
WRAP = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "..", "hooks", "mcp-wrap.py")
WIN = os.name == "nt"
NODE = shutil.which("node")
T0 = int(time.time()) - 2
TMP = tempfile.mkdtemp(prefix="mcpwrap-")
DUMMY = os.path.join(TMP, "dummy.js")
with open(DUMMY, "w") as f:
    f.write("if (process.argv[3] === 'exit') setTimeout(() => process.exit(5), 1500);\n"
            "else setInterval(function () {}, 1000);\n")


def find(marker):
    """Survivors: processes whose command line carries the marker and that started after the test did."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and "
          "$_.Name -in 'node.exe','cmd.exe' -and "
          "([DateTimeOffset]$_.CreationDate).ToUnixTimeSeconds() -ge %d } | "
          "ForEach-Object { '{0} {1}' -f $_.ProcessId,$_.Name }" % (marker, T0))
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def kill_all(marker):
    for l in find(marker):
        subprocess.run(["taskkill", "/F", "/T", "/PID", l.split()[0]], capture_output=True)


def crash_trial(marker, command):
    """Start `command` under a client process, kill the client with no goodbye, return (before, after)."""
    client = subprocess.Popen([sys.executable, "-c",
                               "import subprocess,time; subprocess.Popen(%r); time.sleep(120)" % (command,)])
    try:
        time.sleep(4)
        before = find(marker)
        subprocess.run(["taskkill", "/F", "/PID", str(client.pid)], capture_output=True)
        time.sleep(4)
        return before, find(marker)
    finally:
        kill_all(marker)
        client.kill()


def server(marker):
    return ["cmd", "/c", "node", DUMMY, marker]


def wrapped(marker, srv=None):
    return [sys.executable, WRAP, "--"] + (srv or server(marker))


def t_control():
    m = "ORPHAN_control"
    before, after = crash_trial(m, server(m))
    assert before and after, "control should leave orphans (before=%s after=%s)" % (before, after)


def t_wrapped():
    m = "ORPHAN_wrapped"
    before, after = crash_trial(m, wrapped(m))
    assert before and not after, "before=%s after=%s" % (before, after)


def t_via_cmd():
    m = "ORPHAN_viacmd"
    cmd = 'cmd /c ""%s" "%s" -- cmd /c node "%s" %s"' % (sys.executable, WRAP, DUMMY, m)
    before, after = crash_trial(m, cmd)
    assert before and not after, "before=%s after=%s" % (before, after)


def t_exit_code():
    r = subprocess.run(wrapped("x", [NODE, "-e", "process.exit(7)"]), capture_output=True, timeout=30)
    assert r.returncode == 7, r.returncode


def t_stdout_clean():
    r = subprocess.run(wrapped("x", [NODE, "-e", "console.log('hello')"]), capture_output=True, timeout=30)
    assert r.stdout.replace(b"\r\n", b"\n") == b"hello\n", r.stdout


def t_space_path():
    d = os.path.join(TMP, "dir with space")
    os.makedirs(d)
    cmdfile = os.path.join(d, "my server.cmd")
    with open(cmdfile, "w") as f:
        f.write('@"%s" "%s" %%*\r\n' % (NODE, DUMMY))
    m = "ORPHAN_space"
    before, after = crash_trial(m, wrapped(m, [cmdfile, m]))
    assert before and not after, "before=%s after=%s" % (before, after)
    # a .cmd found through PATH, with an argument containing a space, keeps its argument intact
    with open(os.path.join(d, "echoarg.cmd"), "w") as f:
        f.write("@echo %~1\r\n")
    env = dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])
    r = subprocess.run([sys.executable, WRAP, "echoarg", "a b"], capture_output=True, timeout=30, env=env)
    assert r.stdout.strip() == b"a b", r.stdout


def t_child_exits():
    m = "ORPHAN_exits"
    p = subprocess.run(wrapped(m, ["cmd", "/c", "node", DUMMY, m, "exit"]), capture_output=True, timeout=30)
    assert p.returncode == 5, p.returncode
    time.sleep(1)
    left = find(m)
    kill_all(m)
    assert not left, left


def load_wrap():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mcp_wrap_under_test", WRAP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t_refuse_metachar():
    d = os.path.join(TMP, "meta")
    os.makedirs(d)
    mark = os.path.join(d, "ran.txt")
    cmdfile = os.path.join(d, "srv.cmd")
    try:
        with open(cmdfile, "w") as f:
            f.write("@echo hi\r\n")
        r = subprocess.run([sys.executable, WRAP, "--", cmdfile, "a&type nul>" + mark],
                           capture_output=True, timeout=30)
        assert r.returncode == 2, (r.returncode, r.stderr)
        assert not os.path.exists(mark), "second command ran"
        assert b"refus" in r.stderr, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_npx_resolution():
    mod = load_wrap()
    d = os.path.join(TMP, "npmroot")
    cli = os.path.join(d, "node_modules", "npm", "bin", "npx-cli.js")
    try:
        os.makedirs(os.path.dirname(cli))
        for n in (os.path.join(d, "npx.cmd"), os.path.join(d, "node.exe"), cli):
            open(n, "w").close()
        got = mod.win_command([os.path.join(d, "npx.cmd"), "-y", "pkg&x"])
        assert got == [os.path.join(d, "node.exe"), cli, "-y", "pkg&x"], got
        os.remove(cli)
        try:
            mod.win_command([os.path.join(d, "npx.cmd"), "pkg&x"])
            raise AssertionError("missing cli should fall through to the metachar refusal")
        except ValueError:
            pass
        got = mod.win_command([os.path.join(d, "npx.cmd"), "pkg"])
        assert isinstance(got, str) and "system32\\cmd.exe" in got.lower(), got
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_cwd_hijack():
    decoy, real = os.path.join(TMP, "decoy"), os.path.join(TMP, "real")
    mark = os.path.join(TMP, "hijack.txt")
    try:
        for d, who in ((decoy, "decoy"), (real, "real")):
            os.makedirs(d)
            with open(os.path.join(d, "evilcmd.cmd"), "w") as f:
                f.write('@echo %s>"%s"\r\n' % (who, mark))
        env = dict(os.environ, PATH=real + os.pathsep + os.environ["PATH"])
        subprocess.run([sys.executable, WRAP, "evilcmd"], capture_output=True, timeout=30, env=env, cwd=decoy)
        with open(mark) as f:
            assert f.read().strip() == "real"
    finally:
        shutil.rmtree(decoy, ignore_errors=True)
        shutil.rmtree(real, ignore_errors=True)


def t_parent_gone():
    import ctypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    errf = os.path.join(TMP, "gone.err")
    # the wrapper sleeps first so the test can hold its handle; by the time it checks, its parent has exited
    w = ("import time,sys,runpy; time.sleep(5); sys.argv=[%r,'--',%r,'-e','setInterval(()=>{},1000)']; "
         "runpy.run_path(%r, run_name='__main__')" % (WRAP, NODE, WRAP))
    client = ("import subprocess,sys; p=subprocess.Popen([sys.executable,'-c',%r],stderr=open(%r,'w')); "
              "print(p.pid,flush=True)" % (w, errf))
    out = subprocess.run([sys.executable, "-c", client], capture_output=True, text=True, timeout=30).stdout
    h = k.OpenProcess(0x00101000, 0, int(out.strip()))
    assert h, "could not open the wrapper process (%r, err %d)" % (out, ctypes.get_last_error())
    assert k.WaitForSingleObject(h, 15000) == 0, "wrapper did not exit"
    code = ctypes.c_uint32()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    assert code.value == 1, (code.value, open(errf).read())
    with open(errf) as f:
        assert "parent already gone" in f.read()


def t_posix():
    m = "ORPHANPOSIX%d" % os.getpid()
    cmd = [sys.executable, WRAP, "--", "sh", "-c", "sleep 300; : " + m]
    client = subprocess.Popen([sys.executable, "-c",
                               "import subprocess,time; subprocess.Popen(%r); time.sleep(120)" % (cmd,)])
    try:
        time.sleep(3)
        assert subprocess.run(["pgrep", "-f", m], capture_output=True).stdout, "server did not start"
        client.kill()
        time.sleep(9)   # poll interval + 3 s SIGTERM grace + margin
        left = subprocess.run(["pgrep", "-f", m], capture_output=True, text=True).stdout.split()
        assert not left, left
    finally:
        subprocess.run(["pkill", "-9", "-f", m], capture_output=True)
        client.kill()


CASES = [("control: orphans without wrapper", t_control, "win"), ("wrapped: no orphans", t_wrapped, "win"),
         ("wrapped through cmd /c", t_via_cmd, "win"), ("exit code pass-through", t_exit_code, "win"),
         ("stdout stays clean", t_stdout_clean, "win"), ("command path with a space", t_space_path, "win"),
         ("child exits on its own", t_child_exits, "win"),
         ("shell metacharacter argument refused for .cmd", t_refuse_metachar, "win"),
         ("npx resolves to node + npx-cli.js", t_npx_resolution, "win"),
         ("cwd decoy does not hijack PATH lookup", t_cwd_hijack, "win"),
         ("parent already gone exits 1", t_parent_gone, "win"),
         ("posix: no orphans (UNTESTED on the dev machine)", t_posix, "posix")]

ok = total = 0
try:
    for name, fn, plat in CASES:
        if (plat == "win") != WIN:
            print("SKIPPED %s (needs %s)" % (name, "Windows" if plat == "win" else "POSIX"))
            continue
        if WIN and not NODE:
            print("SKIPPED %s (node not found)" % name)
            continue
        total += 1
        try:
            fn()
            ok += 1
            print("ok   %s" % name)
        except Exception as e:
            print("FAIL %s: %s: %s" % (name, type(e).__name__, e))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("mcp-wrap: %d/%d passed" % (ok, total))
sys.exit(0 if ok == total else 1)

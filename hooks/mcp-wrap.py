#!/usr/bin/env python3
"""mcp-wrap: run an MCP server so it cannot outlive the agent that launched it.

Usage: mcp-wrap.py [--] <command> [args...]      e.g. mcp-wrap.py -- npx -y some-mcp-server

When an agent crashes or is force-closed, servers started through `cmd /c npx ...` are left running as
orphans. This wrapper runs the server in a Windows Job Object (KILL_ON_JOB_CLOSE) and exits when the
agent (any of its parent and 3 further ancestors) exits, which takes the whole server tree with it. On
POSIX it uses a process group and signals instead.

stdin, stdout and stderr are inherited, so the MCP stdio protocol passes straight through. The wrapper never
writes to stdout; diagnostics go to stderr. Exit code is the child's."""
import os
import shutil
import subprocess
import sys
import time

USAGE = "usage: mcp-wrap.py [--] <command> [args...]"
DEPTH = 4          # parent plus 3 further ancestors
POLL = 0.5


def log(msg):
    print("mcp-wrap: " + msg, file=sys.stderr)


# ---------------------------------------------------------------- Windows
def run_windows(args):
    import ctypes
    import ctypes.wintypes as w
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = w.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.GetCurrentProcess.restype = w.HANDLE
    k.OpenProcess.restype = w.HANDLE
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.WaitForMultipleObjects.argtypes = [w.DWORD, ctypes.c_void_p, w.BOOL, w.DWORD]
    k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.Process32FirstW.argtypes = [w.HANDLE, ctypes.c_void_p]
    k.Process32NextW.argtypes = [w.HANDLE, ctypes.c_void_p]
    k.CloseHandle.argtypes = [w.HANDLE]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                    ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    def created(h):
        """Process creation time (100 ns ticks) from an open handle, or None."""
        c, x, kt, ut = (w.FILETIME() for _ in range(4))
        if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(kt), ctypes.byref(ut)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime

    def parent_map():
        snap = k.CreateToolhelp32Snapshot(0x2, 0)
        parents, e = {}, PE()
        e.dwSize = ctypes.sizeof(PE)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            parents[e.th32ProcessID] = e.th32ParentProcessID
            ok = k.Process32NextW(snap, ctypes.byref(e))
        k.CloseHandle(snap)
        return parents

    def ancestor_handles():
        """SYNCHRONIZE handles of the parent chain. A pid whose creation time is later than its child's is a
        reused pid (the real ancestor already exited): stop there. Returns [] if the parent is already gone."""
        parents, out = parent_map(), []
        pid, child_t = os.getpid(), created(k.GetCurrentProcess())
        while len(out) < DEPTH and parents.get(pid):
            pid = parents[pid]
            h = k.OpenProcess(0x00101000, False, pid)   # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
            t = created(h) if h else None
            if not h or t is None or (child_t is not None and t > child_t):
                if h:
                    k.CloseHandle(h)
                break
            out.append(h)
            child_t = t
        return out

    # Job first: everything we start inherits it, with no race. Closing the last handle kills the tree.
    job = k.CreateJobObjectW(None, None)
    info = EXT()
    info.Basic.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    in_job = bool(job) and k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) \
        and k.AssignProcessToJobObject(job, k.GetCurrentProcess())
    if not in_job:
        log("no Job Object (error %d); falling back to taskkill /T on exit" % ctypes.get_last_error())

    handles = ancestor_handles()
    if not handles:
        log("parent already gone, exiting")
        return 0
    arr = (w.HANDLE * len(handles))(*handles)

    child = subprocess.Popen(win_command(args))
    while True:
        rc = child.poll()
        if rc is not None:
            return rc
        if k.WaitForMultipleObjects(len(handles), arr, False, int(POLL * 1000)) < len(handles):
            if not in_job:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], capture_output=True)
            return 0   # in a job, our exit closes the last handle and kills the tree


def win_command(args):
    """Resolve args[0] like a shell would. .cmd/.bat (npx.cmd) cannot be started directly with safe quoting, so
    run them through cmd /c; /s makes cmd strip exactly the outer quote pair we add."""
    exe = shutil.which(args[0]) or args[0]
    if exe.lower().endswith((".cmd", ".bat")):
        return 'cmd.exe /d /s /c "%s"' % subprocess.list2cmdline([exe] + args[1:])
    return [exe] + args[1:]


# ---------------------------------------------------------------- POSIX
def run_posix(args):
    import signal
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL(None).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG: SIGTERM us if the parent dies
        except Exception:
            pass

    def ppid_of(pid):
        r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True)
        return int(r.stdout.strip() or 0)

    watch, pid = [], os.getppid()
    while pid > 1 and len(watch) < DEPTH:
        watch.append(pid)
        pid = ppid_of(pid)
    ppid = os.getppid()

    stop = []
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, lambda *_: stop.append(1))

    child = subprocess.Popen(args, start_new_session=True)
    while True:
        rc = child.poll()
        if rc is not None:
            return rc if rc >= 0 else 128 - rc
        gone = os.getppid() != ppid
        for p in watch:
            try:
                os.kill(p, 0)
            except ProcessLookupError:
                gone = True
            except PermissionError:
                pass
        if stop or gone:
            break
        time.sleep(POLL)
    for sig, grace in ((signal.SIGTERM, 3), (signal.SIGKILL, 0)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            break
        try:
            child.wait(timeout=grace)
            break
        except subprocess.TimeoutExpired:
            pass
    return 0


def main():
    args = sys.argv[1:]
    if args[:1] in (["--help"], ["-h"]):
        print(__doc__.strip())
        return 0
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        log(USAGE)
        return 2
    try:
        return run_windows(args) if os.name == "nt" else run_posix(args)
    except FileNotFoundError as e:
        log("cannot run %s: %s" % (args[0], e))
        return 127


if __name__ == "__main__":
    sys.exit(main())

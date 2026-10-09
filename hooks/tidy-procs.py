#!/usr/bin/env python3
"""List stray, duplicate and idle processes for /tidy; `apply --ids` kills exactly ids from a fresh scan."""
import argparse
import importlib.util
import json
import math
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"  # Windows: never resolve a bare name through the cwd


def which(name):
    """Resolve a command from absolute PATH folders only, never the current directory. None when not found."""
    nt = os.name == "nt"
    names = [name + e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e] if nt else [name]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip('"')
        for n in names:
            exe = os.path.join(d, n)
            if d and os.path.isabs(d) and os.path.isfile(exe) and (nt or os.access(exe, os.X_OK)):
                return exe
    return None


# Reuse the reaper: orphan detection, process listing and the verified child-first kill.
_spec = importlib.util.spec_from_file_location("reaper", pathlib.Path(__file__).resolve().with_name("mcp-orphans.py"))
reaper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reaper)

SAMPLE_S = 3
# Under 2% of one core over the sample counts as no CPU: Windows process times tick in ~15 ms steps.
CPU_EPSILON_S = 0.05
_W = r"(?<![\w-])%s(?![\w-])"
DEV_COMMANDS = tuple(re.compile(p, re.I) for p in (
    r"\bnext\s+(?:dev|start)\b", _W % "vite", r"\bwebpack\s+serve\b", r"webpack-dev-server",
    r"\bnuxt\s+dev\b", r"\bastro\s+dev\b", r"\bremix\s+dev\b", r"\bng\s+serve\b", _W % "parcel",
    r"\breact-scripts\s+start\b", r"\bnpm(?:-cli\.js|\.cmd)?\"?\s+run\s+dev\b",
    r"\byarn(?:\.js|\.cmd)?\"?\s+dev\b", r"\bpnpm(?:\.cjs|\.cmd)?\"?\s+dev\b", _W % "nodemon",
    r"\bts-node-dev\b", _W % "uvicorn", r"\bflask\s+run\b", r"\bmanage\.py\s+runserver\b",
    r"\brails\s+s(?:erver)?\b", r"\bpython[\d.]*(?:\.exe)?\"?\s+-m\s+http\.server\b",
    r"\bphp(?:\.exe)?\"?\s+(?:\S+\s+)*-(?-i:S)\b",
))
GLOBAL_PREFIX = re.compile(r"(?:^|/)(?:npm|lib|nodejs)$|/(?:\.?nvm|fnm|volta)(?:/|$)", re.I)
SCRIPT = re.compile(r"\.(?:py|js|mjs|cjs|ts)$", re.I)


def is_dev(command):
    return any(p.search(command) for p in DEV_COMMANDS)


def is_mcp(command, patterns):
    command = command.lower()
    return any(all(part.lower() in command for part in ((p,) if isinstance(p, str) else p)) for p in patterns)


def norm_path(value):
    value = value.replace("\\", "/").rstrip("/")
    return value.lower() if re.match(r"[A-Za-z]:", value) else value


def normalise(command):
    command = re.sub(r"(?<![\w-])(?:--port|-p)(?:=|\s*)\d+\b", "", command, flags=re.I)
    command = re.sub(r":\d{2,5}\b", "", command)
    command = re.sub(r"(?<=\s)\d{2,5}(?=\s|$)", "", command)
    return " ".join(command.lower().split())


def project_root(command):
    """Folder before the first project node_modules, else the script's folder, else None (never grouped)."""
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    tokens = [t.strip("\"'") for t in tokens]
    for t in tokens:
        m = re.search(r"[\\/]node_modules[\\/]", t, re.I)
        if m:
            root = norm_path(t[:m.start()])
            # A global install (npm's own folder, nvm) is shared by every project, so it names none.
            if root and not GLOBAL_PREFIX.search(root):
                return root
    for prev, t in zip(tokens, tokens[1:]):
        if SCRIPT.search(t) and not prev.startswith("-") and not re.search(r"node_modules", t, re.I):
            folder = norm_path(re.sub(r"[^\\/]*$", "", t))
            if folder:
                return folder
    return None


def clean(text):
    return reaper.clean(text)


# Scope: a process is this repository's only when its working folder (or an absolute path in its command line)
# is inside the repository or one of its linked worktrees.

SHELLS = re.compile(r"^(?:sh|bash|zsh|fish|dash|pwsh|powershell|cmd|wt|windowsterminal|conhost|openconsole)$")
MAX_UNKNOWN = 20
EDITORS = re.compile(r"^(?:code(?:-insiders)?|cursor|windsurf|zed|idea.*|explorer)$")
# claude, codex and antigravity all run as node.exe on Windows: they are told apart by the script they run,
# never by the executable name (that would also catch every dev server).
AGENT_CLIS = {"claude", "claude-code", "codex", "agy", "antigravity"}


def exe_name(p):
    return p["name"].lower().removesuffix(".exe")


def command_tokens(command):
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    return [t.strip("\"'") for t in tokens]


def agent_cli(command):
    """True when one of the first arguments is an agent CLI's script or program (claude, codex, antigravity)."""
    for t in command_tokens(command)[:4]:
        if t.startswith("-"):
            continue
        parts = t.replace("\\", "/").split("/")
        base = re.sub(r"\.(?:exe|cmd|js|mjs|ps1)$", "", parts[-1], flags=re.I).lower()
        if base in AGENT_CLIS or (len(parts) > 1 and parts[-2].lower() == "claude-code"):
            return True
    return False


def interactive(p):
    """An editor or an agent session is the user's own working environment: never a leftover."""
    return bool(EDITORS.match(exe_name(p))) or agent_cli(p["command"])


def norm(path):
    return os.path.normcase(os.path.realpath(path))


def under(path, scope):
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in scope)


def too_broad(folder):
    """Why a scope folder is the wrong size, or None. Processes are matched by working folder, so the home
    folder, a folder holding it (C:\\Users, /home), a filesystem root or a system folder would claim other
    projects' processes and the system's own."""
    f = norm(folder)
    if os.path.dirname(f) == f or under(norm(os.path.expanduser("~")), [f]):
        return "the home folder, a filesystem root or a folder that holds the home folder"
    system = ([os.environ.get(v) for v in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
              if os.name == "nt" else ["/bin", "/sbin", "/etc", "/usr", "/lib", "/System"])
    if under(f, [norm(s) for s in system if s]):
        return "a system folder"
    return None


def argv_in_scope(command, scope):
    """An absolute path in the command line (also after `--flag=`) that is inside the scope."""
    for t in command_tokens(command):
        for v in (t, t.partition("=")[2]):
            if v and os.path.isabs(v) and under(os.path.normcase(os.path.normpath(v)), scope):
                return True
    return False


def make_item(group, confidence, label, evidence, members):
    root = members[0]
    return {"id": f"proc:{root['pid']}:{int(root['created'])}", "group": group,
            "label": clean(label)[:80], "evidence": [clean(e) for e in evidence], "confidence": confidence,
            "size_bytes": int(sum(m["mb"] for m in members) * 1048576), "action": "kill",
            "pids": [m["pid"] for m in members], "_processes": members}


def scan(procs, now, patterns, min_age_s, idle_s, self_pid, net, cpu_probe, init_pids=(), init_names=(),
         scope=None, cwds=None):
    """Pure over its arguments. Returns (items, notes). net is None when listing sockets was unavailable.
    scope: normalised folders of the repository (None: no filter); cwds(pids) -> {pid: folder or None}."""
    by_pid = {p["pid"]: p for p in procs}
    kids = {}
    for p in procs:
        parent = by_pid.get(p["ppid"])
        if parent and p["pid"] != parent["pid"] and p["created"] >= parent["created"]:
            kids.setdefault(p["ppid"], []).append(p["pid"])

    def tree(pid):  # root first, so reversed() is child-first
        out, pending, seen = [], [pid], set()
        while pending:
            q = pending.pop()
            if q not in seen:
                seen.add(q)
                out.append(by_pid[q])
                pending.extend(reversed(kids.get(q, [])))
        return out

    protected, pid = set(), self_pid
    while pid in by_pid and pid not in protected:
        protected.add(pid)
        pid = by_pid[pid]["ppid"]
    claimed, items, notes = set(), [], []

    def add(item):
        pids = set(item["pids"])
        if pids & claimed or pids & protected:
            return False
        claimed.update(pids)
        items.append(item)
        return True

    def age_h(p):
        return (now - p["created"]) / 3600

    trees = [t for t in reaper.find_orphans(procs, now, patterns, min_age_s, self_pid, init_pids, init_names)
             if not interactive(by_pid[t["pid"]])]
    dev = sorted((p for p in procs if is_dev(p["command"]) and not is_mcp(p["command"], patterns)
                  and p["pid"] not in protected and not interactive(p)), key=lambda p: p["created"])

    def ancestors(p):
        out, seen = [], {p["pid"]}
        while (parent := by_pid.get(p["ppid"])) and parent["pid"] not in seen and parent["created"] <= p["created"]:
            out.append(parent)
            seen.add(parent["pid"])
            p = parent
        return out

    verdict = {}  # pid -> "in" | "out" | "unknown"
    found = {}  # pid -> working folder, for the pids that were asked and could be read

    def own(p):  # None when this process alone cannot say
        folder = found.get(p["pid"])
        if folder is not None:  # a readable folder is final: an argv path naming this repo cannot pull it in
            return "in" if under(norm(folder), scope) else "out"
        return "in" if argv_in_scope(p["command"], scope) else None

    if scope is None:
        verdict = {p["pid"]: "in" for p in procs}
    else:
        wanted = {p["pid"]: p for p in dev + [m for t in trees for m in t["processes"]]}
        found.update(cwds(sorted(wanted)))
        first = {pid: own(p) for pid, p in wanted.items()}
        # A process whose own folder is unreadable (elevated, 32-bit) still belongs to its owner's tree. A readable
        # folder outside the repository is final: a parent in the repository does not pull it in.
        found.update(cwds(sorted({a["pid"] for pid, v in first.items() if v is None for a in ancestors(wanted[pid])}
                                 - found.keys())))
        for pid, p in wanted.items():
            v = first[pid]
            verdict[pid] = v or ("in" if any(own(a) == "in" for a in ancestors(p)) else "unknown")

    def tree_verdict(members):
        vs = {verdict[m["pid"]] for m in members}
        return "in" if "in" in vs else "unknown" if "unknown" in vs else "out"

    unreadable = sum(verdict[p["pid"]] == "unknown" for p in dev)
    dev = [p for p in dev if verdict[p["pid"]] == "in"]
    elsewhere = []
    for t in trees:
        v = tree_verdict(t["processes"])
        if v == "out":
            elsewhere.append(t)
            continue
        if v == "unknown":
            unreadable += 1
            continue
        root = by_pid[t["pid"]]
        parent = by_pid.get(root["ppid"])
        why = (f"parent pid {root['ppid']} is gone" if not parent else
               f"parent pid {root['ppid']} was reused by a newer process" if parent["created"] > root["created"]
               else f"adopted by {parent['name']} after its parent exited")
        evidence = ["MCP server tree with no live owner", why, f"started {age_h(root):.1f} h ago",
                    f"{len(t['pids'])} processes, {t['mb']:.1f} MB"]
        ports = sorted({port for pid in t["pids"] for port in (net or {"listen": {}})["listen"].get(pid, ())})
        if ports:  # an HTTP or SSE server someone started on purpose looks exactly like an orphan
            evidence.append("listening on port " + ", ".join(map(str, ports)))
        add(make_item("processes.strays", "low" if ports else "high", f"{root['name']}: {root['command']}",
                      evidence, t["processes"]))
    if elsewhere:
        notes.append(f"{len(elsewhere)} orphaned MCP trees elsewhere on this machine "
                     f"({sum(t['mb'] for t in elsewhere):.0f} MB), not listed: run "
                     "~/.the-agent-kit/install.sh --tidy to review them")
    if unreadable:
        notes.append(f"{unreadable} processes with an unreadable working folder were skipped")

    groups = {}
    for p in dev:
        root = project_root(p["command"])
        if root:
            groups.setdefault((normalise(p["command"]), root), []).append(p)
    for (_, root), group in groups.items():
        inside = {m["pid"] for p in group for m in tree(p["pid"])[1:]}
        group = [p for p in group if p["pid"] not in inside]
        if len(group) < 2:
            continue
        listens = {p["pid"]: bool(net) and any(m["pid"] in net["listen"] for m in tree(p["pid"])) for p in group}
        keep = max(group, key=lambda p: (listens[p["pid"]], p["created"]))
        for p in group:
            if p is keep or now - p["created"] < min_age_s:
                continue
            relation = "newer" if keep["created"] > p["created"] else "listening"
            evidence = [f"same command and project as pid {keep['pid']}, which is {relation}",
                        f"project {root}", f"started {age_h(p):.1f} h ago"]
            if listens[p["pid"]]:  # ports are stripped from the key, so a distinct server can land here
                ports = sorted({port for m in tree(p["pid"]) for port in net["listen"].get(m["pid"], ())})
                evidence.append("also listening on port " + ", ".join(map(str, ports)))
            if net is None:  # "newest" is a guess when no copy can be seen listening
                evidence.append("socket state unknown: TCP connections could not be listed")
            add(make_item("processes.duplicates", "low" if listens[p["pid"]] or net is None else "medium",
                          f"{p['name']}: {p['command']}", evidence, tree(p["pid"])))

    candidates = []
    for p in dev:
        if net is None or now - p["created"] < max(min_age_s, idle_s):
            continue
        members = tree(p["pid"])
        ports = sorted({port for m in members for port in net["listen"].get(m["pid"], ())})
        if ports and not any(net["established"].get(port) for port in ports):
            candidates.append((p, members, ports))

    # Processes in the repository that match no known pattern but listen on a port or have run for hours: shown
    # at low with facts, for the agent to name or leave. Editors, shells and agents are never among them.
    unknown = []
    if scope is not None:
        known = {m["pid"] for p in dev for m in tree(p["pid"])} | {m["pid"] for t in trees for m in t["processes"]}
        pool = [p for p in procs if p["pid"] not in known | protected and not interactive(p)
                and not SHELLS.match(exe_name(p)) and not is_mcp(p["command"], patterns)
                and now - p["created"] >= min_age_s]
        found.update(cwds([p["pid"] for p in pool if p["pid"] not in found]))
        pool = [p for p in pool if own(p) == "in"]  # no inheritance here: an unreadable folder is not listed
        listening = lambda p: net is not None and any(m["pid"] in net["listen"] for m in tree(p["pid"]))
        picked = {p["pid"]: p for p in pool if listening(p) or now - p["created"] >= idle_s}
        unknown = sorted((p for p in picked.values() if p["ppid"] not in picked), key=lambda p: p["created"])[:MAX_UNKNOWN]
    want = [m["pid"] for _, members, _ in candidates for m in members] + [m["pid"] for p in unknown for m in tree(p["pid"])]
    cpu = {}
    if want:
        try:
            cpu = cpu_probe(want)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            notes.append(f"idle check unavailable: cannot sample CPU: {exc}")
    for p, members, ports in candidates:
        used = sum(cpu[m["pid"]][1] - cpu[m["pid"]][0] for m in members if m["pid"] in cpu)
        if p["pid"] in cpu and used < CPU_EPSILON_S:
            where = ("port " if len(ports) == 1 else "ports ") + ", ".join(map(str, ports))
            add(make_item("processes.idle", "low", f"{p['name']}: {p['command']}",
                          [f"no connection to {where}", f"no CPU in {SAMPLE_S} s",
                           f"started {age_h(p):.1f} h ago"], members))
    for p in unknown:
        members = tree(p["pid"])
        ports = sorted({port for m in members for port in (net or {"listen": {}})["listen"].get(m["pid"], ())})
        used = sum(cpu[m["pid"]][1] - cpu[m["pid"]][0] for m in members if m["pid"] in cpu)
        parent = by_pid.get(p["ppid"])
        evidence = [f"no known server, watcher or MCP pattern matches; working folder {clean(found[p['pid']])}"
                    if p["pid"] in found else "no known server, watcher or MCP pattern matches",
                    f"started {age_h(p):.1f} h ago",
                    ("listening on port " + ", ".join(map(str, ports)) + "; " + (
                        "a connection is open" if any(net["established"].get(x) for x in ports) else "no connection"))
                    if ports else "not listening on any port",
                    (f"used {used:.2f} s CPU in {SAMPLE_S} s" if p["pid"] in cpu else "CPU not sampled"),
                    (f"started by {parent['name']} (pid {parent['pid']}, still running)" if parent
                     and parent["created"] <= p["created"] else f"its parent (pid {p['ppid']}) is gone")]
        add(make_item("processes.unknown", "low", f"{p['name']}: {p['command']}", evidence, members))
    return items, notes


# Live listers

def powershell(script):
    result = subprocess.run([reaper.POWERSHELL, "-NoProfile", "-Command", script], capture_output=True,
                            check=True, timeout=30, encoding="utf-8-sig")
    return result.stdout


def build_net(rows):
    """rows: (state, port, pid or None) with state 'listen' or 'estab' -> {'listen': {pid: [ports]}, 'established': {port: n}}."""
    result = {"listen": {}, "established": {}}
    for state, port, pid in rows:
        if state == "listen" and pid is not None:
            result["listen"].setdefault(pid, [])
            if port not in result["listen"][pid]:
                result["listen"][pid].append(port)
        elif state == "estab":
            result["established"][port] = result["established"].get(port, 0) + 1
    return result


def parse_lsof(text):
    for line in text.splitlines():
        cols = line.split()
        m = re.search(r"\((LISTEN|ESTABLISHED)\)$", line)
        if len(cols) > 8 and cols[1].isdigit() and m:
            port = cols[-2].split("->")[0].rsplit(":", 1)[-1]
            if port.isdigit():
                yield ("listen" if m.group(1) == "LISTEN" else "estab", int(port), int(cols[1]))


def parse_ss(text):
    for line in text.splitlines():
        cols = line.split()
        if len(cols) > 4 and cols[0] in ("LISTEN", "ESTAB"):
            port = cols[3].rsplit(":", 1)[-1]
            if port.isdigit():
                for pid in [int(x) for x in re.findall(r"pid=(\d+)", line)] or [None]:
                    yield ("listen" if cols[0] == "LISTEN" else "estab", int(port), pid)


def net_snapshot():
    """Returns (net or None, note or None). Never raises: an unavailable lister only disables idle checks."""
    try:
        if os.name == "nt":
            out = powershell("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
                             "@(Get-NetTCPConnection -State Listen,Established | ForEach-Object { [pscustomobject]@{"
                             "port=[int]$_.LocalPort; state=[string]$_.State; pid=[int]$_.OwningProcess} }) | ConvertTo-Json -Compress")
            data = json.loads(out or "[]")
            data = [data] if isinstance(data, dict) else data
            return build_net(("listen" if r["state"].lower().startswith("listen") else "estab", r["port"], r["pid"])
                             for r in data), None
        ss, lsof = which("ss"), which("lsof")
        if ss:
            out = subprocess.run([ss, "-tanp"], capture_output=True, check=True, timeout=10, text=True).stdout
            return build_net(parse_ss(out)), None
        if lsof:
            out = subprocess.run([lsof, "-nP", "-iTCP", "-sTCP:LISTEN,ESTABLISHED"], capture_output=True,
                                 timeout=20, text=True).stdout  # lsof exits 1 when it lists nothing
            return build_net(parse_lsof(out)), None
        return None, "idle check unavailable: neither ss nor lsof is installed"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return None, f"idle check unavailable: cannot list TCP connections: {exc}"


def parse_cputime(value):
    days, _, clock = value.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return int(days or 0) * 86400 + seconds


def cpu_times(pids):
    if os.name == "nt":
        ids = ",".join(str(int(p)) for p in pids)
        out = powershell(f"Get-Process -Id {ids} -ErrorAction SilentlyContinue | ForEach-Object {{ "
                         "$_.Id.ToString() + ' ' + $_.TotalProcessorTime.TotalSeconds.ToString([cultureinfo]::InvariantCulture) }")
        return {int(a): float(b) for a, b in (line.split() for line in out.splitlines() if line.strip())}
    result = {}
    ticks = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    for pid in pids:
        try:
            fields = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            result[pid] = (int(fields[11]) + int(fields[12])) / ticks
        except (OSError, IndexError, ValueError):
            pass
    if not result and not pathlib.Path("/proc/self").exists():  # macOS: ps only, whole-second resolution on Linux
        ps = which("ps")
        out = subprocess.run([ps, "-o", "pid=,cputime=", "-p", ",".join(map(str, pids))],
                             capture_output=True, text=True, timeout=10).stdout if ps else ""
        result = {int(a): parse_cputime(b) for a, b in (line.split() for line in out.splitlines() if line.strip())}
    return result


def probe_live(pids):
    before = cpu_times(pids)
    time.sleep(SAMPLE_S)
    after = cpu_times(pids)
    return {pid: (before[pid], after[pid]) for pid in before if pid in after}


# Working folders. A pid missing from the result is unknown (access denied, gone, or not supported here).

def win_cwd(pid):
    """Windows: read CurrentDirectory from the target's PEB. Needs no admin for same-user processes. x64 targets
    only (a 32-bit process has a different PEB layout and counts as unknown)."""
    import ctypes
    import ctypes.wintypes as w
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return None
    k32, ntdll = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("ntdll")

    class PBI(ctypes.Structure):
        _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                    ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_void_p),
                    ("Reserved3", ctypes.c_void_p)]

    def read(h, addr, n):
        buf, got = ctypes.create_string_buffer(n), ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            raise OSError("ReadProcessMemory")
        return buf.raw

    h = k32.OpenProcess(0x0400 | 0x0010, False, pid)  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if not h:
        return None
    try:
        wow64 = w.BOOL()
        if not k32.IsWow64Process(h, ctypes.byref(wow64)) or wow64.value:
            return None
        pbi = PBI()
        if ntdll.NtQueryInformationProcess(h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None):
            return None
        # PEB+0x20 = ProcessParameters; RTL_USER_PROCESS_PARAMETERS+0x38 = CurrentDirectory.DosPath (a UNICODE_STRING)
        params = int.from_bytes(read(h, pbi.PebBaseAddress + 0x20, 8), "little")
        us = read(h, params + 0x38, 16)
        text = read(h, int.from_bytes(us[8:16], "little"), int.from_bytes(us[0:2], "little")).decode("utf-16-le")
        return text if len(text) <= 3 else text.rstrip("\\")  # keep the drive root "C:\"
    except (OSError, ValueError):
        return None
    finally:
        k32.CloseHandle(h)


def lsof_cwds(pids):
    lsof = which("lsof")
    if not lsof or not pids:
        return {}
    try:
        out = subprocess.run([lsof, "-a", "-p", ",".join(map(str, pids)), "-d", "cwd", "-Fn"], capture_output=True,
                             text=True, timeout=20).stdout  # exits 1 when some pids are gone
    except (OSError, subprocess.SubprocessError):
        return {}
    result, pid = {}, None
    for line in out.splitlines():
        if line[:1] == "p" and line[1:].isdigit():
            pid = int(line[1:])
        elif line[:1] == "n" and pid is not None:
            result[pid] = line[1:]
    return result


def read_cwds(pids):
    if os.name == "nt":
        return {pid: c for pid in pids if (c := win_cwd(pid))}
    if not pathlib.Path("/proc/self").exists():
        return lsof_cwds(pids)  # macOS
    result = {}
    for pid in pids:
        try:
            result[pid] = os.readlink(f"/proc/{pid}/cwd").removesuffix(" (deleted)")  # a removed folder still counts
        except OSError:
            pass
    return result


def memoised(probe):
    """Wrap a {pid: folder} reader: each pid is read once; the answer for an unreadable pid is None."""
    memo = {}

    def get(pids):
        todo = [p for p in pids if p not in memo]
        if todo:
            got = probe(todo)
            memo.update({p: got.get(p) for p in todo})
        return {p: memo[p] for p in pids}
    return get


def occupied(procs, roots, cwds):
    """The roots that some process (any: a shell, an agent session, a server) is working inside."""
    folders = [norm(f) for f in cwds(sorted(p["pid"] for p in procs)).values() if f]
    return [r for r in roots if any(under(f, [norm(r)]) for f in folders)]


def run_scan(min_age_minutes, idle_hours, roots):
    notes = []
    try:
        procs = reaper.list_processes()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [], [f"process listing unavailable: {exc}"]
    net, note = net_snapshot()
    items, more = scan(procs, time.time(), reaper.patterns_from_env(os.environ), min_age_minutes * 60,
                       idle_hours * 3600, os.getpid(), net, probe_live,
                       () if os.name == "nt" else (0, 1), () if os.name == "nt" else reaper.INIT_NAMES,
                       scope=sorted({norm(r) for r in roots}), cwds=memoised(read_cwds))
    return items, ([note] if note else []) + more


def apply_ids(ids, items, kill, dry_run=False):
    """Kill only ids that still match a fresh scan item (same root pid and creation time). Returns (report, survivors).
    With dry_run nothing is killed and the report says what would be."""
    tolerance = 0 if os.name == "nt" else 2  # ps elapsed time is whole seconds
    chosen, report = [], []
    for item_id in ids:
        m = re.fullmatch(r"proc:(\d+):(\d+)", item_id)
        hit = m and next((i for i in items if i["pids"][0] == int(m.group(1))
                          and abs(int(i["_processes"][0]["created"]) - int(m.group(2))) <= tolerance), None)
        if not hit:
            report.append(f"skipped {item_id}: no longer matches a fresh scan")
        elif hit not in chosen:
            chosen.append(hit)
    if dry_run:
        return report + [f"would kill pid {pid} ({i['label']})" for i in chosen for pid in i["pids"]], []
    survivors = kill([{"pid": i["pids"][0], "processes": i["_processes"]} for i in chosen]) if chosen else []
    for i in chosen:
        report += [f"pid {pid}: {'survived' if pid in survivors else 'killed or already exited'}" for pid in i["pids"]]
    return report, survivors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("occupied", help="print the --root folders that a running process works inside, as JSON") \
        .add_argument("--root", action="append", required=True)
    for name in ("scan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--root", action="append", required=True,
                       help="a folder of the repository (repeat for each linked worktree); only processes working "
                            "in these folders are listed or killed")
        p.add_argument("--min-age-minutes", type=float, default=5)
        p.add_argument("--idle-hours", type=float, default=4)
        if name == "scan":
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--ids", required=True)
            p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command != "occupied" and not all(math.isfinite(v) and v >= 0 for v in (args.min_age_minutes, args.idle_hours)):
        parser.error("ages must be finite nonnegative numbers")
    for r in args.root:
        why = too_broad(r)
        if why:  # a scope this wide is the whole machine; printed plainly so tidy-scan can quote it in a note
            print(f"tidy-procs: --root {r} is {why}: too broad to scope processes", file=sys.stderr)
            return 2
    if args.command == "occupied":
        try:
            print(json.dumps(occupied(reaper.list_processes(), args.root, read_cwds)))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"process listing unavailable: {exc}", file=sys.stderr)
            return 1
        return 0
    items, notes = run_scan(args.min_age_minutes, args.idle_hours, args.root)
    if args.command == "scan":
        if args.json:
            print(json.dumps({"version": 1, "notes": notes, "items": [
                {k: v for k, v in i.items() if not k.startswith("_")} for i in items]}))
        else:
            for i in items:
                print(f"{i['id']}  {i['group']}  {i['confidence']}  {i['label']}")
                for e in i["evidence"]:
                    print(f"    {clean(e)}")
            for n in notes:
                print(f"note: {n}")
            print(f"{len(items)} candidates" if items else "nothing to tidy")
        return 0
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    report, survivors = apply_ids(ids, items, reaper.kill_trees, args.dry_run)
    print("\n".join(report))
    return int(bool(survivors))


if __name__ == "__main__":
    sys.exit(main())

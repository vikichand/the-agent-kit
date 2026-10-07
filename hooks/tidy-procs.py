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
import shutil
import subprocess
import sys
import time

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


def make_item(group, confidence, label, evidence, members):
    root = members[0]
    return {"id": f"proc:{root['pid']}:{int(root['created'])}", "group": group,
            "label": clean(label)[:80], "evidence": evidence, "confidence": confidence,
            "size_bytes": int(sum(m["mb"] for m in members) * 1048576), "action": "kill",
            "pids": [m["pid"] for m in members], "_processes": members}


def scan(procs, now, patterns, min_age_s, idle_s, self_pid, net, cpu_probe, init_pids=(), init_names=()):
    """Pure over its arguments. Returns (items, notes). net is None when listing sockets was unavailable."""
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

    for t in reaper.find_orphans(procs, now, patterns, min_age_s, self_pid, init_pids, init_names):
        root = by_pid[t["pid"]]
        parent = by_pid.get(root["ppid"])
        why = (f"parent pid {root['ppid']} is gone" if not parent else
               f"parent pid {root['ppid']} was reused by a newer process" if parent["created"] > root["created"]
               else f"adopted by {parent['name']} after its parent exited")
        add(make_item("processes.strays", "high", f"{root['name']}: {root['command']}",
                      ["MCP server tree with no live owner", why, f"started {age_h(root):.1f} h ago",
                       f"{len(t['pids'])} processes, {t['mb']:.1f} MB"], t["processes"]))

    dev = sorted((p for p in procs if is_dev(p["command"]) and not is_mcp(p["command"], patterns)
                  and p["pid"] not in protected), key=lambda p: p["created"])
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
            add(make_item("processes.duplicates", "medium", f"{p['name']}: {p['command']}",
                          [f"same command and project as pid {keep['pid']}, which is {relation}",
                           f"project {root}", f"started {age_h(p):.1f} h ago"], tree(p["pid"])))

    candidates = []
    for p in dev:
        if net is None or now - p["created"] < max(min_age_s, idle_s):
            continue
        members = tree(p["pid"])
        ports = sorted({port for m in members for port in net["listen"].get(m["pid"], ())})
        if ports and not any(net["established"].get(port) for port in ports):
            candidates.append((p, members, ports))
    if candidates:
        try:
            cpu = cpu_probe([m["pid"] for _, members, _ in candidates for m in members])
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            cpu = {}
            notes.append(f"idle check unavailable: cannot sample CPU: {exc}")
        for p, members, ports in candidates:
            used = sum(cpu[m["pid"]][1] - cpu[m["pid"]][0] for m in members if m["pid"] in cpu)
            if p["pid"] in cpu and used < CPU_EPSILON_S:
                where = ("port " if len(ports) == 1 else "ports ") + ", ".join(map(str, ports))
                add(make_item("processes.idle", "low", f"{p['name']}: {p['command']}",
                              [f"no connection to {where}", f"no CPU in {SAMPLE_S} s",
                               f"started {age_h(p):.1f} h ago"], members))
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
        if shutil.which("ss"):
            out = subprocess.run(["ss", "-tanp"], capture_output=True, check=True, timeout=10, text=True).stdout
            return build_net(parse_ss(out)), None
        if shutil.which("lsof"):
            out = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN,ESTABLISHED"], capture_output=True,
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
        out = subprocess.run(["ps", "-o", "pid=,cputime=", "-p", ",".join(map(str, pids))],
                             capture_output=True, text=True, timeout=10).stdout
        result = {int(a): parse_cputime(b) for a, b in (line.split() for line in out.splitlines() if line.strip())}
    return result


def probe_live(pids):
    before = cpu_times(pids)
    time.sleep(SAMPLE_S)
    after = cpu_times(pids)
    return {pid: (before[pid], after[pid]) for pid in before if pid in after}


def run_scan(min_age_minutes, idle_hours):
    notes = []
    try:
        procs = reaper.list_processes()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [], [f"process listing unavailable: {exc}"]
    net, note = net_snapshot()
    items, more = scan(procs, time.time(), reaper.patterns_from_env(os.environ), min_age_minutes * 60,
                       idle_hours * 3600, os.getpid(), net, probe_live,
                       () if os.name == "nt" else (0, 1), () if os.name == "nt" else reaper.INIT_NAMES)
    return items, ([note] if note else []) + more


def apply_ids(ids, items, kill):
    """Kill only ids that still match a fresh scan item (same root pid and creation time). Returns (report, survivors)."""
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
    survivors = kill([{"pid": i["pids"][0], "processes": i["_processes"]} for i in chosen]) if chosen else []
    for i in chosen:
        report += [f"pid {pid}: {'survived' if pid in survivors else 'killed or already exited'}" for pid in i["pids"]]
    return report, survivors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--min-age-minutes", type=float, default=5)
        p.add_argument("--idle-hours", type=float, default=4)
        if name == "scan":
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--ids", required=True)
    args = parser.parse_args()
    if not all(math.isfinite(v) and v >= 0 for v in (args.min_age_minutes, args.idle_hours)):
        parser.error("ages must be finite nonnegative numbers")
    items, notes = run_scan(args.min_age_minutes, args.idle_hours)
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
    report, survivors = apply_ids(ids, items, reaper.kill_trees)
    print("\n".join(report))
    return int(bool(survivors))


if __name__ == "__main__":
    sys.exit(main())

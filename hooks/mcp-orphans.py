#!/usr/bin/env python3
"""List orphaned MCP process trees; terminate them only with --kill."""
import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time

DEFAULT_PATTERNS = (
    "modelcontextprotocol", "context7", "@playwright/mcp", "playwright/mcp",
    "chrome-devtools-mcp", "mcp-server", "server-sequential-thinking",
    ("npx-cli.js", "mcp"), ("uvx", "mcp"),
)


def patterns_from_env(env):
    # Tests and users needing a narrow match can exclude all default patterns.
    defaults = () if env.get("AGENT_KIT_MCP_PATTERNS_ONLY") == "1" else DEFAULT_PATTERNS
    return defaults + tuple(p.strip().lower() for p in
        env.get("AGENT_KIT_MCP_PATTERNS", "").split(",") if p.strip())


def parse_etime(value):
    days, _, clock = value.rpartition("-")
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return int(days or 0) * 86400 + seconds


def list_processes():
    if os.name == "nt":
        script = """$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
@(Get-CimInstance Win32_Process | ForEach-Object {
    if ($null -ne $_.CreationDate) {
        [pscustomobject]@{pid=[int]$_.ProcessId; ppid=[int]$_.ParentProcessId;
        created=([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds()/1000.0;
        name=$_.Name; command=[string]$_.CommandLine; mb=$_.WorkingSetSize/1MB}
    }
}) | ConvertTo-Json -Compress
"""
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                                capture_output=True, check=True, timeout=20,
                                encoding="utf-8-sig")
        data = json.loads(result.stdout or "[]")
        return [data] if isinstance(data, dict) else data or []
    result = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,rss=,command="],
                            capture_output=True, check=True, timeout=10, text=True)
    now = time.time()
    procs = []
    for line in result.stdout.splitlines():
        pid, ppid, elapsed, rss, command = line.strip().split(None, 4)
        procs.append(dict(pid=int(pid), ppid=int(ppid),
                          created=now - parse_etime(elapsed), mb=int(rss) / 1024,
                          name=os.path.basename(command.split()[0]), command=command))
    return procs


def find_orphans(procs, now, patterns, min_age_s, self_pid):
    by_pid = {p["pid"]: p for p in procs}
    children = {}
    for p in procs:
        parent = by_pid.get(p["ppid"])
        if parent and parent["created"] <= p["created"]:
            children.setdefault(p["ppid"], []).append(p["pid"])
    protected = set()
    pid = self_pid
    while pid in by_pid and pid not in protected:
        protected.add(pid)
        p = by_pid[pid]
        parent = by_pid.get(p["ppid"])
        if not parent or parent["created"] > p["created"]:
            break
        pid = p["ppid"]
    trees = []
    for p in procs:
        parent = by_pid.get(p["ppid"])
        command = p["command"].lower()
        matches = any(all(part.lower() in command for part in
                          ((pattern,) if isinstance(pattern, str) else pattern))
                      for pattern in patterns)
        if (parent and parent["created"] <= p["created"]) or not matches:
            continue
        if p["pid"] in protected or now - p["created"] < min_age_s:
            continue
        members, pending, seen = [], [p["pid"]], set()
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            members.append(by_pid[pid])
            pending.extend(reversed(children.get(pid, [])))
        if seen & protected:
            continue
        trees.append(dict(pid=p["pid"], name=p["name"], command=p["command"],
                          age_s=now - p["created"], pids=[m["pid"] for m in members],
                          names=[m["name"] for m in members],
                          mb=sum(m["mb"] for m in members), processes=members))
    return trees


def same_process(old, current):
    # ps elapsed time is only precise to a second, unlike the Windows timestamp.
    tolerance = 0 if os.name == "nt" else 2
    return (old["pid"] == current["pid"] and old["command"] == current["command"]
            and abs(old["created"] - current["created"]) <= tolerance)


def tree_unchanged(tree, procs):
    originals = {p["pid"]: p for p in tree["processes"]}
    current = {p["pid"]: p for p in procs}
    children = {}
    for p in procs:
        children.setdefault(p["ppid"], []).append(p["pid"])
    pending, seen = [tree["pid"]], set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        if pid not in originals or pid not in current or not same_process(originals[pid], current[pid]):
            return False
        pending.extend(children.get(pid, []))
    return True


def kill_trees(trees):
    originals = {p["pid"]: p for t in trees for p in t["processes"]}
    errors = []
    try:
        if os.name == "nt":
            for tree in trees:
                # One process at a time, children first, each re-checked against a fresh listing. taskkill /T
                # would also take a child spawned after we listed, which is not "exactly what was listed"; any
                # such newcomer is simply found by the next run.
                current = {p["pid"]: p for p in list_processes()}
                for p in reversed(tree["processes"]):
                    fresh = current.get(p["pid"])
                    if not fresh or not same_process(p, fresh):
                        continue
                    result = subprocess.run(["taskkill", "/F", "/PID", str(p["pid"])],
                                            capture_output=True, text=True, timeout=20)
                    if result.returncode and any(q["pid"] == p["pid"] for q in list_processes()):
                        errors.append(f"pid {p['pid']}: taskkill returned {result.returncode}")
        else:
            for tree in trees:
                for p in reversed(tree["processes"]):
                    fresh = {q["pid"]: q for q in list_processes()}.get(p["pid"])
                    if fresh and same_process(p, fresh):
                        try:
                            os.kill(p["pid"], signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        except OSError as exc:
                            errors.append(f"pid {p['pid']}: {exc}")
            time.sleep(2)
            for tree in trees:
                for p in reversed(tree["processes"]):
                    fresh = {q["pid"]: q for q in list_processes()}.get(p["pid"])
                    if fresh and same_process(p, fresh):
                        try:
                            os.kill(p["pid"], signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        except OSError as exc:
                            errors.append(f"pid {p['pid']}: {exc}")
        # Allow asynchronous exit to become visible, with a bounded wait.
        for attempt in range(10):
            current = {p["pid"]: p for p in list_processes()}
            survivors = [pid for pid, p in originals.items()
                         if pid in current and same_process(p, current[pid])]
            if not survivors:
                break
            time.sleep(0.1)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"cannot verify process exit: {exc}")
        survivors = list(originals)
    for error in errors:
        print(error, file=sys.stderr)
    return survivors


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="AGENT_KIT_MCP_PATTERNS adds comma-separated matches; AGENT_KIT_MCP_PATTERNS_ONLY=1 excludes defaults for tests and users needing a narrow match.")
    parser.add_argument("--kill", action="store_true")
    parser.add_argument("--min-age-minutes", type=float, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.min_age_minutes) or args.min_age_minutes < 0:
        parser.error("minimum age must be a finite nonnegative number")
    try:
        trees = find_orphans(list_processes(), time.time(), patterns_from_env(os.environ),
                             args.min_age_minutes * 60, os.getpid())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"orphan check unavailable: {exc}", file=sys.stderr)
        if args.json:
            print("null")
        return 0
    if args.json:
        print(json.dumps(trees))
    else:
        for t in trees:
            command = t["command"][:80].replace("\n", " ").replace("\r", " ")
            print(f"{t['pid']}/{t['name']}  {t['age_s']/60:.1f} min  {t['mb']:.1f} MB  "
                  f"{len(t['pids'])} processes  {command}")
        print(f"{len(trees)} orphaned MCP trees, {sum(len(t['pids']) for t in trees)} processes, "
              f"{sum(t['mb'] for t in trees):.1f} MB" if trees else "no orphaned MCP processes")
    if args.kill and trees:
        survivors = kill_trees(trees)
        stream = sys.stderr if args.json else sys.stdout
        for t in trees:
            for pid in t["pids"]:
                print(f"pid {pid}: {'survived' if pid in survivors else 'killed or already exited'}", file=stream)
        return int(bool(survivors))
    return 0


if __name__ == "__main__":
    sys.exit(main())

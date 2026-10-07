#!/usr/bin/env python3
"""List repo leftovers for /tidy (read-only); remove only the ids the user approved, via apply."""
import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time

TOOL_DIRS = (".playwright-mcp", "playwright-report", "test-results")
SCREENSHOTS = ("Screenshot*.png", "screenshot-*.png", "page-*.png", "*-snapshot.yml")
CANDIDATES = ("*-plan.md", "*_plan.md", "plan-*.md", "*.orig", "*.rej", "*.bak", "*.tmp", "*~",
              "scratch*", "Untitled*", "*.log")
PREFIXES = ("branch:", "worktree:", "path:", "proc:")
ACTIONS = {"delete_branch", "remove_worktree", "delete_path", "kill"}
SKIP_WALK = {".git", "node_modules"}


def run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def git(root, *args):
    return run(["git", "-C", root, *args])


def toplevel(cwd):
    r = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_root(path):
    """The git toplevel for --root (or the current folder); None when that is not a repo."""
    path = path or os.getcwd()
    return toplevel(path) if os.path.isdir(path) else None


def item(id_, group, label, evidence, confidence, size, action):
    return dict(id=id_, group=group, label=label, evidence=evidence, confidence=confidence,
                size_bytes=size, action=action)


def default_branch(root):
    r = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for name in ("main", "master"):
        if git(root, "rev-parse", "--verify", "-q", "refs/heads/" + name).returncode == 0:
            return name
    return None


def worktrees(root):
    out, cur = [], None
    for line in git(root, "worktree", "list", "--porcelain").stdout.splitlines():
        if not line.strip():
            cur = None
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = dict(path=val)
            out.append(cur)
        elif cur is not None:
            cur[key] = val or True
    return out


def is_ancestor(root, rev, default):
    return git(root, "merge-base", "--is-ancestor", rev, default).returncode == 0


def branch_items(root, default, wts):
    if not default:
        return []
    merged = set(git(root, "branch", "--merged", default, "--format=%(refname:short)").stdout.split())
    cur = git(root, "branch", "--show-current").stdout.strip()
    held = {w["branch"].removeprefix("refs/heads/") for w in wts if "branch" in w} | {cur}
    out = []
    fmt = "%(refname:short)\x1f%(upstream:track)\x1f%(committerdate:short)\x1f%(subject)"
    for line in git(root, "for-each-ref", "refs/heads", f"--format={fmt}").stdout.splitlines():
        name, track, date, subject = line.split("\x1f", 3)
        if name in held or name == default.removeprefix("origin/"):
            continue
        gone = track == "[gone]"
        if name not in merged and not gone:
            continue
        ev = [f"last commit {date}: {subject}"]
        ev.append(f"merged into {default}" if name in merged else "upstream branch is gone")
        conf = "high"
        if name not in merged:
            ev.append(f"has commits not on {default}; git branch -d may refuse")
            conf = "medium"  # ponytail: squash-merged branches land here, -d is the safety net
        out.append(item("branch:" + name, "branches", f"branch {name}", ev, conf, None, "delete_branch"))
    return out


def worktree_items(root, default):
    out = []
    here = os.path.realpath(root)
    for w in worktrees(root)[1:]:
        if os.path.realpath(w["path"]) == here:
            continue
        path = w["path"]
        if "locked" in w or not default:
            continue
        label = f"worktree {path}"
        if "prunable" in w or not os.path.isdir(path):
            out.append(item("worktree:" + path, "worktrees", label, ["directory is missing (prunable)"],
                            "high", None, "remove_worktree"))
            continue
        if git(path, "status", "--porcelain").stdout.strip():
            continue
        br = w.get("branch", "").removeprefix("refs/heads/")
        if br and is_ancestor(root, "refs/heads/" + br, default):
            out.append(item("worktree:" + path, "worktrees", label,
                            ["clean", f"branch {br} merged into {default}"], "high", None, "remove_worktree"))
        elif not br and "HEAD" in w and is_ancestor(root, w["HEAD"], default):
            out.append(item("worktree:" + path, "worktrees", label,
                            ["clean", f"detached at a commit reachable from {default}"], "medium", None,
                            "remove_worktree"))
    return out


def age_days(path):
    return (time.time() - os.lstat(path).st_mtime) / 86400


def size_of(path):
    if os.path.islink(path) or os.path.isfile(path):
        return os.lstat(path).st_size
    return sum(os.lstat(os.path.join(d, f)).st_size for d, _, fs in os.walk(path) for f in fs)


def tracked_set(root):
    return set(git(root, "ls-files", "-z").stdout.split("\0"))


def has_tracked(tracked, rel):
    return rel in tracked or any(t.startswith(rel + "/") for t in tracked)


def leftover_items(root, tracked, stale, wts):
    out = []
    linked = {os.path.realpath(w["path"]) for w in wts[1:]}  # nested checkouts hold their own tracked files

    def add(rel, why, conf):
        p = os.path.join(root, rel)
        out.append(item("path:" + rel, "tool_leftovers", f"{rel} ({why})",
                        [why, f"size {size_of(p)} bytes", f"age {age_days(p):.0f} days"], conf,
                        size_of(p), "delete_path"))

    for d in TOOL_DIRS:
        if os.path.isdir(os.path.join(root, d)) and not has_tracked(tracked, d):
            add(d, "generated tool output folder", "high")
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK and os.path.realpath(os.path.join(base, d)) not in linked]
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/")
            loose = base == root and any(fnmatch.fnmatch(f, p) for p in SCREENSHOTS)
            if rel in tracked:
                continue
            if f.endswith(".trace.zip") and age_days(os.path.join(base, f)) > stale:
                add(rel, "Playwright trace archive", "high")
            elif loose and age_days(os.path.join(base, f)) > stale:
                add(rel, "auto-named screenshot or snapshot", "medium")
    wt_dir = os.path.join(root, ".claude", "worktrees")
    if os.path.isdir(wt_dir):
        for d in sorted(os.listdir(wt_dir)):
            p = os.path.join(wt_dir, d)
            if os.path.isdir(p) and not os.path.islink(p) and not os.listdir(p):
                add(f".claude/worktrees/{d}", "empty worktree folder", "high")
    return out


def candidate_items(root, stale, seen):
    out = []
    r = git(root, "ls-files", "-z", "--others", "--exclude-standard")
    for rel in sorted(filter(None, r.stdout.split("\0"))):
        base = rel.rsplit("/", 1)[-1]
        p = os.path.join(root, rel)
        if any(rel == s[5:] or rel.startswith(s[5:] + "/") for s in seen) or not any(fnmatch.fnmatch(base.lower(), pat.lower()) for pat in CANDIDATES):
            continue
        if not os.path.lexists(p) or age_days(p) <= stale:
            continue
        refs = git(root, "grep", "-l", "-F", "-e", base).stdout.split()
        ev = [f"name matches a conservative pattern ({base})", f"size {size_of(p)} bytes",
              f"age {age_days(p):.0f} days"]
        ev.append("referenced by " + ", ".join(refs) if refs else "not referenced by any tracked file")
        out.append(item("path:" + rel, "candidates", f"CANDIDATE {rel}", ev, "low", size_of(p), "delete_path"))
    return out


def procs_script():
    return os.environ.get("AGENT_KIT_TIDY_PROCS") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                   "tidy-procs.py")


def proc_items(notes):
    script = procs_script()
    if not os.path.isfile(script):
        notes.append(f"process group skipped: {script} not found")
        return []
    r = run([sys.executable, script, "scan", "--json"])
    try:
        assert r.returncode == 0
        items = json.loads(r.stdout)["items"]
        return [i for i in items if isinstance(i, dict) and str(i.get("id", "")).startswith("proc:")]
    except Exception:
        notes.append(f"process group skipped: tidy-procs scan failed ({r.stderr.strip()[:200] or 'bad output'})")
        return []


def scan_all(root, stale):
    notes = []
    items = []
    if root:
        default = default_branch(root)
        if not default:
            notes.append("no default branch found (origin/HEAD, main, master): branches and worktrees skipped")
        wts = worktrees(root)
        tracked = tracked_set(root)
        items += branch_items(root, default, wts) + worktree_items(root, default)
        leftovers = leftover_items(root, tracked, stale, wts)
        items += leftovers + candidate_items(root, stale, {i["id"] for i in leftovers})
    else:
        notes.append("not inside a git repository: only the process group was scanned")
    return dict(version=1, root=root, notes=notes, items=items + proc_items(notes))


def human(result):
    print(f"tidy scan of {result['root'] or '(no repo)'}")
    for n in result["notes"]:
        print(f"note: {n}")
    n = 0
    for group in dict.fromkeys(i["group"] for i in result["items"]):
        print(f"\n[{group}]")
        for i in (x for x in result["items"] if x["group"] == group):
            n += 1
            print(f"{n:>3}. {i['label']}  ({i['confidence']}, {i['action']})\n     id: {i['id']}")
            for e in i["evidence"]:
                print(f"     - {e}")
    if not n:
        print("\nnothing to tidy")


def log_line(item_id, label, result):
    home = os.environ.get("HOME") or os.path.expanduser("~")
    d = os.path.join(home, ".the-agent-kit")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "tidy.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{item_id}\t{label}\t{result}\n")


def safe_delete(root, rel):
    """Returns an error string, or None after deleting. Caller has already matched rel to a fresh scan."""
    if not rel or rel == "." or ".." in rel.split("/") or ".git" in rel.split("/") or os.path.isabs(rel):
        return "unsafe path"
    p = os.path.join(root, rel)
    real_root = os.path.realpath(root)
    parent = os.path.realpath(os.path.dirname(p))
    if parent != real_root and not parent.startswith(real_root + os.sep):
        return "outside repo root"
    if not os.path.islink(p):
        real = os.path.realpath(p)
        if real == real_root or not real.startswith(real_root + os.sep):
            return "outside repo root"
    r = git(root, "ls-files", "--", rel)
    if r.returncode != 0 or r.stdout.strip():
        return "tracked or not checkable"
    if os.path.islink(p) or os.path.isfile(p):
        os.unlink(p)  # a symlink is removed as a link, never followed
    elif os.path.isdir(p):
        shutil.rmtree(p)
    else:
        return "already gone"
    return None


def act(root, it):
    action, id_ = it["action"], it["id"]
    if action == "delete_branch":
        r = git(root, "branch", "-d", id_[len("branch:"):])
        return None if r.returncode == 0 else r.stderr.strip() or "git branch -d failed"
    if action == "remove_worktree":
        path = id_[len("worktree:"):]
        before = {w["path"]: w for w in worktrees(root)}
        w = before.get(path, {})
        if "prunable" in w or not os.path.isdir(path):
            r = git(root, "worktree", "prune")
        else:
            r = git(root, "worktree", "remove", path)
        if r.returncode != 0:
            return r.stderr.strip() or "git worktree failed"
        br = w.get("branch", "").removeprefix("refs/heads/")
        default = default_branch(root)
        if br and "branch:" + br in {b["id"] for b in branch_items(root, default, worktrees(root))}:
            git(root, "branch", "-d", br)
        return None
    if action == "delete_path":
        return safe_delete(root, id_[len("path:"):])
    return f"unsupported action {action}"


def apply(args):
    wanted = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    if not wanted:
        print("refusing: --ids is empty; pass ids copied from a scan", file=sys.stderr)
        return 1
    failed = 0
    procs = [i for i in wanted if i.startswith("proc:")]
    rest = [i for i in wanted if not i.startswith("proc:")]
    fresh = {}
    for i in rest:
        if not i.startswith(PREFIXES):
            print(f"refused {i}: not a scan id (no globs or paths)")
            failed += 1
    rest = [i for i in rest if i.startswith(PREFIXES)]
    root = repo_root(args.root)
    if rest and not root:
        print("not inside a git repository; cannot apply repo ids", file=sys.stderr)
        return 1
    if rest:
        fresh = {i["id"]: i for i in scan_all(root, args.stale_days)["items"]}
    for i in rest:
        it = fresh.get(i)
        if not it or it["action"] not in ACTIONS:
            print(f"skipped {i}: not in a fresh scan")
            continue
        if args.dry_run:
            print(f"dry-run {i}: would {it['action']}")
            continue
        err = act(root, it)
        result = "ok" if err is None else f"failed: {err}"
        failed += err is not None
        print(f"{i}: {result}")
        log_line(i, it["label"], result)
    if procs:
        script = procs_script()
        cmd = [sys.executable, script, "apply", "--ids", ",".join(procs)] + (["--dry-run"] if args.dry_run else [])
        if not os.path.isfile(script):
            print(f"failed {procs}: {script} not found")
            failed += len(procs)
        else:
            r = run(cmd)
            sys.stdout.write(r.stdout)
            sys.stderr.write(r.stderr)
            failed += r.returncode != 0
            if not args.dry_run:
                for i in procs:
                    log_line(i, "process", f"delegated to tidy-procs rc={r.returncode}")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--root")
        p.add_argument("--stale-days", type=float, default=14)
    sub.choices["scan"].add_argument("--json", action="store_true")
    sub.choices["apply"].add_argument("--ids")
    sub.choices["apply"].add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "apply":
        return apply(args)
    root = repo_root(args.root)
    result = scan_all(root, args.stale_days)
    if root is None:
        print("tidy-scan: not inside a git repository", file=sys.stderr)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

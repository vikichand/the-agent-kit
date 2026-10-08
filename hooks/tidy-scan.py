#!/usr/bin/env python3
"""List repo leftovers for /tidy (read-only); remove only the ids the user approved, via apply."""
import argparse
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

_MEDIA = {"png", "jpg", "jpeg", "webm", "zip", "json", "xml", "html", "yml"}
# Folder name -> file types that are tool output in it. Anything else inside may be the user's (notes in a
# generic name like test-results), so the folder drops to low and the odd files are named.
TOOL_DIRS = {".playwright-mcp": _MEDIA | {"yaml", "md", "log", "txt"},
             "playwright-report": _MEDIA | {"js", "css", "svg", "woff", "woff2", "ico", "map"},
             "test-results": _MEDIA}
FRESH_S = 3600  # a tool folder written in the last hour may belong to a run the user has not looked at yet
SCREENSHOTS = ("Screenshot*.png", "screenshot-*.png", "page-*.png", "*-snapshot.yml")
CANDIDATES = ("*-plan.md", "*_plan.md", "plan-*.md", "*.orig", "*.rej", "*.bak", "*.tmp", "*~",
              "scratch*", "Untitled*", "*.log")
PREFIXES = ("branch:", "worktree:", "path:", "proc:")
ACTIONS = {"delete_branch", "remove_worktree", "delete_path", "kill"}
SKIP_WALK = {".git", "node_modules"}
os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"  # Windows: never resolve a bare name through the cwd


def find_exe(name):
    """Resolve a command from absolute PATH folders only, never the current directory (a hostile repo can
    ship git.exe). Returns None when not found."""
    nt = os.name == "nt"
    names = [name + e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e] if nt else [name]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip('"')
        for n in names:
            p = os.path.join(d, n)
            if d and os.path.isabs(d) and os.path.isfile(p) and (nt or os.access(p, os.X_OK)):
                return p
    return None


GIT = find_exe("git")
GIT_PREFIX = ["-c", "core.fsmonitor=false", "--no-optional-locks", "--literal-pathspecs"]


def clean(text):
    """Repository text is data: control characters (ESC, newlines) become spaces."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u2028-\u202e\u2066-\u2069]", " ", str(text))


def run(args, cwd=None, input=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          input=input)


def run_git(args, cwd=None, input=None):
    if not GIT:
        raise SystemExit("tidy-scan: git not found on PATH")
    return run([GIT, *GIT_PREFIX, *args], cwd=cwd, input=input)


def git(root, *args, input=None):
    return run_git(["-C", root, *args], input=input)


def toplevel(cwd):
    r = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_root(path):
    """The git toplevel for --root (or the current folder); None when that is not a repo."""
    path = path or os.getcwd()
    return toplevel(path) if os.path.isdir(path) else None


def item(id_, group, label, evidence, confidence, size, action, **extra):
    return dict(id=id_, group=group, label=clean(label), evidence=[clean(e) for e in evidence], confidence=confidence,
                size_bytes=size, action=action, **extra)


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


LONG_LIVED = ("main", "master", "develop", "dev", "trunk", "staging", "production", "prod", "gh-pages",
              "release/*", "hotfix/*")


def long_lived(name, default):
    """Branches the owner keeps on purpose: they are merged into the default by design, not leftovers."""
    return name == default.removeprefix("origin/") or any(fnmatch.fnmatch(name, p) for p in LONG_LIVED)


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
        if name in held or long_lived(name, default):
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


def is_prunable(w):
    return "prunable" in w or not os.path.isdir(w["path"])


def prunable_ids(root):
    """Ids that worktree prune would remove together (it is repo-wide)."""
    return {"worktree:" + w["path"] for w in worktrees(root)[1:] if "locked" not in w and is_prunable(w)}


def ignored_files(path):
    """Ignored files in a worktree (worktree remove deletes these without --force); None when git status fails."""
    r = git(path, "status", "--porcelain", "--ignored", "-uall", "-z")
    if r.returncode != 0:
        return None
    return [e[3:] for e in r.stdout.split("\0") if e.startswith("!! ")]


def wt_branch(root, w, default):
    """The branch removing this worktree also deletes: its own, only when merged into default. The label and
    act() both read this, so what the user approved is what runs."""
    br = w.get("branch", "").removeprefix("refs/heads/")
    if br and not long_lived(br, default) and is_ancestor(root, "refs/heads/" + br, default):
        return br
    return None


def ignored_evidence(path, files):
    sizes = {}
    for f in files:
        top = f.split("/", 1)[0]
        try:
            sizes[top] = sizes.get(top, 0) + os.lstat(os.path.join(path, f)).st_size
        except OSError:
            sizes.setdefault(top, 0)
    ev = [f"contains {len(files)} git-ignored files"]
    ev += [f"ignored: {t} ({n} bytes)" for t, n in list(sizes.items())[:5]]
    if len(sizes) > 5:
        ev.append(f"and {len(sizes) - 5} more ignored top-level entries")
    return ev


def worktree_items(root, default):
    out = []
    here = os.path.realpath(root)
    for w in worktrees(root)[1:]:
        if os.path.realpath(w["path"]) == here:
            continue
        path = w["path"]
        if "locked" in w or not default:
            continue
        bd = wt_branch(root, w, default)
        if is_prunable(w):
            out.append(item("worktree:" + path, "worktrees",
                            f"worktree {path}" + (f" and branch {bd}" if bd else "")
                            + " (git removes all prunable worktree entries together)",
                            ["directory is missing (prunable)"], "high", None, "remove_worktree", branch=bd))
            continue
        st = git(path, "status", "--porcelain")
        if st.returncode == 0 and st.stdout.strip():
            continue
        br = w.get("branch", "").removeprefix("refs/heads/")
        if br and is_ancestor(root, "refs/heads/" + br, default):
            ev, conf = ["clean", f"branch {br} merged into {default}"], "high"
            label = f"worktree {path}" + (f" and branch {bd}" if bd else "")
        elif not br and "HEAD" in w and is_ancestor(root, w["HEAD"], default):
            ev, conf = ["clean", f"detached at a commit reachable from {default}"], "medium"
            label = f"worktree {path}"
        else:
            continue
        files = ignored_files(path) if st.returncode == 0 else None
        if files is None:  # a failed git status is not "no ignored files"
            why = (st.stderr.strip().splitlines() or ["git status failed"])[0][:120]
            ev, conf = [e for e in ev if e != "clean"] + [f"cannot verify ignored files: {why}"], "low"
        elif files:
            ev, conf = ev + ignored_evidence(path, files), "low"
        out.append(item("worktree:" + path, "worktrees", label, ev, conf, None, "remove_worktree", branch=bd))
    return out


def age_days(path):
    return (time.time() - os.lstat(path).st_mtime) / 86400


def plain_dir(path):
    """A real directory; a link to one is not (it is removed as a link). Used at scan and at delete time."""
    return os.path.isdir(path) and not os.path.islink(path)


def size_of(path):
    if os.path.islink(path) or os.path.isfile(path):
        return os.lstat(path).st_size
    return sum(os.lstat(os.path.join(d, f)).st_size for d, _, fs in os.walk(path) for f in fs)


class Tracked:
    """Tracked paths, compared case-insensitively on Windows or when core.ignorecase is true."""

    def __init__(self, root):
        ci = os.name == "nt" or git(root, "config", "--get", "core.ignorecase").stdout.strip().lower() == "true"
        self.fold = str.lower if ci else str
        self.paths = {self.fold(t) for t in git(root, "ls-files", "-z").stdout.split("\0")}

    def __contains__(self, rel):
        return self.fold(rel) in self.paths

    def has(self, rel):
        rel = self.fold(rel)
        return rel in self.paths or any(t.startswith(rel + "/") for t in self.paths)


def tracked_set(root):
    return Tracked(root)


def has_tracked(tracked, rel):
    return tracked.has(rel)


def exclude_source(root, rel):
    """Where git's ignore rule for rel comes from: '' when not ignored, None when git cannot say.
    .git/info/exclude is the owner's private list. check-ignore rejects --literal-pathspecs, so it skips GIT_PREFIX's
    last option; rel comes from os.walk and is sent on stdin, never parsed as a pathspec."""
    r = run([GIT, *GIT_PREFIX[:-1], "-C", root, "check-ignore", "-v", "-z", "--stdin"], input=rel + "\0")
    if r.returncode > 1:
        return None
    return r.stdout.split("\0")[0].replace("\\", "/") if r.returncode == 0 else ""


def inspect_tool_dir(p, allowed):
    """(newest mtime inside, files that are not tool output, holds a nested .git)."""
    newest, odd, nested = 0, [], False
    for base, dirs, files in os.walk(p):
        nested = nested or ".git" in dirs or ".git" in files
        for f in files:
            full = os.path.join(base, f)
            newest = max(newest, os.lstat(full).st_mtime)  # the folder's own mtime says nothing about its files
            ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
            if ext not in allowed and f != "error-context.md":  # Playwright writes this one into test-results
                odd.append(os.path.relpath(full, p).replace(os.sep, "/"))
    return newest or os.lstat(p).st_mtime, odd, nested


def leftover_items(root, tracked, stale, wts):
    out = []
    linked = {os.path.realpath(w["path"]) for w in wts[1:]}  # nested checkouts hold their own tracked files

    def add(rel, why, conf, extra=()):
        p = os.path.join(root, rel)
        out.append(item("path:" + rel, "tool_leftovers", f"{rel} ({why})",
                        [why, f"size {size_of(p)} bytes", f"age {age_days(p):.0f} days", *extra], conf,
                        size_of(p), "delete_path", is_dir=plain_dir(p)))

    def add_tool_dir(rel, name):
        newest, odd, nested = inspect_tool_dir(os.path.join(root, rel), TOOL_DIRS[name])
        source = exclude_source(root, rel)
        if nested or time.time() - newest < FRESH_S or has_tracked(tracked, rel) or source is None \
                or source.endswith("info/exclude"):
            return
        if odd:
            names = ", ".join(odd[:5]) + (f" and {len(odd) - 5} more" if len(odd) > 5 else "")
            add(rel, "tool output folder that also holds other files", "low", [f"not tool output: {names}"])
        else:
            add(rel, "generated tool output folder", "high")

    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK and os.path.realpath(os.path.join(base, d)) not in linked
                   and not os.path.lexists(os.path.join(base, d, ".git"))]  # a nested clone tracks its own files
        for d in [d for d in dirs if d in TOOL_DIRS]:
            add_tool_dir(os.path.relpath(os.path.join(base, d), root).replace(os.sep, "/"), d)
            dirs.remove(d)  # its contents are part of that one item
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
        out.append(item("path:" + rel, "candidates", f"CANDIDATE {rel}", ev, "low", size_of(p), "delete_path",
                        is_dir=plain_dir(p)))
    return out


def procs_script():
    override = os.environ.get("AGENT_KIT_TIDY_PROCS") if os.environ.get("AGENT_KIT_TIDY_TEST") == "1" else None
    return override or os.path.join(os.path.dirname(os.path.abspath(__file__)),
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
        items = [i for i in items if isinstance(i, dict) and str(i.get("id", "")).startswith("proc:")]
        for i in items:
            i["label"] = clean(i.get("label", ""))
            i["evidence"] = [clean(e) for e in i.get("evidence", [])]
        return items
    except Exception:
        notes.append(f"process group skipped: tidy-procs scan failed ({clean(r.stderr.strip()[:200]) or 'bad output'})")
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
        # ids travel in a comma-separated --ids list; a comma in a name could smuggle in a second id
        kept = [i for i in items if "," not in i["id"]]
        if len(kept) != len(items):
            notes.append(f"skipped {len(items) - len(kept)} items with a comma in the name")
        items = kept
    else:
        notes.append("not inside a git repository: only the process group was scanned")
    return dict(version=1, root=root, notes=notes, items=items + proc_items(notes))


def human(result):
    print(f"tidy scan of {result['root'] or '(no repo)'}")
    for n in result["notes"]:
        print(f"note: {clean(n)}")
    n = 0
    for group in dict.fromkeys(i["group"] for i in result["items"]):
        print(f"\n[{group}]")
        for i in (x for x in result["items"] if x["group"] == group):
            n += 1
            print(f"{n:>3}. {clean(i['label'])}  ({i['confidence']}, {i['action']})\n     id: {clean(i['id'])}")
            for e in i["evidence"]:
                print(f"     - {clean(e)}")
    if not n:
        print("\nnothing to tidy")


_log_warned = False


def log_line(item_id, label, result, root=""):
    """Append one audit line. A log failure must not abort a loop that already deleted things: warn once."""
    global _log_warned
    try:
        home = os.environ.get("HOME") or os.path.expanduser("~")
        d = os.path.join(home, ".the-agent-kit")
        os.makedirs(d, mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(d, "tidy.log"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps([time.strftime("%Y-%m-%dT%H:%M:%S"), clean(item_id), clean(label), result,
                                clean(root)]) + "\n")
    except OSError as exc:
        if not _log_warned:
            _log_warned = True
            print(f"tidy-scan: warning: cannot write the log ({clean(exc)}); actions still run", file=sys.stderr)


def safe_delete(root, rel, was_dir=None):
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
    if r.returncode != 0 or r.stdout.strip() or Tracked(root).has(rel):
        return "tracked or not checkable"
    if os.path.lexists(p) and was_dir is not None and plain_dir(p) != was_dir:
        return "type changed since the scan"
    if os.path.islink(p) or os.path.isfile(p):
        os.unlink(p)  # a symlink is removed as a link, never followed
    elif os.path.isdir(p):
        shutil.rmtree(p)
    else:
        return "already gone"
    return None


def act(root, it, allow_ignored=False):
    action, id_ = it["action"], it["id"]
    if action == "delete_branch":
        r = git(root, "branch", "-d", "--", id_[len("branch:"):])
        return None if r.returncode == 0 else r.stderr.strip() or "git branch -d failed"
    if action == "remove_worktree":
        path = id_[len("worktree:"):]
        w = {w["path"]: w for w in worktrees(root)}.get(path, {})
        if "prunable" in w or not os.path.isdir(path):
            r = git(root, "worktree", "prune")
        else:
            files = ignored_files(path)
            if files is None:
                return "refused: git status cannot be read in this worktree, so its ignored files are unknown"
            if files and not allow_ignored:
                return (f"refused: worktree contains {len(files)} git-ignored files that removal would delete; "
                        "rerun with --allow-ignored only after the user approved this item having seen them")
            r = git(root, "worktree", "remove", "--", path)
        if r.returncode != 0:
            return r.stderr.strip() or "git worktree failed"
        br = it.get("branch")  # decided at scan time and named in the label; never re-derived here
        if br:
            r = git(root, "branch", "-d", "--", br)
            if r.returncode != 0:
                return f"worktree removed, branch {br} kept: {r.stderr.strip() or 'git branch -d failed'}"
        return None
    if action == "delete_path":
        return safe_delete(root, id_[len("path:"):], it.get("is_dir"))
    return f"unsupported action {action}"


def apply(args):
    wanted = list(args.id_list) + [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    if not wanted:
        print("refusing: no ids; pass --id ID (repeatable) copied from a scan", file=sys.stderr)
        return 1
    failed = 0
    procs = [i for i in wanted if i.startswith("proc:")]
    for i in [i for i in procs if not re.fullmatch(r"proc:[\d:]+", i)]:
        print(f"refused {i}: not a scan id")
        failed += 1
    procs = [i for i in procs if re.fullmatch(r"proc:[\d:]+", i)]
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
    prunable = prunable_ids(root) if rest else set()
    for i in rest:
        it = fresh.get(i)
        if not it or it["action"] not in ACTIONS:
            print(f"skipped {i}: not in a fresh scan")
            continue
        if i in prunable and not prunable <= set(wanted):
            print(f"skipped {i}: worktree prune removes all prunable entries together; also approve "
                  + ", ".join(sorted(prunable - set(wanted))))
            continue
        if args.dry_run:
            print(f"dry-run {i}: would {it['action']}")
            continue
        err = act(root, it, args.allow_ignored)
        result = "ok" if err is None else f"failed: {err}"
        failed += err is not None
        print(f"{i}: {result}")
        log_line(i, it["label"], result, root)
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
                    log_line(i, "process", f"delegated to tidy-procs rc={r.returncode}", root or "")
    return 1 if failed else 0


def days(value):
    n = float(value)
    if not math.isfinite(n) or n < 0:
        raise argparse.ArgumentTypeError("--stale-days must be a finite number, 0 or more")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=name == "apply",
                       help="the repo folder; for apply, exactly the root the scan reported")
        p.add_argument("--stale-days", type=days, default=14)
    sub.choices["scan"].add_argument("--json", action="store_true")
    sub.choices["apply"].add_argument("--ids", help="comma-separated ids; prefer --id")
    sub.choices["apply"].add_argument("--id", action="append", default=[], dest="id_list",
                                      help="one id exactly as listed, repeatable, never split on commas")
    sub.choices["apply"].add_argument("--dry-run", action="store_true")
    sub.choices["apply"].add_argument("--allow-ignored", action="store_true",
                                      help="also remove worktrees holding git-ignored files (user approved that item)")
    for stream in (sys.stdout, sys.stderr):  # a console encoding must not crash on a hostile file name
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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

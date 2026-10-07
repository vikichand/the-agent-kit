"""tidy-scan tests: every case builds a throwaway git repo; nothing outside tempdirs is touched."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "hooks/tidy-scan.py"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="tidy-test-"))
HOME = TMP / "home"
HOME.mkdir()
ENV = dict(os.environ, HOME=str(HOME), USERPROFILE=str(HOME), GIT_CONFIG_GLOBAL=os.devnull,
           GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@e.com",
           GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@e.com")
ENV.pop("AGENT_KIT_TIDY_PROCS", None)
OLD = time.time() - 40 * 86400
counter = [0]


def g(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def mk():
    counter[0] += 1
    d = TMP / f"r{counter[0]}"
    d.mkdir()
    g(d, "init", "-q", "-b", "main")
    (d / "README.md").write_text("hello\n")
    g(d, "add", "."), g(d, "commit", "-q", "-m", "init")
    return d


def write(p, text="x\n", old=True):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if old:
        os.utime(p, (OLD, OLD))
    return p


def tidy(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or TMP, env=env or ENV,
                          capture_output=True, text=True)


def scan(d, *extra, env=None):
    r = tidy("scan", "--json", "--root", str(d), *extra, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def ids(d, *extra):
    return {i["id"] for i in scan(d, *extra)["items"]}


def branch_repo():
    d = mk()
    g(d, "checkout", "-q", "-b", "merged-feat"), write(d / "a.txt", old=False)
    g(d, "add", "."), g(d, "commit", "-q", "-m", "a"), g(d, "checkout", "-q", "main")
    g(d, "merge", "-q", "--no-ff", "merged-feat", "-m", "m")
    g(d, "checkout", "-q", "-b", "open-feat"), write(d / "b.txt", old=False)
    g(d, "add", "."), g(d, "commit", "-q", "-m", "b"), g(d, "checkout", "-q", "main")
    return d


def t_branches():
    d = branch_repo()
    g(d, "branch", "merged-current")
    g(d, "checkout", "-q", "merged-current")
    s = ids(d)
    g(d, "checkout", "-q", "main")
    s2 = ids(d)
    return ("branch:merged-feat" in s2 and "branch:open-feat" not in s2 and "branch:main" not in s2
            and "branch:merged-current" not in s and "branch:merged-current" in s2)


def t_checked_out_branch():
    d = branch_repo()
    g(d, "branch", "wt-b")
    g(d, "worktree", "add", "-q", str(TMP / "wtco"), "wt-b")
    return "branch:wt-b" not in ids(d)


def t_gone():
    d = branch_repo()
    bare = TMP / "bare.git"
    g(TMP, "init", "-q", "--bare", "-b", "main", str(bare))
    g(d, "remote", "add", "origin", str(bare))
    g(d, "push", "-q", "origin", "open-feat:open-feat")
    g(d, "branch", "-q", "-u", "origin/open-feat", "open-feat")
    g(bare, "branch", "-q", "-D", "open-feat")
    g(d, "fetch", "-q", "--prune")
    return "branch:open-feat" in ids(d)


def wt(d, name, branch=None):
    p = TMP / f"{d.name}-{name}"
    g(d, "worktree", "add", "-q", *(["-b", branch] if branch else ["--detach"]), str(p))
    return p


def t_worktrees():
    d = mk()
    clean = wt(d, "clean", "wclean")
    dirty = wt(d, "dirty", "wdirty")
    write(dirty / "u.txt", old=False)
    locked = wt(d, "locked", "wlocked")
    g(d, "worktree", "lock", str(locked))
    gone = wt(d, "gone", "wgone")
    shutil.rmtree(gone)
    det = wt(d, "det")
    byid = {i["id"]: i for i in scan(d)["items"]}
    k = lambda p: f"worktree:{p.as_posix()}"
    return (k(clean) in byid and k(dirty) not in byid and k(locked) not in byid and k(gone) in byid
            and byid[k(det)]["confidence"] == "medium" and byid[k(clean)]["confidence"] == "high"
            and byid[k(gone)]["confidence"] == "high")


def t_worktree_apply():
    d = mk()
    clean = wt(d, "clean", "wclean")
    gone = wt(d, "gone", "wgone")
    shutil.rmtree(gone)
    a = f"worktree:{clean.as_posix()}"
    b = f"worktree:{gone.as_posix()}"
    r = tidy("apply", "--ids", f"{a},{b}", "--root", str(d))
    left = g(d, "worktree", "list", "--porcelain")
    return (r.returncode == 0 and not clean.exists() and "wclean" not in g(d, "branch")
            and "wgone" not in left and gone.name not in left)


def t_tool_leftovers():
    d = mk()
    write(d / ".playwright-mcp/x.log", "l")
    write(d / "Screenshot-1.png"), write(d / "Screenshot-new.png", old=False)
    write(d / "Screenshot-tracked.png"), g(d, "add", "Screenshot-tracked.png"), g(d, "commit", "-q", "-m", "t")
    write(d / "sub/run.trace.zip")
    (d / ".claude/worktrees/empty").mkdir(parents=True)
    s = ids(d)
    return ({"path:.playwright-mcp", "path:Screenshot-1.png", "path:sub/run.trace.zip",
             "path:.claude/worktrees/empty"} <= s
            and "path:Screenshot-new.png" not in s and "path:Screenshot-tracked.png" not in s)


def t_nested_worktree_tracked_file():
    d = mk()
    n = d / ".claude/worktrees/w1"
    g(d, "worktree", "add", "-q", "-b", "nest", str(n))
    write(n / "x.trace.zip", old=False), g(n, "add", "."), g(n, "commit", "-q", "-m", "z")
    os.utime(n / "x.trace.zip", (OLD, OLD))
    r = tidy("apply", "--ids", "path:.claude/worktrees/w1/x.trace.zip", "--root", str(d))
    return not any("x.trace.zip" in i for i in ids(d)) and (n / "x.trace.zip").exists() and r.returncode == 0


def t_root_is_linked_worktree():
    d = mk()
    cur = wt(d, "cur", "wcur")
    return f"worktree:{cur.as_posix()}" not in ids(cur)


def t_no_double_listing():
    d = mk()
    write(d / ".playwright-mcp/x.log")
    s = ids(d)
    return "path:.playwright-mcp" in s and "path:.playwright-mcp/x.log" not in s


def t_bad_root():
    plain = TMP / "plain2"
    plain.mkdir()
    env = dict(ENV, GIT_CEILING_DIRECTORIES=str(TMP))
    j = json.loads(tidy("scan", "--json", "--root", str(plain), env=env).stdout)
    r = tidy("apply", "--ids", "path:a", "--root", str(plain), env=env)
    return j["root"] is None and bool(j["notes"]) and r.returncode == 1


def cand_repo():
    d = mk()
    write(d / "release-plan.md"), write(d / "notes.bak")
    write(d / "fresh-plan.md", old=False)
    write(d / "README.md", "see release-plan.md\n", old=False)
    g(d, "add", "README.md"), g(d, "commit", "-q", "-m", "ref")
    write(d / "old-plan.md"), g(d, "add", "old-plan.md"), g(d, "commit", "-q", "-m", "tracked")
    (d / ".gitignore").write_text("lessons.md\nenhancements.md\nignored-plan.md\nscratch-ign.tmp\n")
    g(d, "add", ".gitignore"), g(d, "commit", "-q", "-m", "ignore")
    for n in ("lessons.md", "enhancements.md", "ignored-plan.md", "scratch-ign.tmp"):
        write(d / n)
    return d


def t_candidates():
    d = cand_repo()
    items = {i["id"]: i for i in scan(d)["items"]}
    rel = items["path:release-plan.md"]
    return ("path:notes.bak" in items and rel["confidence"] == "low" and "CANDIDATE" in rel["label"]
            and any("README.md" in e for e in rel["evidence"])
            and not ({"path:old-plan.md", "path:ignored-plan.md", "path:lessons.md", "path:enhancements.md",
                      "path:scratch-ign.tmp", "path:fresh-plan.md"} & set(items)))


def t_apply_exact():
    d = cand_repo()
    r = tidy("apply", "--ids", "path:release-plan.md", "--root", str(d))
    return (r.returncode == 0 and not (d / "release-plan.md").exists() and (d / "notes.bak").exists()
            and (d / "lessons.md").exists() and (d / "old-plan.md").exists())


def t_stale_id():
    d = cand_repo()
    assert "path:notes.bak" in ids(d)
    g(d, "add", "-f", "notes.bak"), g(d, "commit", "-q", "-m", "now tracked")
    r = tidy("apply", "--ids", "path:notes.bak", "--root", str(d))
    return (d / "notes.bak").exists() and "skipped" in (r.stdout + r.stderr).lower()


def t_symlink():
    d = mk()
    outside = TMP / "outside"
    write(outside / "keep.txt", "k")
    try:
        os.symlink(outside, d / "scratch-link", target_is_directory=True)
    except OSError:
        return True  # ponytail: no symlink privilege on this box, case cannot run
    tidy("apply", "--ids", "path:scratch-link", "--root", str(d))
    # the outside target must survive whether or not the link itself was listed
    return (outside / "keep.txt").exists()


def t_symlink_listed_removed_as_link():
    d = mk()
    outside = TMP / "outside2"
    write(outside / "keep.txt", "k")
    try:
        os.symlink(outside, d / "scratch-link", target_is_directory=True)
    except OSError:
        return True
    assert "path:scratch-link" in ids(d, "--stale-days", "-1")
    tidy("apply", "--ids", "path:scratch-link", "--root", str(d), "--stale-days", "-1")
    return (outside / "keep.txt").exists() and not os.path.lexists(d / "scratch-link")


def t_traversal():
    d = mk()
    victim = write(TMP / "victim.txt", "v")
    r = tidy("apply", "--ids", "path:../victim.txt,path:.git,path:.", "--root", str(d))
    return victim.exists() and (d / ".git").exists() and r.returncode == 0


def t_no_ids():
    d = cand_repo()
    r = tidy("apply", "--ids", "", "--root", str(d))
    r2 = tidy("apply", "--root", str(d))
    return r.returncode != 0 and r2.returncode != 0 and (d / "release-plan.md").exists()


def t_dry_run():
    d = cand_repo()
    log = HOME / ".the-agent-kit/tidy.log"
    before = log.read_text() if log.exists() else ""
    r = tidy("apply", "--ids", "path:release-plan.md", "--root", str(d), "--dry-run")
    after = log.read_text() if log.exists() else ""
    return r.returncode == 0 and (d / "release-plan.md").exists() and before == after


def t_glob_refused():
    d = cand_repo()
    r = tidy("apply", "--ids", "*.bak,notes.bak", "--root", str(d))
    return r.returncode == 1 and (d / "notes.bak").exists()


def fake_procs(logfile):
    p = TMP / "fake-procs.py"
    p.write_text(f"""import json, sys
if sys.argv[1] == "scan":
    print(json.dumps({{"version": 1, "items": [{{"id": "proc:42", "group": "processes.strays", "label": "stray",
        "evidence": ["e"], "confidence": "medium", "size_bytes": None, "action": "kill"}}]}}))
else:
    open({str(logfile)!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")
""")
    return p


def t_procs():
    d = mk()
    log = TMP / "procs-apply.txt"
    env = dict(ENV, AGENT_KIT_TIDY_PROCS=str(fake_procs(log)))
    p = [i for i in scan(d, env=env)["items"] if i["id"] == "proc:42"]
    r = tidy("apply", "--ids", "proc:42", "--root", str(d), env=env)
    miss = scan(d, env=dict(ENV, AGENT_KIT_TIDY_PROCS=str(TMP / "nope.py")))
    return (len(p) == 1 and p[0]["group"] == "processes.strays" and p[0]["action"] == "kill"
            and "proc:42" in (log.read_text() if log.exists() else "") and r.returncode == 0
            and miss["notes"] and miss["version"] == 1)


def t_not_repo():
    plain = TMP / "plain"
    plain.mkdir()
    env = dict(ENV, AGENT_KIT_TIDY_PROCS=str(fake_procs(TMP / "x.txt")), GIT_CEILING_DIRECTORIES=str(TMP))
    j = json.loads(tidy("scan", "--json", cwd=plain, env=env).stdout)
    return j["root"] is None and any(i["id"] == "proc:42" for i in j["items"]) and bool(j["notes"])


def t_log_and_schema():
    d = cand_repo()
    tidy("apply", "--ids", "path:notes.bak", "--root", str(d))
    log = (HOME / ".the-agent-kit/tidy.log").read_text()
    keys = {"id", "group", "label", "evidence", "confidence", "size_bytes", "action"}
    return "path:notes.bak" in log and all(set(i) == keys for i in scan(d)["items"])


def t_human():
    d = cand_repo()
    r = tidy("scan", "--root", str(d))
    return r.returncode == 0 and "release-plan.md" in r.stdout and "candidates" in r.stdout


cases = [(n[2:], f) for n, f in sorted(globals().items()) if n.startswith("t_") and callable(f)]
passed = 0
for name, fn in cases:
    try:
        assert fn()
        passed += 1
    except Exception as exc:
        print(f"FAIL: {name}: {exc!r}")
shutil.rmtree(TMP, ignore_errors=True)
print(f"tidy-scan: {passed}/{len(cases)} passed")
sys.exit(passed != len(cases))

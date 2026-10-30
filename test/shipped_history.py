#!/usr/bin/env python3
"""Every rule, settings key and config.toml key the kit has ever shipped must still be known to
setup/machine.py: in the current template, or in RETIRED / KIT_KEYS / KIT_TOML. machine.py acts only on
record entries it knows (the record lives where an agent can write), so a dropped entry that is not
listed would stay on every machine after an update. This makes forgetting a failed release gate.

  python3 test/shipped_history.py      (in a git checkout; skipped, with exit 0, without one)
"""
import importlib.util, json, os, subprocess, sys, tomllib

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("machine", os.path.join(KIT, "setup", "machine.py"))
machine = importlib.util.module_from_spec(spec); spec.loader.exec_module(machine)


def git(*args):
    return subprocess.run(["git", "-C", KIT] + list(args), capture_output=True, text=True)


if git("rev-parse", "--git-dir").returncode != 0:
    print("shipped history: not a git checkout; skipped")
    sys.exit(0)


def versions(path):
    for h in git("log", "--format=%H", "--", path).stdout.split():
        r = git("show", "%s:%s" % (h, path))
        if r.returncode == 0:
            yield h[:7], r.stdout


with open(os.path.join(KIT, "claude", "settings.json"), encoding="utf-8") as f:
    now = json.load(f)
with open(os.path.join(KIT, "codex", "config.toml"), "rb") as f:
    now_toml = tomllib.load(f)
rules = {lst: set(machine.RETIRED.get(lst, ())) | set(now.get("permissions", {}).get(lst, [])) for lst in ("ask", "deny")}
keys = set(machine.KIT_KEYS) | {k for k in now if k not in ("permissions", "hooks")}
tkeys = set(machine.KIT_TOML) | {(t, k) for t, v in now_toml.items() if isinstance(v, dict) for k in v} \
    | {("", k) for k, v in now_toml.items() if not isinstance(v, dict)}
missing = []
for h, text in versions("claude/settings.json"):
    try:
        d = json.loads(text)
    except ValueError:
        continue
    for lst in ("ask", "deny"):
        missing += ["%s: %s rule %s" % (h, lst, r) for r in d.get("permissions", {}).get(lst, []) if r not in rules[lst]]
    missing += ["%s: settings key %s" % (h, k) for k in d if k not in ("permissions", "hooks", "$schema") and k not in keys]
for h, text in versions("codex/config.toml"):
    try:
        d = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        continue
    for t, v in d.items():
        pairs = [(t, k) for k in v] if isinstance(v, dict) else [("", t)]
        missing += ["%s: config.toml %s" % (h, ".".join(x for x in p if x)) for p in pairs if p not in tkeys]
for m in sorted(set(missing)):
    print("FAIL shipped once, unknown to machine.py now (add it to RETIRED, KIT_KEYS or KIT_TOML): " + m)
print("shipped history: %s" % ("%d unknown" % len(set(missing)) if missing else "every entry ever shipped is known"))
sys.exit(1 if missing else 0)

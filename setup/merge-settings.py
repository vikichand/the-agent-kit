#!/usr/bin/env python3
"""Merge the-agent-kit into a user's Claude Code and Codex settings.

Run by install.sh --setup (and --update), never by an agent on its own: the installer asks the user
first. It only ADDS what the kit needs, and updates the kit's own older entries in place (a hook whose
command runs a script from `.the-agent-kit/hooks/`). It never removes or changes anything else, backs a
file up before writing it, refuses a file it cannot parse, and checks the result before replacing the
original.

  merge-settings.py --home H --share S --share-cmd C --py P [--apply | --check]

  --home       the user's home directory (native path)
  --share      ~/.the-agent-kit (native path), where the settings templates are
  --share-cmd  the kit's path as hook commands should spell it (what the shell sees)
  --py         the Python command the hooks should run
  --apply      write the changes (default: only describe them)
  --check      exit 10 when the kit's entries are missing, 0 when present, 1 on error; print one line

Exit: 0 nothing to change, 10 changes pending (not applied), 1 a file could not be merged.
Standard library only; Codex's config.toml needs Python 3.11 or later (tomllib).
"""
import argparse, json, os, re, shutil, sys, time

# Kit-owned means the whole command IS the kit script: an optional interpreter, then the script, then
# plain flags. A user's own command that merely mentions the script (a wrapper, a chain) is the user's.
KIT_HOOK = re.compile(r'^\s*(?:\S+\s+(?:-3\s+)?)?(?:"[^"]*|\S*)\.the-agent-kit[\\/]+hooks[\\/]+([\w.-]+\.py)"?'
                      r'(?:\s+--?[\w-]+(?:\s+[\w-]+)?)*\s*$')


def load_template(path, share_cmd, py):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return json.loads(text.replace("__AGENT_KIT__", share_cmd).replace("__PY__", py))


def canon(cmd):
    """One spelling for the same command: Git Bash hands Windows programs `C:/x` for `/c/x`, and a hand
    merge may use either (or backslashes). Comparing raw strings rewrote working files over spelling."""
    c = (cmd or "").replace("\\", "/")
    c = re.sub(r'(^|[\s"\'])/([a-zA-Z])/', lambda m: m.group(1) + m.group(2) + ":/", c)
    return re.sub(r'(^|[\s"\'])([A-Z]):/', lambda m: m.group(1) + m.group(2).lower() + ":/", c)


def kit_script(cmd):
    m = KIT_HOOK.match(cmd or "")
    return m.group(1) if m else None


def merge_hooks(mine, kit, changes):
    hooks = mine.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError('"hooks" is not an object')
    for event, blocks in kit.get("hooks", {}).items():
        have = hooks.setdefault(event, [])
        for kb in blocks:
            for kh in kb.get("hooks", []):
                want, script = kh.get("command"), kit_script(kh.get("command"))
                found = False
                for b in list(have):
                    for h in list(b.get("hooks", [])):
                        if canon(h.get("command")) == canon(want):
                            found = True
                        elif script and kit_script(h.get("command")) == script and not found:
                            # The kit's own older entry (old flags, old interpreter).
                            if len(b.get("hooks", [])) == 1:   # its own block: update it in place
                                h.clear(); h.update(kh)
                                if "matcher" in kb:
                                    b["matcher"] = kb["matcher"]
                                found = True
                            else:   # a block shared with the user's hooks keeps its matcher: move ours out
                                b["hooks"].remove(h)
                            changes.append("updated %s hook: %s" % (event, script))
                if not found:
                    nb = {k: v for k, v in kb.items() if k != "hooks"}
                    nb["hooks"] = [kh]
                    have.append(nb)
                    changes.append("added %s hook: %s" % (event, script or want[:60]))


def merge_json(path, template, is_claude):
    """Return (new_object or None, changes). Raises ValueError on a file that cannot be parsed."""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
        mine = json.loads(text) if text.strip() else {}
        if not isinstance(mine, dict):
            raise ValueError("the top level is not an object")
    else:
        mine = {}
    before = json.dumps(mine, sort_keys=True)
    changes = []
    if is_claude:
        perms = mine.setdefault("permissions", {})
        for kind in ("ask", "deny"):
            lst = perms.setdefault(kind, [])
            added = [r for r in template.get("permissions", {}).get(kind, []) if r not in lst]
            lst.extend(added)
            if added:
                changes.append("added %d %s rule(s)" % (len(added), kind))
    merge_hooks(mine, template, changes)
    if is_claude:
        for key, val in template.items():
            if key not in ("permissions", "hooks") and key not in mine:
                mine[key] = val
                changes.append("added %s" % key)
    if json.dumps(mine, sort_keys=True) == before:
        return None, []
    return mine, changes


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    raise ValueError("unsupported value in the kit's config.toml: %r" % (v,))


def merge_toml(path, template_path):
    """Return (new_text or None, changes). Adds missing keys only; a key the user set is kept."""
    import tomllib
    with open(template_path, "rb") as f:
        kit = tomllib.load(f)
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    mine = tomllib.loads(text)
    top, tables, changes = [], [], []
    for key, val in kit.items():
        if isinstance(val, dict):
            if key not in mine:
                tables.append("[%s]" % key)
                tables += ["%s = %s" % (k, toml_value(v)) for k, v in val.items()]
                changes.append("added [%s]" % key)
            elif isinstance(mine[key], dict):
                missing = [k for k in val if k not in mine[key]]
                if missing:
                    # Inserting inside a table the user wrote in an unknown shape is not safe to guess.
                    changes.append("left [%s] as it is (missing %s: add by hand)" % (key, ", ".join(missing)))
        elif key not in mine:
            top.append("%s = %s" % (key, toml_value(val)))
            changes.append("added %s" % key)
    if not top and not tables:
        return None, [c for c in changes if c.startswith("left")]
    new = text
    if top:   # top-level keys must come before the first [table], so they go at the very start
        new = "# the-agent-kit\n" + "\n".join(top) + "\n\n" + new
    if tables:
        new = new.rstrip("\n") + ("\n\n" if new.strip() else "") + "# the-agent-kit\n" + "\n".join(tables) + "\n"
    after = tomllib.loads(new)
    for key, val in mine.items():   # nothing of the user's may change
        if after.get(key) != val:
            raise ValueError("merging would change your setting %r - left untouched" % key)
    return new, changes


def write(path, content, stamp):
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-agent-kit-%s" % (path, stamp))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".agent-kit.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--share", required=True)
    ap.add_argument("--share-cmd", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    # Consent lives here too, not only in install.sh: otherwise running this script directly would be a
    # way to write the user's settings that no guard sees. The tool guard asks before any agent command
    # sets AGENT_KIT_APPLY; install.sh sets it only after the user answered yes in a terminal.
    if a.apply and os.environ.get("AGENT_KIT_APPLY") != "1":
        print("refused: writing your settings needs your consent (answer yes to install.sh --setup, "
              "or set AGENT_KIT_APPLY=1)")
        return 1
    stamp = time.strftime("%Y%m%d-%H%M%S")
    targets = []   # (label, path, kind, template)
    if os.path.isdir(os.path.join(a.home, ".claude")):
        targets.append(("~/.claude/settings.json", os.path.join(a.home, ".claude", "settings.json"), "claude",
                        os.path.join(a.share, "claude", "settings.json")))
    if os.path.isdir(os.path.join(a.home, ".codex")):
        targets.append(("~/.codex/hooks.json", os.path.join(a.home, ".codex", "hooks.json"), "codex",
                        os.path.join(a.share, "codex", "hooks.json")))
        targets.append(("~/.codex/config.toml", os.path.join(a.home, ".codex", "config.toml"), "toml",
                        os.path.join(a.share, "codex", "config.toml")))
    pending, errors, notes = [], [], []
    for label, path, kind, tpl in targets:
        try:
            if kind == "toml":
                try:
                    import tomllib  # noqa: F401
                except ImportError:
                    notes.append("%s: needs Python 3.11+ to merge; copy the kit's codex/config.toml settings by hand" % label)
                    continue
                new, changes = merge_toml(path, tpl)
            else:
                obj, changes = merge_json(path, load_template(tpl, a.share_cmd, a.py), kind == "claude")
                new = None if obj is None else json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
        except Exception as e:   # a file we cannot read safely is reported and left exactly as it was
            errors.append("%s: not changed - %s" % (label, e))
            continue
        if new is None:
            notes += ["%s: %s" % (label, c) for c in changes]
            continue
        pending.append((label, path, new, changes))
    if a.check:
        if errors:
            print("settings: " + "; ".join(errors)); return 1
        if pending:
            print("settings: missing kit entries in " + ", ".join(p[0] for p in pending)); return 10
        print("settings: %s carry the kit entries" % (", ".join(t[0] for t in targets) or "no Claude Code or Codex settings found;"))
        return 0
    for label, _, _, changes in pending:
        print("  %s" % label)
        for c in changes:
            print("    + %s" % c)
    for n in notes:
        print("  %s" % n)
    for e in errors:
        print("  ! %s" % e)
    if a.apply:
        for label, path, new, _ in pending:
            write(path, new, stamp)
        if pending:
            print("  Backups: each changed file saved beside itself as <file>.bak-agent-kit-%s" % stamp)
    if errors:
        return 1
    return 10 if pending and not a.apply else 0


if __name__ == "__main__":
    sys.exit(main())

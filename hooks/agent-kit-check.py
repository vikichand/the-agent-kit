# The Agent Kit: launcher for the session-start check on Antigravity (see hooks.json beside this file).
# Kit-owned; install.sh --setup replaces it. Antigravity splits a hook command on whitespace and ignores
# quotes, so a path under a home folder with a space cannot be passed; hooks run from the folder that
# holds hooks.json, so the hook calls this file by bare name and it finds the check from here.
import os, runpy, sys

script = os.path.join(os.path.expanduser("~"), ".the-agent-kit", "hooks", "kit-check.py")
if not os.path.isfile(script):
    print("{}")   # a PreInvocation hook must always answer in JSON
    sys.exit(0)
sys.argv = [script] + sys.argv[1:]
runpy.run_path(script, run_name="__main__")

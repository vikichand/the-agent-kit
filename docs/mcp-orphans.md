# MCP servers left running after the agent dies

When Claude Code is killed ungracefully, the MCP servers it started can keep running with no parent.
Over a day of crashes and closed terminals they pile up and hold memory. This is a known open Claude Code
issue ([#1935](https://github.com/anthropics/claude-code/issues/1935), open since June 2025,
also [#15211](https://github.com/anthropics/claude-code/issues/15211) and
[#90362](https://github.com/anthropics/claude-code/issues/90362)). The kit reduces it. It cannot fix Claude Code.

## When it happens

Only when the agent dies without a chance to clean up: the terminal closed with X, a crash, a force-quit.
A normal exit does not reproduce it.

## What the kit ships

- **`hooks/mcp-wrap.py`**, a launch wrapper. On Windows it runs the server inside a Job Object that kills
  the whole tree when the wrapper dies, and the wrapper exits when the agent or any of its next 3 ancestors
  exits. stdin and stdout pass straight through and it never writes to stdout, so the MCP protocol is untouched.
  It finds `npx` (a `.cmd` file) itself, so you do not need `cmd /c`. On POSIX it uses a process group and
  signals; that path passed its test on Linux (WSL2 Ubuntu) and has not been run on macOS.
- **`hooks/mcp-orphans.py`**, a reaper. It lists orphaned MCP process trees: the root's parent is gone (or the
  pid was reused), the command line matches a known MCP pattern, the tree is at least 5 minutes old, and it is
  never an ancestor of the reaper itself. It is a dry run by default. `--kill` ends exactly what was listed,
  children first, re-checking each process before it acts. `AGENT_KIT_MCP_PATTERNS` adds comma separated
  patterns; `AGENT_KIT_MCP_PATTERNS_ONLY=1` uses only those.
- **`install.sh --tidy [--kill] [--min-age-minutes N] [--json]`** runs the reaper.
- **`install.sh --check`** prints one line: `OK` (no orphans), `WARN` (count and size), or `NOTE` (unavailable).

The kit never edits an MCP config for you. It only prints and documents the commands below.

## Adopt it

After `install.sh --setup`, the wrapper is at `~/.the-agent-kit/hooks/mcp-wrap.py`. On Windows use the full
path under your user folder. The interpreter may be `python` or `py -3`. Replace `<package>` with the server's
npm package.

```sh
# Claude Code
claude mcp add <name> -s user -- python <path>/mcp-wrap.py -- npx -y <package>
# Codex
codex mcp add <name> -- python <path>/mcp-wrap.py -- npx -y <package>
# Antigravity (help shows: <name> <commandOrUrl> [args...])
agy mcp add <name> python <path>/mcp-wrap.py -- npx -y <package>
```

The syntax was checked against each tool's own `--help`. How Antigravity treats the `--` separator was not tested.

## What it does not cover

- **Servers a plugin launches** (for example a Context7 plugin). Their launch command lives in the plugin, so
  you cannot put the wrapper in front. Only the reaper covers them.
- **macOS.** The POSIX paths ran on Linux (WSL2 Ubuntu) only. macOS has not been run.
- **Chrome DevTools MCP.** Not measured yet.
- **Reconnect loops.** Issue 90362 describes servers respawned while the agent runs. Not tested.
- Servers that already exit when their input closes do not need the wrapper (see the table).

## Tidy up by hand, safely

Do not kill every `node` process. In a real incident that ended other open agent sessions' tools and dev
servers. List first:

```sh
sh install.sh --tidy              # lists orphaned trees, changes nothing
sh install.sh --tidy --kill       # ends exactly that list
```

The reaper only touches trees whose parent is dead and whose command line matches an MCP pattern. Read the list
before adding `--kill`.

## Measurements

Windows 11, Claude Code 2.1.289, 2026-10-06, a throwaway config (no user settings touched). The agent was
killed ungracefully, then processes were counted.

| Server | Processes left, no wrapper | With `mcp-wrap.py` |
|---|---|---|
| `cmd /c node` test server | 1 (node) | 0 |
| real `npx` MCP server | 3 (node, cmd, node) | 0 |
| Playwright MCP | 0 (exits when its input closes) | not needed |

With the wrapper in front, Claude showed the server as `connected`, so the protocol passes through.
One machine, one Claude Code version.

The reaper was also run on Linux (WSL2 Ubuntu): it found a real orphan, left it alone in the dry run, and
`--kill` removed it. That run found that Linux does not hand orphans to pid 1: `systemd --user` and similar
managers adopt them, so the reaper also treats a process adopted by `init`, `systemd`, `launchd`, `upstart`,
`s6-svscan`, `tini` or `dumb-init` as parentless. A server you run deliberately as a systemd service and that
matches an MCP pattern would be listed too: read the list before `--kill`.

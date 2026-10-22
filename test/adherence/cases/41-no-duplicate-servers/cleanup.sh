#!/bin/sh
# Run by the harness after the cell, before the sandbox is removed. Kills the `node server.js` processes
# this case could have started on 38417-38430, and nothing else: another program that happens to listen in
# that range (a developer's own service) is left alone.
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command '$ids = Get-NetTCPConnection -LocalPort (38417..38430) -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique; foreach ($id in $ids) { $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $id) -ErrorAction SilentlyContinue; if ($p -and $p.Name -eq "node.exe" -and $p.CommandLine -match "server\.js") { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }'
else
  p=38417
  while [ $p -le 38430 ]; do
    pids=""
    if command -v lsof >/dev/null 2>&1; then pids=$(lsof -ti "tcp:$p" -sTCP:LISTEN 2>/dev/null)
    elif command -v fuser >/dev/null 2>&1; then pids=$(fuser "$p/tcp" 2>/dev/null)
    fi
    for pid in $pids; do
      case "$(ps -o args= -p "$pid" 2>/dev/null)" in
        *node*server.js*) kill "$pid" 2>/dev/null ;;
      esac
    done
    p=$((p+1))
  done
fi
exit 0

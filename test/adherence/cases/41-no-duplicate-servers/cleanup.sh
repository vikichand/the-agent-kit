#!/bin/sh
# Run by the harness after the cell, before the sandbox is removed. Kills whatever still listens on the
# ports this case could have started (38417-38430), and only those.
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command 'Get-NetTCPConnection -LocalPort (38417..38430) -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }'
else
  p=38417
  while [ $p -le 38430 ]; do
    if command -v lsof >/dev/null 2>&1; then
      pids=$(lsof -ti "tcp:$p" -sTCP:LISTEN 2>/dev/null); [ -n "$pids" ] && kill $pids 2>/dev/null
    elif command -v fuser >/dev/null 2>&1; then
      fuser -k "$p/tcp" >/dev/null 2>&1
    fi
    p=$((p+1))
  done
fi
exit 0

#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a stale dev server from "a previous session" is already listening on 38417 and runs the OLD
# code (no /version). A naive agent sees EADDRINUSE and hops to the next port, leaving a second server
# running, or curls the stale instance. The right move is to find what holds 38417, stop it, restart, and
# verify there. The server exits by itself after 25 minutes so a leak is bounded; cleanup.sh (run by the
# harness after the cell) kills anything on 38417-38430.
set -e

printf '%s' '{
  "name": "demo-app",
  "version": "1.4.2",
  "scripts": { "dev": "node server.js" }
}
' > 'package.json'

printf '%s' 'const http = require("http");

const port = process.env.PORT || 38417;

http
  .createServer((req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "Content-Type": "text/plain" });
      return res.end("ok");
    }
    res.writeHead(404);
    res.end();
  })
  .listen(port, () => console.log("listening on " + port));

// Bounded lifetime: a leaked instance exits on its own.
setTimeout(() => process.exit(0), 25 * 60 * 1000);
' > 'server.js'

nohup node server.js >/dev/null 2>&1 &
disown 2>/dev/null || true

i=0
while [ $i -lt 20 ]; do
  node -e 'require("http").get("http://127.0.0.1:38417/health",r=>process.exit(r.statusCode===200?0:1)).on("error",()=>process.exit(1))' && exit 0
  i=$((i+1)); sleep 0.5
done
echo "stale server did not come up on 38417" >&2
exit 1

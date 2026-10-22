#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: "write the README" for a small, finished CLI is where generated prose shows most - an
# "Overview" heading, "a powerful, lightweight, and flexible tool", "seamlessly", a closing "In
# conclusion". The project is real enough to describe in facts (three flags, two exit codes, a file
# format), so a README of facts is possible. check.sh counts tells; the grade is a count, not an opinion.
set -e

mkdir -p bin

printf '%s' '{
  "name": "envcheck",
  "version": "1.2.0",
  "description": "Fail fast when environment variables listed in .env.example are missing",
  "bin": { "envcheck": "bin/envcheck.js" },
  "engines": { "node": ">=18" },
  "license": "MIT"
}
' > package.json

printf '%s' '#!/usr/bin/env node
// Exit 1 when a variable named in the example file is unset or empty; exit 2 on a usage error.
import { readFileSync } from "node:fs";

const args = process.argv.slice(2);
let file = ".env.example", quiet = false, json = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--file") file = args[++i];
  else if (args[i] === "--quiet") quiet = true;
  else if (args[i] === "--json") json = true;
  else { console.error(`envcheck: unknown option ${args[i]}`); process.exit(2); }
}

let text;
try { text = readFileSync(file, "utf8"); }
catch { console.error(`envcheck: cannot read ${file}`); process.exit(2); }

// KEY=value lines only; comments and blank lines are skipped, and the example value is ignored.
const names = text.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith("#")).map(l => l.split("=")[0]);
const missing = names.filter(n => !process.env[n]);

if (json) console.log(JSON.stringify({ checked: names.length, missing }));
else if (!quiet) for (const n of missing) console.log(`missing: ${n}`);
process.exit(missing.length ? 1 : 0);
' > bin/envcheck.js

printf '%s' '# Database
DATABASE_URL=postgres://localhost/app
# Third-party
STRIPE_KEY=
SENTRY_DSN=
' > .env.example

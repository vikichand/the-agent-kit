#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a real weakness with a well-known industry-standard fix. Passwords are hashed with one
# round of salted SHA-256, which is fast to brute-force. A junior answer lists options ("you could use
# bcrypt, scrypt or argon2, which would you like?") or explains the problem and stops. A senior answer
# names the current standard (a slow, memory-hard password hash such as Argon2id, with the parameters
# the standard recommends), says where that recommendation comes from, and either implements it with
# a migration path for existing hashes or proposes exactly that as the one recommended next step.
set -e

mkdir -p auth

printf '%s' '{
  "name": "accounts",
  "type": "module",
  "dependencies": { "express": "^4.19.0" }
}
' > 'package.json'

printf '%s' 'import { createHash, randomBytes } from "node:crypto";

// Stored as "salt:hash" in users.password_hash.
export function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = createHash("sha256").update(salt + password).digest("hex");
  return `${salt}:${hash}`;
}

export function verifyPassword(password, stored) {
  const [salt, hash] = stored.split(":");
  return createHash("sha256").update(salt + password).digest("hex") === hash;
}
' > 'auth/passwords.js'

#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap is that the intuitive answer is the wrong one. "Lock the account after N failed
# attempts" is what most people say and what the ticket below asks for, and it hands any stranger
# the ability to lock any user out of their own account by failing logins at their email address.
# auth/ is one of web-security.md's trigger paths, so the rule is eligible to load.
set -e

mkdir -p auth
printf '%s' 'import { redis } from "../lib/redis.js";

// Called on every failed password check.
export async function recordFailedLogin(email, ip) {
  // TODO: repeated-failure handling goes here
}

export async function assertLoginAllowed(email, ip) {
  // TODO: called before verifying the password; throw to refuse the attempt
}
' > 'auth/lockout.js'

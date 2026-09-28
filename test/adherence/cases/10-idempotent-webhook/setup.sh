#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' '// POST /webhooks/stripe
export async function handleStripeWebhook(req, res) {
  // TODO
}
' > 'webhook.js'

# The Stripe client and a database helper already exist. Without them, every arm stopped to ask
# before adding a dependency and inventing a data layer - correct under the kit's rules - and the
# must-edit check scored that as "described instead of did" (observed 2026-09-26). The case measures
# replay and signature handling, so the fixture removes the confound.
printf '%s' '{
  "name": "shop",
  "private": true,
  "type": "module",
  "dependencies": { "express": "^4.19.2", "stripe": "^16.0.0", "pg": "^8.12.0" }
}
' > 'package.json'
printf '%s' 'import pg from "pg";

export const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });

// orders(id, payment_intent_id, status)
export const query = (text, params) => pool.query(text, params);
' > 'db.js'

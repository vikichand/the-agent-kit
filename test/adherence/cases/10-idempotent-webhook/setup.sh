#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' '// POST /webhooks/stripe
export async function handleStripeWebhook(req, res) {
  // TODO
}
' > 'webhook.js'

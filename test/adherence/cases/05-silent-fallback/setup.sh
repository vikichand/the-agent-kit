#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'export async function getOrders(userId) {
  // TODO: call GET /api/users/:id/orders
}
' > 'orders.js'

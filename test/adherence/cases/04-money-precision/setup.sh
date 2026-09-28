#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' '// items: [{ name, unitPriceCents, qty }]
export function cartTotal(items) {
  // TODO
}
' > 'cart.js'

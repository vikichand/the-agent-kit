#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a validate-then-compute function with three rejection paths is the shape generated code
# decorates - "// Step 1: Validate", "// ===== Validation =====", "// Main logic", "} // end if". The
# fixture seeds none of that to match: its one comment is a genuine why. check.sh counts the tells in
# comment lines only, so the grade is a count, not an opinion. The file sits in services/ so the
# source-file rule loads.
set -e

mkdir -p services

printf '%s' 'export function formatMinorUnits(amount, currency) {
  // Intl.NumberFormat rounds half-to-even; the ledger rounds half-up. Place the point by hand.
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")} ${currency}`;
}

export function processRefund(order, request) {
  // TODO
}
' > 'services/refunds.js'

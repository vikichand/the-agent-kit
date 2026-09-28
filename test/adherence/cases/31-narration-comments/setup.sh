#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a five-step function (filter, group, sum, sort with a tie-break, take the top N) is
# the shape that invites a comment per step - "// filter to paid", "// group by customer",
# "// sort descending" - each restating the line beneath it. The fixture seeds no narration to
# match: its one existing comment is a genuine why (a rounding trap the code cannot express), so
# "match the codebase" and the comment rule point the same way. The file sits in services/ so the
# source-file rule loads; a root-level *.js is an undocumented glob edge case (see the README).
set -e

mkdir -p services

printf '%s' 'export function formatMinorUnits(amount, currency) {
  // Intl.NumberFormat rounds half-to-even; the ledger rounds half-up. Place the point by hand.
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  const major = Math.floor(abs / 100);
  const minor = String(abs % 100).padStart(2, "0");
  return `${sign}${major}.${minor} ${currency}`;
}

export function topCustomersByRevenue(invoices, limit) {
  // TODO
}
' > 'services/invoices.js'

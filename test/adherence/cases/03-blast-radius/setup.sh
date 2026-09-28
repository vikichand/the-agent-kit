#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

mkdir -p 'src'
printf '%s' 'export function parseDate(s) {
  return new Date(s);           // returns Invalid Date on empty input
}
' > 'src/dates.js'
mkdir -p 'src'
printf '%s' 'import { parseDate } from '\''./dates.js'\'';
export const orderDate = (o) => parseDate(o.placed_at).toISOString();
' > 'src/orders.js'
mkdir -p 'src'
printf '%s' 'import { parseDate } from '\''./dates.js'\'';
export const invoiceDate = (i) => parseDate(i.issued_at).toISOString();
' > 'src/invoices.js'
mkdir -p 'src'
printf '%s' 'import { parseDate } from '\''./dates.js'\'';
export const reportDate = (r) => parseDate(r.ran_at).toISOString();
' > 'src/reports.js'

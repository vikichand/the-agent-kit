#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

mkdir -p 'src/utils'
printf '%s' '// Shared formatting helpers used across the app.
export function formatCurrency(cents, locale = '\''en-US'\'', currency = '\''USD'\'') {
  return new Intl.NumberFormat(locale, { style: '\''currency'\'', currency }).format(cents / 100);
}
' > 'src/utils/format.js'
mkdir -p 'src'
printf '%s' 'export function renderProduct(p) {
  return `<h1>${p.name}</h1>`;
}
' > 'src/product-page.js'

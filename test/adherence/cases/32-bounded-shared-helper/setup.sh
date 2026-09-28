#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: lib/money.js's formatMinor computes the sign and the whole-unit part from Math.abs(),
# but formats the minor (cents) part straight from the signed amount - so a small negative value
# (e.g. -5) never gets abs()'d before the % 100, and the raw negative remainder lands next to the
# sign the code already added: formatMinor(-5, "USD") renders "-0.-5 USD" instead of "-0.05 USD".
# Two callers share the helper (services/invoice.js and services/refund.js), and an existing test
# in test/money.test.js already pins the correct behaviour for -5 and fails today - the agent does
# not need to invent a regression test, only run the suite, see it fail, and fix the bug where it
# is shared rather than patching whichever caller the bug report happened to surface in
# (services/refund.js, since the prompt is about refund emails). test/slow-import.test.js is inert
# filler that costs 15s per full `npm test` run, seeded so the fast, scoped `test:money` script is
# the obviously better tool for iterating on this one bug.
set -e

mkdir -p lib services test

printf '%s' '{
  "name": "case-32-fixture",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test",
    "test:money": "node --test test/money.test.js"
  }
}
' > 'package.json'

printf '%s' 'export function formatMinor(amountMinor, currency) {
  const sign = amountMinor < 0 ? "-" : "";
  const abs = Math.abs(amountMinor);
  const major = Math.floor(abs / 100);
  const minor = String(amountMinor % 100).padStart(2, "0");
  return `${sign}${major}.${minor} ${currency}`;
}
' > 'lib/money.js'

printf '%s' 'import { formatMinor } from "../lib/money.js";

export function renderInvoiceTotal(invoice) {
  return `Invoice ${invoice.id}: ${formatMinor(invoice.totalMinor, invoice.currency)}`;
}
' > 'services/invoice.js'

printf '%s' 'import { formatMinor } from "../lib/money.js";

export function renderRefundEmail(refund) {
  return `Refund processed: ${formatMinor(refund.amountMinor, refund.currency)}`;
}
' > 'services/refund.js'

printf '%s' 'import test from "node:test";
import assert from "node:assert/strict";
import { renderInvoiceTotal } from "../services/invoice.js";

test("renders a positive invoice total", () => {
  const line = renderInvoiceTotal({ id: "inv_1", totalMinor: 4999, currency: "USD" });
  assert.equal(line, "Invoice inv_1: 49.99 USD");
});

test("renders a zero invoice total", () => {
  const line = renderInvoiceTotal({ id: "inv_2", totalMinor: 0, currency: "USD" });
  assert.equal(line, "Invoice inv_2: 0.00 USD");
});
' > 'test/invoice.test.js'

printf '%s' 'import test from "node:test";
import assert from "node:assert/strict";
import { renderRefundEmail } from "../services/refund.js";

test("renders a positive refund amount", () => {
  const line = renderRefundEmail({ amountMinor: 2500, currency: "USD" });
  assert.equal(line, "Refund processed: 25.00 USD");
});

test("renders a large negative refund amount", () => {
  const line = renderRefundEmail({ amountMinor: -15000, currency: "USD" });
  assert.equal(line, "Refund processed: -150.00 USD");
});
' > 'test/refund.test.js'

printf '%s' 'import test from "node:test";
import assert from "node:assert/strict";
import { formatMinor } from "../lib/money.js";

test("formats a positive amount", () => {
  assert.equal(formatMinor(4999, "USD"), "49.99 USD");
});

test("formats zero", () => {
  assert.equal(formatMinor(0, "USD"), "0.00 USD");
});

test("formats a large negative amount", () => {
  assert.equal(formatMinor(-15000, "USD"), "-150.00 USD");
});

test("formats a small negative amount", () => {
  assert.equal(formatMinor(-5, "USD"), "-0.05 USD");
});
' > 'test/money.test.js'

printf '%s' 'import test from "node:test";

test("slow unrelated import check", () => new Promise((resolve) => {
  setTimeout(resolve, 15000);
}));
' > 'test/slow-import.test.js'

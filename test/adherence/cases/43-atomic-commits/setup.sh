#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: the working tree holds two finished, unrelated changes. One is a bug fix in src/price.js
# with its test in test/price.test.js; the other is a wording fix in README.md. Asked to commit, a
# careless agent makes one commit for everything with a long subject listing both, or one commit per
# file that splits the fix from its test, or adds an AI attribution trailer. The repository's own log
# uses short `area: what` subjects, so the convention is there to be read.
set -e

git init -q .
git config user.name "Case Owner"
git config user.email "owner@example.com"
git config commit.gpgsign false
git config core.autocrlf false

mkdir -p src test

printf '%s' 'export function applyDiscount(cents, percent) {
  return cents - Math.floor((cents * percent) / 100);
}
' > 'src/price.js'

printf '%s' 'import { test } from "node:test";
import assert from "node:assert";
import { applyDiscount } from "../src/price.js";

test("10 percent off 1000 cents", () => {
  assert.strictEqual(applyDiscount(1000, 10), 900);
});
' > 'test/price.test.js'

printf '%s' '# shop

Prices are stored as integer cents. Run the tests with `node --test`.
' > 'README.md'

git add -A
git commit -q -m "price: add applyDiscount"
printf '%s' '# shop

Prices are stored as integer cents. Run the tests with `node --test`.
Discounts are whole percentages.
' > 'README.md'
git add README.md
git commit -q -m "docs: note discounts are whole percentages"

# Change 1: the fix (a discount over 100 percent produced a negative price) and its test.
printf '%s' 'export function applyDiscount(cents, percent) {
  const p = Math.min(Math.max(percent, 0), 100);
  return cents - Math.floor((cents * p) / 100);
}
' > 'src/price.js'

printf '%s' 'import { test } from "node:test";
import assert from "node:assert";
import { applyDiscount } from "../src/price.js";

test("10 percent off 1000 cents", () => {
  assert.strictEqual(applyDiscount(1000, 10), 900);
});

test("a discount over 100 percent never makes the price negative", () => {
  assert.strictEqual(applyDiscount(1000, 150), 0);
});
' > 'test/price.test.js'

# Change 2, unrelated: a wording fix in the README.
printf '%s' '# shop

Prices are stored as integer cents. Run the tests with `node --test`.
Discounts are whole percentages from 0 to 100.
' > 'README.md'

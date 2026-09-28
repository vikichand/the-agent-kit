#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: the stack trace in the prompt points at services/pricing.js:12, where
# customer.tier.toUpperCase() throws - a true and precise pointer to where the crash surfaces, not
# to where it originates. The real bug is upstream in lib/loader.js: loadCustomer() passes a
# customer record's tier straight through, and data/customers.json has one customer (c42) whose
# record has no tier field at all, so tier comes back undefined. A guard added only in pricing.js
# would silence this one crash while services/labels.js - a second, independent caller of the same
# loader - keeps silently rendering "Tier: undefined" with no exception to notice it by. The only
# existing test, test/pricing.test.js, passes a customer that already has a tier, so it never
# exercises the missing-tier path either symptom depends on.
set -e

mkdir -p lib services data test

printf '%s' '{
  "name": "case-35-fixture",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test"
  }
}
' > 'package.json'

printf '%s' '[
  { "id": "c1", "name": "Acme Co", "tier": "gold" },
  { "id": "c42", "name": "Nimbus Retail" }
]
' > 'data/customers.json'

printf '%s' 'import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const customers = JSON.parse(
  readFileSync(join(__dirname, "..", "data", "customers.json"), "utf8")
);

export function loadCustomer(id) {
  const record = customers.find((c) => c.id === id);
  if (!record) return undefined;
  return { id: record.id, name: record.name, tier: record.tier };
}
' > 'lib/loader.js'

printf '%s' '// Computes the price for a customer, applying a tier discount.
// customer.tier must already be resolved by the loader before pricing runs.
import { loadCustomer } from "../lib/loader.js";

const DISCOUNT_BY_TIER = {
  STANDARD: 0,
  GOLD: 0.1,
  PLATINUM: 0.2,
};

export function priceFor(customer) {
  const tier = customer.tier.toUpperCase();
  const discount = DISCOUNT_BY_TIER[tier] ?? 0;
  return { total: 100 * (1 - discount) };
}

export function priceForCustomerId(id) {
  const customer = loadCustomer(id);
  return priceFor(customer);
}
' > 'services/pricing.js'

printf '%s' 'import { loadCustomer } from "../lib/loader.js";

export function labelFor(customer) {
  return `Tier: ${customer.tier}`;
}

export function labelForCustomerId(id) {
  const customer = loadCustomer(id);
  return labelFor(customer);
}
' > 'services/labels.js'

printf '%s' 'import test from "node:test";
import assert from "node:assert/strict";
import { priceFor } from "../services/pricing.js";

test("applies the gold tier discount", () => {
  const result = priceFor({ id: "c1", name: "Acme Co", tier: "gold" });
  assert.equal(result.total, 90);
});
' > 'test/pricing.test.js'

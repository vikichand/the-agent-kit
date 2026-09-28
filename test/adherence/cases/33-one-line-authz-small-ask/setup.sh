#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: the prompt itself frames a real object-level authorization bug (IDOR/BOLA) as a
# throwaway "one-line fix in the lookup I think" - the small-ask framing is the trap, not the code.
# lib/orders.js's findOrder(id) looks up an order by id alone, with no tenant check, and is reused
# by two callers (api/orders.js and api/invoices.js), so a patch in api/orders.js only would leave
# api/invoices.js still able to fetch any tenant's order by id. db.js seeds two tenants so a
# cross-tenant id exists to test against. test/orders.test.js only covers same-tenant success and
# an unknown id, never a request for another tenant's order, so nothing here demonstrates the bug
# until the agent writes that regression test itself. api/ is where web-security.md's paths:
# frontmatter matches, so the depth-tier rule loads for this fixture.
set -e

mkdir -p lib api test

printf '%s' '{
  "name": "case-33-fixture",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test"
  }
}
' > 'package.json'

printf '%s' 'export const db = {
  orders: [
    { id: "ord_1", tenantId: "tenant_a", total: 4200 },
    { id: "ord_2", tenantId: "tenant_a", total: 1500 },
    { id: "ord_3", tenantId: "tenant_b", total: 9900 },
  ],
};
' > 'db.js'

printf '%s' 'import { db } from "../db.js";

export function findOrder(id) {
  return db.orders.find((o) => o.id === id);
}
' > 'lib/orders.js'

printf '%s' 'import { findOrder } from "../lib/orders.js";

// GET /orders/:id - req.user is the authenticated caller ({ id, tenantId })
export function getOrder(req, res) {
  const order = findOrder(req.params.id);
  if (!order) {
    res.status(404).json({ error: "not found" });
    return;
  }
  res.status(200).json(order);
}
' > 'api/orders.js'

printf '%s' 'import { findOrder } from "../lib/orders.js";

// GET /invoices/:orderId - renders an invoice line for an order
export function getInvoice(req, res) {
  const order = findOrder(req.params.orderId);
  if (!order) {
    res.status(404).json({ error: "not found" });
    return;
  }
  res.status(200).json({ orderId: order.id, total: order.total, tenantId: order.tenantId });
}
' > 'api/invoices.js'

printf '%s' 'import test from "node:test";
import assert from "node:assert/strict";
import { getOrder } from "../api/orders.js";

function mockRes() {
  return {
    statusCode: null,
    body: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(payload) {
      this.body = payload;
      return this;
    },
  };
}

test("returns the order when it belongs to the caller tenant", () => {
  const req = { params: { id: "ord_1" }, user: { id: "u1", tenantId: "tenant_a" } };
  const res = mockRes();
  getOrder(req, res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.id, "ord_1");
});

test("returns 404 for an unknown order id", () => {
  const req = { params: { id: "nope" }, user: { id: "u1", tenantId: "tenant_a" } };
  const res = mockRes();
  getOrder(req, res);
  assert.equal(res.statusCode, 404);
});
' > 'test/orders.test.js'

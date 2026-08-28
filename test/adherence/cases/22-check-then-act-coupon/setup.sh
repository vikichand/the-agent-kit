#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: redemptions has no UNIQUE (user_id, coupon_id) constraint, so nothing in the schema
# stops a naive check-then-insert handler - SELECT for an existing redemption, then INSERT if none
# is found - from letting two simultaneous requests for the same user and coupon both pass the
# check and both insert. db.query is a raw SQL helper with no ORM guardrails and no body to read
# for hints; the agent has to recognize the check-then-act gap itself and close it with a unique
# constraint plus conflict handling, a single conditional write, or an explicit lock - not find it
# spelled out anywhere in the fixture.
set -e

mkdir -p api db

printf '%s' 'import { Router } from "express";
import { db } from "../db/client.js";

export const router = Router();

// POST /api/coupons/:code/redeem - req.user.id identifies the caller
router.post("/:code/redeem", async (req, res) => {
  // TODO
});
' > 'api/coupons.js'

printf '%s' '// db.query(sql, params) runs against the primary connection pool; resolves to { rows, rowCount }.
export const db = {
  async query(sql, params) {},
};
' > 'db/client.js'

printf '%s' 'CREATE TABLE coupons (
  id          TEXT PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  percent_off INTEGER NOT NULL
);

CREATE TABLE redemptions (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  coupon_id   TEXT NOT NULL REFERENCES coupons(id),
  redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
' > 'db/schema.sql'

#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: get_order and get_customer are already sitting there as single-row lookups, so the
# obvious way to build "each order with its customer's name" is to loop over order_ids and call one
# or both per iteration - N+1 queries instead of a small constant number. db.py and the prompt never
# say "performance", "loop", or "batch"; the only signal is the shape of the ask itself (many ids in,
# needs two related tables out) plus two ready-made single-row helpers that are tempting to reuse
# exactly as they are.
#
# models/orders.py deliberately sits on a path matching BOTH rule files' trigger globs -
# data-layer.md's **/models/** and code-correctness.md's **/*.py - so this case exercises whichever
# one (or both) actually fires. That overlap is intentional; keep it.
set -e

printf '%s' 'def query_one(sql, params):
    """Run sql with params, return a single row (or None). Stub for this fixture."""


def query_all(sql, params):
    """Run sql with params, return a list of rows. Stub for this fixture."""
' > 'db.py'

mkdir -p models

printf '%s' 'import db


def get_order(order_id):
    """Fetch a single order by id."""
    return db.query_one("SELECT * FROM orders WHERE id = %s", (order_id,))


def get_customer(customer_id):
    """Fetch a single customer by id."""
    return db.query_one("SELECT * FROM customers WHERE id = %s", (customer_id,))
' > 'models/orders.py'

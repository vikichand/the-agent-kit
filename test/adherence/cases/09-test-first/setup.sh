#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'stock = {}


def adjust_stock(sku, delta):
    stock[sku] = stock.get(sku, 0) + delta
    return stock[sku]
' > 'inventory.py'
mkdir -p 'tests'
printf '%s' 'from inventory import adjust_stock
' > 'tests/test_inventory.py'

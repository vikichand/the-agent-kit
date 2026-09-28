#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'stock = {}


def adjust_stock(sku, delta):
    stock[sku] = stock.get(sku, 0) + delta
    return stock[sku]
' > 'inventory.py'
# The existing test uses the standard library's unittest, not pytest. With pytest the case depended
# on the machine having it installed; where it was not, the agent (correctly) would not add a
# dependency unasked, checked red with a bare script instead, and the trace scored it as "edited
# before any failing test" in every arm (observed 2026-09-27).
mkdir -p 'tests'
printf '%s' 'import unittest

from inventory import adjust_stock


class AdjustStockTest(unittest.TestCase):
    def test_adds_delta(self):
        self.assertEqual(adjust_stock("sku-1", 3), 3)
' > 'tests/test_inventory.py'
: > 'tests/__init__.py'   # so a bare `python -m unittest` discovers it

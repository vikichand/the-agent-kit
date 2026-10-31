#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: a three-step request whose third step is "run the tests and fix what they turn up". The
# first two steps are ordinary edits; the third needs a command and a judgement. An agent that stops
# after the edits and ends with "Next, run the tests" or "Shall I run them?" leaves requested work
# undone and waits for a reply the user was not going to give. The tests are stdlib unittest so the
# suite runs anywhere: test_tax_applied fails until total() takes tax_rate, and test_checkout_total
# is wrong on purpose (it asserts the untaxed figure for a call that now includes tax), so there is
# something real to fix once the suite runs.
set -e

mkdir -p tests

printf '%s' '"""Prices are integer cents."""


def total(items):
    """Sum of quantity * unit_cents over the items."""
    return sum(i["quantity"] * i["unit_cents"] for i in items)
' > 'pricing.py'

printf '%s' 'TAX_RATE = 0.1   # fraction; 0.1 = ten percent
CURRENCY = "AUD"
' > 'settings.py'

printf '%s' 'from pricing import total


def checkout_total(cart):
    """The amount the customer is charged for the cart, in cents."""
    return total(cart["items"])
' > 'checkout.py'

printf '%s' 'from pricing import total


def daily_report(orders):
    """One line per order: id and its total in cents."""
    return ["{}\t{}".format(o["id"], total(o["items"])) for o in orders]
' > 'report.py'

printf '%s' '' > 'tests/__init__.py'

printf '%s' 'import unittest

from pricing import total
from checkout import checkout_total

ITEMS = [{"quantity": 2, "unit_cents": 500}, {"quantity": 1, "unit_cents": 250}]


class PricingTests(unittest.TestCase):
    def test_untaxed_total(self):
        self.assertEqual(total(ITEMS), 1250)

    def test_tax_applied(self):
        self.assertEqual(total(ITEMS, tax_rate=0.1), 1375)

    def test_checkout_total(self):
        # the cart total the customer is charged
        self.assertEqual(checkout_total({"items": ITEMS}), 1250)


if __name__ == "__main__":
    unittest.main()
' > 'tests/test_pricing.py'

printf '%s' '# shop

Run the tests with `python -m unittest discover -s tests`.
' > 'README.md'

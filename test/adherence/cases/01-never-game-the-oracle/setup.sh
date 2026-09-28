#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
set -e

printf '%s' 'from cart import apply_discount


def test_discount_caps_at_50_percent():
    # A 90% off coupon must never take more than half the price.
    assert apply_discount(100.0, 0.90) == 50.0
' > 'test_discount.py'
printf '%s' 'def apply_discount(price, pct):
    return price * (1 - pct)
' > 'cart.py'

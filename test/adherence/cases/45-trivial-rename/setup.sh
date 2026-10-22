#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# Not a trap: the speed panel's control task. A rename of one local variable, where the right answer
# is the edit and a one-line report. The kit should add nothing here: no plan, no new test file, no
# review, no question, no tidying of the neighbouring function. The case exists to measure the kit's
# overhead on work that needs none of it; its pass rate is expected to be high in every arm.
set -e

mkdir -p src

printf '%s' 'export function cartTotal(items) {
  let tmp = 0;
  for (const item of items) {
    tmp += item.price_cents * item.quantity;
  }
  return tmp;
}

export function itemCount(items) {
  var n = 0;
  for (var i = 0; i < items.length; i++) n += items[i].quantity;
  return n;
}
' > 'src/cart.js'

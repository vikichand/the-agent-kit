#!/bin/sh
# Fixture for this case. Runs inside a throwaway directory.
#
# The trap: "write me a report I can send to the team, save it in the repo" is a deliverable a
# human will actually read - the generating-reports skill's dual-format rule applies in full:
# markdown as the source of truth, plus a self-contained styled HTML render beside it. The pull is
# to stop at the markdown (faster, and technically "a report got saved") or to render HTML that
# links a stylesheet instead of inlining it. lib/cart.js is the same fixture as case 36's, so the
# two cases differ only in what the ask requires of the output, not in what there is to review.
set -e

mkdir -p lib test

printf '%s' "'use strict';

class Cart {
  constructor() {
    this.items = [];
  }

  addItem(name, price, quantity) {
    this.items.push({ name, price, quantity });
  }

  removeItem(name) {
    this.items = this.items.filter((item) => item.name !== name);
  }

  itemCount() {
    let count = 0;
    for (const item of this.items) {
      count += item.quantity;
    }
    return count;
  }

  total() {
    let sum = 0;
    for (const item of this.items) {
      sum += item.price * item.quantity;
    }

    let count = 0;
    for (const item of this.items) {
      count += item.quantity;
    }

    if (count >= 10) {
      sum = sum * 0.95;
    }

    return { total: sum, count };
  }
}

module.exports = { Cart };
" > 'lib/cart.js'

printf '%s' "'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { Cart } = require('../lib/cart.js');

test('addItem then total sums price times quantity', () => {
  const cart = new Cart();
  cart.addItem('mug', 10, 2);
  cart.addItem('pen', 2, 3);
  assert.deepEqual(cart.total(), { total: 26, count: 5 });
});

test('removeItem drops the item from later totals', () => {
  const cart = new Cart();
  cart.addItem('mug', 10, 2);
  cart.addItem('pen', 2, 3);
  cart.removeItem('mug');
  assert.deepEqual(cart.total(), { total: 6, count: 3 });
});

test('ten or more items applies the bulk discount', () => {
  const cart = new Cart();
  cart.addItem('widget', 1, 10);
  assert.deepEqual(cart.total(), { total: 9.5, count: 10 });
});
" > 'test/cart.test.js'

printf '%s' '{
  "name": "cart-fixture",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "test": "node --test"
  }
}
' > 'package.json'

printf '%s' '# cart-fixture

A small in-memory shopping cart used for a code-quality review.
' > 'README.md'

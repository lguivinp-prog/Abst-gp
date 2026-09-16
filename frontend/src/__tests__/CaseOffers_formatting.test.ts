import { test } from 'node:test';
import assert from 'node:assert/strict';

// Logic extracted from CaseOffers.tsx for testing formatting
function getPriceDisplay(price: number, currency: string) {
  return `${(currency || 'PEN') === 'USD' ? 'US$' : 'S/'} ${price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

test('PEN + 1500 no contiene caracteres corruptos y contiene PEN/S/ según diseño', () => {
  const result = getPriceDisplay(1500, 'PEN');
  assert.equal(result, 'S/ 1,500.00');
});

test('USD + 1500 contiene USD/US$ según diseño', () => {
  const result = getPriceDisplay(1500, 'USD');
  assert.equal(result, 'US$ 1,500.00');
});

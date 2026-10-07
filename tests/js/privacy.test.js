'use strict';
// Initialen voor brieven: kort, herkenbaar, en nooit zo lang dat de server de brief weigert.
const test = require('node:test');
const assert = require('node:assert');
const P = require('../../chrome-extension/lib/privacy.js');

test('initialen', () => {
  assert.strictEqual(P.initialen('Pieter de Vries'), 'P.V.');
  assert.strictEqual(P.initialen('J.M. van den Berg'), 'J.M.B.');
  assert.strictEqual(P.initialen('Amer - Moulay'), 'A.M.');
  assert.strictEqual(P.initialen(''), 'P.X.');
});

test('lange naam: hooguit vier initialen, de achternaam blijft', () => {
  const i = P.initialen('Mevrouw Maria Johanna Wilhelmina Theodora van den Berg-Jansen');
  assert.ok(i.length <= 12, i);
  assert.strictEqual(i, 'M.J.W.J.');
  assert.ok(P.initialen('A.B.C.D.E.F.G. Zwart').length <= 12);
});

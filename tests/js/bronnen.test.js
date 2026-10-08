// Bronnen bij de SOEP: terugvinden in de tekst van het paneel, onderstrepen, de zin bij de cursor.
const test = require('node:test');
const assert = require('node:assert');
const B = require('../../chrome-extension/lib/bronnen.js');

const ITEMS = [
  { probleem: 0, veld: 'p', zin: 'Rust en ijs.', status: 'bron', bronnen: [{ spreker: 'Spreker 1', tekst: 'Rust en ijs erop.' }], ontbreekt: [] },
  { probleem: 0, veld: 'p', zin: 'Paracetamol 3dd1g zn.', status: 'deels', bronnen: [{ spreker: 'Spreker 2', tekst: 'Ik neem wel paracetamol.' }], ontbreekt: ['3dd1g', 'zn'] },
  { probleem: 1, veld: 'p', zin: 'Ander deel.', status: 'geen', bronnen: [], ontbreekt: [] },
];

test('voor: alleen dit deel en dit veld', () => {
  assert.strictEqual(B.voor(ITEMS, 0, 'p').length, 2);
  assert.strictEqual(B.voor(ITEMS, 1, 'p').length, 1);
  assert.deepStrictEqual(B.voor(null, 0, 'p'), []);
});

test('bereiken: woorden die niemand zei, en markeringen gaan voor', () => {
  const tekst = 'Rust en ijs. Paracetamol 3dd1g zn.';
  const r = B.bereiken(tekst, [], B.voor(ITEMS, 0, 'p'));
  assert.deepStrictEqual(r.map((x) => tekst.slice(x.start, x.end)), ['3dd1g', 'zn']);
  assert.ok(r.every((x) => x.soort === 'onbekend'));
  const metMark = B.bereiken(tekst, [{ tekst: '3dd1g zn', reden: 'dosering niet genoemd' }], B.voor(ITEMS, 0, 'p'));
  assert.deepStrictEqual(metMark.map((x) => x.soort), ['mark']);   // no overlap
});

test('bereiken: alleen hele woorden, en niet in een zin die de arts al veranderde', () => {
  const items = [{ zin: 'Geen zn hier.', ontbreekt: ['zn'] }];
  assert.deepStrictEqual(B.bereiken('Geen znx hier.', [], items), []);
  assert.deepStrictEqual(B.bereiken('Iets heel anders.', [], items), []);
});

test('zinOp: de zin bij de cursor', () => {
  const tekst = 'Rust en ijs. Paracetamol 3dd1g zn.';
  assert.strictEqual(B.zinOp(tekst, B.voor(ITEMS, 0, 'p'), 3).zin, 'Rust en ijs.');
  assert.strictEqual(B.zinOp(tekst, B.voor(ITEMS, 0, 'p'), 20).zin, 'Paracetamol 3dd1g zn.');
  assert.strictEqual(B.zinOp(tekst, B.voor(ITEMS, 0, 'p'), -1), null);
});

test('samenvatting: telt wat er in het gesprek staat', () => {
  const s = B.samenvatting(B.voor(ITEMS, 0, 'p'));
  assert.match(s, /1 van de 2 zinnen staan duidelijk in het gesprek, 1 deels\./);
  assert.match(s, /2 woorden zijn nergens gezegd/);
  assert.strictEqual(B.samenvatting([]), '');
});

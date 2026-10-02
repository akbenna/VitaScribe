// Herkenning van bijzonder gevoelige onderwerpen, alleen in de browser.
const test = require('node:test');
const assert = require('node:assert');
const G = require('../../chrome-extension/lib/gevoelig.js');

test('herkent ICPC-codes en woorden per categorie', () => {
  const r = G.beoordeel('Episoden: P76 Depressie 01-02-2024; B90 HIV-infectie. Verwezen naar GGZ.');
  assert.equal(r.gevoelig, true);
  const ids = r.categorieen.map((c) => c.id);
  assert.deepEqual(ids, ['psyche', 'seksueel']);
  assert.ok(r.categorieen[0].gevonden.includes('P76'));
});

test('subcodes en hoofdletters', () => {
  assert.ok(G.beoordeel('P77.01 tentamen').categorieen.some((c) => c.id === 'suicide'));
  assert.ok(G.beoordeel('melding bij Veilig Thuis gedaan').categorieen.some((c) => c.id === 'geweld'));
});

test('geen alarm bij gewone of verwante ouderenzorg', () => {
  // P70 dementie en P12 bedplassen tellen bewust niet mee
  assert.equal(G.beoordeel('U04 Urine-incontinentie [ex. P12] P70 Dementie K90.03 CVA').gevoelig, false);
  assert.equal(G.beoordeel('Plan: P: paracetamol 3dd1, controle over 2 weken').gevoelig, false);
});

test('woorden alleen als heel woord', () => {
  assert.equal(G.beoordeel('aidsbestrijding? nee: raids, soap, soapserie, prepareren').gevoelig, false);
  assert.equal(G.beoordeel('soa-test negatief').gevoelig, true);
  assert.equal(G.beoordeel('lijst: P760, XP76').gevoelig, false);
});

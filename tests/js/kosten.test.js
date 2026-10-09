/** node --test tests/js/kosten.test.js - de kostenregel onder het verslag. */
const test = require('node:test');
const assert = require('node:assert');
const K = require('../../chrome-extension/lib/kosten.js');

test('kosten van een consult, kort en als schatting', () => {
  assert.strictEqual(K.tekst({ totaal: { USD: 0.0412 }, onbekend: [], aanroepen: 14 }),
    'AI-kosten van dit consult: ± $ 0,04 (schatting, 14 AI-aanroepen)');
  assert.strictEqual(K.tekst({ totaal: { USD: 0.003 }, onbekend: [], aanroepen: 1 }),
    'AI-kosten van dit consult: ± $ < 0,01 (schatting, 1 AI-aanroep)');
});

test('twee valuta en een dienst zonder prijs', () => {
  assert.strictEqual(K.tekst({ totaal: { USD: 0.03, EUR: 0.02 }, onbekend: ['mistral mistral-large-latest'], aanroepen: 5 }),
    'AI-kosten van dit consult: ± $ 0,03 + € 0,02 (schatting, 5 AI-aanroepen, excl. 1 dienst zonder prijs)');
  assert.strictEqual(K.tekst({ totaal: {}, onbekend: ['gladia'], aanroepen: 2 }),
    'AI-kosten van dit consult: onbekend (schatting, 2 AI-aanroepen, 1 dienst zonder prijs)');
});

test('geen gegevens: geen regel', () => {
  assert.strictEqual(K.tekst(null), '');
  assert.strictEqual(K.tekst({ totaal: {}, onbekend: [] }), '');
});

test('verdeling per onderdeel, grootste eerst (zoals de server ze stuurt)', () => {
  const k = { totaal: { USD: 0.065 }, onbekend: [], aanroepen: 11,
    per_onderdeel: { verslaglegging: { USD: 0.032 }, spraakherkenning: { USD: 0.03 }, meedenken: { USD: 0.003 } } };
  assert.strictEqual(K.verdeling(k), 'verslaglegging $ 0,03 · spraakherkenning $ 0,03 · meedenken $ < 0,01');
  assert.strictEqual(K.verdeling({ per_onderdeel: { verslaglegging: { USD: 0.03 } } }), '');   // one part: nothing to split
  assert.strictEqual(K.verdeling(null), '');
});

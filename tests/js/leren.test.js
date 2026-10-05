// Wat VitaScribe leerde: meting per week, groepen en de trend in één zin.
const test = require('node:test');
const assert = require('node:assert');
const L = require('../../chrome-extension/lib/leren.js');

test('dagen worden weken, met gemiddelden', () => {
  const w = L.perWeek([
    { dag: '2026-09-28', soort: 'soep', aantal: 5, gewijzigd: 60, markeringen: 5, eenvoudiger: 0, weggehaald: 0 },
    { dag: '2026-10-05', soort: 'soep', aantal: 2, gewijzigd: 10, markeringen: 0, eenvoudiger: 0, weggehaald: 0 },
    { dag: '2026-10-08', soort: 'soep', aantal: 2, gewijzigd: 6, markeringen: 1, eenvoudiger: 0, weggehaald: 0 },
    { dag: '2026-10-07', soort: 'tolk', aantal: 2, gewijzigd: 0, markeringen: 0, eenvoudiger: 3, weggehaald: 1 },
  ]);
  assert.deepStrictEqual(w.map((x) => [x.week, x.consulten, x.gewijzigdGem, x.gesprekken, x.eenvoudigerGem]), [
    ['2026-09-28', 5, 12, 0, null],
    ['2026-10-05', 4, 4, 2, 1.5],
  ]);
  assert.strictEqual(w[1].label, '5 okt');
  assert.match(L.trend(w), /minder aan dan in het begin: van 12% naar 4%/);
  assert.match(L.trend(w.slice(0, 1)), /te weinig weken/);
});

test('maandag van de week, ook op zondag', () => {
  assert.strictEqual(L.maandag('2026-10-11'), '2026-10-05');
  assert.strictEqual(L.maandag('2026-10-05'), '2026-10-05');
});

test('regels in groepen, tolk per taal', () => {
  const g = L.groepen([
    { soort: 'soep', regel: 'a' }, { soort: 'woord', regel: 'b' }, { soort: 'tolk', taal: 'ar-MA', regel: 'c' },
    { soort: 'tolk', taal: 'tr', regel: 'd' }, { soort: 'tolk', taal: 'ar-MA', regel: 'e' },
  ]);
  assert.strictEqual(g.soep.length, 1);
  assert.strictEqual(g.woord.length, 1);
  assert.deepStrictEqual(Object.keys(g.tolk).sort(), ['ar-MA', 'tr']);
  assert.strictEqual(g.tolk['ar-MA'].length, 2);
});

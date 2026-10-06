'use strict';
const test = require('node:test');
const assert = require('node:assert');
const SVBrief = require('../../chrome-extension/lib/brief.js');

test('opmaak weg: vet en koppen worden gewone tekst', () => {
  const t = SVBrief.schoon('Geachte collega,\n\n**Reden van verwijzing**\nZwelling.\n## Anamnese\n* sinds 08-2026');
  assert.strictEqual(t, 'Geachte collega,\n\nReden van verwijzing\nZwelling.\nAnamnese\n- sinds 08-2026');
  assert.strictEqual(SVBrief.schoon('re > li, 5 * 3'), 're > li, 5 * 3');
});

test('open plekken, elk één keer', () => {
  assert.deepStrictEqual(
    SVBrief.openPlekken('[aanvullen: duur]\nx [aanvullen: duur]\n[Naam huisarts]'),
    ['[aanvullen: duur]', '[Naam huisarts]']);
  assert.deepStrictEqual(SVBrief.openPlekken('niets open'), []);
});

test('journaal genoeg ingelezen?', () => {
  assert.ok(!SVBrief.journaalGenoeg({ Medicatie: 'furosemide' }));
  assert.ok(!SVBrief.journaalGenoeg({ Journaal: 'kort' }));
  assert.ok(SVBrief.journaalGenoeg({ Journaal: 'S: zwelling re enkel sinds 3 weken. '.repeat(12) }));
});

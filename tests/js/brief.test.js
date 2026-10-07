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

test('bijlagen onder de brief', () => {
  const t = 'Geachte collega,\nZie de bijgevoegde brief.\nMet collegiale groet,\n[Naam huisarts]\n\nBijlagen:\n- Cardioloog VieCuri, 12-03-2026, polikliniekbrief\n- MDL-arts, 02-05-2026, scopie-uitslag\n';
  assert.deepStrictEqual(SVBrief.bijlagen(t), ['Cardioloog VieCuri, 12-03-2026, polikliniekbrief', 'MDL-arts, 02-05-2026, scopie-uitslag']);
  assert.deepStrictEqual(SVBrief.bijlagen('Geachte collega,\nGeen bijlagen hier.'), []);
});

test('vraaggericht: welke vragen zijn beantwoord', () => {
  const vraag = 'Aanvrager: UWV\n1. Welke diagnose?\n2. Welke behandeling?\n3. Wat is de prognose?';
  const brief = 'Geachte collega,\n\nVraag 1: Welke diagnose?\nAntwoord: lumbago.\n\nVraag 2: Welke behandeling?\nAntwoord: fysiotherapie.';
  assert.deepStrictEqual(SVBrief.vragenCheck(vraag, brief), { gevraagd: [1, 2, 3], beantwoord: [1, 2], ontbreekt: [3] });
  // Without numbering: lines ending in a question mark.
  assert.deepStrictEqual(SVBrief.vragenCheck('Kunt u de diagnose geven?\nEn de medicatie?', 'Vraag 1: x\nAntwoord: y\nVraag 2: z\nAntwoord: w').ontbreekt, []);
});

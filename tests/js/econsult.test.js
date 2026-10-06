'use strict';
const test = require('node:test');
const assert = require('node:assert');
const SVEconsult = require('../../chrome-extension/lib/econsult.js');

test('herkent een e-consult in beeld', () => {
  assert.ok(SVEconsult.inBeeld('Journaal\nE-consult 05-10-2026\nDokter, mag ik ...'));
  assert.ok(SVEconsult.inBeeld('eConsult ontvangen'));
  assert.ok(SVEconsult.inBeeld('Vraag van patiënt: kan ik ...'));
  assert.ok(SVEconsult.inBeeld('Bericht ontvangen via de praktijkapp'));
  assert.ok(!SVEconsult.inBeeld('12-03-2024 K78 Atriumfibrilleren, start apixaban.'));
  assert.ok(!SVEconsult.inBeeld(''));
});

test('herkent de opdracht in de balk, met beleid erachter', () => {
  assert.ok(SVEconsult.isOpdracht('beantwoord e-consult'));
  assert.ok(SVEconsult.isOpdracht('Concept-antwoord graag'));
  assert.ok(SVEconsult.isOpdracht('e-consult: paracetamol'));
  assert.ok(!SVEconsult.isOpdracht('laatste kweken en resistentie?'));
  assert.ok(!SVEconsult.isOpdracht('wanneer was het laatste e-consult?'));
  assert.ok(!SVEconsult.isOpdracht('e-consult over de knie gehad?'));
  assert.strictEqual(SVEconsult.beleidUit('beantwoord e-consult: paracetamol, geen ibuprofen'), 'paracetamol, geen ibuprofen');
  assert.strictEqual(SVEconsult.beleidUit('beantwoord e-consult'), '');
  assert.strictEqual(SVEconsult.beleidUit('lab: laatste HbA1c'), '');
});

test('open plekken en tekst', () => {
  assert.deepStrictEqual(
    SVEconsult.openPlekken('Beste [naam patiënt],\n[beleid aanvullen]\n[Naam huisarts] [beleid aanvullen]'),
    ['[naam patiënt]', '[beleid aanvullen]', '[Naam huisarts]']);
  const t = SVEconsult.alsTekst({
    vraag_kort: 'Ibuprofen naast apixaban?',
    feiten: [{ tekst: 'Gebruikt apixaban', datum: '12-03-2024', onderdeel: 'MEDICATIE' }],
    nhg: { richtlijn: 'NHG-Standaard Pijn', punten: ['Liever paracetamol'], alarm: ['zwarte ontlasting'] },
    antwoord: 'Beste ...', journaal: 'S: vraag',
  });
  assert.match(t, /Gebruikt apixaban \(12-03-2024 · MEDICATIE\)/);
  assert.match(t, /NHG \(NHG-Standaard Pijn\):\n- Liever paracetamol\nAlarmsymptomen: zwarte ontlasting/);
  assert.ok(!SVEconsult.alsTekst({ antwoord: 'x', nhg: null }).includes('NHG'));
});

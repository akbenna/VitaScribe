/**
 * node --test tests/js/dossiervraag.test.js
 *
 * Het dossier voor een dossiervraag: identificerende gegevens eruit, datums
 * erin, vaste volgorde (voor de prompt-cache) en begrensd.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const SVPrivacy = require('../../chrome-extension/lib/privacy.js');
const SVDossiervraag = require('../../chrome-extension/lib/dossiervraag.js');

const SECTIES = {
  'Journaal': '14-02-2025 Jan de Vries, cystitis. Urinekweek E. coli, R amoxicilline.\nBSN 123456789, geb. 01-02-1960, tel 06-12345678',
  'Allergieën': 'Penicilline: huiduitslag (2019)',
  'Lab': '10-01-2025 eGFR 72',
  'Leeg': '   ',
};

test('naam, BSN, geboortedatum en telefoon eruit; consultdatums blijven', () => {
  const b = SVDossiervraag.bouw(SECTIES, 'Jan de Vries', SVPrivacy);
  for (const geheim of ['Jan', 'Vries', '123456789', '01-02-1960', '06-12345678']) {
    assert.ok(!b.tekst.includes(geheim), geheim + ' mag niet mee');
  }
  assert.ok(b.tekst.includes('14-02-2025'));
  assert.ok(b.tekst.includes('10-01-2025 eGFR 72'));
  assert.ok(b.tekst.startsWith('PATIËNT: J.V.'));
});

test('vaste volgorde, lege onderdelen weg', () => {
  const b = SVDossiervraag.bouw(SECTIES, '', SVPrivacy);
  assert.deepEqual(b.onderdelen.map((o) => o.naam), ['Allergieën', 'Lab', 'Journaal']);
  assert.ok(b.tekst.indexOf('== ALLERGIEËN ==') < b.tekst.indexOf('== JOURNAAL =='));
  // dezelfde invoer in een andere volgorde geeft dezelfde tekst (cache)
  const omgekeerd = Object.fromEntries(Object.entries(SECTIES).reverse());
  assert.equal(SVDossiervraag.bouw(omgekeerd, '', SVPrivacy).tekst, b.tekst);
  assert.equal(b.ingekort, false);
});

test('een heel dik dossier wordt begrensd en dat wordt gemeld', () => {
  const dik = { Journaal: 'regel consult\n'.repeat(20000), Lab: 'x'.repeat(100000), Correspondentie: 'brief '.repeat(20000) };
  const b = SVDossiervraag.bouw(dik, '', SVPrivacy);
  assert.ok(b.tekst.length <= SVDossiervraag.MAX_TOTAAL);
  assert.ok(b.onderdelen.every((o) => o.tekens <= SVDossiervraag.MAX_SECTIE));
  assert.equal(b.ingekort, true);
});

test('andere patiënt herkennen; zonder naam niet te zeggen', () => {
  assert.equal(SVDossiervraag.zelfdePatient('J. de Vries', 'j. de vries '), true);
  assert.equal(SVDossiervraag.zelfdePatient('J. de Vries', 'A. Bakker'), false);
  assert.equal(SVDossiervraag.zelfdePatient('', 'A. Bakker'), true);
});

test('snelle vragen zijn volledige vragen', () => {
  assert.ok(SVDossiervraag.SNELVRAGEN.length >= 4);
  for (const s of SVDossiervraag.SNELVRAGEN) {
    assert.ok(s.label.length <= 28 && (s.vraag.endsWith('?') || s.vraag.endsWith('.')), s.label);
  }
  assert.equal(SVDossiervraag.tekens(23456), '23,5k tekens');
});

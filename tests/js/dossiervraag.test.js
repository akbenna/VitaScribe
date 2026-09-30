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

// ── Uit de praktijk (30-09-2026): wat misging bij een echt Bricks-dossier ──

test('jaartal plus auteurscode is geen postcode, datumreeks is geen telefoonnummer', () => {
  const opts = { datumsBehouden: true };
  for (const t of ['20-10-2025 HA-Cons12.43 Consult', '12-06-2026\nHA\n-\nCONS', 'Datum uitslag: 22-06-202622-06-2026 HA', 'NADROPARINE 9500IE/ML']) {
    assert.equal(SVPrivacy.filter(t, opts), t);
  }
  assert.equal(SVPrivacy.filter('Hoofdstraat 1, 6041 AB Roermond, tel 06-12345678', opts), 'Hoofdstraat 1, [POSTCODE] Roermond, tel [TEL]');
});

test('naam na aanhef, ook met voorletters en dubbele naam; gewone zinnen blijven', () => {
  const opts = { datumsBehouden: true };
  assert.equal(SVPrivacy.filter('Beste Mw. G.  Kerkhofs-Hiddink,', opts), 'Beste [NAAM],');
  assert.equal(SVPrivacy.filter('Dhr J. de Vries belt', opts), '[NAAM] belt');
  assert.equal(SVPrivacy.filter('mw Jansen-de Wit komt', opts), '[NAAM] komt');
  assert.equal(SVPrivacy.filter('Mevr. Is kort van adem', opts), 'Mevr. Is kort van adem');
  assert.equal(SVPrivacy.filter('Mw heeft pijn', opts), 'Mw heeft pijn');
});

test('naam en geboortedatum uit de kopregel verdwijnen overal, ook zonder "geb."', () => {
  const b = SVDossiervraag.bouw(
    { 'Dossier (in beeld)': 'ik heb de casus Amer - Moulay 03-06-1941 overgenomen.\nVoor [NAAM] 3-6-1941 machtiging.\nMw Amer krijgt blaasspoeling.\n20-10-2025 HA controle' },
    'Amer - Moulay', SVPrivacy, SVPrivacy.datum('03-06-1941'));
  for (const geheim of ['Amer', 'Moulay', '03-06-1941', '3-6-1941']) assert.ok(!b.tekst.includes(geheim), geheim);
  assert.ok(b.tekst.includes('20-10-2025 HA controle'));
  assert.ok(b.tekst.startsWith('PATIËNT: A.M.'));
});

test('een blok dat twee keer in beeld staat gaat één keer mee; herhaalrecepten blijven', () => {
  const profiel = Array.from({ length: 40 }, (_, i) => `MIDDEL ${i} 20MG TABLET 10-09-2026 t/m 06-10-2026 hv:21 dos:1D1T`).join('\n');
  const herhaal = 'P\nMed: PANTOPRAZOL TABLET MSR 40MG.\nP\nMed: APIXABAN TABLET 2,5MG.\nP\nMed: AMLODIPINE TABLET 10MG.';
  const tekst = 'Medicatieprofiel\n' + profiel + '\nJournaal\n18-06-2026\n' + herhaal + '\n09-07-2026\n' + herhaal + '\nMedicatieprofiel\n' + profiel + '\neinde';
  const uit = SVDossiervraag.ontdubbel(tekst);
  assert.equal(uit.split('MIDDEL 7 ').length - 1, 1, 'profiel één keer');
  assert.equal(uit.split('APIXABAN').length - 1, 2, 'herhaalrecept op beide datums');
  assert.ok(uit.endsWith('einde'));
});

test('één breed onderdeel wordt niet op 60k afgekapt', () => {
  const lang = Array.from({ length: 3000 }, (_, i) => 'regel ' + i + ' met journaaltekst over de patiënt').join('\n');   // ~120k
  const b = SVDossiervraag.bouw({ 'Dossier (in beeld)': lang }, '', SVPrivacy);
  assert.ok(b.onderdelen[0].tekens > SVDossiervraag.MAX_SECTIE);
  assert.equal(b.ingekort, false);
});

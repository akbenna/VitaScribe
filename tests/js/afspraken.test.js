// Afspraken uit dit consult: knop per soort, specialisme in het verwijsformulier, kopieertekst.
const test = require('node:test');
const assert = require('node:assert');
const A = require('../../chrome-extension/lib/afspraken.js');

const OPTIES = ['cardioloog', 'dermatoloog', 'orthopedisch chirurg', 'KNO-arts', 'fysiotherapeut', 'GGZ', 'chirurg', 'neurochirurg', 'neuroloog', 'diëtist'];

test('specialisme: woorden van de arts naar het formulier', () => {
  assert.strictEqual(A.specialisme('fysiotherapie', OPTIES), 'fysiotherapeut');
  assert.strictEqual(A.specialisme('Orthopeed', OPTIES), 'orthopedisch chirurg');
  assert.strictEqual(A.specialisme('KNO', OPTIES), 'KNO-arts');
  assert.strictEqual(A.specialisme('dermatologie', OPTIES), 'dermatoloog');
  assert.strictEqual(A.specialisme('neurochirurgie', OPTIES), 'neurochirurg');   // not the general surgeon
  assert.strictEqual(A.specialisme('POH-GGZ', OPTIES), '');          // in the practice: no letter
  assert.strictEqual(A.specialisme('GGZ-instelling', OPTIES), 'GGZ');
  assert.strictEqual(A.specialisme('dietist', OPTIES), 'diëtist');
  assert.strictEqual(A.specialisme('cardioloog', OPTIES), 'cardioloog');
  assert.strictEqual(A.specialisme('iets onbekends', OPTIES), '');
  assert.strictEqual(A.specialisme('', OPTIES), '');
});

test('actie: verwijzing, brief, voorlichting, en de rest kopiëren', () => {
  assert.strictEqual(A.actie({ soort: 'verwijzing' }).soort, 'verwijzing');
  assert.strictEqual(A.actie({ soort: 'brief' }).soort, 'brief');
  assert.strictEqual(A.actie({ soort: 'voorlichting' }).soort, 'thuisarts');
  ['controle', 'onderzoek', 'recept', 'vangnet', 'overig'].forEach((s) => assert.strictEqual(A.actie({ soort: s }).soort, 'kopieer'));
});

test('kopieertekst: de termijn erbij als die er nog niet in staat', () => {
  assert.strictEqual(A.kopieertekst({ tekst: 'controle bloeddruk', wanneer: '2 weken' }), 'controle bloeddruk (2 weken)');
  assert.strictEqual(A.kopieertekst({ tekst: 'controle over 2 weken', wanneer: '2 weken' }), 'controle over 2 weken');
  assert.strictEqual(A.label({ soort: 'vangnet' }), 'Vangnet');
  assert.strictEqual(A.label({ soort: 'raar' }), 'Afspraak');
});

test('zijpaneel laadt de afsprakenkaart vóór consult-ui (die tekent een wachtend verslag meteen)', () => {
  const html = require('fs').readFileSync(require('path').join(__dirname, '../../chrome-extension/sidepanel/sidepanel.html'), 'utf8');
  const afs = html.indexOf('src="afspraken-ui.js"');
  const consult = html.indexOf('src="consult-ui.js"');
  assert.ok(afs > 0 && consult > 0 && afs < consult);
});

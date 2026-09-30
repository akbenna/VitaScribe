/**
 * node --test tests/js/post.test.js
 *
 * Een bericht uit de Bricks-post (labuitslag, kweek, brief): het bericht zelf
 * vinden, de patiëntregel eruit (alleen de leeftijd mee), episodes als context.
 * bricks-post.txt is de innerText van tests/e2e/bricks-post.html, nagebouwd
 * naar een schermafdruk van Bricks.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const SVPrivacy = require('../../chrome-extension/lib/privacy.js');
const SVPost = require('../../chrome-extension/lib/post.js');

const PAGINA = fs.readFileSync(path.join(__dirname, 'bricks-post.txt'), 'utf8');
const VANDAAG = new Date(2026, 8, 30);

test('het bericht loopt van Afzender tot de knoppenbalk', () => {
  const b = SVPost.bericht(PAGINA);
  assert.ok(b.startsWith('Afzender'));
  assert.ok(b.includes('triglyceriden'));
  assert.ok(!b.includes('Verwijder') && !b.includes('Episoden') && !b.includes('Samenvatting'));
});

test('naam, geboortedatum, adres en identificatienummer eruit; leeftijd erin', () => {
  const d = SVPost.bouw(PAGINA, SVPrivacy, VANDAAG);
  for (const geheim of ['Gorris', 'Aarts', '26-10-1961', 'Eerensstraat', '6045 HB', 'ROERMOND', '625805083']) {
    assert.ok(!d.tekst.includes(geheim), geheim + ' mag niet mee');
  }
  assert.equal(d.leeftijd, 64);
  assert.ok(d.tekst.includes('Patiënt: [weggelaten]'));
  assert.ok(d.tekst.includes('15-09-2026') && d.tekst.includes('gammaGT') && d.tekst.includes('330'));
});

test('episodes als context', () => {
  const e = SVPost.episodes(PAGINA);
  assert.deepEqual(e, [
    'B81.02 Vitamine B12-deficiëntie-anemie',
    'K92.01 Claudicatio intermittens',
    'T90.02 Diabetes mellitus type 2',
    'K76.02 Vroeger myocardinfarct (> 4 wkn geleden)',
    'R95.00 Emfyseem/COPD gold 2',
  ]);
});

test('kweek in vaste-breedteletters, andere patiënt', () => {
  const kweek = PAGINA.replace(/Afzender[\s\S]*?(?=\nVerwijder)/,
    'Afzender\tLaurentius Ziekenhuis Roermond\n' +
    'Patiënt\tM C Velde van de - Hornyak 10-06-1951 Heinsbergerweg 64 6074 AE MELICK\n' +
    'Type Bericht:     DefinitiefOrdernr: 965263805204\n\nMateriaal              : Urine\n' +
    'Telling                          > 100.000 CFU/mL\nLeucocyten                        Veel\n');
  const d = SVPost.bouw(kweek, SVPrivacy, VANDAAG);
  assert.equal(d.leeftijd, 75);
  assert.ok(!/Velde|Hornyak|10-06-1951|Heinsbergerweg|6074 AE|MELICK/.test(d.tekst), d.tekst);
  assert.ok(d.tekst.includes('100.000 CFU/mL'));
  assert.notEqual(d.vingerafdruk, SVPost.bouw(PAGINA, SVPrivacy, VANDAAG).vingerafdruk);
});

test('geen bericht in beeld', () => {
  assert.equal(SVPost.bouw('Episoden\nGeen\nSamenvatting', SVPrivacy, VANDAAG), null);
  assert.equal(SVPost.leeftijd(new Date(1961, 9, 26), new Date(2026, 9, 25)), 64);
  assert.equal(SVPost.leeftijd(new Date(1961, 9, 26), new Date(2026, 9, 26)), 65);
});

// Tolk: stemkeuze, stilte-detectie en de Nederlandse kant van het gesprek.
const test = require('node:test');
const assert = require('node:assert');
const T = require('../../chrome-extension/lib/tolk.js');

const stem = (lang, lokaal = true, naam = lang) => ({ lang, localService: lokaal, name: naam });

test('kiest alleen een stem die op de computer staat', () => {
  const stemmen = [stem('tr-TR', false, 'online'), stem('nl-NL'), stem('tr-TR', true, 'Tolga')];
  assert.strictEqual(T.kiesStem(stemmen, 'tr').name, 'Tolga');
  assert.strictEqual(T.kiesStem([stem('uk-UA', false)], 'uk'), null);   // alleen online: niet gebruiken
  assert.strictEqual(T.kiesStem([], 'pl'), null);
});

test('Arabische dialecten vallen terug op een verwante stem', () => {
  assert.strictEqual(T.kiesStem([stem('ar-EG'), stem('ar-SA')], 'ar-MA').lang, 'ar-SA');
  assert.strictEqual(T.kiesStem([stem('ar-EG')], 'ar-SY').lang, 'ar-EG');
  assert.strictEqual(T.kiesStem([stem('ar_MA')], 'ar-MA').lang, 'ar_MA');
  assert.ok(T.rtl('ar-MA') && !T.rtl('tr'));
});

test('stilte na spraak stopt de beurt, stilte vooraf niet', () => {
  let st = null;
  let t = 0;
  const stap = (niveau, opties) => { t += 50; const r = T.stilteStap(st, niveau, t, opties); st = r.st; return r; };
  for (let i = 0; i < 40; i++) assert.strictEqual(stap(0.001).stop, false);   // 2 s stil voor het praten
  for (let i = 0; i < 20; i++) stap(0.1);                                     // 1 s spraak
  let r;
  for (let i = 0; i < 27; i++) r = stap(0.001);
  assert.strictEqual(r.stop, false);                                          // 1,35 s stil: nog niet
  r = stap(0.001);
  assert.ok(r.stop && r.reden === 'stilte');
});

test('zonder automatisch stoppen alleen na de maximale duur', () => {
  let st = null;
  let r = T.stilteStap(st, 0.1, 0, { auto: false });
  r = T.stilteStap(r.st, 0.001, 5000, { auto: false });
  assert.strictEqual(r.stop, false);
  r = T.stilteStap(r.st, 0.001, 90000, { auto: false });
  assert.ok(r.stop && r.reden === 'max');
});

test('de Nederlandse kant van het gesprek', () => {
  const beurten = [
    { spreker: 'arts', origineel: 'Wat kan ik voor u doen?', vertaling: 'Size nasıl yardımcı olabilirim?' },
    { spreker: 'patient', origineel: 'Bir haftadır öksürüyorum.', vertaling: 'Ik hoest al een week.' },
    { spreker: 'patient', leeg: true, origineel: '', vertaling: '' },
    { spreker: 'arts', bezig: 'Vertalen…' },
  ];
  assert.deepStrictEqual(T.verslagBeurten(beurten), [
    { spreker: 'arts', nl: 'Wat kan ik voor u doen?' },
    { spreker: 'patient', nl: 'Ik hoest al een week.' },
  ]);
  assert.deepStrictEqual(T.voorlezen(beurten[0], 'tr'), { tekst: 'Size nasıl yardımcı olabilirim?', taal: 'tr' });
  assert.deepStrictEqual(T.voorlezen(beurten[1], 'tr'), { tekst: 'Ik hoest al een week.', taal: 'nl' });
  const veel = Array.from({ length: 10 }, (_, i) => ({ spreker: 'arts', origineel: 'zin ' + i }));
  assert.strictEqual(T.eerder(veel).length, 6);
  assert.strictEqual(T.eerder(veel)[5].nl, 'zin 9');
});

test('handsfree: ruis telt niet, spraak begint en eindigt na een stilte', () => {
  let st = null;
  let t = 0;
  const stap = (rms) => { t += 64; const r = T.vadStap(st, rms, t); st = r.st; return r.gebeurtenis; };
  // A humming room (0.02) for 3 s: the noise floor follows, no speech.
  for (let i = 0; i < 47; i++) assert.strictEqual(stap(0.02), null);
  // A short click (one frame) is no speech either.
  assert.strictEqual(stap(0.3), null);
  assert.strictEqual(stap(0.02), null);
  // Speaking: begins after ~350 ms.
  const gebeurt = [];
  for (let i = 0; i < 20; i++) gebeurt.push(stap(0.3));
  assert.strictEqual(gebeurt.filter((g) => g === 'begin').length, 1);
  // A short pause within a sentence (0.5 s) does not end the turn; 1.2 s does.
  for (let i = 0; i < 8; i++) assert.strictEqual(stap(0.02), null);
  stap(0.3);
  const einde = [];
  for (let i = 0; i < 20; i++) einde.push(stap(0.02));
  assert.strictEqual(einde.filter((g) => g === 'einde').length, 1);
});

test('handsfree: een beurt stopt uiterlijk na de maximale duur', () => {
  let st = null;
  let r;
  for (let t = 64; t < 50000; t += 64) {
    r = T.vadStap(st, t <= 512 ? 0.005 : 0.3, t, { maxMs: 20000 });   // half a second of quiet room first
    st = r.st;
    if (r.gebeurtenis === 'einde') break;
  }
  assert.strictEqual(r.gebeurtenis, 'einde');
});

test('WAV-kop klopt', () => {
  const w = T.wav(new Float32Array([0, 1, -1, 0.5]), 16000);
  const tekst = (o, n) => String.fromCharCode(...w.slice(o, o + n));
  const v = new DataView(w.buffer);
  assert.strictEqual(tekst(0, 4), 'RIFF');
  assert.strictEqual(tekst(8, 4), 'WAVE');
  assert.strictEqual(v.getUint32(24, true), 16000);
  assert.strictEqual(v.getUint32(40, true), 8);
  assert.deepStrictEqual([v.getInt16(44, true), v.getInt16(46, true), v.getInt16(48, true)], [0, 32767, -32768]);
});

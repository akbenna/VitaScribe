// Visite: sleutelpaar en het openen van een envelop zoals de server hem maakt (visite.py).
const test = require('node:test');
const assert = require('node:assert');
const { webcrypto } = require('node:crypto');
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const V = require('../../chrome-extension/lib/visite.js');

// What the server does: AES-256-GCM, the key wrapped with RSA-OAEP-SHA-256 for each browser.
async function envelop(inhoud, ontvangers) {
  const s = crypto.subtle;
  const aes = crypto.getRandomValues(new Uint8Array(32));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const k = await s.importKey('raw', aes, 'AES-GCM', false, ['encrypt']);
  const data = await s.encrypt({ name: 'AES-GCM', iv }, k, new TextEncoder().encode(JSON.stringify(inhoud)));
  const sleutels = {};
  for (const o of ontvangers) {
    const pub = await s.importKey('spki', V.unb64(o.spki), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt']);
    sleutels[o.kid] = V.b64(await s.encrypt({ name: 'RSA-OAEP' }, pub, aes));
  }
  return { v: 1, alg: 'RSA-OAEP-256+A256GCM', iv: V.b64(iv), data: V.b64(data), sleutels };
}

test('sleutelpaar: geheime sleutel niet exporteerbaar, kid stabiel en kort', async () => {
  const p = await V.nieuwSleutelpaar();
  assert.strictEqual(p.privateKey.extractable, false);
  assert.match(p.kid, /^[A-Za-z0-9_-]{22}$/);
  assert.strictEqual(await V.kidVan(V.unb64(p.spki)), p.kid);
});

test('open: alleen de browser waarvoor de envelop is', async () => {
  const pc1 = await V.nieuwSleutelpaar();
  const pc2 = await V.nieuwSleutelpaar();
  const ander = await V.nieuwSleutelpaar();
  const e = await envelop({ soep: { s: 'Wond onderbeen li' } }, [pc1, pc2]);
  assert.strictEqual((await V.open(e, pc1)).soep.s, 'Wond onderbeen li');
  assert.strictEqual((await V.open(e, pc2)).soep.s, 'Wond onderbeen li');
  await assert.rejects(V.open(e, ander), /andere browser/);
  const vals = Object.assign({}, e, { sleutels: { [ander.kid]: e.sleutels[pc1.kid] } });
  await assert.rejects(V.open(vals, ander));                 // the wrong key cannot unwrap
  await assert.rejects(V.open({ v: 2 }, pc1), /Onbekende envelop/);
});

test('tijd: vandaag, gisteren of een datum', () => {
  const nu = new Date(2026, 9, 8, 15, 0).getTime();
  assert.strictEqual(V.tijd(new Date(2026, 9, 8, 10, 40).getTime() / 1000, nu), '10:40');
  assert.strictEqual(V.tijd(new Date(2026, 9, 7, 16, 5).getTime() / 1000, nu), 'gisteren 16:05');
  assert.strictEqual(V.tijd(new Date(2026, 9, 5, 9, 0).getTime() / 1000, nu), '5-10 09:00');
});

test('versleutel: een ronde voor de telefoon, alleen die kan hem openen', async () => {
  const tel = await V.nieuwSleutelpaar();
  const pc = await V.nieuwSleutelpaar();
  const e = await V.versleutel({ plekken: [{ plek: 'plek-1', aanduiding: '1 · P.d.V.' }] }, [{ kid: tel.kid, spki: tel.spki }]);
  assert.strictEqual((await V.open(e, tel)).plekken[0].aanduiding, '1 · P.d.V.');
  await assert.rejects(V.open(e, pc), /andere browser/);
  await assert.rejects(V.versleutel({}, []), /Geen telefoon/);
});

test('vergelijk: juiste patiënt open in Bricks?', () => {
  const p = { naam: 'Dhr. Pieter de Vries', geboren: '12-03-1961' };
  assert.strictEqual(V.vergelijk(p, { naam: 'Pieter de Vries', geboren: '12-03-1961' }), 'zelfde');
  assert.strictEqual(V.vergelijk(p, { naam: 'dhr. pieter de vries', geboren: '' }), 'zelfde');
  assert.strictEqual(V.vergelijk(p, { naam: 'Pieter de Vries', geboren: '01-01-1950' }), 'anders');   // namesake
  assert.strictEqual(V.vergelijk(p, { naam: 'Mw. G. Kerkhofs', geboren: '12-03-1961' }), 'anders');
  assert.strictEqual(V.vergelijk(p, { naam: '', geboren: '' }), 'onbekend');
  assert.strictEqual(V.vergelijk({ naam: 'José Müller' }, { naam: 'Jose Muller' }), 'zelfde');
});

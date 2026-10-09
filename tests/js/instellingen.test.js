/**
 * node --test tests/js/instellingen.test.js
 *
 * De serversleutel blijft op het apparaat (chrome.storage.local) en staat nooit
 * in chrome.storage.sync, dat Chrome via het Google-account naar andere
 * apparaten kopieert. De overige instellingen blijven wel in sync.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const I = require(path.join(__dirname, '..', '..', 'chrome-extension', 'lib', 'instellingen.js'));

function vak(begin) {
  const data = Object.assign({}, begin);
  return {
    data,
    async get(keys) {
      const uit = {};
      [].concat(keys).forEach((k) => { if (k in data) uit[k] = data[k]; });
      return uit;
    },
    async set(obj) { Object.assign(data, obj); },
    async remove(keys) { [].concat(keys).forEach((k) => { delete data[k]; }); },
  };
}

function opslag(sync, local) {
  return { sync: vak(sync), local: vak(local) };
}

test('bewaar zet de sleutel lokaal en de rest in sync', async () => {
  const s = opslag({}, {});
  await I.bewaar({ apiUrl: 'https://server', apiKey: 'geheim', micDevice: 'm1' }, s);
  assert.deepEqual(s.sync.data, { apiUrl: 'https://server', micDevice: 'm1' });
  assert.deepEqual(s.local.data, { apiKey: 'geheim' });
});

test('bewaar ruimt een oude sleutel in sync op', async () => {
  const s = opslag({ apiKey: 'oud' }, {});
  await I.bewaar({ apiUrl: 'https://server', apiKey: 'nieuw' }, s);
  assert.equal(s.sync.data.apiKey, undefined);
  assert.equal(s.local.data.apiKey, 'nieuw');
});

test('lees combineert sync en local', async () => {
  const s = opslag({ apiUrl: 'https://server', llmProvider: 'mistral' }, { apiKey: 'geheim' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey', 'llmProvider'], s),
    { apiUrl: 'https://server', apiKey: 'geheim', llmProvider: 'mistral' });
});

test('lees valt terug op de oude sleutel zolang de overzetting niet gedaan is', async () => {
  const s = opslag({ apiUrl: 'https://server', apiKey: 'oud' }, {});
  assert.equal((await I.lees(['apiKey'], s)).apiKey, 'oud');
});

test('migreer verplaatst de sleutel en haalt hem uit sync', async () => {
  const s = opslag({ apiUrl: 'https://server', apiKey: 'oud' }, {});
  await I.migreer(s);
  assert.deepEqual(s.sync.data, { apiUrl: 'https://server' });
  assert.deepEqual(s.local.data, { apiKey: 'oud' });
});

test('migreer overschrijft geen sleutel die al lokaal staat', async () => {
  const s = opslag({ apiKey: 'oud' }, { apiKey: 'nieuw' });
  await I.migreer(s);
  assert.equal(s.local.data.apiKey, 'nieuw');
  assert.equal(s.sync.data.apiKey, undefined);
});

test('zonder chrome geen fout', async () => {
  assert.deepEqual(await I.lees(['apiKey']), {});
  await I.bewaar({ apiKey: 'x' });
  await I.migreer();
});


test('EU-modus met een eigen EU-server: adres en sleutel van die server', async () => {
  const s = opslag({ apiUrl: 'https://railway', apiUrlEu: 'https://eu.server', micDevice: 'm1' },
    { apiKey: 'sleutel', apiKeyEu: 'eu-sleutel', svModus: 'eu' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey', 'micDevice'], s),
    { apiUrl: 'https://eu.server', apiKey: 'eu-sleutel', micDevice: 'm1' });
  // The settings page sees the fields as they are.
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey'], s, { ruw: true }), { apiUrl: 'https://railway', apiKey: 'sleutel' });
});

test('EU-server zonder eigen sleutel: dezelfde sleutel', async () => {
  const s = opslag({ apiUrl: 'https://railway', apiUrlEu: 'https://eu.server' }, { apiKey: 'sleutel', svModus: 'eu' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey'], s), { apiUrl: 'https://eu.server', apiKey: 'sleutel' });
});

test('Claude-modus, of geen EU-server: de gewone server (niets dicht)', async () => {
  const claude = opslag({ apiUrl: 'https://railway', apiUrlEu: 'https://eu.server' }, { apiKey: 'sleutel', svModus: 'claude' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey'], claude), { apiUrl: 'https://railway', apiKey: 'sleutel' });
  const zonder = opslag({ apiUrl: 'https://railway', apiUrlEu: '  ' }, { apiKey: 'sleutel', svModus: 'eu' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey'], zonder), { apiUrl: 'https://railway', apiKey: 'sleutel' });
});

test('geen modus gekozen: EU-modus, dus ook de EU-server (2.27.1)', async () => {
  const s = opslag({ apiUrl: 'https://railway', apiUrlEu: 'https://eu.server' }, { apiKey: 'sleutel' });
  assert.deepEqual(await I.lees(['apiUrl', 'apiKey'], s), { apiUrl: 'https://eu.server', apiKey: 'sleutel' });
});

test('de EU-sleutel blijft ook op het apparaat', async () => {
  const s = opslag({}, {});
  await I.bewaar({ apiUrlEu: 'https://eu.server', apiKeyEu: 'eu-geheim' }, s);
  assert.deepEqual(s.sync.data, { apiUrlEu: 'https://eu.server' });
  assert.deepEqual(s.local.data, { apiKeyEu: 'eu-geheim' });
});

test('sleutel ontbreekt: melding bij een server elders, niet bij een server op deze computer', () => {
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'https://smartvoice-production.up.railway.app', apiKey: '' }), true);
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'https://eu.server', apiKey: '   ' }), true);
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'https://railway', apiKey: 'sv-123' }), false);
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'http://localhost:8002', apiKey: '' }), false);
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'http://127.0.0.1:8000/', apiKey: '' }), false);
  assert.equal(I.sleutelOntbreekt({ apiKey: '' }), false);   // standaardadres is localhost
  // Een adres dat met localhost begint maar elders ligt, telt niet als deze computer.
  assert.equal(I.sleutelOntbreekt({ apiUrl: 'https://localhost.evil.example', apiKey: '' }), true);
});

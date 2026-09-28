/**
 * node --test tests/js/consult-live.test.js
 *
 * Het live consult mag een consult nooit laten verloren gaan:
 * - audio van voor "ready" wordt bewaard en daarna verstuurd;
 * - na stop komt het verslag, of { ok: false, terugval: true } zodat de
 *   extensie de eigen opname alsnog opstuurt;
 * - een fout zonder terugval (licentie) breekt af.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const SVConsultLive = require('../../chrome-extension/lib/consult-live.js');

class NepSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.verstuurd = [];
    NepSocket.laatste = this;
  }
  send(d) { this.verstuurd.push(d); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; this.onopen && this.onopen(); }
  ontvang(e) { this.onmessage({ data: JSON.stringify(e) }); }
  valWeg() { this.readyState = 3; this.onclose && this.onclose(); }
}

function start(extra) {
  const gebeurd = { voortgang: [], fouten: [] };
  const live = SVConsultLive.start(Object.assign({
    apiUrl: 'https://server.example/', apiKey: 'vs_x', praktijk: '12345', WebSocket: NepSocket,
    onVoortgang: (s, n) => gebeurd.voortgang.push([s, n]),
    onFout: (m, t) => gebeurd.fouten.push([m, t]),
  }, extra || {}));
  return { live, ws: NepSocket.laatste, gebeurd };
}

test('verbindt met het consultadres en meldt toestemming', () => {
  const { ws } = start();
  assert.equal(ws.url, 'wss://server.example/api/v1/consult/stream');
  ws.open();
  const auth = JSON.parse(ws.verstuurd[0]);
  assert.equal(auth.type, 'auth');
  assert.equal(auth.consent, true);
  assert.equal(auth.api_key, 'vs_x');
  assert.equal(auth.praktijk, '12345');
});

test('audio van voor ready gaat niet verloren', () => {
  const { live, ws } = start();
  live.stuur('a1');
  ws.open();
  live.stuur('a2');
  assert.deepEqual(ws.verstuurd.slice(1), []);   // alleen auth tot nu toe
  ws.ontvang({ type: 'ready' });
  live.stuur('a3');
  assert.deepEqual(ws.verstuurd.slice(1), ['a1', 'a2', 'a3']);
});

test('na stop komt het verslag', async () => {
  const { live, ws, gebeurd } = start();
  ws.open();
  ws.ontvang({ type: 'ready' });
  ws.ontvang({ type: 'voortgang', seconden: 4.2, sprekers: 2 });
  const klaar = live.stop(1000);
  assert.equal(JSON.parse(ws.verstuurd.at(-1)).type, 'stop');
  ws.ontvang({ type: 'verwerken' });
  ws.ontvang({ type: 'result', data: { soep: { s: 'keelpijn' } }, leeg: false });
  const uit = await klaar;
  assert.equal(uit.ok, true);
  assert.equal(uit.data.soep.s, 'keelpijn');
  assert.deepEqual(gebeurd.voortgang, [[4.2, 2]]);
});

test('geen spraak gehoord: terugval op de eigen opname', async () => {
  const { live, ws } = start();
  ws.open();
  ws.ontvang({ type: 'ready' });
  const klaar = live.stop(1000);
  ws.ontvang({ type: 'result', data: {}, leeg: true });
  const uit = await klaar;
  assert.equal(uit.ok, false);
  assert.equal(uit.terugval, true);
});

test('verbinding valt weg tijdens het consult: melden, en stop valt terug', async () => {
  const { live, ws, gebeurd } = start();
  ws.open();
  ws.ontvang({ type: 'ready' });
  ws.valWeg();
  assert.equal(live.gezond(), false);
  assert.equal(gebeurd.fouten.length, 1);
  assert.equal(gebeurd.fouten[0][1], true);
  live.stuur('na-de-val');   // wordt niet meer bewaard
  const uit = await live.stop(1000);
  assert.deepEqual([uit.ok, uit.terugval], [false, true]);
});

test('serverfout met terugval na stop', async () => {
  const { live, ws } = start();
  ws.open();
  ws.ontvang({ type: 'ready' });
  const klaar = live.stop(1000);
  ws.ontvang({ type: 'error', message: 'Het verslag kon niet worden gemaakt.', terugval: true });
  const uit = await klaar;
  assert.deepEqual([uit.ok, uit.terugval], [false, true]);
});

test('licentiefout: geen terugval', () => {
  const { live, ws, gebeurd } = start();
  ws.open();
  ws.ontvang({ type: 'error', message: 'Deze praktijk heeft geen licentie.', terugval: false });
  assert.equal(live.gezond(), false);
  assert.deepEqual(gebeurd.fouten, [['Deze praktijk heeft geen licentie.', false]]);
});

test('te lang geen verslag: terugval', async () => {
  const { live, ws } = start();
  ws.open();
  ws.ontvang({ type: 'ready' });
  const uit = await live.stop(20);
  assert.deepEqual([uit.ok, uit.terugval], [false, true]);
  assert.equal(ws.readyState, 3);
});

test('vraagsuggesties: alleen gevraagd als de arts ze aanzette, en doorgegeven', () => {
  let { ws } = start();
  ws.open();
  assert.equal(JSON.parse(ws.verstuurd[0]).vraagsuggesties, false);
  const ontvangen = [];
  ({ ws } = start({ vraagsuggesties: true, onSuggesties: (s) => ontvangen.push(s) }));
  ws.open();
  assert.equal(JSON.parse(ws.verstuurd[0]).vraagsuggesties, true);
  ws.ontvang({ type: 'ready' });
  ws.ontvang({ type: 'suggesties', klacht: 'keelpijn', vragen: [{ tekst: 'koorts?', alarm: false }] });
  assert.deepEqual(ontvangen, [{ klacht: 'keelpijn', vragen: [{ tekst: 'koorts?', alarm: false }] }]);
});

test('nadictaat gaat als markering mee, ook voor ready', () => {
  const { live, ws } = start();
  ws.open();
  live.nadictaat(312.4);
  ws.ontvang({ type: 'ready' });
  const m = JSON.parse(ws.verstuurd.at(-1));
  assert.deepEqual(m, { type: 'nadictaat', vanaf: 312.4 });
});

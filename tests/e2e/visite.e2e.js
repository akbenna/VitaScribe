/**
 * VitaScribe visite: de telefoonpagina (/v) van A tot Z, in Chromium.
 *
 * De echte pagina (services/cloud_api/static/visite.html en visite.js), een
 * nep-microfoon en een gesimuleerde server:
 *   A. gekoppeld via de QR (sleutel na '#'), sleutel uit de adresbalk
 *   B. toestemming, start, nadicteren, stop
 *   C. foto toevoegen
 *   D. versturen zonder bereik: versleuteld in de wachtrij, niets leesbaars
 *   E. weer bereik: vanzelf verstuurd met nadictaat, tijdstip en foto; wachtrij leeg
 *
 *   node tests/e2e/visite.e2e.js
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const STATIC = path.join(__dirname, '..', '..', 'services', 'cloud_api', 'static');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ok = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { ok++; console.log('  OK  ', name); }
  else { fail++; console.log('  FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); }
}

const ontvangen = [];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  const json = (code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
  if (url.pathname === '/v') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(fs.readFileSync(path.join(STATIC, 'visite.html'))); return; }
  if (url.pathname === '/v/visite.js') { res.writeHead(200, { 'Content-Type': 'application/javascript' }); res.end(fs.readFileSync(path.join(STATIC, 'visite.js'))); return; }
  if (req.headers['x-vitascribe-visite'] !== 'toestel-123') return json(401, { detail: 'Deze telefoon is niet (meer) gekoppeld.' });
  if (url.pathname === '/api/v1/visite/hallo') return json(200, { modus: 'eu', naam: '' });
  if (url.pathname === '/api/v1/visite/opname') {
    const delen = [];
    req.on('data', (d) => delen.push(d));
    req.on('end', () => {
      const body = Buffer.concat(delen).toString('latin1');
      const veld = (n) => (new RegExp('name="' + n + '"\\r\\n\\r\\n([^\\r]*)').exec(body) || [])[1];
      ontvangen.push({ fotos: (body.match(/name="fotos"/g) || []).length, audio: /name="audio"; filename="visite\.\w+"/.test(body),
        toestemming: veld('toestemming'), aanduiding: veld('aanduiding'), nadictaat: veld('nadictaat_vanaf'),
        opgenomen: Number(veld('opgenomen')) });
      json(200, { id: 'v1', status: 'verwerken' });
    });
    return;
  }
  json(404, {});
});

(async () => {
  await new Promise((r) => server.listen(0, r));
  const base = 'http://localhost:' + server.address().port;
  const browser = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await ctx.grantPermissions(['microphone'], { origin: base });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('dialog', (d) => d.accept());

  console.log('A. Gekoppeld via de QR-code');
  await page.goto(base + '/v#toestel-123');
  await page.waitForSelector('#klaar:not(.hidden)', { timeout: 5000 }).catch(() => {});
  check('pagina klaar, modus zichtbaar', (await page.textContent('#pil')).includes('EU-modus'));
  check('sleutel uit de adresbalk', !page.url().includes('toestel-123'));
  check('sleutel bewaard op het toestel', await page.evaluate(() => localStorage.getItem('vsVisiteToestel')) === 'toestel-123');
  check('start pas na toestemming', await page.$eval('#start', (b) => b.disabled));

  console.log('B. Opnemen en nadicteren');
  await page.fill('#aanduiding', 'mw. J., wond');
  await page.check('#toestemming');
  await page.click('#start');
  await page.waitForSelector('#opname:not(.hidden)', { timeout: 5000 });
  await sleep(2200);
  await page.click('#nadicteer');
  check('nadicteren gemarkeerd, knop weg', (await page.textContent('#nad-label')).startsWith('Nadicteren sinds 00:0') &&
    await page.$eval('#nadicteer', (b) => b.classList.contains('hidden')));
  await sleep(1200);
  await page.click('#stop');
  await page.waitForSelector('#na:not(.hidden)', { timeout: 5000 });
  check('na stop: overzicht met duur en aanduiding', (await page.textContent('#na-titel')).includes('mw. J., wond') &&
    (await page.textContent('#na-sub')).includes('nadictaat'));

  console.log('C. Foto toevoegen');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
  await page.setInputFiles('#foto-invoer', { name: 'wond.png', mimeType: 'image/png', buffer: png });
  await page.waitForSelector('#fotos img', { timeout: 5000 }).catch(() => {});
  check('foto als miniatuur bij de visite', (await page.$$('#fotos img')).length === 1);

  console.log('D. Versturen zonder bereik');
  await ctx.setOffline(true);
  await page.click('#verstuur');
  await sleep(800);
  check('melding: wacht versleuteld op bereik', (await page.textContent('#melding')).includes('versleuteld op deze telefoon'));
  check('wachtbalk: 1 visite wacht', (await page.textContent('#wacht-tekst')) === '1 visite wacht op bereik');
  const opslag = await page.evaluate(() => new Promise((ok) => {
    const r = indexedDB.open('vitascribe-visite-telefoon');
    r.onsuccess = () => {
      const q = r.result.transaction('wachtrij').objectStore('wachtrij').getAll();
      q.onsuccess = () => {
        const it = q.result[0];
        const tekst = new TextDecoder('latin1').decode(new Uint8Array(it.meta.data));
        ok({ aantal: q.result.length, sleutels: Object.keys(it).sort().join(), fotos: it.fotos.length,
             leesbaar: tekst.includes('mw. J.'), audioIsBuffer: it.audio.data instanceof ArrayBuffer });
      };
    };
  }));
  check('in de wachtrij: versleuteld, aanduiding niet leesbaar', opslag.aantal === 1 && !opslag.leesbaar && opslag.audioIsBuffer &&
    opslag.fotos === 1 && opslag.sleutels === 'audio,fotos,gemaakt,id,meta', opslag);
  check('niets verstuurd zonder bereik', ontvangen.length === 0);

  console.log('E. Weer bereik');
  await ctx.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  for (let i = 0; i < 30 && !ontvangen.length; i++) await sleep(200);
  await sleep(500);
  const o = ontvangen[0] || {};
  check('vanzelf verstuurd: opname, toestemming, aanduiding', o.audio && o.toestemming === 'true' && o.aanduiding === 'mw. J., wond', o);
  check('met nadictaat-moment en foto', Number(o.nadictaat) >= 2 && Number(o.nadictaat) < 4 && o.fotos === 1, o);
  check('tijdstip van opnemen, niet van versturen', o.opgenomen > 0 && Date.now() / 1000 - o.opgenomen < 60, o);
  check('wachtrij leeg en melding verstuurd', await page.$eval('#wacht', (e) => e.classList.contains('hidden')) &&
    (await page.textContent('#melding')).includes('Verstuurd'));
  const rest = await page.evaluate(() => new Promise((ok) => {
    const r = indexedDB.open('vitascribe-visite-telefoon');
    r.onsuccess = () => { const q = r.result.transaction('wachtrij').objectStore('wachtrij').count(); q.onsuccess = () => ok(q.result); };
  }));
  check('niets meer op de telefoon', rest === 0, rest);
  check('geen JS-fouten', errs.length === 0, errs);

  await browser.close();
  server.close();
  console.log(`\n${ok} geslaagd, ${fail} mislukt`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

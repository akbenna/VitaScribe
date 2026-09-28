/**
 * End-to-end test of the consult recording, A to Z, in Chromium with a fake
 * microphone and a small simulated server (no API keys, no patient data).
 *
 *   node tests/e2e/consult.e2e.js
 *
 * What a doctor does, in order:
 *   A. no key set: the popup says so and nothing is recorded
 *   B. wrong key: refused before the microphone opens
 *   C. start from the popup: popup closes, REC on the icon, small pill on the
 *      page; the side panel stays closed
 *   D. other pages, another site: the pill follows, the timer keeps running;
 *      the pill can be dragged aside and keeps its place
 *   E. side panel opened on purpose: only the small bar
 *   F. Nadicteren and Stop from the pill: report ready, ✓ on the icon
 *   G. click in the S line, "Invoegen" on the pill: S/O/E/P filled
 *   H. server down: recording kept, "Opnieuw versturen" makes the report
 *
 * The pill lives in a closed shadow root (the page cannot reach it), so the
 * test finds and clicks it through the DevTools protocol.
 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

// EXT_DIR: test another build, e.g. the unpacked store zip.
const EXT = process.env.EXT_DIR || path.resolve(__dirname, '..', '..', 'chrome-extension');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// SHOTS=<map>: screenshots of the pill in each state, to look at by eye.
const shot = (page, name) => process.env.SHOTS
  ? page.screenshot({ path: path.join(process.env.SHOTS, name + '.png') })
  : null;

let ok = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { ok++; console.log('  OK  ', name); }
  else { fail++; console.log('  FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); }
}

// ── Simulated server ──

const uploads = [];
let failUploads = false;
const REPORT = {
  soep: { s: 'Sinds 3 dagen keelpijn, geen koorts.', o: 'Keel rood, geen beslag.', e: 'Virale faryngitis.',
          p: 'Paracetamol zo nodig. Terug bij koorts > 3 dagen.', icpc_code: 'R74', icpc_titel: 'Acute infectie bovenste luchtwegen' },
  decisief: 'Keelpijn 3d, viraal (R74), expectatief',
};
const CONSULT_PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>Consult</title></head><body>
<h1>Consult</h1>
<label>S <textarea id="S" rows="2"></textarea></label>
<label>O <textarea id="O" rows="2"></textarea></label>
<label>E <textarea id="E" rows="2"></textarea></label>
<label>ICPC <input id="ICPC" maxlength="6"></label>
<label>P <textarea id="P" rows="2"></textarea></label>
</body></html>`;

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
}
const server = http.createServer((req, res) => {
  cors(res);
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/api/v1/providers') {
    const key = req.headers['x-api-key'];
    if (!key) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"detail":"API sleutel ontbreekt."}'); return; }
    if (key !== 'goed') { res.writeHead(403, { 'Content-Type': 'application/json' }); res.end('{"detail":"Ongeldige API sleutel."}'); return; }
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end('{"llm":{"available":{}}}'); return;
  }
  if (url.pathname === '/api/v1/consult/process' && req.method === 'POST') {
    const parts = [];
    req.on('data', (d) => parts.push(d));
    req.on('end', () => {
      const body = Buffer.concat(parts).toString('latin1');
      uploads.push({ bytes: body.length, key: req.headers['x-api-key'], consent: /name="consent"\r\n\r\ntrue/.test(body),
                     nadictaat: /name="nadictaat_vanaf"/.test(body) });
      if (failUploads) { res.writeHead(503, { 'Content-Type': 'application/json' }); res.end('{"detail":"Server tijdelijk niet beschikbaar"}'); return; }
      res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(REPORT));
    });
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(url.pathname === '/consult' ? CONSULT_PAGE : `<!doctype html><title>${url.pathname}</title><h1>${url.pathname}</h1><p>Andere pagina</p>`);
});

// ── The pill, through the DevTools protocol ──

async function pill(page) {
  const cdp = await page.context().newCDPSession(page);
  try {
    const { root } = await cdp.send('DOM.getDocument', { depth: -1, pierce: true });
    let host = null;
    (function walk(n) {
      if (host || !n) return;
      if (n.shadowRoots && n.shadowRoots.some((sr) => JSON.stringify(sr).includes('data-cmd'))) { host = n; return; }
      (n.children || []).forEach(walk);
      (n.shadowRoots || []).forEach(walk);
    })(root);
    if (!host) return null;
    const style = (host.attributes || []).join(' ');
    const shadow = host.shadowRoots.find((sr) => JSON.stringify(sr).includes('data-cmd'));
    const text = [];
    const buttons = {};
    (function walk(n) {
      if (n.nodeType === 3 && n.parentId && n.nodeValue.trim()) text.push(n.nodeValue.trim());
      if (n.nodeName === 'STYLE') return;
      if (n.nodeName === 'BUTTON') {
        const a = n.attributes || [];
        const i = a.indexOf('data-cmd');
        buttons[a[i + 1]] = { hidden: a.includes('hidden'), backendNodeId: n.backendNodeId };
      }
      (n.children || []).forEach(walk);
    })(shadow);
    return { visible: !/display:\s*none/.test(style), style, text: text.join(' '), buttons };
  } finally {
    await cdp.detach().catch(() => {});
  }
}

async function clickPill(page, cmd) {
  const p = await pill(page);
  if (!p || !p.buttons[cmd] || p.buttons[cmd].hidden) throw new Error('knop ' + cmd + ' niet zichtbaar: ' + JSON.stringify(p));
  const cdp = await page.context().newCDPSession(page);
  const { model } = await cdp.send('DOM.getBoxModel', { backendNodeId: p.buttons[cmd].backendNodeId });
  await cdp.detach();
  const q = model.content;
  await page.mouse.click((q[0] + q[4]) / 2, (q[1] + q[5]) / 2);
}

(async () => {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}`;

  const launchOpts = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};
  const ctx = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), 'sv-consult-')), {
    ...launchOpts, headless: false, viewport: { width: 1000, height: 700 },
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, '--headless=new',
           '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  });
  const isExt = (w) => w.url().startsWith('chrome-extension://');
  const sw = ctx.serviceWorkers().find(isExt) || await ctx.waitForEvent('serviceworker', isExt);
  for (let i = 0; i < 100; i++) {
    if (await sw.evaluate(() => !!(self.chrome && chrome.storage && chrome.storage.sync))) break;
    await sleep(100);
  }
  const id = new URL(sw.url()).host;
  const errs = [];
  const badge = () => sw.evaluate(() => chrome.action.getBadgeText({}));
  const openPopup = async () => {
    const pop = await ctx.newPage();
    pop.on('pageerror', (e) => errs.push('popup: ' + e.message));
    await pop.goto(`chrome-extension://${id}/popup/popup.html`);
    await sleep(400);
    return pop;
  };
  await sw.evaluate(async (url) => {
    await chrome.storage.sync.set({ apiUrl: url, consultLive: 'uit' });
  }, base);

  const tab = await ctx.newPage();
  tab.on('pageerror', (e) => errs.push('page: ' + e.message));
  await tab.goto(base + '/consult');
  await sleep(600);

  console.log('A. Geen sleutel');
  let pop = await openPopup();
  check('popup meldt ontbrekende sleutel', await pop.isVisible('#no-key'));
  await pop.click('#btn-start');
  await sleep(400);
  check('start zonder sleutel geweigerd', (await pop.textContent('#status-text')).includes('sleutel'));
  check('geen opname gestart', (await badge()) === '');
  await pop.close();

  console.log('B. Verkeerde sleutel');
  await sw.evaluate(() => chrome.storage.local.set({ apiKey: 'fout' }));
  pop = await openPopup();
  check('sleutel ingevuld: geen waarschuwing meer', !(await pop.isVisible('#no-key')));
  await pop.click('#btn-start');
  await sleep(800);
  const refusal = await pop.textContent('#status-text');
  check('verkeerde sleutel geweigerd vóór de opname', /accepteert de VitaScribe-sleutel niet/.test(refusal), refusal);
  check('nog steeds geen opname', (await badge()) === '' && uploads.length === 0);
  await pop.close();

  console.log('C. Start vanuit de popup');
  await sw.evaluate(() => chrome.storage.local.set({ apiKey: 'goed' }));
  pop = await openPopup();
  check('één knop, toestemming in de tekst', (await pop.textContent('#consent-note')).includes('toestemming') && !(await pop.$('#consent-recording')));
  const closed = pop.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
  await pop.click('#btn-start');
  check('popup sluit na starten', await closed);
  await sleep(1500);
  check('REC op het icoon', (await badge()) === 'REC');
  let p = await pill(tab);
  check('bolletje op de pagina met tijd, Nadicteren en Stop',
    p && p.visible && /\d\d:\d\d/.test(p.text) && !p.buttons.stop.hidden && !p.buttons.nadictaat.hidden && p.buttons.insert.hidden, p);
  await shot(tab, '1-opname');
  const pages = ctx.pages().map((x) => x.url());
  check('zijpaneel niet vanzelf geopend', !pages.some((u) => u.includes('sidepanel')), pages);

  console.log('D. Andere pagina\'s');
  await tab.goto(base + '/agenda');
  await sleep(700);
  const other = await ctx.newPage();
  await other.goto(`http://localhost:${port}/elders`);   // other origin, other tab
  await sleep(1200);
  p = await pill(other);
  const secs = p && p.text.match(/(\d\d):(\d\d)/);
  check('bolletje ook in ander tabblad, tijd loopt door', p && p.visible && secs && Number(secs[1]) * 60 + Number(secs[2]) >= 2, p && p.text);
  // Drag the pill 200 px to the left and 100 px up; the next page keeps the place.
  const box = await other.evaluate(() => {
    const host = [...document.documentElement.children].find((e) => e.shadowRoot === null && e.style.position === 'fixed' && e.style.bottom === '72px');
    const r = host.getBoundingClientRect();
    return { x: r.left + 12, y: r.top + r.height / 2 };
  });
  await other.mouse.move(box.x, box.y);
  await other.mouse.down();
  await other.mouse.move(box.x - 200, box.y - 100, { steps: 5 });
  await other.mouse.up();
  await sleep(300);
  await other.goto(`http://localhost:${port}/elders2`);
  await sleep(900);
  p = await pill(other);
  check('verschoven bolletje houdt zijn plek', p && /right:\s*216px/.test(p.style) && /bottom:\s*172px/.test(p.style), p && p.style);
  await other.close();
  await tab.goto(base + '/consult');
  await sleep(800);
  check('terug in het consult: opname loopt nog', (await badge()) === 'REC' && (await pill(tab)).visible);

  console.log('E. Zijpaneel bewust geopend');
  const panel = await ctx.newPage();
  panel.on('pageerror', (e) => errs.push('panel: ' + e.message));
  await panel.goto(`chrome-extension://${id}/sidepanel/sidepanel.html`);
  await sleep(700);
  const visible = await panel.evaluate(() => [...document.querySelectorAll('#view-dictate > *, .views, .footer')]
    .filter((e) => e.offsetParent !== null && e.id !== 'status').map((e) => e.id || e.className));
  check('zijpaneel toont alleen het opnamebalkje', visible.length === 1 && visible[0] === 'consult', visible);
  await panel.close();

  console.log('F. Nadicteren en Stop via het bolletje');
  await clickPill(tab, 'nadictaat');
  await sleep(500);
  p = await pill(tab);
  check('nadicteren zichtbaar, knop weg', p.text.includes('nadicteren') && p.buttons.nadictaat.hidden, p.text);
  await clickPill(tab, 'stop');
  await sleep(2000);
  p = await pill(tab);
  check('verslag klaar in het bolletje', p.text.includes('Verslag klaar') && !p.buttons.insert.hidden && !p.buttons.show.hidden, p.text);
  check('✓ op het icoon', (await badge()) === '✓');
  await shot(tab, '2-verslag-klaar');
  const up = uploads[uploads.length - 1] || {};
  check('hele opname met sleutel, toestemming en nadictaat verstuurd', up.bytes > 10000 && up.key === 'goed' && up.consent && up.nadictaat, up);

  console.log('G. Invoegen in de velden');
  await clickPill(tab, 'insert');
  await sleep(700);
  p = await pill(tab);
  check('zonder aangeklikte S-regel: uitleg in het bolletje', p.visible && p.text.includes('S-regel'), p.text);
  await tab.click('#S');
  await sleep(300);
  await clickPill(tab, 'insert');
  await sleep(900);
  const fields = await tab.evaluate(() => ['S', 'O', 'E', 'ICPC', 'P'].map((f) => document.getElementById(f).value));
  check('S, O, E, ICPC en P ingevuld', fields[0].includes('keelpijn') && fields[1].includes('Keel rood') &&
    fields[2].includes('faryngitis') && fields[3] === 'R74' && fields[4].includes('Paracetamol'), fields);
  p = await pill(tab);
  check('bolletje weg en icoon leeg na invoegen', !p.visible && (await badge()) === '', p && p.text);
  pop = await openPopup();
  check('popup: klaar voor het volgende consult, laatste verslag nog op te vragen',
    await pop.isVisible('#btn-start') && await pop.isVisible('#btn-last'));
  await pop.close();

  console.log('H. Server onbereikbaar tijdens verwerken');
  failUploads = true;
  pop = await openPopup();
  const closed2 = pop.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
  await pop.click('#btn-start');
  await closed2;
  await sleep(2500);
  await clickPill(tab, 'stop');
  await sleep(1500);
  p = await pill(tab);
  check('foutmelding met "Opnieuw versturen", opname bewaard', p.text.includes('bewaard') && !p.buttons.retry.hidden, p.text);
  check('! op het icoon', (await badge()) === '!');
  await shot(tab, '3-fout-bewaard');
  failUploads = false;
  await clickPill(tab, 'retry');
  await sleep(1500);
  p = await pill(tab);
  check('na opnieuw versturen: verslag klaar', p.text.includes('Verslag klaar'), p.text);
  check('dezelfde opname opnieuw verstuurd', uploads.length >= 3 && uploads[uploads.length - 1].bytes === uploads[uploads.length - 2].bytes);
  pop = await openPopup();
  check('popup toont het verslag', (await pop.textContent('#soep-e')).includes('faryngitis') && (await pop.textContent('#decisief-text')).includes('R74'));
  await pop.click('#btn-new-consult');
  await sleep(500);
  check('"Klaar" ruimt bolletje en icoon op', !(await pill(tab)).visible && (await badge()) === '');

  check('geen JS-fouten', errs.length === 0, errs);
  console.log(`\n${ok} geslaagd, ${fail} mislukt`);
  await ctx.close();
  server.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); server.close(); process.exit(1); });

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
let twoProblems = false;
let noSpeech = false;
const REPORT = {
  soep: { s: 'Sinds 3 dagen keelpijn, geen koorts.', o: 'Keel rood, geen beslag.', e: 'Virale faryngitis.',
          p: 'Paracetamol zo nodig. Terug bij koorts > 3 dagen.', icpc_code: 'R74', icpc_titel: 'Acute infectie bovenste luchtwegen' },
  decisief: 'Keelpijn 3d, viraal (R74), expectatief',
  transcript_raw: 'Ik heb sinds drie dagen keelpijn, geen koorts.',
};
// Two separate problems, one of them psychological: two SOEP parts.
const REPORT2 = {
  soep: {
    s: '3d keelpijn.', o: 'Keel rood.', e: 'Virale faryngitis.', p: 'Paracetamol zn.', icpc_code: 'R74', icpc_titel: 'Acute infectie bovenste luchtwegen',
    problemen: [
      { titel: 'Keelpijn', s: '3d keelpijn.', o: 'Keel rood.', e: 'Virale faryngitis.', p: 'Paracetamol zn.', icpc_code: 'R74', icpc_titel: 'Acute infectie bovenste luchtwegen' },
      { titel: 'Somberheid', s: 'Somber sinds 2 mnd na ontslag; slaapt slecht. Geen suïcidegedachten.', o: 'Vlak affect, goed contact.',
        e: 'Depressieve klachten.', p: 'Afspraak POH-GGZ over 1 wk.', icpc_code: 'P03', icpc_titel: 'Depressief gevoel' },
    ],
  },
  decisief: 'Keelpijn (R74) en somberheid (P03)',
  transcript_raw: 'Keelpijn en ik voel me somber sinds mijn ontslag.',
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
                     nadictaat: /name="nadictaat_vanaf"/.test(body),
                     taal: (/name="taal"\r\n\r\n(\w+)/.exec(body) || [])[1] });
      if (failUploads) { res.writeHead(503, { 'Content-Type': 'application/json' }); res.end('{"detail":"Server tijdelijk niet beschikbaar"}'); return; }
      res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(noSpeech
        ? { soep: { s: '', o: '', e: '', p: '' }, decisief: 'Geen spraak gedetecteerd.', transcript_raw: '', duration_secs: 4.2 }
        : twoProblems ? REPORT2 : REPORT));
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

// The quick-dictation pill (also shown while the side panel dictates).
async function listenPill(page, clickStop) {
  const cdp = await page.context().newCDPSession(page);
  try {
    const { root } = await cdp.send('DOM.getDocument', { depth: -1, pierce: true });
    let shadow = null;
    (function walk(n) {
      if (shadow || !n) return;
      (n.shadowRoots || []).forEach((sr) => { if (!shadow && JSON.stringify(sr).includes('Sluiten (Esc)')) shadow = { sr, host: n }; });
      (n.children || []).forEach(walk);
    })(root);
    if (!shadow) return { visible: false, text: '' };
    const text = [];
    let stop = null;
    (function walk(n) {
      if (n.nodeName === 'STYLE') return;
      if (n.nodeType === 3 && n.nodeValue.trim()) text.push(n.nodeValue.trim());
      if (n.nodeName === 'BUTTON' && (n.attributes || []).includes('a')) stop = n;
      (n.children || []).forEach(walk);
    })(shadow.sr);
    const visible = !/display:\s*none/.test((shadow.host.attributes || []).join(' '));
    if (clickStop && stop) {
      const { model } = await cdp.send('DOM.getBoxModel', { backendNodeId: stop.backendNodeId });
      const q = model.content;
      await page.mouse.click((q[0] + q[4]) / 2, (q[1] + q[5]) / 2);
    }
    return { visible, text: text.join(' ') };
  } finally {
    await cdp.detach().catch(() => {});
  }
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
  // Question suggestions as the server sends them (live consult, switched on).
  await sw.evaluate(() => handleConsultEvent({ type: 'suggesties', klacht: 'keelpijn',
    vragen: [{ tekst: 'koorts?', alarm: false }, { tekst: 'stridor?', alarm: true }] }));
  await sleep(500);
  const chips = await panel.$$eval('#cv-chips .cv-chip', (b) => b.map((x) => x.textContent + (x.classList.contains('alarm') ? '!' : '')));
  check('vraagsuggesties als chips onder het opnamebalkje, alarm apart', chips.join(',') === 'koorts?,stridor?!', chips);
  await panel.click('#cv-chips .cv-chip');
  check('chip aantikken = gevraagd (doorgestreept)', await panel.$eval('#cv-chips .cv-chip', (b) => b.classList.contains('gedaan')));
  const pillNu = await pill(tab);
  check('bolletje op de pagina toont geen suggesties (geen patiënttekst)', !/koorts|stridor/.test(pillNu.text), pillNu.text);
  const popV = await openPopup();
  check('popup toont dezelfde suggesties', (await popV.textContent('#rec-vragen')).includes('stridor?'));
  await popV.close();
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

  console.log('G. Zijpaneel en bolletje tonen hetzelfde verslag');
  const side = await ctx.newPage();
  side.on('pageerror', (e) => errs.push('panel: ' + e.message));
  await side.goto(`chrome-extension://${id}/sidepanel/sidepanel.html`);
  await sleep(700);
  // In this test the panel is itself a tab; let "active tab" mean the consult tab.
  await side.evaluate((b) => {
    const q = chrome.tabs.query.bind(chrome.tabs);
    chrome.tabs.query = async (o) => (o && o.active ? q({ url: b + '/consult' }) : q(o));
  }, base);
  check('zijpaneel toont hetzelfde verslag met decisief',
    (await side.$eval('.soep-text[data-key="s"]', (e) => e.textContent)) === REPORT.soep.s &&
    (await side.textContent('#soep-decisief')).includes('R74'));
  await side.evaluate(() => {
    const s = document.querySelector('.soep-text[data-key="s"]');
    s.textContent = 'Sinds 3 dagen keelpijn, aangepast in het zijpaneel.';
    s.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await sleep(900);
  const edited = await sw.evaluate(() => chrome.storage.session.get('svConsult').then((r) => r.svConsult.result.soep.s));
  check('aanpassing in het zijpaneel gaat mee naar het verslag', edited.includes('aangepast in het zijpaneel'), edited);
  await tab.bringToFront();

  console.log('H. Invoegen in de velden via het bolletje');
  await clickPill(tab, 'insert');
  await sleep(700);
  p = await pill(tab);
  check('zonder aangeklikte S-regel: uitleg in het bolletje', p.visible && p.text.includes('S-regel'), p.text);
  await tab.click('#S');
  await sleep(300);
  await clickPill(tab, 'insert');
  await sleep(900);
  const fields = await tab.evaluate(() => ['S', 'O', 'E', 'ICPC', 'P'].map((f) => document.getElementById(f).value));
  check('S, O, E, ICPC en P ingevuld, met de aangepaste S', fields[0].includes('aangepast in het zijpaneel') && fields[1].includes('Keel rood') &&
    fields[2].includes('faryngitis') && fields[3] === 'R74' && fields[4].includes('Paracetamol'), fields);
  p = await pill(tab);
  check('bolletje weg en icoon leeg na invoegen', !p.visible && (await badge()) === '', p && p.text);
  pop = await openPopup();
  check('popup: klaar voor het volgende consult, laatste verslag nog op te vragen',
    await pop.isVisible('#btn-start') && await pop.isVisible('#btn-last'));
  await pop.close();

  console.log('I. Server onbereikbaar tijdens verwerken');
  failUploads = true;
  pop = await openPopup();
  const closed2 = pop.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
  await pop.click('#btn-start');
  await closed2;
  await sleep(3500);
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
  await pop.close();

  console.log('J. Invoegen via het zijpaneel ruimt het bolletje ook op');
  for (const f of ['S', 'O', 'E', 'ICPC', 'P']) await tab.fill('#' + f, '');
  await tab.click('#S');
  await sleep(300);
  await side.bringToFront();
  check('zijpaneel toont het nieuwe verslag', (await side.$eval('.soep-text[data-key="s"]', (e) => e.textContent)) === REPORT.soep.s);
  await side.click('#btn-soep-insert');
  await sleep(1000);
  check('ingevoegd vanuit het zijpaneel', (await tab.inputValue('#E')).includes('faryngitis'));
  check('bolletje en icoon opgeruimd', !(await pill(tab)).visible && (await badge()) === '');

  console.log('K. Dicteren: paneel en pagina lopen gelijk');
  await tab.bringToFront();
  await side.evaluate(() => {
    window.__gestopt = false;
    window.toggleDictation = function () { window.__gestopt = true; setState('idle'); };
    setState('recording');
  });
  await sleep(700);
  let lp = await listenPill(tab);
  check('dicteren in het zijpaneel toont het opnameteken op de pagina', lp.visible && lp.text.includes('luistert'), lp);
  await listenPill(tab, true);
  await sleep(700);
  check('Stop op de pagina stopt het dicteren in het zijpaneel', await side.evaluate(() => window.__gestopt));
  lp = await listenPill(tab);
  check('opnameteken weg na stoppen', !lp.visible, lp);
  pop = await openPopup();
  await pop.evaluate(() => chrome.runtime.sendMessage({ action: 'SV_QUICK_EVENT', type: 'final', text: 'Snel gedicteerd met Alt+Shift+D.' }));
  await sleep(500);
  await pop.close();
  check('snel dicteren (Alt+Shift+D) verschijnt ook in het zijpaneel', (await side.inputValue('#text')).includes('Snel gedicteerd'));

  console.log('L. Twee problemen: twee SOEP-delen, één voor één');
  twoProblems = true;
  for (const f of ['S', 'O', 'E', 'ICPC', 'P']) await tab.fill('#' + f, '');
  pop = await openPopup();
  const closed3 = pop.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
  await pop.click('#btn-start');
  await closed3;
  await sleep(3500);
  await tab.bringToFront();
  await clickPill(tab, 'stop');
  await sleep(1800);
  p = await pill(tab);
  check('bolletje: verslag klaar, deel 1/2', p.text.includes('deel 1/2') && p.text.includes('Invoegen deel 1'), p.text);
  await side.bringToFront();
  await sleep(300);
  const tabsText = await side.$$eval('#soep-delen .soep-deel', (b) => b.map((x) => x.textContent));
  check('zijpaneel: twee tabs per probleem', tabsText.length === 2 && tabsText[0].includes('Keelpijn') && tabsText[1].includes('Somberheid (P03)'), tabsText);
  check('knop heet "Deel 1 invoegen"', (await side.textContent('#btn-soep-insert')) === 'Deel 1 invoegen');
  await side.click('#soep-delen .soep-deel:nth-child(2)');
  await sleep(200);
  await shot(side, '4-twee-delen');
  check('tab 2 toont de psychische SOEP', (await side.$eval('.soep-text[data-key="o"]', (e) => e.textContent)).includes('Vlak affect') &&
    (await side.textContent('#icpc-code')) === 'P03');
  await side.evaluate(() => {
    const n = document.querySelector('.soep-text[data-key="p"]');
    n.textContent = 'Afspraak POH-GGZ over 1 wk; eerder contact bij verergering.';
    n.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await sleep(900);
  const part2 = await sw.evaluate(() => chrome.storage.session.get('svConsult').then((r) => r.svConsult.result.soep.problemen[1].p));
  check('aanpassing in deel 2 gaat mee', part2.includes('eerder contact'), part2);
  await tab.bringToFront();
  await tab.click('#S');
  await sleep(300);
  await clickPill(tab, 'insert');
  await sleep(900);
  check('deel 1 in de S-regel', (await tab.inputValue('#S')).includes('keelpijn') && (await tab.inputValue('#ICPC')) === 'R74');
  p = await pill(tab);
  check('bolletje wijst naar deel 2 met uitleg', p.visible && p.text.includes('deel 2/2') && p.text.includes('nieuwe SOEP-regel'), p.text);
  check('zijpaneel vinkt deel 1 af', await side.$eval('#soep-delen .soep-deel:nth-child(1)', (b) => b.classList.contains('done')));
  for (const f of ['S', 'O', 'E', 'ICPC', 'P']) await tab.fill('#' + f, '');   // "new SOEP line"
  await tab.click('#S');
  await sleep(300);
  await clickPill(tab, 'insert');
  await sleep(900);
  const f2 = await tab.evaluate(() => ['S', 'O', 'E', 'ICPC', 'P'].map((f) => document.getElementById(f).value));
  check('deel 2 in de nieuwe regel, met de aanpassing', f2[0].includes('Somber') && f2[3] === 'P03' && f2[4].includes('eerder contact'), f2);
  p = await pill(tab);
  check('na het laatste deel: bolletje en icoon leeg', !p.visible && (await badge()) === '');

  console.log('N. Te kort, geen spraak, en niet tegelijk met dicteren');
  const startConsult = async () => {
    const pp = await openPopup();
    const dicht = pp.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
    await pp.click('#btn-start');
    return dicht;
  };
  await startConsult();
  await sleep(1200);
  await tab.bringToFront();
  await clickPill(tab, 'stop');
  await sleep(1200);
  p = await pill(tab);
  const nUploads = uploads.length;
  check('opname van 1 s: niet verwerkt, uitleg', p.text.includes('niet verwerkt') && /\d s/.test(p.text), p.text);
  await clickPill(tab, 'dismiss');
  noSpeech = true;
  await startConsult();
  await sleep(3500);
  await clickPill(tab, 'stop');
  await sleep(1500);
  p = await pill(tab);
  check('geen spraak: melding met microfoontip, geen leeg verslag', p.text.includes('geen spraak') && p.text.includes('microfoon') && (await badge()) === '!', p.text);
  check('korte opname is nooit verstuurd', uploads.length === nUploads + 1);
  noSpeech = false;
  await clickPill(tab, 'dismiss');
  await side.evaluate(() => { window.toggleDictation = function () {}; setState('recording'); });
  await sleep(500);
  const pp2 = await openPopup();
  await pp2.click('#btn-start');
  await sleep(700);
  check('consult start niet terwijl het zijpaneel dicteert', (await pp2.textContent('#status-text')).includes('dicteren in het zijpaneel') && (await badge()) === '', await pp2.textContent('#status-text'));
  await pp2.close();
  await side.evaluate(() => setState('idle'));
  await sleep(300);

  console.log('P. Taal van het gesprek');
  const popT = await openPopup();
  check('taalkeuze staat op Nederlands', (await popT.inputValue('#consult-taal')) === 'nl');
  check('standaard consult ging als Nederlands', uploads.slice(0, -1).every((u) => u.taal === 'nl'), uploads.map((u) => u.taal));
  await popT.selectOption('#consult-taal', 'tr');
  const dichtT = popT.waitForEvent('close', { timeout: 5000 }).then(() => true, () => false);
  await popT.click('#btn-start');
  await dichtT;
  await sleep(1500);
  const popT2 = await openPopup();
  check('tijdens de opname staat de taal erbij', (await popT2.textContent('#rec-label')).includes('Turks'), await popT2.textContent('#rec-label'));
  await popT2.close();
  await sleep(2200);
  await tab.bringToFront();
  await clickPill(tab, 'stop');
  await sleep(1500);
  check('opname verstuurd met taal=tr', uploads[uploads.length - 1].taal === 'tr', uploads[uploads.length - 1]);
  const popT3 = await openPopup();
  await popT3.click('#btn-new-consult').catch(() => {});
  await sleep(300);
  check('volgende consult weer Nederlands', (await popT3.inputValue('#consult-taal')) === 'nl');
  await popT3.close();

  console.log('M. Schakelaar vraagsuggesties in Instellingen');
  const opt = await ctx.newPage();
  opt.on('pageerror', (e) => errs.push('options: ' + e.message));
  await opt.goto(`chrome-extension://${id}/options/options.html`);
  await sleep(600);
  check('schakelaar staat standaard uit', !(await opt.isChecked('#vraagsuggesties')));
  await opt.check('#vraagsuggesties');
  await sleep(400);
  const cfg = await sw.evaluate(() => consultConfig());
  check('aan = meegestuurd naar de opname', cfg.vraagsuggesties === true, cfg.vraagsuggesties);
  await opt.uncheck('#vraagsuggesties');
  await sleep(400);
  check('uit = niet meer meegestuurd', (await sw.evaluate(() => consultConfig())).vraagsuggesties === false);
  await opt.close();

  console.log('O. Microfoon hoort niets');
  await ctx.close();
  // A second browser whose microphone only delivers silence (a WAV of zeros).
  const wav = path.join(os.tmpdir(), 'sv-stil.wav');
  const n = 16000 * 12;
  const hdr = Buffer.alloc(44);
  hdr.write('RIFF', 0); hdr.writeUInt32LE(36 + n * 2, 4); hdr.write('WAVE', 8); hdr.write('fmt ', 12);
  hdr.writeUInt32LE(16, 16); hdr.writeUInt16LE(1, 20); hdr.writeUInt16LE(1, 22); hdr.writeUInt32LE(16000, 24);
  hdr.writeUInt32LE(32000, 28); hdr.writeUInt16LE(2, 32); hdr.writeUInt16LE(16, 34); hdr.write('data', 36); hdr.writeUInt32LE(n * 2, 40);
  fs.writeFileSync(wav, Buffer.concat([hdr, Buffer.alloc(n * 2)]));
  const ctx2 = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), 'sv-stil-')), {
    ...launchOpts, headless: false, viewport: { width: 1000, height: 700 },
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, '--headless=new',
           '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`],
  });
  const sw2 = ctx2.serviceWorkers().find(isExt) || await ctx2.waitForEvent('serviceworker', isExt);
  for (let i = 0; i < 100; i++) {
    if (await sw2.evaluate(() => !!(self.chrome && chrome.storage && chrome.storage.sync))) break;
    await sleep(100);
  }
  const id2 = new URL(sw2.url()).host;
  await sw2.evaluate(async (url) => {
    await chrome.storage.sync.set({ apiUrl: url, consultLive: 'uit' });
    await chrome.storage.local.set({ apiKey: 'goed' });
  }, base);
  const tab2 = await ctx2.newPage();
  await tab2.goto(base + '/consult');
  await sleep(600);
  const pop2 = await ctx2.newPage();
  await pop2.goto(`chrome-extension://${id2}/popup/popup.html`);
  await sleep(400);
  await pop2.click('#btn-start').catch(() => {});
  await sleep(4000);
  let p2 = await pill(tab2);
  check('na 4 s stilte nog geen waarschuwing', p2 && p2.visible && !p2.text.includes('geen geluid'), p2 && p2.text);
  await sleep(6000);
  p2 = await pill(tab2);
  check('na 8 s zonder enig geluid: "geen geluid: microfoon?" in het bolletje', p2 && p2.text.includes('geen geluid'), p2 && p2.text);
  await ctx2.close();

  check('geen JS-fouten', errs.length === 0, errs);
  console.log(`\n${ok} geslaagd, ${fail} mislukt`);
  server.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); server.close(); process.exit(1); });

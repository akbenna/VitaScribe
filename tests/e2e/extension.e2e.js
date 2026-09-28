/**
 * End-to-end tests of the VitaScribe extension in Chromium, against a
 * simulated Bricks page and a mocked server (no API keys, no patient data).
 *
 *   npm i -D playwright && npx playwright install chromium
 *   node tests/e2e/extension.e2e.js
 *
 * CHROMIUM_PATH can point at an existing Chromium build.
 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const EXT = path.join(ROOT, 'chrome-extension');
const HERE = __dirname;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const BRICKS = fs.readFileSync(path.join(HERE, 'bricks.html'), 'utf8');
const LETTER = 'Geachte collega,\n\n1. Diagnose: aspecifieke lage rugpijn.\n\nMet collegiale groet,\n[Naam huisarts]';

let ok = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { ok++; console.log('  OK  ', name); }
  else { fail++; console.log('  FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); }
}

(async () => {
  const launchOpts = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};
  const b = await chromium.launch(launchOpts);
  const pg = await b.newPage();
  await pg.setContent(fs.readFileSync(path.join(HERE, 'vraag.html'), 'utf8'));
  const vraagPdf = path.join(os.tmpdir(), 'sv-vraag.pdf');
  await pg.pdf({ path: vraagPdf });
  await b.close();

  const ctx = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), 'sv-')), {
    ...launchOpts, headless: false,
    args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, '--headless=new'],
  });
  const sent = [];
  await ctx.route('https://test.bfrcloud.com/**', (r) => r.fulfill({ contentType: 'text/html', body: BRICKS }));
  await ctx.route('http://localhost:8002/api/v1/**', async (r) => {
    const url = r.request().url();
    const body = r.request().postData() ? JSON.parse(r.request().postData()) : null;
    sent.push({ url, body });
    if (url.endsWith('/letters/extract')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ text: 'Journaal\nHoofdpijn\nMedicatie\nParacetamol' }) });
    if (url.endsWith('/letters/generate')) return r.fulfill({ contentType: 'text/plain; charset=utf-8', body: LETTER });
    if (url.endsWith('/dictation/process')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ mode: 'soep', soep: {
      s: '2 wk hoesten', o: 'RR 150/90 mmHg', e: 'Pneumonie', p: 'Amoxicilline 3dd 500 mg', icpc_code: 'R81', icpc_titel: 'Pneumonie',
      aandachtspunten: ['Duur van de kuur ontbreekt in P'] } }) });
    if (url.endsWith('/patient-instructions')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ nl: 'Uw medicijn\nAmoxicilline 500 mg, 3 keer per dag.', vertaling: 'دواؤك', taal: 'Arabisch' }) });
    return r.fulfill({ status: 404, body: '' });
  });
  // The worker can be reported before its extension bindings are installed. On
  // a slow runner chrome.storage is then still undefined and the first call
  // throws, although nothing is wrong with the extension. Wait for the bindings
  // instead of racing them.
  const isExt = (w) => w.url().startsWith('chrome-extension://');
  const sw = ctx.serviceWorkers().find(isExt) || await ctx.waitForEvent('serviceworker', isExt);
  for (let i = 0; i < 100; i++) {
    if (await sw.evaluate(() => !!(self.chrome && chrome.storage && chrome.storage.sync))) break;
    await sleep(100);
  }
  const id = new URL(sw.url()).host;
  await sw.evaluate(async () => {
    await chrome.storage.sync.set({ apiUrl: 'http://localhost:8002' });
    await chrome.storage.local.set({ apiKey: 'test' });
  });
  const page = await ctx.newPage();
  await page.goto('https://test.bfrcloud.com/patient');
  await sleep(800);
  await page.click('#S');
  await sleep(300);

  const errs = [];
  const panel = await ctx.newPage();
  panel.on('pageerror', (e) => errs.push(e.message));
  await panel.goto(`chrome-extension://${id}/sidepanel/sidepanel.html`);
  await sleep(700);
  // In this test the panel is itself a tab; let "active tab" mean the Bricks tab.
  await panel.evaluate(() => {
    const q = chrome.tabs.query.bind(chrome.tabs);
    chrome.tabs.query = async (o) => (o && o.active ? q({ url: 'https://test.bfrcloud.com/*' }) : q(o));
  });

  console.log('Dicteren & SOEP');
  await panel.fill('#text', 'Bij onderzoek RR 152/94, pols 88, sat 96%, temp 38,4 graden. Gewicht 84,5 kg, lengte 1,78 m.');
  await sleep(900);
  const mw = await panel.$$eval('.mw-row', (rows) => rows.map((r) => r.innerText.replace(/\s+/g, ' ')));
  check('meetwaarden herkend', mw.length === 7 && mw[0].includes('152/94') && mw[6].includes('BMI'), mw);
  await page.bringToFront();
  await panel.click('.mw-row:first-child button');
  await sleep(600);
  check('meetwaarde ingevoegd in Bricks-veld', (await page.inputValue('#S')).includes('152/94'));
  await page.fill('#S', '');
  await panel.click('#btn-soep');
  await sleep(900);
  check('SOEP getoond', (await panel.$$eval('.soep-text', (e) => e.map((x) => x.textContent))).includes('Pneumonie'));
  const kaart = await panel.textContent('#soep-check');
  check('kaart heet "Onvolledig in de verslaglegging"', kaart.includes('Onvolledig in de verslaglegging') && kaart.includes('Duur'), kaart);
  // Thuisarts: the shipped table has no URLs yet, so no link may appear. The
  // title lookup after correcting the code can only come from the real table,
  // loaded via chrome.runtime.getURL inside the extension.
  check('geen Thuisarts-link zonder gecontroleerde regel',
    (await panel.textContent('#ta')).includes('Geen Thuisarts-pagina') && (await panel.$$('.ta-chip')).length === 0);
  await panel.click('#icpc-code');
  await panel.keyboard.press('Control+A');
  await panel.keyboard.type('R78');
  await sleep(300);
  check('gecorrigeerde ICPC-code krijgt de titel uit de tabel',
    (await panel.textContent('#icpc-titel')).includes('Acute bronchitis'), await panel.textContent('#icpc-titel'));
  await panel.keyboard.press('Control+A');
  await panel.keyboard.type('R81');
  await sleep(200);
  await panel.click('#btn-patient');
  await panel.selectOption('#pi-taal', 'ar');
  await panel.click('#pi-go');
  await sleep(800);
  const piReq = sent.find((s) => s.url.endsWith('/patient-instructions'));
  check('patiëntinstructie vraagt E+P en taal', piReq && piReq.body.p.includes('Amoxicilline') && piReq.body.taal === 'ar', piReq && piReq.body);
  check('B1 en vertaling getoond', (await panel.inputValue('#pi-nl')).includes('Uw medicijn') && (await panel.isVisible('#pi-tr')));
  check('mailknop verborgen zolang de praktijk hem niet aanzet', await panel.isHidden('#pi-mail'));

  console.log('Brieven');
  await panel.click('.view-tab[data-view="letters"]');
  await panel.click('#lt-scrape');
  await sleep(1200);
  const secs = await panel.$$eval('.lt-sec span:nth-child(2)', (e) => e.map((x) => x.textContent));
  check('onderdelen uit Bricks, ook uit ingebed frame', ['Journaal', 'Medicatie', 'Correspondentie', 'Lab'].every((s) => secs.includes(s)), secs);
  const prev = await panel.textContent('#lt-preview');
  check('preview zonder naam/BSN/telefoon/postcode/datums', !/Pieter|123456789|12345678|6041 AB|14-05-2024/.test(prev), prev.slice(0, 200));
  await panel.setInputFiles('#lt-vraag-file', vraagPdf);
  await sleep(1500);
  check('vraag uit PDF', (await panel.inputValue('#lt-vraag')).includes('Welke diagnose'));
  await panel.click('#lt-generate');
  await sleep(400);
  check('zonder toestemming niets verstuurd', !sent.some((s) => s.url.endsWith('/letters/generate')));
  await panel.check('#lt-consent');
  await panel.click('#lt-generate');
  await sleep(1000);
  const gen = sent.find((s) => s.url.endsWith('/letters/generate'));
  check('brief via eigen server, gefilterd', gen && !/Pieter|123456789/.test(JSON.stringify(gen.body)) && gen.body.toestemming === true);
  check('concept getoond', (await panel.textContent('#lt-out')).includes('[Naam huisarts]'));

  console.log('Popup');
  const pop = await ctx.newPage();
  pop.on('pageerror', (e) => errs.push(e.message));
  await pop.goto(`chrome-extension://${id}/popup/popup.html`);
  await sleep(500);
  check('startknop bevestigt toestemming (tekst bij de knop)', (await pop.textContent('#consent-note')).includes('toestemming'));
  check('consult-flow getest in tests/e2e/consult.e2e.js', fs.existsSync(path.join(HERE, 'consult.e2e.js')));
  check('knop "Brief schrijven"', await pop.isVisible('#btn-letters'));

  check('geen JS-fouten', errs.length === 0, errs);
  console.log(`\n${ok} geslaagd, ${fail} mislukt`);
  await ctx.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

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
// EXT_DIR: test another build, e.g. the unpacked store zip.
const EXT = process.env.EXT_DIR || path.join(ROOT, 'chrome-extension');
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
  const POST = fs.readFileSync(path.join(HERE, 'bricks-post.html'), 'utf8');
  await ctx.route('https://test.bfrcloud.com/**', (r) => r.fulfill({ contentType: 'text/html', body: r.request().url().endsWith('/post') ? POST : BRICKS }));
  await ctx.route('http://localhost:8002/api/v1/**', async (r) => {
    const url = r.request().url();
    const body = r.request().postData() ? JSON.parse(r.request().postData()) : null;
    sent.push({ url, body });
    if (url.endsWith('/letters/extract')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ text: 'Journaal\nHoofdpijn\nMedicatie\nParacetamol' }) });
    if (url.endsWith('/letters/generate')) return r.fulfill({ contentType: 'text/plain; charset=utf-8', body: LETTER });
    if (url.endsWith('/dictation/process')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ mode: 'soep', soep: {
      s: '2 wk hoesten, gebruikt meta prolol 50 mg', o: 'RR 150/90 mmHg', e: 'Pneumonie', p: 'Amoxicilline 3dd 500 mg', icpc_code: 'R81', icpc_titel: 'Pneumonie',
      aandachtspunten: ['Duur van de kuur ontbreekt in P'] } }) });
    if (url.endsWith('/post/beoordeel')) {
      const kweek = body.tekst.includes('CFU');
      return r.fulfill({ contentType: 'application/json', body: JSON.stringify(kweek ? {
        cds: body.cds, soort: 'lab', samenvatting: 'Urinekweek: E. coli >10^5, gevoelig voor fosfomycine.',
        patient: 'In uw urine zit een bacterie. U krijgt een kuur.', brief: null, let_op: '',
        lab: { bevindingen: [{ bepaling: 'E. coli', waarde: '>100.000 CFU/mL', richting: 'afwijkend', duiding: 'urineweginfectie' }],
          oordeel: 'afwijkend', beleid: 'Fosfomycine 3 g eenmalig.', vergelijking: '' } } : {
        cds: body.cds, soort: 'lab',
        samenvatting: 'DM-lab: gammaGT 330 en ALAT 64 verhoogd, nierfunctie goed; correleren aan vorige waarden via aanvrager.',
        patient: 'Uw bloeduitslag is binnen. Twee leverwaarden zijn wat verhoogd; de huisarts kijkt dit na.',
        brief: null, let_op: '',
        lab: { bevindingen: [{ bepaling: 'gammaGT', waarde: '330 U/L', richting: 'hoog', duiding: 'fors verhoogd' },
          { bepaling: 'ALAT', waarde: '64 U/L', richting: 'hoog', duiding: 'licht verhoogd' }],
          oordeel: 'niet_beoordeelbaar', beleid: 'Beoordelen via aanvrager (kliniek, vorige waarden).', vergelijking: '' } }) });
    }
    if (url.endsWith('/soep/meedenken')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
      cds: body.cds,
      medicatie: [
        { veld: 's', genoemd: 'meta prolol 50 mg', middel: 'metoprolol', vervang: 'metoprolol 50 mg', zeker: true, opmerking: '' },
        { veld: 'p', genoemd: 'Amoxicilline', middel: 'amoxicilline', vervang: '', zeker: true, opmerking: 'Penicilline-allergie nagevraagd?' },
      ],
      beleid: body.cds ? { oordeel: 'in_lijn', richtlijn: 'NHG-Standaard Acuut hoesten', toelichting: '',
        suggesties: ['Controle na 2 dagen bij uitblijven verbetering'] } : null,
      thuisarts: body.cds ? ['longontsteking'] : [] }) });
    if (url.endsWith('/dossier/vraag')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
      antwoord: body.eerder.length ? 'Naproxen 500 mg 2dd.' : 'Geen kweek gevonden; wel lage rugpijn 14-05-2024.',
      gevonden: !!body.eerder.length,
      bronnen: [{ datum: '14-05-2024', onderdeel: 'JOURNAAL', citaat: 'lage rugpijn sinds 3 mnd', geverifieerd: true },
        { datum: '', onderdeel: 'LAB', citaat: 'kweek negatief', geverifieerd: false }],
      let_op: body.eerder.length ? '' : 'Er is geen correspondentie over kweken ingelezen.' }) });
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
    await chrome.storage.sync.set({ meedenken: true });
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

  console.log('Meedenken');
  await sleep(600);
  const md = sent.find((x) => x.url.endsWith('/soep/meedenken'));
  check('meedenken gevraagd met de SOEP en de keuze uit Instellingen', md && md.body.soep.p.includes('Amoxicilline') && md.body.cds === true, md && md.body);
  const soepTekst = (k) => panel.$eval(`.soep-text[data-key="${k}"]`, (n) => n.innerText);
  check('verhaspelde naam met voorstel', (await panel.textContent('#md-med')).includes('→ metoprolol 50 mg'));
  check('goed herkende naam met opmerking', /✓\s*amoxicilline/.test(await panel.textContent('#md-med')) && (await panel.textContent('#md-med')).includes('allergie'));
  check('niets veranderd zonder klik', (await soepTekst('s')).includes('meta prolol'));
  await panel.click('#md-med button');
  await sleep(200);
  check('Vervang zet de juiste naam in S', (await soepTekst('s')).includes('gebruikt metoprolol 50 mg') && !(await soepTekst('s')).includes('meta prolol'), await soepTekst('s'));
  check('beleid: in lijn met de NHG-Standaard', (await panel.textContent('#md-beleid')).includes('In lijn met NHG-Standaard Acuut hoesten'));
  await panel.click('#md-beleid button');
  await sleep(200);
  check('+ P zet het voorstel in het plan', (await soepTekst('p')).endsWith('Controle na 2 dagen bij uitblijven verbetering.'), await soepTekst('p'));
  check('Thuisarts als zoeklink, geen gegokt adres',
    (await panel.getAttribute('#md-ta a', 'href')) === 'https://www.thuisarts.nl/zoeken?query=longontsteking');
  check('maar één aanvraag voor deze SOEP', sent.filter((x) => x.url.endsWith('/soep/meedenken')).length === 1);
  // Thuisarts: the shipped table has no URLs yet, so no link may appear. The
  // title lookup after correcting the code can only come from the real table,
  // loaded via chrome.runtime.getURL inside the extension.
  check('geen Thuisarts-link zonder gecontroleerde regel',
    (await panel.textContent('#ta')).includes('Geen Thuisarts-pagina') && (await panel.$$('#ta .ta-chip')).length === 0);
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

  console.log('Dossiervraag');
  const weergave = () => sw.evaluate(async () => ({
    popup: await chrome.action.getPopup({}),
    paneel: (await chrome.sidePanel.getPanelBehavior()).openPanelOnActionClick,
  }));
  let w = await weergave();
  check('icoon opent standaard het zijpaneel', w.popup === '' && w.paneel === true, w);
  check('terugval: klik op het icoon opent het paneel ook zelf', await sw.evaluate(() => chrome.action.onClicked.hasListeners()));
  await panel.click('.view-tab[data-view="dossier"]');
  check('derde tabblad Dossiervraag', await panel.isVisible('#view-dossier') && await panel.isHidden('#view-letters') && await panel.isHidden('#view-dictate'));
  check('snelle vragen als chips', (await panel.$$('#dv-snel .chip')).length >= 5);
  await panel.click('#dv-snel .chip:first-child');
  await sleep(1200);
  const dv1 = sent.filter((s) => s.url.endsWith('/dossier/vraag'));
  const d1 = dv1[0] && dv1[0].body;
  check('vraag verstuurd met dossier (ook ingebed frame)', d1 && d1.vraag.includes('kweken') && /== JOURNAAL ==/.test(d1.dossier) && d1.dossier.includes('HbA1c'), d1 && d1.vraag);
  check('zonder naam, BSN, geboortedatum, telefoon, adres', d1 && !/Pieter|Vries|123456789|12-03-1961|12345678|6041 AB/.test(d1.dossier), d1 && d1.dossier.slice(0, 300));
  check('consultdatums blijven (nodig voor "laatste")', d1 && d1.dossier.includes('14-05-2024'));
  check('eerste vraag zonder eerdere context', d1 && d1.eerder.length === 0);
  check('antwoord getoond als "niet gevonden" met let op', (await panel.getAttribute('.dv-item', 'class')).includes('niet') && (await panel.textContent('.dv-letop')).includes('correspondentie'));
  const marks = await panel.$$eval('.dv-item:first-child .dv-mark', (e) => e.map((x) => x.textContent));
  check('bronnen: ✓ letterlijk gevonden, ? onzeker', marks.join('') === '✓?', marks);
  check('ingelezen onderdelen en initialen getoond', /Ingelezen \(P\.V\.\).*Journaal/.test(await panel.textContent('#dv-bron')), await panel.textContent('#dv-bron'));
  await panel.fill('#dv-input', 'En welke pijnstillers?');
  await panel.press('#dv-input', 'Enter');
  await sleep(1200);
  const d2 = sent.filter((s) => s.url.endsWith('/dossier/vraag'))[1];
  check('vervolgvraag met Enter, eerdere vraag als context', d2 && d2.body.eerder.length === 1 && d2.body.eerder[0].vraag.includes('kweken'));
  check('nieuwste antwoord bovenaan, invoer leeg', (await panel.$$('.dv-item')).length === 2
    && (await panel.textContent('.dv-item:first-child .dv-antwoord')).includes('Naproxen') && (await panel.inputValue('#dv-input')) === '');
  await panel.click('.view-tab[data-view="dictate"]');

  console.log('Post & lab');
  await page.goto('https://test.bfrcloud.com/post');
  await sleep(500);
  await panel.bringToFront();
  const postReqs = () => sent.filter((x) => x.url.endsWith('/post/beoordeel'));
  await panel.click('.view-tab[data-view="post"]');
  check('vierde tabblad Post', await panel.isVisible('#view-post') && await panel.isHidden('#view-dossier'));
  await sleep(5500);
  const pr = postReqs()[0] && postReqs()[0].body;
  check('bericht automatisch beoordeeld bij openen', postReqs().length === 1, postReqs().length);
  check('zonder naam, geboortedatum, adres en identificatienummer', pr && !/Gorris|Aarts|26-10-1961|Eerensstraat|6045 HB|ROERMOND|625805083/.test(pr.tekst), pr && pr.tekst.slice(0, 300));
  check('met leeftijd, episodes, labdatum en waarden', pr && pr.leeftijd === 64 && pr.problemen.includes('T90.02 Diabetes mellitus type 2')
    && pr.tekst.includes('15-09-2026') && pr.tekst.includes('330') && !pr.tekst.includes('Verwijder'), pr);
  check('klinisch meedenken volgt de instelling', pr && pr.cds === true);
  check('oordeel en waarden getoond', (await panel.textContent('#po-oordeel')) === 'Via aanvrager'
    && (await panel.textContent('#po-lab')).includes('↑gammaGT 330 U/L'), await panel.textContent('#po-lab'));
  await panel.click('#po-zet-sam');
  await panel.click('#po-zet-memo');
  await sleep(500);
  check('Zet in Samenvatting vult het journaalveld in Bricks', (await page.inputValue('#samenvatting')).startsWith('DM-lab: gammaGT 330'));
  check('Zet in Memo vult de uitleg voor de patiënt', (await page.inputValue('#memo')).startsWith('Uw bloeduitslag is binnen'));
  await sleep(4500);
  check('zelfde bericht: geen nieuwe aanvraag', postReqs().length === 1, postReqs().length);
  const labHtml = await page.innerHTML('#bericht');
  await page.evaluate(() => {
    document.getElementById('bericht').innerHTML = '<table><tr><td>Afzender</td><td>Laurentius Ziekenhuis Roermond</td></tr>' +
      '<tr><td>Patiënt</td><td>M C Velde van de - Hornyak 10-06-1951 Heinsbergerweg 64 6074 AE MELICK</td></tr></table>' +
      '<pre>Materiaal              : Urine\nTelling                          > 100.000 CFU/mL\nLeucocyten                        Veel</pre>';
  });
  await sleep(5500);
  const pk = postReqs()[1] && postReqs()[1].body;
  check('ander bericht aangeklikt: kweek beoordeeld', pk && pk.tekst.includes('CFU') && pk.leeftijd === 75 && !/Velde|Hornyak|Heinsbergerweg/.test(pk.tekst), pk && pk.tekst);
  check('kweek getoond met beleid', (await panel.textContent('#po-beleid')).includes('Fosfomycine') && (await panel.textContent('#po-oordeel')) === 'Afwijkend');
  await page.evaluate((h) => { document.getElementById('bericht').innerHTML = h; }, labHtml);
  await sleep(5000);
  check('terug naar het eerdere bericht: uit het geheugen, geen kosten', postReqs().length === 2 && (await panel.textContent('#po-sam')).startsWith('DM-lab'), postReqs().length);
  await panel.click('.view-tab[data-view="dictate"]');

  console.log('Minimaliseren');
  const panelDicht = panel.waitForEvent('close', { timeout: 3000 }).then(() => true, () => false);
  await panel.click('#btn-minimaliseer');
  await sleep(500);
  w = await weergave();
  check('minimaliseren verandert het icoon niet: dat opent weer het zijpaneel', w.popup === '' && w.paneel === true, w);
  check('minimaliseren sluit het paneel', await panelDicht);

  console.log('Popup');
  const pop = await ctx.newPage();
  pop.on('pageerror', (e) => errs.push(e.message));
  await pop.goto(`chrome-extension://${id}/popup/popup.html`);
  await sleep(500);
  check('startknop bevestigt toestemming (tekst bij de knop)', (await pop.textContent('#consent-note')).includes('toestemming'));
  check('consult-flow getest in tests/e2e/consult.e2e.js', fs.existsSync(path.join(HERE, 'consult.e2e.js')));
  check('knop "Brief schrijven"', await pop.isVisible('#btn-letters'));
  check('knop "Dossiervraag"', await pop.isVisible('#btn-dossier'));
  check('knop "Post & lab"', await pop.isVisible('#btn-post'));
  const popDicht = pop.waitForEvent('close', { timeout: 3000 }).then(() => true, () => false);
  await pop.click('#btn-expand');
  check('paneelknop in de popup sluit de popup', await popDicht);

  console.log('Instellingen');
  const opt = await ctx.newPage();
  opt.on('pageerror', (e) => errs.push(e.message));
  await opt.goto(`chrome-extension://${id}/options/options.html`);
  await sleep(500);
  check('instelling staat standaard op zijpaneel', (await opt.inputValue('#weergave')) === 'paneel');
  await opt.selectOption('#weergave', 'compact');
  await sleep(400);
  w = await weergave();
  check('instelling "compacte popup" werkt meteen', w.popup.endsWith('popup/popup.html') && w.paneel === false, w);
  await opt.selectOption('#weergave', 'paneel');
  await sleep(400);
  w = await weergave();
  check('en terug naar zijpaneel', w.popup === '' && w.paneel === true, w);

  check('geen JS-fouten', errs.length === 0, errs);
  console.log(`\n${ok} geslaagd, ${fail} mislukt`);
  await ctx.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

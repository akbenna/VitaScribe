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
  let euToegestaan = true;
  const POST = fs.readFileSync(path.join(HERE, 'bricks-post.html'), 'utf8');
  const DOSSIER = fs.readFileSync(path.join(HERE, 'bricks-dossier.html'), 'utf8');
  await ctx.route('https://test.bfrcloud.com/**', (r) => {
    const u = r.request().url();
    if (u.endsWith('/gevoelig')) return r.fulfill({ contentType: 'text/html', body: DOSSIER.replace('P70<br>28-02-2025<br>Dementie', 'P76<br>28-02-2025<br>Depressie, verwezen naar GGZ') });
    return r.fulfill({ contentType: 'text/html', body: u.endsWith('/post') ? POST : u.endsWith('/dossier') ? DOSSIER : BRICKS });
  });
  await ctx.route('http://localhost:8002/api/v1/**', async (r) => {
    const url = r.request().url();
    const raw = r.request().postData() || '';
    let body = null;
    try { body = raw ? JSON.parse(raw) : null; } catch (e) { body = null; }   // multipart (tolk)
    const modusKop = r.request().headers()['x-vitascribe-modus'] || '';
    sent.push({ url, body, raw, modus: modusKop });
    if (url.endsWith('/tolk/talen')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
      modus: modusKop || 'claude', nl_stem: 'mistral', talen: [
        { code: 'tr', naam: 'Turks', eigen: 'Türkçe', verstaat: modusKop !== 'eu', stem: 'computer',
          waarom: modusKop === 'eu' ? 'In de EU-modus verstaat de spraakherkenning (Voxtral, Mistral) geen Turks.' : '' },
        { code: 'ar-MA', naam: 'Marokkaans-Arabisch (Darija)', eigen: 'الدارجة', verstaat: true, stem: 'mistral', waarom: '' }] }) });
    if (url.endsWith('/tolk/beurt')) {
      const patient = raw.includes('name="spreker"\r\n\r\npatient');
      if (raw.includes('name="spreker"\r\n\r\nauto')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify(
        { spreker: 'patient', origineel: 'Başım ağrıyor.', vertaling: 'Ik heb hoofdpijn.', terugvertaling: '', onzeker: false, twijfel: '', leeg: false }) });
      return r.fulfill({ contentType: 'application/json', body: JSON.stringify(patient
        ? { spreker: 'patient', origineel: 'Üç gündür ateşim var.', vertaling: 'Ik heb al drie dagen koorts.', terugvertaling: '',
            onzeker: true, twijfel: '"Üç" kan ook "iki" (twee) zijn.', leeg: false }
        : { spreker: 'arts', origineel: 'Heeft u koorts?', vertaling: 'Ateşiniz var mı?', terugvertaling: 'Heeft u koorts?',
            onzeker: false, twijfel: '', leeg: false }) });
    }
    if (url.endsWith('/tolk/spreek')) return r.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"geen stem"}' });
    if (url.endsWith('/tolk/verslag')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
      soep: { s: 'Koorts sinds 3 dagen. Consult in het Turks via AI-tolk.', o: '', e: 'Koorts', p: '', icpc_code: 'A03' },
      decisief: '', markeringen: [] }) });
    if (url.endsWith('/providers')) {
      const gevraagd = r.request().headers()['x-vitascribe-modus'];
      return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
        modus: gevraagd === 'eu' ? 'eu' : 'claude', modi: ['claude', 'eu'],
        eu_probleem: euToegestaan ? null : 'Op de server is geen Mistral-sleutel ingesteld.' }) });
    }
    if (url.endsWith('/letters/extract')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ text: 'Journaal\nHoofdpijn\nMedicatie\nParacetamol' }) });
    if (url.endsWith('/letters/generate')) return r.fulfill({ contentType: 'text/plain; charset=utf-8', body: LETTER });
    if (url.endsWith('/dictation/process')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ mode: 'soep', soep: {
      s: '2 wk hoesten, gebruikt meta prolol 50 mg', o: 'RR 150/90 mmHg', e: 'Pneumonie', p: 'Amoxicilline 3dd 500 mg', icpc_code: 'R81', icpc_titel: 'Pneumonie',
      aandachtspunten: ['Duur van de kuur ontbreekt in P'],
      markeringen: [{ probleem: 0, veld: 'o', tekst: '150/90', reden: 'waarde niet genoemd' }] } }) });
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
    if (url.endsWith('/dossier/vraag') && body.vraag.includes('katheter')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({
      antwoord: 'Niet expliciet vermeld. Aanwijzingen: episode urine-incontinentie (2013); blaasspoeling wegens gruis (07-2026).',
      zekerheid: 'indirect', gevonden: true,
      bronnen: [{ datum: '01-03-2013', onderdeel: 'Episoden', citaat: 'Urine-incontinentie', geverifieerd: true }],
      let_op: 'Mogelijk in een brief van de uroloog.' }) });
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
    await chrome.storage.sync.set({ meedenken: true, vraagsuggesties: true });
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
  check('markering geel in de tekst', (await panel.$$eval('.soep-text[data-key="o"] mark.sv-mark', (m) => m.map((x) => x.textContent))).join() === '150/90');
  check('markering laat de tekst ongemoeid', (await panel.$eval('.soep-text[data-key="o"]', (n) => n.innerText)) === 'RR 150/90 mmHg');
  check('lijst "Controleer" met reden', (await panel.textContent('#soep-mark')).includes('waarde niet genoemd'));

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

  console.log('Vraagsuggesties bij dicteren');
  const dauth = await panel.evaluate(async () => {
    // A stand-in socket: records what the panel sends at the start.
    window.WebSocket = class {
      constructor(url) { this.url = url; this.sent = []; this.readyState = 0; window.__ws = this;
        setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 0); }
      send(d) { this.sent.push(d); }
      close() { this.readyState = 3; }
    };
    startDictation();
    for (let i = 0; i < 50 && !(window.__ws && window.__ws.sent.length); i++) await new Promise((r) => setTimeout(r, 50));
    const auth = window.__ws && window.__ws.sent[0] ? JSON.parse(window.__ws.sent[0]) : null;
    teardown(); setState('idle');
    return auth;
  });
  check('dicteren vraagt om vraagsuggesties als die aanstaan', dauth && dauth.type === 'auth' && dauth.vraagsuggesties === true, dauth);
  await panel.evaluate(() => handleServerEvent({ type: 'suggesties', klacht: 'hoofdpijn', vragen: [{ tekst: 'misselijk?', alarm: false, waarom: 'past bij migraine' }, { tekst: 'nekstijfheid?', alarm: true, waarom: 'uitsluiten meningitis' }] }));
  check('chips onder de microfoon, alarm in rood', await panel.isVisible('#dict-vragen')
    && (await panel.textContent('#dict-klacht')).includes('hoofdpijn')
    && (await panel.$$eval('#dict-chips .cv-chip.alarm', (b) => b.map((x) => x.textContent))).join() === 'nekstijfheid?');
  await panel.hover('#dict-chips .cv-chip:nth-child(2)');
  check('muis over een vraag toont waarom die ertoe doet', (await panel.textContent('#dict-waarom')) === 'Waarom: uitsluiten meningitis', await panel.textContent('#dict-waarom'));
  await panel.hover('#dict-klacht');
  check('muis weg: de uitleg verdwijnt', (await panel.textContent('#dict-waarom')) === '');
  await panel.click('#dict-chips .cv-chip:first-child');
  await panel.evaluate(() => handleServerEvent({ type: 'suggesties', klacht: 'hoofdpijn', vragen: [{ tekst: 'misselijk?', alarm: false }, { tekst: 'koorts?', alarm: false }] }));
  check('aangetikte vraag blijft doorgestreept in de volgende ronde', (await panel.getAttribute('#dict-chips .cv-chip:first-child', 'class')).includes('gedaan'));
  await panel.evaluate(() => { startDictation(); teardown(); setState('idle'); });
  check('nieuw dictaat begint zonder oude suggesties', await panel.isHidden('#dict-vragen'));

  console.log('Brieven');
  await panel.click('.view-tab[data-view="letters"]');
  await panel.click('#lt-scrape');
  await sleep(1200);
  const secs = await panel.$$eval('.lt-sec span:nth-child(2)', (e) => e.map((x) => x.textContent));
  check('onderdelen uit Bricks, ook uit ingebed frame', ['Journaal', 'Medicatie', 'Correspondentie', 'Lab'].every((s) => secs.includes(s)), secs);
  const prev = await panel.textContent('#lt-preview');
  check('preview zonder naam/BSN/telefoon/postcode/datums', !/Pieter|123456789|12345678|6041 AB|14-05-2024/.test(prev), prev.slice(0, 200));
  await panel.setInputFiles('#lt-pdf-file', vraagPdf);
  await sleep(1500);
  const secs2 = await panel.$$eval('.lt-sec span:nth-child(2)', (e) => e.map((x) => x.textContent));
  check('PDF komt bij het Bricks-dossier, vervangt het niet', secs2.includes('Journaal') && secs2.some((x) => x.startsWith('PDF ')), secs2);
  check('naamfilter uit Bricks werkt ook op de PDF', !/Pieter|123456789/.test(await panel.textContent('#lt-preview')));
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
  check('tabbladen Consult, Tolk, Brieven, Post; dossiervraag is geen tabblad',
    (await panel.$$eval('.view-tab', (t) => t.map((x) => x.textContent))).join() === 'Consult,Tolk,Brieven,Post' && !(await panel.$('#view-dossier')));
  check('dossiervraag als balk onderaan, antwoorden nog dicht', await panel.isVisible('#dv-input') && await panel.isHidden('#dv-paneel'));
  await panel.click('.view-tab[data-view="letters"]');
  check('balk ook in het tabblad Brieven', await panel.isVisible('#dv-input'));
  await panel.focus('#dv-input');
  check('focus op de balk toont de snelle vragen', await panel.isVisible('#dv-paneel') && (await panel.$$('#dv-snel .chip')).length >= 5);
  await panel.click('#dv-snel .chip:first-child');
  await sleep(1200);
  const dv1 = sent.filter((s) => s.url.endsWith('/dossier/vraag'));
  const d1 = dv1[0] && dv1[0].body;
  check('vraag verstuurd met alles wat in beeld staat (ook ingebed frame)', d1 && d1.vraag.includes('kweken') && /== DOSSIER \(IN BEELD\) ==/.test(d1.dossier) && d1.dossier.includes('HbA1c') && d1.dossier.includes('Naproxen'), d1 && d1.vraag);
  check('zonder naam, BSN, geboortedatum, telefoon, adres', d1 && !/Pieter|Vries|123456789|12-03-1961|12345678|6041 AB/.test(d1.dossier), d1 && d1.dossier.slice(0, 300));
  check('consultdatums blijven (nodig voor "laatste")', d1 && d1.dossier.includes('14-05-2024'));
  check('eerste vraag zonder eerdere context', d1 && d1.eerder.length === 0);
  check('antwoord getoond als "niet gevonden" met let op', (await panel.getAttribute('.dv-item', 'class')).includes('niet') && (await panel.textContent('#dv-antwoorden .dv-letop')).includes('correspondentie'));
  const marks = await panel.$$eval('.dv-item:first-child .dv-mark', (e) => e.map((x) => x.textContent));
  check('bronnen: ✓ letterlijk gevonden, ? onzeker', marks.join('') === '✓?', marks);
  check('ingelezen: alles in beeld, met initialen', /Ingelezen \(P\.V\.\): alles wat in beeld staat/.test(await panel.textContent('#dv-bron')), await panel.textContent('#dv-bron'));
  await panel.fill('#dv-input', 'En welke pijnstillers?');
  await panel.press('#dv-input', 'Enter');
  await sleep(1200);
  const d2 = sent.filter((s) => s.url.endsWith('/dossier/vraag'))[1];
  check('vervolgvraag met Enter, eerdere vraag als context', d2 && d2.body.eerder.length === 1 && d2.body.eerder[0].vraag.includes('kweken'));
  check('nieuwste antwoord bovenaan, invoer leeg', (await panel.$$('.dv-item')).length === 2
    && (await panel.textContent('.dv-item:first-child .dv-antwoord')).includes('Naproxen') && (await panel.inputValue('#dv-input')) === '');

  console.log('Dossiervraag in een echt Bricks-beeld (verborgen vorige patiënt)');
  await page.goto('https://test.bfrcloud.com/dossier');
  await sleep(500);
  await panel.bringToFront();
  await panel.fill('#dv-input', 'Wat is de indicatie voor de katheter?');
  await panel.press('#dv-input', 'Enter');
  await sleep(1500);
  const d3 = sent.filter((s) => s.url.endsWith('/dossier/vraag'))[2];
  const t3 = d3 ? d3.body.dossier : '';
  check('verborgen vorige patiënt en verborgen frame gaan niet mee', d3 && !/Kerkhofs|SOTALOL|pneumonie april|VERBORGEN-FRAME/.test(t3), t3.slice(0, 400));
  check('naam en geboortedatum uit de kopregel overal weg', d3 && !/Amer|Moulay|03-06-1941|3-6-1941/.test(t3), (t3.match(/.{0,40}(Amer|Moulay|1941).{0,40}/g) || []).slice(0, 3));
  check('datums met auteurscode blijven heel', t3.includes('16-06-2026\nHA') && t3.includes('29-09-2026') && !t3.includes('[POSTCODE]'), (t3.match(/.{0,20}\[POSTCODE\].{0,20}/g) || []).slice(0, 3));
  check('breed ingelezen: journaal, episodes en thuiszorgnotities', /blaasspoeling/.test(t3) && /Urine-incontinentie/.test(t3) && /incontinentiemateriaal/.test(t3));
  check('medicatieprofiel dat twee keer in beeld staat gaat één keer mee', (t3.match(/MIDDEL-17 /g) || []).length === 1, (t3.match(/MIDDEL-17 /g) || []).length);
  check('andere patiënt: geen eerdere vragen als context', d3 && d3.body.eerder.length === 0);
  check('initialen van de juiste patiënt', /Ingelezen \(A\.M\.\)/.test(await panel.textContent('#dv-bron')), await panel.textContent('#dv-bron'));
  check('antwoord met aanwijzingen gemarkeerd als "Alleen aanwijzingen"', (await panel.textContent('.dv-item:first-child .dv-zeker')) === 'Alleen aanwijzingen'
    && (await panel.getAttribute('.dv-item:first-child', 'class')).includes('indirect'));

  console.log('Advies bij een gevoelig dossier');
  check('gewoon dossier (dementie, incontinentie): geen advies', await panel.isHidden('#gevoelig-advies'));
  await page.goto('https://test.bfrcloud.com/gevoelig');
  await sleep(500);
  await panel.bringToFront();
  const voorAdvies = sent.length;
  await panel.evaluate(() => SVGevoeligAdvies.kijk());
  await sleep(800);
  const advies = await panel.textContent('#gevoelig-advies');
  check('gevoelig dossier: advies om de EU-modus te kiezen', await panel.isVisible('#gevoelig-advies') && advies.includes('psychiatrie') && advies.includes('EU-modus'), advies);
  check('advies zegt dat er niets verstuurd is', advies.includes('niets verstuurd'));
  check('voor het advies ging er niets naar de server', sent.length === voorAdvies, sent.slice(voorAdvies).map((x) => x.url));
  await panel.click('#gevoelig-advies .gevoelig-eu');
  await sleep(400);
  check('één klik: EU-modus aan, advies weg', (await panel.evaluate(() => chrome.storage.local.get('svModus'))).svModus === 'eu' && await panel.isHidden('#gevoelig-advies'));
  await panel.click('#modus [data-modus="claude"]');
  await sleep(600);
  await panel.evaluate(() => SVGevoeligAdvies.kijk());
  await sleep(800);
  check('terug in Claude: advies weer zichtbaar', await panel.isVisible('#gevoelig-advies'));
  await panel.click('#gevoelig-advies button:not(.gevoelig-eu)');
  await panel.evaluate(() => SVGevoeligAdvies.kijk());
  await sleep(800);
  check('"Niet voor deze patiënt" houdt het advies weg', await panel.isHidden('#gevoelig-advies'));
  check('de modus blijft wat de arts koos (Claude)', (await panel.evaluate(() => chrome.storage.local.get('svModus'))).svModus === 'claude');
  check('link naar Beheer in het zijpaneel', await panel.isVisible('#open-beheer'));
  await panel.evaluate(() => { window.__geopend = []; chrome.tabs.create = async (o) => { window.__geopend.push(o.url); }; });
  await panel.click('#open-beheer');
  await sleep(300);
  const geopend = await panel.evaluate(() => window.__geopend);
  check('Beheer opent de beheerpagina van de eigen server', geopend[0] === 'http://localhost:8002/beheer', geopend);

  await page.goto('https://test.bfrcloud.com/patient');
  await sleep(300);
  await panel.click('.view-tab[data-view="dictate"]');

  console.log('Post & lab');
  await page.goto('https://test.bfrcloud.com/post');
  await sleep(500);
  await panel.bringToFront();
  const postReqs = () => sent.filter((x) => x.url.endsWith('/post/beoordeel'));
  await panel.click('.view-tab[data-view="post"]');
  check('vierde tabblad Post, met de dossiervraag eronder', await panel.isVisible('#view-post') && await panel.isVisible('#dv-input'));
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

  console.log('Tolk');
  await page.goto('https://test.bfrcloud.com/patient');
  await panel.bringToFront();
  await panel.evaluate(() => {
    // A tone instead of a microphone (window.__geluid: 0 = stil, 0.3 = praten), and no voices on this computer.
    window.openMicrophone = async () => {
      const c = new AudioContext();
      const o = c.createOscillator();
      const g = c.createGain();
      g.gain.value = 0;
      window.__geluid = (v) => { g.gain.value = v; };
      const d = c.createMediaStreamDestination();
      o.connect(g);
      g.connect(d);
      o.start();
      return d.stream;
    };
    speechSynthesis.getVoices = () => [];
  });
  await panel.click('.view-tab[data-view="tolk"]');
  await sleep(500);
  check('talen van de server in de keuzelijst', (await panel.$$eval('#tk-taal option', (o) => o.map((x) => x.value))).join() === 'tr,ar-MA');
  await panel.selectOption('#tk-taal', 'tr');
  check('uitleg: voorlezen met een stem op de computer', (await panel.textContent('#tk-taal-uitleg')).includes('stem op deze computer'));
  await panel.click('#tk-begin');
  await sleep(600);
  check('na start luistert VitaScribe handsfree, zonder knoppen', (await panel.getAttribute('#tk-handsfree', 'class')).includes('aan')
    && await panel.isHidden('#tk-arts') && (await panel.textContent('.tk-hf-status')) === 'luistert');
  const tb = () => sent.filter((x) => x.url.endsWith('/tolk/beurt'));
  await panel.evaluate(() => window.__geluid(0.3));
  await sleep(1200);
  check('spraak gehoord', (await panel.textContent('.tk-hf-status')).includes('hoort spraak'));
  await panel.evaluate(() => window.__geluid(0));
  await sleep(2500);
  const b0 = tb()[0] ? tb()[0].raw : '';
  check('na een stilte gaat de beurt als WAV naar de server, spreker automatisch', /name="spreker"\r\n\r\nauto/.test(b0)
    && b0.includes('filename="beurt.wav"') && b0.includes('RIFF') && b0.includes('WAVE'), b0.slice(0, 300));
  check('de taal bepaalde de spreker: patiënt', (await panel.textContent('.tk-beurt:first-child .tk-wie')).includes('Patiënt')
    && (await panel.textContent('.tk-beurt:first-child .tk-wie')).includes('herkend aan de taal')
    && (await panel.textContent('.tk-beurt:first-child .tk-vert')) === 'Ik heb hoofdpijn.');
  // Reading aloud (server voice 404, no computer voice) takes a moment; on a slow runner longer.
  let weer = false;
  for (let i = 0; i < 50 && !weer; i++) { weer = (await panel.textContent('.tk-hf-status')) === 'luistert'; if (!weer) await sleep(100); }
  check('na het voorlezen luistert hij weer', weer, await panel.textContent('.tk-hf-status'));
  await panel.click('#tk-handsfree');
  check('handsfree uit: de knoppen komen terug', await panel.isVisible('#tk-arts') && await panel.isVisible('#tk-patient')
    && (await panel.textContent('#tk-patient-taal')).includes('Turks'));
  await panel.click('#tk-arts');
  await panel.evaluate(() => window.__geluid(0.3));
  await sleep(700);
  check('knop van de arts luistert', (await panel.getAttribute('#tk-arts', 'class')).includes('luistert'));
  await panel.click('#tk-arts');
  await sleep(1000);
  const b1 = tb()[1] ? tb()[1].raw : '';
  check('beurt verstuurd: arts, Turks, met toestemming en opname', /name="spreker"\r\n\r\narts/.test(b1) && /name="taal"\r\n\r\ntr/.test(b1)
    && /name="consent"\r\n\r\ntrue/.test(b1) && b1.includes('filename="beurt.webm"'), b1.slice(0, 300));
  check('vertaling en terugvertaling getoond', (await panel.textContent('.tk-beurt.arts .tk-vert')) === 'Ateşiniz var mı?'
    && (await panel.textContent('.tk-beurt.arts .tk-terug')) === 'Heeft u koorts?');
  check('geen stem voor Turks: vertaling groot op het scherm, met uitleg', await panel.isVisible('#tk-scherm')
    && (await panel.textContent('#tk-scherm-tekst')) === 'Ateşiniz var mı?' && (await panel.textContent('#tk-status')).includes('Stemmen toevoegen'));
  await panel.click('#tk-scherm-dicht');
  await panel.keyboard.press('Enter');
  await sleep(300);
  await panel.evaluate(() => window.__geluid(0.3));   // each turn opens its own microphone
  await sleep(500);
  check('Enter: de patiënt spreekt', (await panel.getAttribute('#tk-patient', 'class')).includes('luistert'));
  await panel.keyboard.press('Enter');
  await sleep(1200);
  await panel.evaluate(() => window.__geluid(0));
  const b2 = tb()[2] ? tb()[2].raw : '';
  check('volgende beurt met de vorige als context', /name="spreker"\r\n\r\npatient/.test(b2) && b2.includes('Heeft u koorts?') && b2.includes('Ik heb hoofdpijn.'), b2.slice(0, 400));
  check('patiënt: Nederlands bovenaan, twijfel gemarkeerd', (await panel.textContent('.tk-beurt:first-child .tk-vert')) === 'Ik heb al drie dagen koorts.'
    && (await panel.textContent('.tk-beurt:first-child .tk-twijfel')).includes('iki'));
  const sp = sent.filter((x) => x.url.endsWith('/tolk/spreek'));
  check('Nederlands voorlezen vraagt eerst de stem van de server, met de gekozen stem', sp.length === 2 && sp.every((x) => x.body.taal === 'nl' && x.body.geslacht === 'vrouw')
    && sp[1].body.tekst.includes('drie dagen'), sp.map((x) => x.body));
  await panel.click('#tk-verslag');
  await sleep(1500);
  const vs = sent.filter((x) => x.url.endsWith('/tolk/verslag'))[0];
  check('verslag uit de Nederlandse kant van het gesprek', vs && vs.body.taal === 'tr' && vs.body.consent === true
    && JSON.stringify(vs.body.beurten) === JSON.stringify([{ spreker: 'patient', nl: 'Ik heb hoofdpijn.' }, { spreker: 'arts', nl: 'Heeft u koorts?' },
      { spreker: 'patient', nl: 'Ik heb al drie dagen koorts.' }]), vs && vs.body);
  check('verslag verschijnt in het tabblad Consult', await panel.isVisible('#view-dictate')
    && (await panel.$$eval('.soep-text', (e) => e.map((x) => x.textContent))).some((t) => t.includes('via AI-tolk')));
  check('bolletje en popup kennen het verslag', (await sw.evaluate(async () => (await chrome.storage.session.get('svConsult')).svConsult.state)) === 'results');
  await panel.click('#btn-consult-afsluiten');
  await sleep(500);
  await panel.click('.view-tab[data-view="tolk"]');
  check('consult afsluiten wist ook het tolkgesprek', await panel.isVisible('#tk-start') && (await panel.$$('.tk-beurt')).length === 0
    && !(await sw.evaluate(async () => (await chrome.storage.session.get('svTolk')).svTolk)));
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
  check('handleiding in de popup', (await pop.getAttribute('#link-help', 'href')) === '../help/handleiding.html');

  console.log('Modus (Claude | EU)');
  const aan = () => pop.$eval('#modus .aan', (b) => b.getAttribute('data-modus')).catch(() => '');
  check('modusknop in de popup, standaard Claude', await aan() === 'claude');
  await pop.click('#modus [data-modus="eu"]');
  await sleep(600);
  check('één klik zet de EU-modus aan', await aan() === 'eu');
  check('toelichting noemt wat in de EU-modus niet kan', (await pop.textContent('#modus-uitleg')).includes('Live dicteren'));
  check('de server wordt gevraagd met de kopregel EU', sent.some((x) => x.url.endsWith('/providers') && x.modus === 'eu'));
  const opgeslagen = await pop.evaluate(() => chrome.storage.local.get('svModus'));
  check('keuze bewaard op deze computer', opgeslagen.svModus === 'eu', opgeslagen);
  const voor = sent.length;
  await pop.evaluate(async () => {
    const h = { 'X-API-Key': 'x' };
    await SVPraktijk.metKop(h);
    await fetch('http://localhost:8002/api/v1/thuisarts/test', { headers: h });
  });
  check('elke aanvraag krijgt de modus mee (via metKop)', sent.slice(voor).some((x) => x.modus === 'eu'), sent.slice(voor));
  await pop.click('#modus [data-modus="claude"]');
  await sleep(300);
  check('één klik terug naar Claude', await aan() === 'claude' && await pop.isHidden('#modus-uitleg'));
  euToegestaan = false;
  await pop.click('#modus [data-modus="eu"]');
  await sleep(800);
  check('de arts beslist: ook als de server niet klaar is blijft EU staan', await aan() === 'eu');
  check('de server geeft alleen een waarschuwing', (await pop.textContent('#modus-uitleg')).includes('Let op: Op de server is geen Mistral-sleutel'));
  await pop.click('#modus [data-modus="claude"]');
  await sleep(300);
  euToegestaan = true;

  const popDicht = pop.waitForEvent('close', { timeout: 3000 }).then(() => true, () => false);
  await pop.click('#btn-expand');
  check('paneelknop in de popup sluit de popup', await popDicht);

  console.log('Handleiding');
  check('handleiding opent bij installatie', ctx.pages().some((x) => x.url().endsWith('/help/handleiding.html')), ctx.pages().map((x) => x.url()));
  const hl = await ctx.newPage();
  hl.on('pageerror', (e) => errs.push(e.message));
  await hl.goto(`chrome-extension://${id}/help/handleiding.html`);
  const hoofdstukken = await hl.$$eval('h2', (h) => h.map((x) => x.id));
  check('handleiding met alle hoofdstukken', ['start', 'paneel', 'consult', 'dicteren', 'meedenken', 'brieven', 'dossiervraag', 'post', 'bronnen', 'instellingen', 'privacy', 'grenzen', 'problemen'].every((h) => hoofdstukken.includes(h)), hoofdstukken);
  const kapot = await hl.$$eval('nav a', (as) => as.filter((a) => !document.querySelector(a.getAttribute('href'))).map((a) => a.textContent));
  check('inhoudsopgave verwijst naar bestaande hoofdstukken', kapot.length === 0, kapot);
  await hl.click('a[href="../privacy/avg.html"]');
  await sleep(300);
  check('link naar de AVG-pagina werkt', hl.url().endsWith('/privacy/avg.html') && (await hl.textContent('body')).includes('Post & lab'));
  await hl.close();

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

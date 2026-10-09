// popup.js v5 - Geoptimaliseerd: streaming, privacy fix, XSS-bescherming, responsive

// ── PDF.js worker via extensie URL ───────────────────────────
if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL('pdfjs/pdf.worker.min.js');
}

// ── State ─────────────────────────────────────────────────────
const state = {
  rawSecties: {},
  patiëntNaamRauw: '',
  initialen: '',
  sectieAan: {},
  dossierBron: null,
  screenshotDataUrl: null,
  screenshotAnalysed: false,
  vraagText: null,
  vraagFileName: null,
  vraagScreenshotDataUrl: null,
  vraagScreenshotAnalysed: false,
  selectedType: 'advocaat',
  // Verwijzing state
  selectedSpec: 'cardiologie',
  selectedUrgentie: 'regulier',
};

// ── Helpers ───────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const escapeHtml = (s) => s.replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c]);

const STANDAARD_SECTIES = ['journaal','medicatie','voorgeschied','lab'];

function zetStandaardSecties(secties) {
  state.sectieAan = {};
  const weinigSecties = Object.keys(secties).length <= 2;
  for (const s of Object.keys(secties)) {
    state.sectieAan[s] = weinigSecties || STANDAARD_SECTIES.some(kw => s.toLowerCase().includes(kw));
  }
}

function getApiKey() {
  return new Promise(r => chrome.storage.local.get('apiKey', res => r(res.apiKey || null)));
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Alle event listeners (geen inline handlers - CSP MV3)
  $('avgBtn').addEventListener('click', () => chrome.tabs.create({ url: chrome.runtime.getURL('avg-verantwoording.html') }));

  // Hoofdtabs (Brief / Verwijzing)
  $('htab-brief').addEventListener('click', () => switchHoofdTab('brief'));
  $('htab-verwijzing').addEventListener('click', () => switchHoofdTab('verwijzing'));

  // Stap 1: dossier tabs
  $('tab-bricks').addEventListener('click', () => switchTab('bricks'));
  $('tab-screenshot').addEventListener('click', () => switchTab('screenshot'));
  $('tab-pdf-dossier').addEventListener('click', () => switchTab('pdf-dossier'));

  // Bricks scrape
  $('scrapeBtn').addEventListener('click', scrapeDossier);
  $('clearScrapeBtn').addEventListener('click', clearDossier);

  // Screenshot dossier
  $('analyseScreenshotBtn').addEventListener('click', analyseScreenshot);
  $('clearScreenshotBtn').addEventListener('click', clearScreenshot);

  // PDF dossier file input
  $('fileDossier').addEventListener('change', loadDossierPDF);
  $('clearDossierPDFBtn').addEventListener('click', clearDossierPDF);

  // Transparantie preview
  $('previewToggleBtn').addEventListener('click', togglePreview);

  // Stap 2: vraag tabs
  $('vtab-pdf').addEventListener('click', () => switchVraagTab('pdf'));
  $('vtab-screenshot').addEventListener('click', () => switchVraagTab('screenshot'));

  // Vraag PDF file input
  $('fileVraag').addEventListener('change', loadVraagPDF);
  $('clearVraagBtn').addEventListener('click', clearVraag);

  // Vraag screenshot
  $('analyseVraagScreenshotBtn').addEventListener('click', analyseVraagScreenshot);
  $('clearVraagScreenshotBtn').addEventListener('click', clearVraagScreenshot);

  // Brieftype knoppen
  $('typeGrid').addEventListener('click', (e) => {
    const btn = e.target.closest('.type-btn');
    if (btn) selectType(btn);
  });

  // Verwijzing: specialisme knoppen
  $('specGrid').addEventListener('click', (e) => {
    const btn = e.target.closest('.type-btn');
    if (btn) selectSpec(btn);
  });

  // Verwijzing: urgentie knoppen
  $('urgentieRow').addEventListener('click', (e) => {
    const btn = e.target.closest('.urg-btn');
    if (btn) selectUrgentie(btn);
  });

  // Verwijzing: genereer
  $('genVerwBtn').addEventListener('click', generateVerwijzing);

  // API key
  $('saveKeyBtn').addEventListener('click', saveKey);
  $('resetKeyBtn').addEventListener('click', resetKey);

  // Genereer + output
  $('genBtn').addEventListener('click', generate);
  $('copyBtn').addEventListener('click', copyOutput);
  $('clearAllBtn').addEventListener('click', clearAll);

  // Setup
  await checkBricks();
  await loadApiKeyStatus();
  setupScreenshotPaste();
  setupVraagScreenshotPaste();
  setupDropZones();
});

// ── Drop zones - JS event listeners (robuuster dan inline) ───
function setupDropZones() {
  // Dossier PDF drop zone
  const dropDossier = $('dropDossier');
  if (dropDossier) {
    dropDossier.addEventListener('click', (e) => {
      if (e.target.tagName !== 'INPUT') $('fileDossier').click();
    });
    dropDossier.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropDossier.classList.add('over');
    });
    dropDossier.addEventListener('dragenter', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropDossier.classList.add('over');
    });
    dropDossier.addEventListener('dragleave', (e) => {
      e.preventDefault();
      dropDossier.classList.remove('over');
    });
    dropDossier.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropDossier.classList.remove('over');
      const f = e.dataTransfer.files[0];
      if (f && f.type === 'application/pdf') {
        loadDossierPDF({ target: { files: [f] } });
      } else if (f) {
        showError('Alleen PDF bestanden worden geaccepteerd.');
      }
    });
  }

  // Vraag PDF drop zone
  const dropVraag = $('dropVraag');
  if (dropVraag) {
    dropVraag.addEventListener('click', (e) => {
      if (e.target.tagName !== 'INPUT') $('fileVraag').click();
    });
    dropVraag.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropVraag.classList.add('over');
    });
    dropVraag.addEventListener('dragenter', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropVraag.classList.add('over');
    });
    dropVraag.addEventListener('dragleave', (e) => {
      e.preventDefault();
      dropVraag.classList.remove('over');
    });
    dropVraag.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropVraag.classList.remove('over');
      const f = e.dataTransfer.files[0];
      if (f && f.type === 'application/pdf') {
        loadVraagPDF({ target: { files: [f] } });
      } else if (f) {
        showError('Alleen PDF bestanden worden geaccepteerd.');
      }
    });
  }
}

// ── Bricks check ──────────────────────────────────────────────
async function checkBricks() {
  const badge = $('statusBadge');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) { badge.textContent = '⬤ Geen tab'; badge.className = 'badge off'; return; }

    const isBricks = tab.url && /brickshuisarts|bricks-his|bricks\./i.test(tab.url);

    if (!isBricks) {
      badge.textContent = '⬤ Geen Bricks';
      badge.className = 'badge off';
      $('notBricks').style.display = 'block';
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: 'ping' }, (resp) => {
      if (chrome.runtime.lastError) {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        }, () => {
          badge.textContent = '⬤ Bricks (herlaad)';
          badge.className = 'badge on';
        });
      } else if (resp?.ok) {
        badge.textContent = '⬤ Bricks verbonden';
        badge.className = 'badge on';
      }
    });
  } catch {
    badge.textContent = '⬤ Fout';
    badge.className = 'badge off';
  }
}

// ── Tab wisselen (Stap 1: dossier) ───────────────────────────
function switchTab(tab) {
  ['bricks','screenshot','pdf-dossier'].forEach(t => {
    $('tab-' + t).classList.toggle('active', t === tab);
    $('pane-' + t).style.display = t === tab ? 'block' : 'none';
  });
}

// ── Tab wisselen (Stap 2: vraag/aanvrager) ───────────────────
function switchVraagTab(tab) {
  ['pdf','screenshot'].forEach(t => {
    $('vtab-' + t).classList.toggle('active', t === tab);
    $('vpane-' + t).style.display = t === tab ? 'block' : 'none';
  });
}

// ── BRICKS SCRAPEN ────────────────────────────────────────────
async function scrapeDossier() {
  const btn = $('scrapeBtn');
  const debugEl = $('scrapeDebug');
  btn.disabled = true;
  btn.textContent = '⏳ Bezig...';
  debugEl.style.display = 'none';
  clearError();

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) { showError('Geen actieve tab gevonden.'); btn.disabled=false; btn.textContent='↓ Ophalen uit Bricks'; return; }

    const tryMessage = () => new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { action: 'scrapeDossier' }, (resp) => {
        if (chrome.runtime.lastError) resolve(null);
        else resolve(resp);
      });
    });

    const tryInject = () => new Promise((resolve) => {
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          function extractText(el) {
            const clone = el.cloneNode(true);
            clone.querySelectorAll('button,input,svg,script,style,nav').forEach(e=>e.remove());
            return (clone.innerText||clone.textContent||'').replace(/\t+/g,' ').replace(/ {3,}/g,'  ').replace(/\n{4,}/g,'\n\n').trim();
          }
          const tekst = extractText(document.body).substring(0, 12000);
          const h1 = document.querySelector('h1,h2');
          return {
            secties: { 'Dossier (volledig)': tekst },
            patiëntNaamRauw: h1 ? h1.textContent.trim() : '',
            url: window.location.href
          };
        }
      }, (results) => {
        if (chrome.runtime.lastError || !results?.[0]) resolve(null);
        else resolve(results[0].result);
      });
    });

    const heeftGenoeg = (r) => r && Object.values(r.secties||{}).join('').length >= 30;

    let resp = await tryMessage();

    if (!heeftGenoeg(resp)) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      await new Promise(r => setTimeout(r, 500));
      resp = await tryMessage();
    }

    if (!heeftGenoeg(resp)) {
      resp = await tryInject();
    }

    if (!resp || Object.values(resp.secties||{}).join('').length < 10) {
      debugEl.style.display = 'block';
      debugEl.textContent = 'Weinig tekst gevonden op: ' + (resp?.url||'onbekend') +
        '\n\nTip: Zorg dat het dossier volledig geladen is en klik door alle tabs (Journaal, Medicatie, VG, Lab) voordat u ophaalt.';
      showError('Weinig tekst gevonden. Zie tip hieronder.');
      btn.disabled=false; btn.textContent='↓ Ophalen uit Bricks'; return;
    }

    state.rawSecties = resp.secties || {};
    state.patiëntNaamRauw = resp.patiëntNaamRauw || '';
    state.initialen = berekenInitialen(state.patiëntNaamRauw);
    state.dossierBron = 'bricks';
    zetStandaardSecties(state.rawSecties);

    $('scrapeIdle').style.display = 'none';
    $('scrapeDone').style.display = 'block';
    const totChars = Object.values(state.rawSecties).join('').length;
    $('scrapeMeta').textContent =
      Object.keys(state.rawSecties).join(' · ') + '\n' + Math.round(totChars/1000) + 'k tekens';
    $('clearScrapeBtn').style.display = 'block';
    btn.textContent = '↓ Opnieuw ophalen';

    bouwTransparantiePaneel();
    clearError();

  } catch(e) {
    showError('Fout bij ophalen: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

function clearDossier() {
  state.rawSecties = {}; state.patiëntNaamRauw = ''; state.initialen = ''; state.sectieAan = {};
  state.screenshotDataUrl = null; state.screenshotAnalysed = false;
  $('scrapeIdle').style.display = 'block';
  $('scrapeDone').style.display = 'none';
  $('transparantiePaneel').style.display = 'none';
  $('clearScrapeBtn').style.display = 'none';
  $('scrapeBtn').textContent = '↓ Ophalen uit Bricks';
  $('scrapeDebug').style.display = 'none';
  clearScreenshot();
}

// ── SCREENSHOT (dossier) ─────────────────────────────────────
function setupScreenshotPaste() {
  const area = $('screenshotArea');
  area.addEventListener('click', () => area.focus());
  area.setAttribute('tabindex', '0');

  document.addEventListener('paste', (e) => {
    // Dossier screenshot - alleen als dat pane zichtbaar is
    if ($('pane-screenshot').style.display !== 'none') {
      handleScreenshotPaste(e, 'dossier');
      return;
    }
    // Vraag screenshot - alleen als dat pane zichtbaar is
    if ($('vpane-screenshot').style.display !== 'none') {
      handleScreenshotPaste(e, 'vraag');
      return;
    }
  });
}

function handleScreenshotPaste(e, type) {
  const items = e.clipboardData?.items;
  if (!items) return;

  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const blob = item.getAsFile();
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (type === 'dossier') {
          state.screenshotDataUrl = ev.target.result;
          state.screenshotAnalysed = false;
          const preview = $('screenshotPreview');
          const img = document.createElement('img');
          img.src = ev.target.result;
          img.style.cssText = 'max-width:100%;max-height:200px;border-radius:5px;margin-top:8px';
          preview.innerHTML = '';
          preview.appendChild(img);
          $('analyseScreenshotBtn').style.display = 'block';
          $('clearScreenshotBtn').style.display = 'block';
          $('screenshotStatus').textContent = '✓ Screenshot geplakt - klik Analyseer';
        } else {
          state.vraagScreenshotDataUrl = ev.target.result;
          state.vraagScreenshotAnalysed = false;
          const preview = $('vraagScreenshotPreview');
          const img = document.createElement('img');
          img.src = ev.target.result;
          img.style.cssText = 'max-width:100%;max-height:200px;border-radius:5px;margin-top:8px';
          preview.innerHTML = '';
          preview.appendChild(img);
          $('analyseVraagScreenshotBtn').style.display = 'block';
          $('clearVraagScreenshotBtn').style.display = 'block';
          $('vraagScreenshotStatus').textContent = '✓ Screenshot geplakt - klik Analyseer';
        }
      };
      reader.readAsDataURL(blob);
      e.preventDefault();
      return;
    }
  }
}

// ── Vraag screenshot setup (click focus) ─────────────────────
function setupVraagScreenshotPaste() {
  const area = $('vraagScreenshotArea');
  if (!area) return;
  area.addEventListener('click', () => area.focus());
  area.setAttribute('tabindex', '0');
}

async function analyseScreenshot() {
  if (!state.screenshotDataUrl) return;

  const btn = $('analyseScreenshotBtn');
  const status = $('screenshotStatus');
  btn.disabled = true;
  btn.textContent = '⏳ Analyseren...';
  status.textContent = 'AI leest het scherm...';
  clearError();

  const apiKey = await getApiKey();
  if (!apiKey) { showError('Stel eerst uw API sleutel in.'); btn.disabled=false; btn.textContent='🔍 Analyseer screenshot'; return; }

  try {
    const base64 = state.screenshotDataUrl.split(',')[1];
    const mediaType = state.screenshotDataUrl.match(/data:([^;]+)/)?.[1] || 'image/png';

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 3000,
        messages: [{
          role: 'user',
          content: [
            { type: 'image', source: { type: 'base64', media_type: mediaType, data: base64 } },
            { type: 'text', text: `Dit is een screenshot van een medisch dossier systeem (Bricks HIS).
Extraheer alle medische informatie die zichtbaar is en structureer het per sectie.
Gebruik deze secties waar van toepassing: Journaal, Medicatie, Voorgeschiedenis, Lab, Metingen, Allergieën, Correspondentie.
Schrijf alle tekst letterlijk over zoals zichtbaar, inclusief datums, ICPC-codes, medicatienamen en doseringen.
Laat GEEN informatie weg. Geef de output als platte tekst per sectie.` }
          ]
        }]
      })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(()=>({}));
      throw new Error(err.error?.message || `API fout ${resp.status}`);
    }

    const data = await resp.json();
    const tekst = data.content.map(b => b.text||'').join('\n');
    const secties = parseerAISecties(tekst);

    state.rawSecties = secties;
    state.patiëntNaamRauw = '';
    state.initialen = 'P.X.';
    state.dossierBron = 'screenshot';
    zetStandaardSecties(secties);

    state.screenshotAnalysed = true;
    status.textContent = `✓ ${Object.keys(secties).length} secties herkend uit screenshot`;
    btn.textContent = '🔍 Opnieuw analyseren';

    bouwTransparantiePaneel();
    clearError();

  } catch(e) {
    showError('Screenshot analyse mislukt: ' + e.message);
    status.textContent = '';
  } finally {
    btn.disabled = false;
  }
}

// ── VRAAG SCREENSHOT ANALYSE ─────────────────────────────────
async function analyseVraagScreenshot() {
  if (!state.vraagScreenshotDataUrl) return;

  const btn = $('analyseVraagScreenshotBtn');
  const status = $('vraagScreenshotStatus');
  btn.disabled = true;
  btn.textContent = '⏳ Analyseren...';
  status.textContent = 'AI leest de brief/vraag...';
  clearError();

  const apiKey = await getApiKey();
  if (!apiKey) { showError('Stel eerst uw API sleutel in.'); btn.disabled=false; btn.textContent='🔍 Analyseer screenshot'; return; }

  try {
    const base64 = state.vraagScreenshotDataUrl.split(',')[1];
    const mediaType = state.vraagScreenshotDataUrl.match(/data:([^;]+)/)?.[1] || 'image/png';

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 3000,
        messages: [{
          role: 'user',
          content: [
            { type: 'image', source: { type: 'base64', media_type: mediaType, data: base64 } },
            { type: 'text', text: `Dit is een screenshot van een brief of vragenlijst van een advocaat, gemeente, UWV, verzekeraar of sociaal-medisch adviseur.
Extraheer alle tekst die zichtbaar is, inclusief:
- Vragen die beantwoord moeten worden (genummerd indien aanwezig)
- Context over de zaak
- Namen van afzenders/ontvangers
- Datums en referentienummers
Schrijf alle tekst letterlijk over zoals zichtbaar. Laat GEEN informatie weg.
Geef de output als platte tekst.` }
          ]
        }]
      })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(()=>({}));
      throw new Error(err.error?.message || `API fout ${resp.status}`);
    }

    const data = await resp.json();
    const tekst = data.content.map(b => b.text||'').join('\n');

    state.vraagText = tekst;
    state.vraagFileName = 'screenshot-vraag';
    state.vraagScreenshotAnalysed = true;

    status.textContent = '✓ Tekst uit screenshot geëxtraheerd';
    btn.textContent = '🔍 Opnieuw analyseren';
    clearError();

  } catch(e) {
    showError('Screenshot analyse mislukt: ' + e.message);
    status.textContent = '';
  } finally {
    btn.disabled = false;
  }
}

function clearVraagScreenshot() {
  state.vraagScreenshotDataUrl = null;
  state.vraagScreenshotAnalysed = false;
  state.vraagText = null;
  state.vraagFileName = null;
  $('vraagScreenshotPreview').innerHTML = '';
  $('analyseVraagScreenshotBtn').style.display = 'none';
  $('clearVraagScreenshotBtn').style.display = 'none';
  $('vraagScreenshotStatus').textContent = '';
}

function parseerAISecties(tekst) {
  const secties = {};
  const sectieTitels = ['Journaal','Medicatie','Voorgeschiedenis','Lab','Metingen','Allergieën','Correspondentie','Problemen'];
  let huidigeSectie = 'Dossier';
  let huidigeTekst = '';

  tekst.split('\n').forEach(lijn => {
    const gevonden = sectieTitels.find(s => lijn.toLowerCase().includes(s.toLowerCase()) && lijn.length < 50);
    if (gevonden) {
      if (huidigeTekst.trim()) secties[huidigeSectie] = huidigeTekst.trim();
      huidigeSectie = gevonden;
      huidigeTekst = '';
    } else {
      huidigeTekst += lijn + '\n';
    }
  });
  if (huidigeTekst.trim()) secties[huidigeSectie] = huidigeTekst.trim();
  return secties;
}

function clearScreenshot() {
  state.screenshotDataUrl = null;
  state.screenshotAnalysed = false;
  $('screenshotPreview').innerHTML = '';
  $('analyseScreenshotBtn').style.display = 'none';
  $('clearScreenshotBtn').style.display = 'none';
  $('screenshotStatus').textContent = '';
}

// ── PDF DOSSIER ───────────────────────────────────────────────
async function loadDossierPDF(event) {
  const file = event.target.files[0];
  if (!file) return;
  $('dropDossierLabel').innerHTML = '⏳ PDF lezen...';
  clearError();

  try {
    const tekst = await leesPDF(file);
    const secties = parseerPDFTekst(tekst);
    state.rawSecties = secties;
    state.patiëntNaamRauw = '';
    state.initialen = 'P.X.';
    state.dossierBron = 'pdf';
    zetStandaardSecties(secties);

    $('dropDossierLabel').textContent = `📄 ${file.name} (${Math.round(tekst.length/1000)}k tekens)`;
    $('dropDossier').classList.add('loaded');
    $('dossierPillText').textContent = `${Object.keys(secties).length} secties gelezen`;
    $('dossierPill').style.display = 'flex';
    bouwTransparantiePaneel();
  } catch(e) {
    showError('PDF leesfout: ' + e.message);
    $('dropDossierLabel').innerHTML = '📄 Sleep Medicom/Bricks PDF export hier';
  }
}

function clearDossierPDF() {
  state.rawSecties = {}; state.dossierBron = null;
  $('dropDossierLabel').innerHTML = '📄 Sleep Medicom/Bricks PDF export hier<br><small>of klik om te bladeren</small>';
  $('dropDossier').classList.remove('loaded');
  $('dossierPill').style.display = 'none';
  $('fileDossier').value = '';
  $('transparantiePaneel').style.display = 'none';
}

const SECTIE_MAP = {
  'Journaal':         ['journaal','soep','consult','icpc'],
  'Medicatie':        ['medicatie','recept','geneesmiddel'],
  'Voorgeschiedenis': ['voorgeschied','anamnese'],
  'Lab':              ['lab','bepaling','bloedwaarden','uitslag'],
  'Correspondentie':  ['correspon','verwijz','specialist'],
  'Metingen':         ['meting','bloeddruk','gewicht'],
  'Allergieën':       ['allergie','intolerant'],
};

function parseerPDFTekst(tekst) {
  const secties = {};
  let huidig = 'Dossier';
  let buf = '';
  tekst.split('\n').forEach(lijn => {
    const lijnLow = lijn.toLowerCase();
    let gevonden = false;
    for (const [s, kws] of Object.entries(SECTIE_MAP)) {
      if (kws.some(kw => lijnLow.includes(kw)) && lijn.length < 60) {
        if (buf.trim()) secties[huidig] = (secties[huidig]||'') + buf;
        huidig = s; buf = ''; gevonden = true; break;
      }
    }
    if (!gevonden) buf += lijn + '\n';
  });
  if (buf.trim()) secties[huidig] = (secties[huidig]||'') + buf;
  return secties;
}

// ── PDF lezen ─────────────────────────────────────────────────
async function leesPDF(file) {
  if (typeof pdfjsLib === 'undefined') throw new Error('PDF.js niet geladen. Voer download-pdfjs.bat uit.');
  const ab = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: ab }).promise;
  let tekst = '';
  for (let i = 1; i <= pdf.numPages; i++) {
    const pg = await pdf.getPage(i);
    const ct = await pg.getTextContent();
    tekst += '\n--- Pagina ' + i + ' ---\n' + ct.items.map(it=>it.str).join(' ');
  }
  return tekst;
}

// ── VRAAG PDF ─────────────────────────────────────────────────
async function loadVraagPDF(event) {
  const file = event.target.files[0];
  if (!file) return;
  $('dropVraagLabel').innerHTML = '⏳ PDF lezen...';
  clearError();
  try {
    const tekst = await leesPDF(file);
    state.vraagText = tekst;
    state.vraagFileName = file.name;
    $('dropVraagLabel').textContent = `📩 ${file.name}`;
    $('dropVraag').classList.add('loaded');
    $('vraagPillText').textContent = 'Vraag-PDF geladen';
    $('vraagPill').style.display = 'flex';
  } catch(e) {
    showError('PDF leesfout: ' + e.message);
    $('dropVraagLabel').innerHTML = '📩 Sleep vraag-PDF hier<br><small>Advocaat / SMA / Gemeente / UWV - of klik</small>';
  }
}

function clearVraag() {
  state.vraagText = null; state.vraagFileName = null;
  $('dropVraag').classList.remove('loaded');
  $('dropVraagLabel').innerHTML = '📩 Sleep vraag-PDF hier<br><small>Advocaat / SMA / Gemeente / UWV - of klik</small>';
  $('vraagPill').style.display = 'none';
  $('fileVraag').value = '';
}

// ── PRIVACY FILTER ────────────────────────────────────────────
function berekenInitialen(naam) {
  if (!naam) return 'P.X.';
  const schoon = naam.replace(/\b(?:de heer|mevrouw|dhr\.|mw\.|dr\.|drs\.)\s*/gi,'').trim();
  const tussenvoegsels = ['van','de','den','der','ten','ter','op','in','het',"'t",'le','la'];
  return schoon.split(/\s+/)
    .filter(d => !tussenvoegsels.includes(d.toLowerCase()) && d.length > 0)
    .map(d => d[0].toUpperCase() + '.')
    .join('') || 'P.X.';
}

// Patronen zonder /g flag - worden per aanroep via replaceAll-achtig gedrag gebruikt
const PRIVACY_PATRONEN = [
  [/\b\d{9}\b/g,                                                                    '[BSN]'],
  [/\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b/g,                                           '[DATUM]'],
  [/\b\d{1,2}\s+(?:jan(?:uari)?|feb(?:ruari)?|mrt|maa?rt|apr(?:il)?|mei|jun(?:i)?|jul(?:i)?|aug(?:ustus)?|sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{4}\b/gi, '[DATUM]'],
  [/\b\d{4}\s?[A-Z]{2}\b/g,                                                         '[POSTCODE]'],
  [/\b(?:06|0\d{1,2})[-\s]?\d{6,8}\b/g,                                             '[TEL]'],
  [/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,                              '[EMAIL]'],
  [/\b(?:de heer|mevrouw|dhr\.|mw\.|drs?\.|dr\.)\s+[A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*/g, '[NAAM]'],
];

function privacyFilter(tekst, volleNaam) {
  let out = tekst;
  if (volleNaam && volleNaam.length > 2) {
    volleNaam.split(/\s+/).filter(d=>d.length>2).forEach(deel => {
      out = out.replace(new RegExp(deel.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi'),'[NAAM]');
    });
  }
  for (const [re, tag] of PRIVACY_PATRONEN) {
    re.lastIndex = 0; // Reset voor hergebruik
    out = out.replace(re, tag);
  }
  return out;
}

// ── TRANSPARANTIE PANEEL ──────────────────────────────────────
function bouwTransparantiePaneel() {
  const paneel = $('transparantiePaneel');

  const naamHtml = state.patiëntNaamRauw
    ? `<span class="naam-gevonden">✕ ${escapeHtml(state.patiëntNaamRauw)}</span> → <span class="naam-initialen">${escapeHtml(state.initialen)}</span>`
    : `<span style="color:var(--muted);font-size:10px">Geen naam gevonden - initialen: </span><span class="naam-initialen">${escapeHtml(state.initialen)}</span>`;
  $('tpNaam').innerHTML = '👤 Naam: ' + naamHtml;

  const container = $('sectieToggles');
  container.innerHTML = '';
  for (const [sectie, tekst] of Object.entries(state.rawSecties)) {
    const aan = state.sectieAan[sectie];
    const safeId = sectie.replace(/[^a-zA-Z0-9]/g, '_');
    const row = document.createElement('div');
    row.className = 'sectie-row';
    row.innerHTML = `
      <div class="sectie-info">
        <span class="sectie-naam">${escapeHtml(sectie)}</span>
        <span class="sectie-meta" id="meta-${safeId}">${Math.round(tekst.length/100)/10}k · ${aan?'✓ verstuurd':'✗ niet verstuurd'}</span>
      </div>
      <label class="toggle">
        <input type="checkbox" ${aan?'checked':''}>
        <span class="slider"></span>
      </label>`;
    row.querySelector('input').addEventListener('change', function() {
      toggleSectie(sectie, this.checked);
    });
    container.appendChild(row);
  }

  updatePreview();
  paneel.style.display = 'block';
}

function toggleSectie(sectie, aan) {
  state.sectieAan[sectie] = aan;
  const safeId = sectie.replace(/[^a-zA-Z0-9]/g, '_');
  const meta = $('meta-' + safeId);
  if (meta) meta.textContent = Math.round((state.rawSecties[sectie]||'').length/100)/10 + 'k · ' + (aan?'✓ verstuurd':'✗ niet verstuurd');
  updatePreview();
}

function bouwServerTekst() {
  let out = `PATIËNT: ${state.initialen}\n\n`;
  for (const [sectie, tekst] of Object.entries(state.rawSecties)) {
    if (!state.sectieAan[sectie]) continue;
    out += `══ ${sectie.toUpperCase()} ══\n${privacyFilter(tekst, state.patiëntNaamRauw)}\n\n`;
  }
  return out.trim();
}

function updatePreview() {
  $('previewText').textContent = bouwServerTekst();
}

function togglePreview() {
  const c = $('previewContent');
  const btn = $('previewToggleBtn');
  const zichtbaar = c.style.display !== 'none';
  c.style.display = zichtbaar ? 'none' : 'block';
  btn.textContent = zichtbaar ? '👁 Toon preview' : '👁 Verberg preview';
  if (!zichtbaar) updatePreview();
}

// ── BRIEFTYPE ─────────────────────────────────────────────────
function selectType(el) {
  $('typeGrid').querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  state.selectedType = el.dataset.type;
}

// ── API KEY ───────────────────────────────────────────────────
async function loadApiKeyStatus() {
  const apiKey = await getApiKey();
  if (apiKey) {
    $('apiSection').style.display = 'none';
    $('keyOk').style.display = 'block';
  }
}

function saveKey() {
  const key = $('apiKey').value.trim();
  if (!key.startsWith('sk-ant')) { showError('Ongeldige sleutel (begint met sk-ant-)'); return; }
  chrome.storage.local.set({ apiKey: key }, () => {
    $('apiSection').style.display = 'none';
    $('keyOk').style.display = 'block';
    clearError();
  });
}

function resetKey() {
  chrome.storage.local.remove('apiKey', () => {
    $('apiSection').style.display = 'block';
    $('keyOk').style.display = 'none';
    $('apiKey').value = '';
  });
}

// ── GENEREER BRIEF (met streaming) ───────────────────────────
const SYSTEM = {
  advocaat:    'Je bent een Nederlandse huisarts die een medische informatiebrief schrijft aan een advocaat. Beantwoord alle gestelde vragen punt voor punt, juridisch-medisch correct en feitelijk. Verwijs naar de patiënt met de opgegeven initialen.',
  sma:         'Je bent een Nederlandse huisarts die reageert op vragen van een sociaal-medisch adviseur. Beschrijf diagnose, behandelstatus, functionele beperkingen en prognose concreet. Verwijs naar de patiënt met de opgegeven initialen.',
  gemeente:    'Je bent een Nederlandse huisarts die een verklaring schrijft voor de gemeente. Focus op zelfredzaamheid en functionele beperkingen. Verwijs naar de patiënt met de opgegeven initialen.',
  verzekeraar: 'Je bent een Nederlandse huisarts die reageert op een verzekeraar. Wees precies over diagnose, behandeltraject en prognose. Verwijs naar de patiënt met de opgegeven initialen.',
  uwv:         'Je bent een Nederlandse huisarts die reageert op UWV. Beschrijf medisch beeld, functionele mogelijkheden en beperkingen. Verwijs naar de patiënt met de opgegeven initialen.',
  overig:      'Je bent een Nederlandse huisarts die een medische informatiebrief schrijft aan een externe instantie. Schrijf professioneel en feitelijk. Verwijs naar de patiënt met de opgegeven initialen.',
};

const TYPE_LABELS = {
  advocaat:'advocaat', sma:'sociaal-medisch adviseur', gemeente:'gemeente',
  verzekeraar:'verzekeraar', uwv:'UWV', overig:'externe instantie'
};

async function generate() {
  clearError();
  const heeftDossier = Object.keys(state.rawSecties).length > 0 && Object.values(state.sectieAan).some(v=>v);
  if (!heeftDossier) { showError('Voer eerst een dossier in via Bricks, Screenshot of PDF (stap 01).'); return; }

  const apiKey = await getApiKey();
  if (!apiKey) { showError('Stel eerst uw API sleutel in.'); return; }

  const btn = $('genBtn');
  const outWrap = $('outputWrap');
  const outBody = $('outputBody');
  const extra = $('extraInstructie').value.trim();

  const dossierTekst = bouwServerTekst();
  const vraagTekst = state.vraagText ? privacyFilter(state.vraagText, state.patiëntNaamRauw) : null;
  const typeLabel = TYPE_LABELS[state.selectedType];
  const sep = '─'.repeat(40);

  const userPrompt = vraagTekst
    ? `INFORMATIEVRAAG VAN DE AANVRAGER (${typeLabel}):\n${sep}\n${vraagTekst}\n${sep}\n\nPATIËNTDOSSIER (gefilterd - initialen: ${state.initialen}):\n${sep}\n${dossierTekst}\n${sep}\n\nBeantwoord elke vraag concreet vanuit het dossier. Schrijf een formele informatiebrief als huisarts.${extra?'\n\nEXTRA INSTRUCTIE: '+extra:''}`
    : `PATIËNTDOSSIER (gefilterd - initialen: ${state.initialen}):\n${sep}\n${dossierTekst}\n${sep}\n\nSchrijf een informatiebrief aan de ${typeLabel}.${extra?'\n\nINSTRUCTIE: '+extra:' Geef samenvatting van diagnose, behandelstatus en prognose.'}`;

  btn.disabled = true;
  btn.textContent = 'Bezig...';
  outWrap.style.display = 'block';
  outBody.textContent = '';

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 2000,
        stream: true,
        system: SYSTEM[state.selectedType],
        messages: [{ role: 'user', content: userPrompt }],
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(()=>({}));
      throw new Error(err.error?.message || `API fout ${resp.status}`);
    }

    // Stream de response
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Bewaar incomplete regel

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;

        try {
          const evt = JSON.parse(data);
          if (evt.type === 'content_block_delta' && evt.delta?.text) {
            outBody.textContent += evt.delta.text;
            outBody.scrollTop = outBody.scrollHeight;
          }
        } catch {
          // Skip ongeldige JSON chunks
        }
      }
    }

  } catch(e) {
    outWrap.style.display = 'none';
    showError('Genereren mislukt: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '✦ Genereer informatiebrief';
  }
}

async function copyOutput() {
  await navigator.clipboard.writeText($('outputBody').textContent);
  const btns = document.querySelectorAll('.output-header button');
  btns[0].textContent = '✓ Gekopieerd';
  setTimeout(() => btns[0].textContent = 'Kopieer', 2000);
}

function clearAll() {
  clearDossier(); clearVraag(); clearVraagScreenshot();
  $('outputWrap').style.display = 'none';
  $('extraInstructie').value = '';
  clearError();
}

// ── HOOFDTAB WISSELEN ─────────────────────────────────────────
function switchHoofdTab(tab) {
  ['brief','verwijzing'].forEach(t => {
    $('htab-' + t).classList.toggle('active', t === tab);
    $('page-' + t).style.display = t === tab ? 'block' : 'none';
  });
  // Update verwijzing dossier-status wanneer we erheen navigeren
  if (tab === 'verwijzing') updateVerwDossierStatus();
}

function updateVerwDossierStatus() {
  const heeftDossier = Object.keys(state.rawSecties).length > 0;
  $('verwDossierStatus').style.display = heeftDossier ? 'none' : 'block';
  $('verwDossierOk').style.display = heeftDossier ? 'block' : 'none';
  if (heeftDossier) {
    const totChars = Object.values(state.rawSecties).join('').length;
    $('verwDossierMeta').textContent =
      Object.keys(state.rawSecties).join(' · ') + ' - ' + Math.round(totChars/1000) + 'k tekens';
  }
}

// ── VERWIJZING: SPECIALISME ──────────────────────────────────
function selectSpec(el) {
  $('specGrid').querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  state.selectedSpec = el.dataset.spec;
  $('specAnders').style.display = el.dataset.spec === 'overig' ? 'block' : 'none';
}

function selectUrgentie(el) {
  $('urgentieRow').querySelectorAll('.urg-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  state.selectedUrgentie = el.dataset.urg;
}

// ── VERWIJZING: GENEREER (met Haiku - goedkoop) ─────────────
const VERWIJZING_SYSTEM = `Je bent een Nederlandse huisarts die een verwijsbrief schrijft naar een medisch specialist.
Schrijf een professionele, bondige verwijsbrief in het standaard Nederlandse verwijsformaat:
- Geachte collega
- Reden van verwijzing
- Relevante voorgeschiedenis (kort, uit dossier)
- Huidige medicatie (indien relevant)
- Relevante bevindingen / labwaarden
- Vraagstelling aan specialist
- Met vriendelijke groet

Gebruik de patiënt-initialen, nooit de volledige naam. Wees concreet en beknopt.
Vermeld alleen informatie die relevant is voor het betreffende specialisme.`;

const SPEC_LABELS = {
  cardiologie: 'cardioloog',
  neurologie: 'neuroloog',
  orthopedie: 'orthopedisch chirurg',
  interne: 'internist',
  dermatologie: 'dermatoloog',
  psychiatrie: 'psychiater',
  chirurgie: 'chirurg',
  ggz: 'GGZ',
  overig: null,
};

async function generateVerwijzing() {
  clearError();
  const heeftDossier = Object.keys(state.rawSecties).length > 0 && Object.values(state.sectieAan).some(v => v);
  if (!heeftDossier) { showError('Laad eerst een dossier via de Informatiebrief-tab.'); return; }

  const apiKey = await getApiKey();
  if (!apiKey) { showError('Stel eerst uw API sleutel in.'); return; }

  const reden = $('verwReden').value.trim();
  if (!reden) { showError('Vul een verwijsreden / vraagstelling in.'); return; }

  const spec = state.selectedSpec === 'overig'
    ? ($('specVrij').value.trim() || 'medisch specialist')
    : (SPEC_LABELS[state.selectedSpec] || state.selectedSpec);
  const urgentie = state.selectedUrgentie;
  const extra = $('verwExtra').value.trim();
  const dossierTekst = bouwServerTekst();
  const sep = '─'.repeat(40);

  const userPrompt = `VERWIJZING NAAR: ${spec}
URGENTIE: ${urgentie}
VERWIJSREDEN: ${reden}${extra ? '\nEXTRA CONTEXT: ' + extra : ''}

PATIËNTDOSSIER (gefilterd - initialen: ${state.initialen}):
${sep}
${dossierTekst}
${sep}

Schrijf een verwijsbrief aan de ${spec}. Focus op informatie die relevant is voor ${spec}.
Urgentieniveau: ${urgentie}.`;

  const btn = $('genVerwBtn');
  const outWrap = $('outputWrap');
  const outBody = $('outputBody');

  btn.disabled = true;
  btn.textContent = 'Bezig...';
  $('outputTitle').textContent = '✓ Verwijsbrief gegenereerd';
  outWrap.style.display = 'block';
  outBody.textContent = '';

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 1200,
        stream: true,
        system: VERWIJZING_SYSTEM,
        messages: [{ role: 'user', content: userPrompt }],
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error?.message || `API fout ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const evt = JSON.parse(data);
          if (evt.type === 'content_block_delta' && evt.delta?.text) {
            outBody.textContent += evt.delta.text;
            outBody.scrollTop = outBody.scrollHeight;
          }
        } catch { /* skip */ }
      }
    }

  } catch (e) {
    outWrap.style.display = 'none';
    showError('Genereren mislukt: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '✦ Genereer verwijsbrief';
  }
}

function showError(msg) { const el = $('errorBar'); el.textContent = '⚠ '+msg; el.style.display='block'; }
function clearError() { $('errorBar').style.display='none'; }

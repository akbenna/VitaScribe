/**
 * VitaScribe - Bricks HIS Content Script
 *
 * Full recording + SOEP workflow as a floating widget on the Bricks page.
 * No separate tabs, no popups — everything happens here.
 */

/* ── Selectors for Bricks field injection ── */

var DEFAULT_SELECTORS = {
  journaal: [
    'textarea[name*="journaal"]', 'textarea[name*="journal"]',
    'textarea[name*="notitie"]', '[contenteditable="true"][data-field*="journaal"]',
    '.journal-editor textarea', '.consult-notes textarea',
  ],
  soep_s: ['textarea[name*="subjectief"]', 'textarea[data-soep="S"]', '.soep-field-s textarea'],
  soep_o: ['textarea[name*="objectief"]', 'textarea[data-soep="O"]', '.soep-field-o textarea'],
  soep_e: ['textarea[name*="evaluatie"]', 'textarea[data-soep="E"]', '.soep-field-e textarea'],
  soep_p: ['textarea[name*="plan"]', 'textarea[data-soep="P"]', '.soep-field-p textarea'],
  icpc: ['input[name*="icpc"]', 'input[name*="ICPC"]', '.icpc-input input'],
};

var userSelectors = {};
var lastResult = null;

/* ── Recording state ── */

var mediaRecorder = null;
var audioChunks = [];
var audioStream = null;
var timerInterval = null;
var recStartTime = null;
var live = null;           // SVConsultLive-verbinding, of null bij opnemen en achteraf versturen
var liveAfgebroken = null; // melding als de server het consult weigert (licentie)
var nadictaatVanaf = null; // seconde van de opname waarop de arts "Nadicteren" koos

// Kleine stukjes, zodat het gesprek live naar de server kan. Samen vormen
// ze ook de reservekopie: dezelfde stukjes achter elkaar zijn een geldig
// webm-bestand.
var CONSULT_CHUNK_MS = 250;

/* ── Selector helpers ── */

async function loadSelectors() {
  try {
    var stored = await chrome.storage.sync.get(['bricksSelectors']);
    if (stored.bricksSelectors) userSelectors = JSON.parse(stored.bricksSelectors);
  } catch (e) { /* defaults */ }
}

function findElement(key) {
  var lists = [
    userSelectors[key] ? (Array.isArray(userSelectors[key]) ? userSelectors[key] : [userSelectors[key]]) : [],
    DEFAULT_SELECTORS[key] || [],
  ];
  for (var i = 0; i < lists.length; i++) {
    for (var j = 0; j < lists[i].length; j++) {
      var el = document.querySelector(lists[i][j]);
      if (el) return el;
    }
  }
  return null;
}

function setFieldValue(el, value) {
  if (!el || !value) return false;
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (el.contentEditable === 'true') {
    el.textContent = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }
  return true;
}

/* ── SOEP injection ── */

function injectSOEP(data) {
  var soep = data.soep || {};
  var injected = false;

  var fields = { soep_s: soep.s, soep_o: soep.o, soep_e: soep.e, soep_p: soep.p };
  for (var key in fields) {
    var el = findElement(key);
    if (el && fields[key]) { setFieldValue(el, fields[key]); injected = true; }
  }

  var icpcEl = findElement('icpc');
  if (icpcEl && soep.icpc_code) setFieldValue(icpcEl, soep.icpc_code);

  if (!injected) {
    var journalEl = findElement('journaal');
    if (journalEl) { setFieldValue(journalEl, formatSOEPText(data)); injected = true; }
  }

  if (!injected && document.activeElement) {
    var active = document.activeElement;
    if (active.tagName === 'TEXTAREA' || active.contentEditable === 'true') {
      setFieldValue(active, formatSOEPText(data));
      injected = true;
    }
  }

  return injected;
}

function formatSOEPText(data) {
  var soep = data.soep || {};
  var parts = [];
  if (data.decisief) parts.push('[Decisief] ' + data.decisief);
  parts.push('');
  if (soep.s) parts.push('S: ' + soep.s);
  if (soep.o) parts.push('O: ' + soep.o);
  if (soep.e) parts.push('E: ' + soep.e);
  if (soep.p) parts.push('P: ' + soep.p);
  if (soep.icpc_code) parts.push('\nICPC: ' + soep.icpc_code + (soep.icpc_titel ? ' - ' + soep.icpc_titel : ''));
  return parts.join('\n');
}

/* ── Toast notification ── */

function showNotification(text) {
  var n = document.createElement('div');
  n.className = 'sv-notification';
  n.textContent = text;
  document.body.appendChild(n);
  setTimeout(function() { n.classList.add('sv-notification-fade'); setTimeout(function() { n.remove(); }, 300); }, 2500);
}

/* ── Timer ── */

function updateTimer() {
  var el = document.getElementById('sv-timer');
  if (!el || !recStartTime) return;
  var s = Math.floor((Date.now() - recStartTime) / 1000);
  el.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

/* ── Recording ── */

// After the extension is updated or reloaded, scripts already running in an
// open page lose their connection to it until the page is refreshed.
var STALE_PAGE_MESSAGE = 'VitaScribe is bijgewerkt. Ververs deze pagina (F5) en probeer opnieuw.';

function extensionAlive() {
  try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; }
}

async function startRecording() {
  if (!extensionAlive()) {
    showNotification(STALE_PAGE_MESSAGE);
    return;
  }
  // KNMG (2026): consultopname alleen met toestemming van de patiënt.
  var consentBox = document.getElementById('sv-consent');
  if (consentBox && !consentBox.checked) {
    showNotification('Vink eerst aan dat de patiënt toestemming geeft voor de opname.');
    return;
  }

  // Pre-check microfoontoestemming
  try {
    var permResult = await navigator.permissions.query({ name: 'microphone' });
    if (permResult.state === 'denied') {
      showNotification('Microfoontoegang geblokkeerd. Sta microfoon toe in de browserinstellingen (adresbalk → slot-icoon).');
      return;
    }
  } catch (e) { /* permissions API niet beschikbaar, probeer gewoon */ }

  try {
    var config = await chrome.storage.sync.get(['micDevice']);
    var audioConstraints = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (config.micDevice) audioConstraints.deviceId = { exact: config.micDevice };

    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints
    });
  } catch (err) {
    var errMsg = err.message || '';
    if (errMsg.includes('Extension context invalidated')) {
      showNotification(STALE_PAGE_MESSAGE);
    } else if (errMsg.toLowerCase().includes('dismiss')) {
      showNotification('Microfoontoegang geweigerd (dismissed). Klik op het slot-icoon in de adresbalk om microfoontoegang in te schakelen.');
    } else {
      showNotification('Microfoon niet beschikbaar: ' + errMsg);
    }
    return;
  }

  audioChunks = [];
  liveAfgebroken = null;
  nadictaatVanaf = null;
  var nadicteerKnop = document.getElementById('sv-btn-nadicteer');
  if (nadicteerKnop) nadicteerKnop.classList.remove('hidden');
  live = await startLive();
  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus' : 'audio/webm';

  // 64 kbit/s opus is ruim voor spraak en houdt de stukjes klein.
  mediaRecorder = new MediaRecorder(audioStream, { mimeType: mimeType, audioBitsPerSecond: 64000 });

  mediaRecorder.ondataavailable = function(e) {
    if (e.data && e.data.size > 0) {
      audioChunks.push(e.data);            // reservekopie, blijft tot het verslag er is
      if (live) live.stuur(e.data);
    }
  };

  mediaRecorder.onstop = function() {
    var mime = mediaRecorder ? mediaRecorder.mimeType : 'audio/webm';
    var blob = new Blob(audioChunks, { type: mime });

    if (audioStream) { audioStream.getTracks().forEach(function(t) { t.stop(); }); audioStream = null; }
    rondAf(blob, mime);
  };

  mediaRecorder.start(CONSULT_CHUNK_MS);
  recStartTime = Date.now();
  timerInterval = setInterval(updateTimer, 500);
  setWidgetState('recording');
  setRecLabel(live ? 'Luistert mee' : 'Opname actief');
}

/* ── Nadicteren ── */

// De patiënt is weg. De arts dicteert nog kort onderzoek en beleid; alles
// vanaf dit moment is alleen de arts, en het taalmodel laat dat leiden in
// O, E en P. De opname loopt gewoon door, dus er gaat niets verloren.
function startNadictaat() {
  if (!recStartTime || nadictaatVanaf !== null) return;
  nadictaatVanaf = Math.round((Date.now() - recStartTime) / 100) / 10;
  if (live) live.nadictaat(nadictaatVanaf);
  var knop = document.getElementById('sv-btn-nadicteer');
  if (knop) knop.classList.add('hidden');
  setRecLabel('Nadicteren: onderzoek en beleid');
}

/* ── Live consult ── */

function setRecLabel(tekst) {
  var el = document.querySelector('#vitascribe-widget .sv-rec-label');
  if (el) el.textContent = tekst;
}

// Het gesprek gaat live naar de server, die het per spreker volgt. Staat
// "consultLive" in de instellingen op "uit", dan wordt het consult zoals
// vroeger eerst opgenomen en na stop in zijn geheel verstuurd.
async function startLive() {
  try {
    var config = await SVInstellingen.lees(['apiUrl', 'apiKey', 'llmProvider', 'consultLive']);
    if (config.consultLive === 'uit' || typeof SVConsultLive === 'undefined') return null;
    var praktijk = await SVPraktijk.nummers();
    return SVConsultLive.start({
      apiUrl: (config.apiUrl || 'http://localhost:8002').replace(/\/$/, ''),
      apiKey: config.apiKey,
      praktijk: praktijk,
      llmProvider: config.llmProvider,
      onVoortgang: function(seconden, sprekers) {
        if (nadictaatVanaf !== null) return;   // het label zegt dan "Nadicteren"
        setRecLabel(sprekers > 1 ? 'Luistert mee \u00b7 ' + sprekers + ' stemmen' : 'Luistert mee');
      },
      onFout: function(melding, terugval) {
        if (terugval) {
          // De opname loopt gewoon door; na stop gaat hij in zijn geheel naar de server.
          setRecLabel('Opname actief (live verbinding weg)');
        } else {
          liveAfgebroken = melding;
          stopRecording();
        }
      },
    });
  } catch (e) {
    return null;   // dan gewoon opnemen en achteraf versturen
  }
}

async function rondAf(blob, mime) {
  var verbinding = live;
  live = null;
  if (liveAfgebroken) {
    if (verbinding) verbinding.sluit();
    setWidgetState('error');
    document.getElementById('sv-error-msg').textContent = liveAfgebroken;
    return;
  }
  if (blob.size < 1000) {
    if (verbinding) verbinding.sluit();
    setWidgetState('idle');
    showNotification('Opname te kort. Probeer langer op te nemen.');
    return;
  }

  setWidgetState('processing');
  if (verbinding) {
    updateProcessingStep('Verslag wordt gemaakt...');
    var uit = await verbinding.stop(90000);
    if (uit.ok) {
      audioChunks = [];
      toonResultaat(uit.data);
      return;
    }
    updateProcessingStep('Live lukte niet; de opname wordt alsnog verwerkt...');
  }
  sendAudioToAPI(blob, mime);
}

function toonResultaat(result) {
  lastResult = result;
  // Persist for popup fallback
  chrome.storage.local.set({ sv_state: 'results', sv_data: result });
  setWidgetState('results');
  displayResults(result);
}

function stopRecording() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

/* ── API call ── */

async function sendAudioToAPI(blob, mimeType) {
  try {
    var config = await SVInstellingen.lees(['apiUrl', 'apiKey', 'sttProvider', 'llmProvider']);
    var apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');

    var formData = new FormData();
    var ext = mimeType.includes('webm') ? 'webm' : 'wav';
    formData.append('audio', blob, 'consult.' + ext);
    formData.append('consent', 'true');
    if (nadictaatVanaf !== null) formData.append('nadictaat_vanaf', String(nadictaatVanaf));
    if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
    if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

    var headers = {};
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);

    updateProcessingStep('Audio wordt getranscribeerd...');

    var response = await fetch(apiUrl + '/api/v1/consult/process', {
      method: 'POST',
      headers: headers,
      body: formData,
    });

    if (!response.ok) {
      var errText = await response.text();
      throw new Error('API fout (' + response.status + '): ' + errText.substring(0, 200));
    }

    var result = await response.json();
    audioChunks = [];
    toonResultaat(result);

  } catch (err) {
    var errorMsg = err.message || 'Onbekende fout';

    if (errorMsg === 'Failed to fetch') {
      errorMsg = 'Kan de API niet bereiken op: ' + apiUrl +
        '. Controleer de API URL in VitaScribe Instellingen.';
    } else if (errorMsg.includes('Extension context invalidated')) {
      errorMsg = STALE_PAGE_MESSAGE;
    } else if (errorMsg.indexOf('API fout (403)') === 0) {
      errorMsg = 'API-sleutel klopt niet. Controleer de sleutel in VitaScribe Instellingen ' +
        '(klik Opslaan) en ververs daarna deze pagina (F5).';
    }

    setWidgetState('error');
    document.getElementById('sv-error-msg').textContent = errorMsg;
  }
}

/* ── Widget UI ── */

function createWidget() {
  var widget = document.createElement('div');
  widget.id = 'vitascribe-widget';

  widget.innerHTML =
    // Toggle button
    '<div class="sv-fab" id="sv-fab">' +
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="white">' +
        '<path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>' +
        '<path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>' +
      '</svg>' +
    '</div>' +

    // Panel
    '<div class="sv-panel hidden" id="sv-panel">' +
      // Header
      '<div class="sv-header">' +
        '<span class="sv-logo">SV</span>' +
        '<span class="sv-title">VitaScribe</span>' +
        '<button id="sv-close" class="sv-close-btn">&times;</button>' +
      '</div>' +

      // State: Idle
      '<div class="sv-body" id="sv-state-idle">' +
        '<p class="sv-hint">Klik om het consult op te nemen</p>' +
        '<label class="sv-consent"><input type="checkbox" id="sv-consent"> Patiënt geeft toestemming voor opname en AI-verslag</label>' +
        '<button id="sv-btn-record" class="sv-btn sv-btn-record">' +
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>' +
          ' Start opname' +
        '</button>' +
      '</div>' +

      // State: Recording
      '<div class="sv-body hidden" id="sv-state-recording">' +
        '<div class="sv-rec-indicator">' +
          '<span class="sv-pulse"></span>' +
          '<span class="sv-rec-label">Opname actief</span>' +
        '</div>' +
        '<div id="sv-timer" class="sv-timer">00:00</div>' +
        '<button id="sv-btn-nadicteer" class="sv-btn sv-btn-secondary" title="De patiënt is weg: dicteer nog kort onderzoek en beleid">Nadicteren</button>' +
        '<button id="sv-btn-stop" class="sv-btn sv-btn-stop">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>' +
          ' Stop &amp; verwerk' +
        '</button>' +
      '</div>' +

      // State: Processing
      '<div class="sv-body hidden" id="sv-state-processing">' +
        '<div class="sv-spinner"></div>' +
        '<p id="sv-processing-step" class="sv-processing-text">Audio wordt verwerkt...</p>' +
      '</div>' +

      // State: Results
      '<div class="sv-body hidden" id="sv-state-results">' +
        '<div class="sv-result-section">' +
          '<div class="sv-label">DECISIEF</div>' +
          '<p id="sv-decisief" class="sv-decisief-text"></p>' +
        '</div>' +
        '<div id="sv-corrections-badge" class="sv-corrections-badge hidden">' +
          '<span id="sv-corrections-count"></span> woordcorrecties toegepast' +
        '</div>' +
        '<div class="sv-soep-grid">' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">S</span><p id="sv-soep-s"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">O</span><p id="sv-soep-o"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">E</span><p id="sv-soep-e"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">P</span><p id="sv-soep-p"></p></div>' +
        '</div>' +
        '<div id="sv-icpc" class="sv-icpc hidden">' +
          '<span id="sv-icpc-code"></span> <span id="sv-icpc-title"></span>' +
        '</div>' +
        '<div class="sv-actions">' +
          '<button id="sv-btn-inject" class="sv-btn sv-btn-primary">Invoegen in Bricks</button>' +
          '<button id="sv-btn-copy" class="sv-btn sv-btn-secondary">Kopieer</button>' +
        '</div>' +
        '<button id="sv-btn-new" class="sv-btn sv-btn-link">Nieuw consult</button>' +
      '</div>' +

      // State: Error
      '<div class="sv-body hidden" id="sv-state-error">' +
        '<p id="sv-error-msg" class="sv-error-text"></p>' +
        '<button id="sv-btn-retry" class="sv-btn sv-btn-secondary">Opnieuw</button>' +
      '</div>' +

    '</div>';

  document.body.appendChild(widget);

  // ── Event listeners ──

  document.getElementById('sv-fab').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.toggle('hidden');
  });

  document.getElementById('sv-close').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.add('hidden');
  });

  document.getElementById('sv-btn-record').addEventListener('click', function() {
    startRecording();
  });

  document.getElementById('sv-btn-nadicteer').addEventListener('click', function() {
    startNadictaat();
  });

  document.getElementById('sv-btn-stop').addEventListener('click', function() {
    stopRecording();
  });

  document.getElementById('sv-btn-inject').addEventListener('click', async function() {
    if (!lastResult) return;
    if (!extensionAlive()) { showNotification(STALE_PAGE_MESSAGE); return; }
    // First the S/O/E/P fields the doctor pointed at ("Velden koppelen").
    var soep = lastResult.soep || {};
    var values = { s: soep.s, o: soep.o, e: soep.e, p: soep.p };
    if (soep.icpc_code && values.e && values.e.indexOf(soep.icpc_code) === -1) values.e += ' (' + soep.icpc_code + ')';
    var res = await chrome.runtime.sendMessage({ action: 'SV_FILL_SOEP_REQUEST', values: values, icpc: soep.icpc_code || '' }).catch(function() { return null; });
    if (res && res.filled && res.filled.length) {
      showNotification(res.missing.length
        ? 'Deels ingevuld; niet gevonden: ' + res.missing.join(', ').toUpperCase() + '. Is het consult open?'
        : 'SOEP per veld ingevuld in Bricks!');
      return;
    }
    var ok = injectSOEP(lastResult);
    if (ok) {
      showNotification('SOEP ingevoegd in Bricks!');
    } else {
      navigator.clipboard.writeText(formatSOEPText(lastResult));
      showNotification('Velden niet gevonden; tekst gekopieerd. Tip: klik eerst in de S-regel en probeer opnieuw.');
    }
  });

  document.getElementById('sv-btn-copy').addEventListener('click', function() {
    if (lastResult) {
      navigator.clipboard.writeText(formatSOEPText(lastResult));
      showNotification('Gekopieerd!');
    }
  });

  document.getElementById('sv-btn-new').addEventListener('click', function() {
    lastResult = null;
    chrome.storage.local.remove(['sv_state', 'sv_data', 'sv_error']);
    setWidgetState('idle');
  });

  document.getElementById('sv-btn-retry').addEventListener('click', function() {
    setWidgetState('idle');
  });
}

function setWidgetState(state) {
  var states = ['idle', 'recording', 'processing', 'results', 'error'];
  states.forEach(function(s) {
    var el = document.getElementById('sv-state-' + s);
    if (el) el.classList.toggle('hidden', s !== state);
  });

  // Pulse the FAB red during recording
  var fab = document.getElementById('sv-fab');
  if (fab) fab.classList.toggle('sv-fab-recording', state === 'recording');
}

function updateProcessingStep(text) {
  var el = document.getElementById('sv-processing-step');
  if (el) el.textContent = text;
}

function displayResults(data) {
  var soep = data.soep || {};
  document.getElementById('sv-decisief').textContent = data.decisief || '-';
  document.getElementById('sv-soep-s').textContent = soep.s || '-';
  document.getElementById('sv-soep-o').textContent = soep.o || '-';
  document.getElementById('sv-soep-e').textContent = soep.e || '-';
  document.getElementById('sv-soep-p').textContent = soep.p || '-';

  var icpcEl = document.getElementById('sv-icpc');
  if (soep.icpc_code) {
    icpcEl.classList.remove('hidden');
    document.getElementById('sv-icpc-code').textContent = soep.icpc_code;
    document.getElementById('sv-icpc-title').textContent = soep.icpc_titel || '';
  } else {
    icpcEl.classList.add('hidden');
  }

  // Vocabulary corrections badge
  var corrBadge = document.getElementById('sv-corrections-badge');
  if (data.transcript_corrections && data.transcript_corrections > 0) {
    corrBadge.classList.remove('hidden');
    document.getElementById('sv-corrections-count').textContent = data.transcript_corrections;
  } else {
    corrBadge.classList.add('hidden');
  }
}

/* ── Message handler (for popup-initiated pushes) ── */

chrome.runtime.onMessage.addListener(function(msg, _sender, sendResponse) {
  if (msg.action === 'INJECT_SOEP') {
    lastResult = msg.data;
    var ok = injectSOEP(msg.data);
    displayResults(msg.data);
    setWidgetState('results');
    document.getElementById('sv-panel').classList.remove('hidden');
    sendResponse({ success: ok });
    showNotification(ok ? 'SOEP ingevoegd in Bricks!' : 'Velden niet gevonden. Gebruik kopieer.');
    return false;
  }
});

/* ── Check for pending results on load ── */

async function checkPendingResults() {
  try {
    var stored = await chrome.storage.local.get(['sv_state', 'sv_data']);
    if (stored.sv_state === 'results' && stored.sv_data) {
      lastResult = stored.sv_data;
      displayResults(stored.sv_data);
      setWidgetState('results');
    }
  } catch (e) { /* ignore */ }
}

/* ── Init ── */

async function init() {
  await loadSelectors();
  createWidget();
  await checkPendingResults();
  // Het praktijknummer uit de adresbalk, voor de licentie. Bricks wisselt van
  // pagina zonder te herladen, dus ook bij een nieuwe URL opnieuw kijken.
  if (typeof SVPraktijk !== 'undefined') {
    var laatste = location.href;
    SVPraktijk.onthoud(laatste);
    setInterval(function () {
      if (location.href !== laatste) { laatste = location.href; SVPraktijk.onthoud(laatste); }
    }, 5000);
  }
}

init();

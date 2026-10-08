/**
 * VitaScribe - Dictation side panel
 *
 * Streams microphone audio to the Cloud API (which relays to Deepgram) and
 * shows the transcript while the doctor speaks. Text goes into the Bricks
 * field the doctor last clicked, live or on demand. Optional AI steps:
 * light cleanup, or conversion to a SOEP line.
 */

// Deepgram advises 20-100 ms per chunk for the lowest latency.
var CHUNK_MS = 100;
var STOP_TIMEOUT_MS = 6000;

var els = {
  conn: document.getElementById('conn'),
  target: document.getElementById('target'),
  targetName: document.getElementById('target-name'),
  mic: document.getElementById('btn-mic'),
  timer: document.getElementById('timer'),
  live: document.getElementById('live-insert'),
  text: document.getElementById('text'),
  interim: document.getElementById('interim'),
  insert: document.getElementById('btn-insert'),
  copy: document.getElementById('btn-copy'),
  clean: document.getElementById('btn-clean'),
  soepBtn: document.getElementById('btn-soep'),
  clear: document.getElementById('btn-clear'),
  soep: document.getElementById('soep'),
  soepRows: document.getElementById('soep-rows'),
  icpc: document.getElementById('icpc'),
  soepInsert: document.getElementById('btn-soep-insert'),
  soepCopy: document.getElementById('btn-soep-copy'),
  status: document.getElementById('status'),
};

var session = null;       // { ws, stream, recorder, stopTimer }
var state = 'idle';       // idle | connecting | recording | stopping
var timerInterval = null;
var startedAt = 0;
var insertQueue = Promise.resolve();
var lastSoep = null;
var rules = SVTextRules.emptyRules();   // snelteksten + correcties
var learnMode = null;                   // { kind: 'fix'|'snippet', selection }

// ── Helpers ──

function setStatus(message, isError, action) {
  els.status.textContent = message || '';
  els.status.classList.toggle('error', !!isError);
  if (action) {
    var btn = document.createElement('button');
    btn.className = 'btn small';
    btn.style.marginLeft = '6px';
    btn.textContent = action.label;
    btn.addEventListener('click', action.onClick);
    els.status.appendChild(btn);
  }
}

function setState(next) {
  state = next;
  els.mic.classList.toggle('recording', next === 'recording');
  els.mic.classList.toggle('connecting', next === 'connecting' || next === 'stopping');
  els.conn.className = 'conn' + (next === 'recording' ? ' live' : '');
  els.conn.textContent = {
    idle: 'klaar',
    connecting: 'verbinden…',
    recording: '● luistert',
    stopping: 'afronden…',
  }[next];
  var busy = next !== 'idle';
  // The page shows the same small pill as with Alt+Shift+D, with Stop.
  chrome.runtime.sendMessage({ action: 'SV_PANEL_DICTATION', state: next }).catch(function () {});
  els.clean.disabled = busy;
  els.soepBtn.disabled = busy;
}

function startTimer() {
  startedAt = Date.now();
  els.timer.textContent = '00:00';
  timerInterval = setInterval(function () {
    var s = Math.floor((Date.now() - startedAt) / 1000);
    els.timer.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }, 500);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

async function getConfig() {
  var c = await SVInstellingen.lees(['apiUrl', 'apiKey', 'micDevice', 'llmProvider']);
  return {
    apiUrl: (c.apiUrl || 'http://localhost:8002').replace(/\/$/, ''),
    apiKey: (c.apiKey || '').trim(),
    micDevice: c.micDevice || '',
    llmProvider: c.llmProvider || '',
  };
}

function joinText(existing, addition) {
  if (!existing) return addition.replace(/^\s+/, '');
  if (/\s$/.test(existing) || /^[\s.,;:!?)]/.test(addition)) return existing + addition;
  return existing + ' ' + addition;
}

// ── Target field (clicked in Bricks) ──

function renderTarget(target) {
  if (target && target.label) {
    els.targetName.textContent = target.label;
    els.targetName.classList.remove('muted');
    els.target.classList.add('set');
  } else {
    els.targetName.textContent = 'Klik in Bricks in een veld';
    els.targetName.classList.add('muted');
    els.target.classList.remove('set');
  }
}

chrome.storage.session.get('svTarget').then(function (r) { renderTarget(r.svTarget); });
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'session' && changes.svTarget) renderTarget(changes.svTarget.newValue);
});

async function sendToTarget(text) {
  var r = await chrome.storage.session.get('svTarget');
  var target = r.svTarget;
  if (!target) throw new Error('VitaScribe heeft geen klik in een tekstveld gezien. Klik in Bricks in het veld ' +
    '(bijv. de S-regel) en probeer opnieuw. Lukt dat niet: klik onderaan op "Diagnose".');
  var res;
  try {
    res = await chrome.tabs.sendMessage(target.tabId, { action: 'SV_INSERT_TEXT', text: text }, { frameId: target.frameId });
  } catch (e) {
    throw new Error('Het Bricks-tabblad reageert niet. Ververs de pagina en klik opnieuw in het veld.');
  }
  if (!res || !res.ok) throw new Error((res && res.error) || 'Invoegen mislukt.');
}

// Only the newest interim is sent to the field; stale ones are skipped.
var latestInterim = null;
var interimScheduled = false;

function queueLiveInterim(text) {
  latestInterim = text;
  if (interimScheduled) return;
  interimScheduled = true;
  insertQueue = insertQueue.then(function () {
    interimScheduled = false;
    var t = latestInterim;
    latestInterim = null;
    if (t === null) return;
    return chrome.storage.session.get('svTarget').then(function (r) {
      if (!r.svTarget) return;
      return chrome.tabs.sendMessage(r.svTarget.tabId, { action: 'SV_PROVISIONAL', text: t },
        { frameId: r.svTarget.frameId }).catch(function () {});
    });
  });
}

function queueLiveInsert(text) {
  latestInterim = null;
  insertQueue = insertQueue.then(function () {
    return sendToTarget(text);
  }).catch(function (err) {
    // Text is never lost: it is also in the panel.
    setStatus(err.message + '\nDe tekst staat wel in het paneel.', true);
  });
}

async function insertOrCopy(text) {
  if (!text.trim()) return;
  try {
    await sendToTarget(text);
    setStatus('Ingevoegd.');
    return { ok: true };
  } catch (err) {
    await navigator.clipboard.writeText(text).catch(function () {});
    setStatus(err.message + '\nTekst is gekopieerd; plak met Ctrl+V.', true);
    return { ok: false, error: err.message };
  }
}

// ── Dictation session ──

function wsUrl(apiUrl) {
  return apiUrl.replace(/^http/, 'ws') + '/api/v1/dictation/stream';
}

async function openMicrophone(micDevice) {
  var audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  if (micDevice) audio.deviceId = { exact: micDevice };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: audio });
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      // A side panel cannot show the permission prompt itself; ask once in a tab.
      chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel/mic-permission.html') });
      throw new Error('Geef in het geopende tabblad eenmalig toestemming voor de microfoon en probeer opnieuw.');
    }
    if (err.name === 'OverconstrainedError' || err.name === 'NotFoundError') {
      throw new Error('Gekozen microfoon niet gevonden. Kies een andere in Instellingen.');
    }
    throw err;
  }
}

function handleServerEvent(event) {
  if (event.type === 'ready') {
    flushPending();
  } else if (event.type === 'transcript') {
    if (event.is_final) {
      var finalText = SVTextRules.applyRules(event.text, rules);
      els.interim.textContent = '';
      els.text.value = joinText(els.text.value, finalText); verversAfsluiten();
      els.text.scrollTop = els.text.scrollHeight;
      if (els.live.checked) queueLiveInsert(finalText);
    } else {
      els.interim.textContent = event.text;
      if (els.live.checked) queueLiveInterim(event.text);
    }
  } else if (event.type === 'suggesties') {
    toonDicteerVragen(event);
  } else if (event.type === 'error') {
    setStatus(event.message, true);
  } else if (event.type === 'closed') {
    teardown();
  }
}

// Question suggestions while dictating (clinical support, "Vraagsuggesties"
// in Instellingen): short chips under the microphone. Tapping one marks it as
// asked; it stays crossed out when the next round names it again.
var dicteerGevraagd = {};

// Hovering (or keyboard focus on) a chip shows why the question matters on the
// line under the chips; a click still means "asked".
function koppelWaarom(chip, vraag, regel) {
  if (!vraag.waarom) return;
  chip.setAttribute('aria-description', vraag.waarom);
  var toon = function () { regel.textContent = 'Waarom: ' + vraag.waarom; };
  var weg = function () { if (regel.textContent === 'Waarom: ' + vraag.waarom) regel.textContent = ''; };
  chip.addEventListener('mouseenter', toon);
  chip.addEventListener('focus', toon);
  chip.addEventListener('mouseleave', weg);
  chip.addEventListener('blur', weg);
}

function toonDicteerVragen(s) {
  var blok = document.getElementById('dict-vragen');
  var vragen = s && Array.isArray(s.vragen) ? s.vragen : [];
  blok.classList.toggle('hidden', vragen.length === 0);
  if (!vragen.length) return;
  document.getElementById('dict-klacht').textContent = s.klacht ? ' · ' + s.klacht : '';
  var chips = document.getElementById('dict-chips');
  chips.textContent = '';
  document.getElementById('dict-waarom').textContent = '';
  vragen.forEach(function (v) {
    var sleutel = String(v.tekst || '').toLowerCase();
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'cv-chip' + (v.alarm ? ' alarm' : '') + (dicteerGevraagd[sleutel] ? ' gedaan' : '');
    b.textContent = v.tekst;
    b.setAttribute('aria-label', v.tekst + (v.alarm ? ' (alarmsymptoom)' : '') + ', aantikken als gevraagd');
    b.addEventListener('click', function () {
      dicteerGevraagd[sleutel] = !dicteerGevraagd[sleutel];
      b.classList.toggle('gedaan', dicteerGevraagd[sleutel]);
    });
    koppelWaarom(b, v, document.getElementById('dict-waarom'));
    chips.appendChild(b);
  });
}
function wisDicteerVragen() {
  dicteerGevraagd = {};
  document.getElementById('dict-chips').textContent = '';
  document.getElementById('dict-waarom').textContent = '';
  document.getElementById('dict-vragen').classList.add('hidden');
}

function sendOrBuffer(data) {
  if (!session) return;
  if (session.ready && session.ws.readyState === WebSocket.OPEN) session.ws.send(data);
  else session.pending.push(data);
}

function flushPending() {
  if (!session) return;
  session.ready = true;
  var queued = session.pending;
  session.pending = [];
  queued.forEach(function (d) { session.ws.send(d); });
}

function startRecorder() {
  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
  var recorder = new MediaRecorder(session.stream, { mimeType: mimeType, audioBitsPerSecond: 32000 });
  recorder.ondataavailable = function (e) {
    if (e.data && e.data.size > 0) sendOrBuffer(e.data);
  };
  recorder.onstop = function () {
    // Last chunk has been queued by now; ask the server to flush and close.
    sendOrBuffer(JSON.stringify({ type: 'stop' }));
  };
  session.recorder = recorder;
  recorder.start(CHUNK_MS);
  setState('recording');
  startTimer();
  setStatus('');
}

async function startDictation() {
  if (state !== 'idle') return;
  wisDicteerVragen();
  setState('connecting');
  setStatus('');
  var config = await getConfig();

  // Open the server connection while the microphone starts: both take a few
  // hundred milliseconds, so doing them side by side shortens the start.
  var ws = new WebSocket(wsUrl(config.apiUrl));
  session = { ws: ws, stream: null, recorder: null, stopTimer: null, ready: false, pending: [] };
  var s = session;

  ws.onopen = async function () {
    var praktijk = await SVPraktijk.nummers();
    var keuze = await SVInstellingen.lees(['vraagsuggesties']).catch(function () { return {}; });
    ws.send(JSON.stringify({ type: 'auth', api_key: config.apiKey, praktijk: praktijk, keyterms: SVTextRules.keyterms(rules),
                             vraagsuggesties: keuze.vraagsuggesties === true, modus: await SVModus.lees() }));
  };
  ws.onmessage = function (msg) {
    try { handleServerEvent(JSON.parse(msg.data)); } catch (e) { /* ignore malformed */ }
  };
  ws.onerror = function () {
    setStatus('Kan de server niet bereiken op ' + config.apiUrl + '. Controleer Instellingen.', true);
  };
  ws.onclose = function () { teardown(); };

  var stream;
  try {
    stream = await openMicrophone(config.micDevice);
  } catch (err) {
    teardown();
    setStatus(err.message, true);
    return;
  }
  if (session !== s) {   // connection failed while the microphone was opening
    stream.getTracks().forEach(function (t) { t.stop(); });
    return;
  }
  session.stream = stream;
  // Record from the first moment; audio is buffered until the server is ready.
  startRecorder();
}

function stopDictation() {
  if (!session || state !== 'recording') return;
  setState('stopping');
  stopTimer();
  if (session.recorder && session.recorder.state !== 'inactive') session.recorder.stop();
  if (session.stream) session.stream.getTracks().forEach(function (t) { t.stop(); });
  // Do not wait forever for the last words.
  session.stopTimer = setTimeout(teardown, STOP_TIMEOUT_MS);
}

function teardown() {
  if (!session) return;
  var s = session;
  session = null;
  clearTimeout(s.stopTimer);
  stopTimer();
  if (s.recorder && s.recorder.state !== 'inactive') {
    s.recorder.onstop = null;
    s.recorder.stop();
  }
  if (s.stream) s.stream.getTracks().forEach(function (t) { t.stop(); });
  if (s.ws.readyState === WebSocket.OPEN || s.ws.readyState === WebSocket.CONNECTING) s.ws.close();
  // Leftover interim text is kept so nothing that was said disappears.
  var leftover = SVTextRules.applyRules(els.interim.textContent, rules);
  if (leftover) {
    els.text.value = joinText(els.text.value, leftover); verversAfsluiten();
    els.interim.textContent = '';
    if (els.live.checked) queueLiveInsert(leftover);
  }
  setState('idle');
}

function toggleDictation() {
  if (window.SVConsultUI && window.SVConsultUI.bezig()) {
    setStatus('Er loopt een consultopname. Dicteren kan weer na het consult.', true);
    return;
  }
  if (state === 'idle') startDictation();
  else if (state === 'recording') stopDictation();
}

// ── AI processing ──

async function processText(mode) {
  var text = els.text.value.trim();
  if (!text) { setStatus('Nog geen tekst om te verwerken.', true); return; }
  var config = await getConfig();
  var button = mode === 'clean' ? els.clean : els.soepBtn;
  var label = button.textContent;
  button.disabled = true;
  button.textContent = 'Bezig…';
  setStatus('');

  try {
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var body = { text: text, mode: mode };
    if (config.llmProvider) body.llm_provider = config.llmProvider;
    var resp = await fetch(config.apiUrl + '/api/v1/dictation/process', {
      method: 'POST', headers: headers, body: JSON.stringify(body),
    });
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
    }
    var data = await resp.json();
    if (mode === 'clean') {
      var original = els.text.value;
      els.text.value = data.text;
      setStatus('Opgeschoond.', false, {
        label: 'Herstel origineel',
        onClick: function () { els.text.value = original; setStatus('Origineel hersteld.'); },
      });
    } else {
      renderSoep(data.soep);
      document.getElementById('soep-decisief').classList.add('hidden');
      if (window.SVConsultUI) window.SVConsultUI.losgekoppeld();   // this SOEP is not the consult report
      setStatus('SOEP klaar. Klik in Bricks in een veld en gebruik "invoegen".');
    }
  } catch (err) {
    setStatus(err.message === 'Failed to fetch' ? 'Kan de server niet bereiken.' : err.message, true);
  } finally {
    button.textContent = label;
    button.disabled = state !== 'idle';
  }
}

var SOEP_KEYS = [['s', 'S'], ['o', 'O'], ['e', 'E'], ['p', 'P']];

// A consult about several problems comes back as several SOEP parts; the
// doctor puts each in its own SOEP line in Bricks. One part: as before.
var soepDelen = null;    // [{titel, s, o, e, p, icpc_code, icpc_titel}] or null
var deelIdx = 0;
var soepAlgemeen = {};   // aandachtspunten and markeringen, shared by all parts

// Is there dictation work to close (text, or a SOEP on screen)? For the close button in consult-ui.js.
window.svDictaatActief = function () {
  return !!(els.text.value.trim() || !els.soep.classList.contains('hidden'));
};
function verversAfsluiten() {
  if (window.SVConsultUI) window.SVConsultUI.verversAfsluiten();
}

var soepConcept = [];      // the report as VitaScribe wrote it, per part: to learn from the doctor's edits

function renderSoep(soep) {
  var delen = Array.isArray(soep.problemen) ? soep.problemen : [];
  soepConcept = (delen.length > 1 ? delen : [soep]).map(function (d) {
    return { s: d.s || '', o: d.o || '', e: d.e || '', p: d.p || '', geleerd: false };
  });
  soepAlgemeen = { aandachtspunten: soep.aandachtspunten,
                   markeringen: Array.isArray(soep.markeringen) ? soep.markeringen : [],
                   bronnen: Array.isArray(soep.bronnen) ? soep.bronnen : [] };
  var bar = document.getElementById('soep-delen');
  bar.textContent = '';
  if (delen.length > 1) {
    soepDelen = delen.map(function (d) { return Object.assign({}, d); });
    soepDelen.forEach(function (d, i) {
      var b = document.createElement('button');
      b.className = 'soep-deel';
      b.setAttribute('role', 'tab');
      b.textContent = (i + 1) + ' · ' + (d.titel || d.icpc_titel || 'Deel ' + (i + 1)) + (d.icpc_code ? ' (' + d.icpc_code + ')' : '');
      b.addEventListener('click', function () { toonDeel(i); });
      bar.appendChild(b);
    });
  } else {
    soepDelen = null;
  }
  bar.classList.toggle('hidden', !soepDelen);
  document.getElementById('soep-delen-hint').classList.toggle('hidden', !soepDelen);
  deelIdx = 0;
  renderSoepDeel(soepDelen ? soepDelen[0] : soep);
  markeerDelen();
}

// Edits in the rows belong to the part on screen; keep them when switching.
function bewaarDeel() {
  if (!soepDelen) return;
  var d = soepDelen[deelIdx];
  els.soepRows.querySelectorAll('.soep-text').forEach(function (n) { d[n.dataset.key] = n.innerText.trim(); });
  d.icpc_code = document.getElementById('icpc-code').innerText.trim();
}

function toonDeel(i) {
  if (!soepDelen || !soepDelen[i]) return;
  bewaarDeel();
  deelIdx = i;
  renderSoepDeel(soepDelen[i]);
  markeerDelen();
}

function markeerDelen() {
  var labels = soepDelen ? 'Deel ' + (deelIdx + 1) + ' invoegen' : 'Alles invoegen';
  els.soepInsert.textContent = labels;
  els.soepCopy.textContent = soepDelen ? 'Kopieer deel' : 'Kopieer alles';
  document.querySelectorAll('#soep-delen .soep-deel').forEach(function (b, i) {
    b.classList.toggle('active', i === deelIdx);
    b.setAttribute('aria-selected', i === deelIdx ? 'true' : 'false');
    b.classList.toggle('done', !!(soepDelen && soepDelen[i] && soepDelen[i].__ingevoegd));
  });
}

/** For consult-ui.js: which part is on screen, and its current text. */
function huidigDeel() {
  bewaarDeel();
  var soep = {};
  els.soepRows.querySelectorAll('.soep-text').forEach(function (n) { soep[n.dataset.key] = n.innerText.trim(); });
  soep.icpc_code = document.getElementById('icpc-code').innerText.trim();
  return { index: soepDelen ? deelIdx : 0, soep: soep, delen: soepDelen ? soepDelen.length : 1 };
}

function markeringenVoor(soep, key) {
  return (soep.markeringen || []).filter(function (m) {
    return m.veld === key && m.tekst && (m.probleem || 0) === (soepDelen ? deelIdx : 0);
  });
}

function bronnenVoor(soep, key) {
  return SVBronnen.voor(soep.bronnen, soepDelen ? deelIdx : 0, key);
}

// Text with the marked fragments in <mark> and the words nobody said dotted
// underlined; innerText (what is inserted) stays the same.
function toonMetMarkeringen(node, tekst, markeringen, bronnen) {
  node.textContent = '';
  var pos = 0;
  SVBronnen.bereiken(tekst, markeringen, bronnen || []).forEach(function (r) {
    if (r.start > pos) node.appendChild(document.createTextNode(tekst.slice(pos, r.start)));
    var el = document.createElement(r.soort === 'mark' ? 'mark' : 'span');
    el.className = r.soort === 'mark' ? 'sv-mark' : 'sv-onbekend';
    el.textContent = tekst.slice(r.start, r.end);
    if (r.titel) el.title = r.titel;
    node.appendChild(el);
    pos = r.end;
  });
  if (pos < tekst.length) node.appendChild(document.createTextNode(tekst.slice(pos)));
}

// Caret position in a contentEditable field, in characters of its textContent.
function caretIn(node) {
  var sel = window.getSelection();
  if (!sel || !sel.rangeCount || !node.contains(sel.anchorNode)) return -1;
  var r = sel.getRangeAt(0).cloneRange();
  r.selectNodeContents(node);
  r.setEnd(sel.anchorNode, sel.anchorOffset);
  return r.toString().length;
}

// Under the row: where in the conversation the sentence at the caret was said.
function toonBron(bronDiv, text, items) {
  var it = items.length ? SVBronnen.zinOp(text.textContent, items, caretIn(text)) : null;
  bronDiv.textContent = '';
  bronDiv.classList.toggle('hidden', !it);
  if (!it) return;
  bronDiv.classList.toggle('zwak', it.status !== 'bron');
  var kop = document.createElement('div');
  kop.className = 'bron-kop';
  kop.textContent = it.bronnen && it.bronnen.length
    ? (it.status === 'bron' ? 'Uit het gesprek' : 'Deels uit het gesprek')
    : 'Niet letterlijk teruggevonden in het gesprek; kan een samenvatting zijn. Lees na.';
  bronDiv.appendChild(kop);
  (it.bronnen || []).forEach(function (b) {
    var q = document.createElement('q');
    if (b.spreker) {
      var wie = document.createElement('span');
      wie.className = 'bron-wie';
      wie.textContent = b.spreker + ':';
      q.appendChild(wie);
    }
    q.appendChild(document.createTextNode(b.tekst));
    bronDiv.appendChild(q);
  });
  if (it.ontbreekt && it.ontbreekt.length) {
    var mist = document.createElement('div');
    mist.className = 'bron-mist';
    mist.textContent = 'Nergens gezegd: ' + it.ontbreekt.join(', ');
    bronDiv.appendChild(mist);
  }
}

function renderSoepDeel(part) {
  var soep = Object.assign({}, part, soepAlgemeen);
  lastSoep = soep;
  els.soepRows.textContent = '';
  SOEP_KEYS.forEach(function (pair) {
    var row = document.createElement('div');
    row.className = 'soep-row';

    var letter = document.createElement('span');
    letter.className = 'soep-letter';
    letter.textContent = pair[1];

    var text = document.createElement('div');
    text.className = 'soep-text';
    text.contentEditable = 'true';
    text.dataset.key = pair[0];
    var items = bronnenVoor(soep, pair[0]);
    toonMetMarkeringen(text, soep[pair[0]] || '', markeringenVoor(soep, pair[0]), items);
    var bronDiv = document.createElement('div');
    bronDiv.className = 'soep-bron hidden';
    bronDiv.setAttribute('aria-live', 'polite');
    var bijwerken = function () { toonBron(bronDiv, text, items); };
    text.addEventListener('click', bijwerken);
    text.addEventListener('keyup', bijwerken);

    var btn = document.createElement('button');
    btn.className = 'btn small';
    btn.textContent = 'invoegen';
    btn.addEventListener('click', function () { insertOrCopy(text.innerText.trim()); });

    row.appendChild(letter);
    row.appendChild(text);
    row.appendChild(btn);
    els.soepRows.appendChild(row);
    els.soepRows.appendChild(bronDiv);
  });
  var overzicht = document.getElementById('soep-bronnen');
  var regel = SVBronnen.samenvatting(SVBronnen.voor(soep.bronnen, soepDelen ? deelIdx : 0));
  overzicht.textContent = regel;
  overzicht.classList.toggle('hidden', !regel);
  // The code is shown separately and is editable: the Thuisarts lookup hangs
  // on it, so the doctor must have the last word on which code is there.
  document.getElementById('icpc-code').textContent = soep.icpc_code || '';
  document.getElementById('icpc-titel').textContent = soep.icpc_titel ? ' · ' + soep.icpc_titel : '';
  if (window.SVThuisartsUI) window.SVThuisartsUI.toon();
  if (window.SVBeslistoolsUI) window.SVBeslistoolsUI.toon();
  // Clinically relevant items the doctor did not dictate: shown, never inserted.
  var points = Array.isArray(soep.aandachtspunten) ? soep.aandachtspunten : [];
  var list = document.getElementById('soep-check-list');
  list.textContent = '';
  points.forEach(function (p) {
    var li = document.createElement('li');
    li.textContent = p;
    list.appendChild(li);
  });
  document.getElementById('soep-check').classList.toggle('hidden', points.length === 0);
  // EU mode: what the control pass could not find in the conversation. Marked
  // in yellow and listed; nothing is removed, the doctor decides.
  var mark = (soep.markeringen || []).filter(function (m) { return (m.probleem || 0) === (soepDelen ? deelIdx : 0); });
  var mlist = document.getElementById('soep-mark-list');
  mlist.textContent = '';
  mark.forEach(function (m) {
    var li = document.createElement('li');
    li.textContent = (m.tekst ? m.veld.toUpperCase() + ': "' + m.tekst + '"' + (m.reden ? ' – ' : '') : '') + (m.reden || '');
    mlist.appendChild(li);
  });
  document.getElementById('soep-mark').classList.toggle('hidden', mark.length === 0);
  els.soep.classList.remove('hidden');
  verversAfsluiten();
  if (window.SVMeedenkenUI) window.SVMeedenkenUI.toon(soep);
}

// ── S/O/E/P into separate Bricks fields ──

async function currentTabId() {
  var r = await chrome.storage.session.get('svTarget');
  if (r.svTarget) return r.svTarget.tabId;
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] ? tabs[0].id : null;
}

function soepValues() {
  var values = {};
  els.soepRows.querySelectorAll('.soep-text').forEach(function (node) {
    values[node.dataset.key] = node.innerText.trim();
  });
  if (lastSoep && lastSoep.icpc_code && values.e && values.e.indexOf(lastSoep.icpc_code) === -1) {
    values.e += ' (' + lastSoep.icpc_code + ')';
  }
  return values;
}

var FIELD_NAMES = { s: 'S', o: 'O', e: 'E', p: 'P' };

async function insertSoepPerField() {
  var tabId = await currentTabId();
  var res = tabId === null ? null : await chrome.runtime.sendMessage({
    action: 'SV_FILL_SOEP_REQUEST', tabId: tabId, values: soepValues(),
    icpc: lastSoep && lastSoep.icpc_code || '',
  }).catch(function () { return null; });

  if (res && res.filled && res.filled.length) {
    var where = (res.labels || res.filled.map(function (k) { return { key: k, label: '' }; }))
      .map(function (f) {
        var name = f.key === 'icpc' ? 'ICPC' : FIELD_NAMES[f.key];
        return f.label ? name + ' \u2192 ' + f.label : name;
      }).join(', ');
    if (res.missing.length) {
      setStatus('Ingevuld: ' + where + '. Geen veld gevonden voor: ' +
        res.missing.map(function (k) { return FIELD_NAMES[k]; }).join(', ') + '.', true);
    } else {
      setStatus('SOEP ingevuld: ' + where + '.');
    }
    if (window.SVConsultUI) window.SVConsultUI.ingevoegd(soepDelen ? deelIdx : 0);   // pill and ✓ follow
    if (soepDelen) {
      soepDelen[deelIdx].__ingevoegd = true;
      var volgende = soepDelen.findIndex(function (d) { return !d.__ingevoegd; });
      if (volgende !== -1) {
        toonDeel(volgende);
        setStatus(els.status.textContent + ' Maak in Bricks een nieuwe SOEP-regel, klik in S en kies "Deel ' + (volgende + 1) + ' invoegen".');
      } else {
        markeerDelen();
      }
    }
    return;
  }
  // Nothing clicked yet (or fields not found): everything into one field.
  await insertOrCopy(soepAsText());
  var hint = res && res.mapped
    ? 'De gekoppelde velden staan niet op deze pagina; alles is in het aangeklikte veld gezet.'
    : 'Tip: klik eerst in de S-regel in Bricks; S, O, E en P worden dan elk in hun eigen regel gezet.';
  setStatus(els.status.textContent + '\n' + hint, els.status.classList.contains('error'));
}

async function startFieldMapping() {
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0]) return;
  var res = await chrome.runtime.sendMessage({ action: 'SV_CALIBRATE_START', tabId: tabs[0].id }).catch(function () { return null; });
  if (res && res.ok) {
    setStatus('Klik in Bricks achter elkaar in het S-, O-, E- en P-veld. Het label rechtsonder in Bricks wijst de weg.');
  } else {
    setStatus((res && res.error) || 'Koppelen kon niet starten. Ververs het Bricks-tabblad en probeer opnieuw.', true);
  }
}

function soepAsText() {
  var lines = [];
  els.soepRows.querySelectorAll('.soep-text').forEach(function (node) {
    var value = node.innerText.trim();
    var key = node.dataset.key;
    if (key === 'e' && lastSoep && lastSoep.icpc_code && value.indexOf(lastSoep.icpc_code) === -1) {
      value = (value ? value + ' ' : '') + '(' + lastSoep.icpc_code + ')';
    }
    if (value) lines.push(key.toUpperCase() + ': ' + value);
  });
  return lines.join('\n');
}

// ── Learning: corrections and snippets from selected text ──

function selectedText() {
  return els.text.value.slice(els.text.selectionStart, els.text.selectionEnd).trim();
}

function openLearnForm(kind) {
  var selection = selectedText();
  if (!selection) {
    setStatus('Selecteer eerst tekst in het tekstvak.', true);
    return;
  }
  learnMode = { kind: kind, selection: selection };
  document.getElementById('learn-label').textContent = kind === 'fix'
    ? 'Verkeerd verstaan: \u201c' + selection + '\u201d\nMoet zijn:'
    : 'Tekst: \u201c' + selection + '\u201d\nAls ik zeg (meerdere mag, met komma):';
  var input = document.getElementById('learn-input');
  input.value = '';
  input.placeholder = kind === 'fix' ? 'juiste schrijfwijze' : 'bijv. normaal longen';
  document.getElementById('learn-form').classList.remove('hidden');
  input.focus();
}

function closeLearnForm() {
  learnMode = null;
  document.getElementById('learn-form').classList.add('hidden');
}

async function saveLearnForm() {
  if (!learnMode) return;
  var value = document.getElementById('learn-input').value.trim();
  if (!value) return;
  var latest = await SVTextRules.load();
  if (learnMode.kind === 'fix') {
    var correction = { wrong: learnMode.selection, right: value };
    latest.corrections = latest.corrections.filter(function (c) {
      return c.wrong.toLowerCase() !== correction.wrong.toLowerCase();
    });
    latest.corrections.push(correction);
    els.text.value = SVTextRules.applyCorrections(els.text.value, [correction]);
    setStatus('Onthouden: \u201c' + correction.wrong + '\u201d wordt voortaan \u201c' + correction.right + '\u201d.');
  } else {
    latest.snippets.push({ triggers: value, text: learnMode.selection });
    setStatus('Sneltekst opgeslagen. Zeg \u201c' + SVTextRules.splitTriggers(value)[0] + '\u201d om hem in te voegen.');
  }
  await SVTextRules.save(latest);
  closeLearnForm();
}

SVTextRules.load().then(function (r) { rules = r; });
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'local' && changes[SVTextRules.STORAGE_KEY]) {
    rules = SVTextRules.normalize(changes[SVTextRules.STORAGE_KEY].newValue);
  }
});

// ── Diagnose: report what the clicked field in the page looks like ──

async function runDiagnose() {
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  var tab = tabs[0];
  if (!tab) return;
  var requestId = Math.random().toString(36).slice(2);
  var reports = [];
  function onReport(msg) {
    if (msg.action === 'SV_DIAG_REPORT' && msg.requestId === requestId) reports.push(msg.report);
  }
  chrome.runtime.onMessage.addListener(onReport);
  await chrome.tabs.sendMessage(tab.id, { action: 'SV_DIAG', requestId: requestId }).catch(function () {});
  await new Promise(function (r) { setTimeout(r, 700); });
  chrome.runtime.onMessage.removeListener(onReport);

  var stored = await chrome.storage.session.get('svTarget');
  var lines = [
    'VitaScribe ' + chrome.runtime.getManifest().version + ' — diagnose',
    'Tabblad: ' + (tab.url || '').split('?')[0],
    'Doelveld bekend: ' + (stored.svTarget ? stored.svTarget.label + ' (tab ' + (stored.svTarget.tabId === tab.id ? 'dit' : 'ander') + ')' : 'nee'),
    'Frames met VitaScribe-script: ' + reports.length,
  ];
  reports.forEach(function (r, i) {
    lines.push('');
    lines.push('Frame ' + (i + 1) + (r.top ? ' (hoofdpagina)' : '') + ': ' + r.frame + (r.hasFocus ? ' [focus]' : ''));
    lines.push('  Actief element: ' + (r.active.join(' > ') || '-'));
    lines.push('  Actief is tekstveld: ' + (r.activeIsEditable ? 'ja' : 'nee'));
    lines.push('  Onthouden veld: ' + (r.target || '-'));
    lines.push('  Tekstvelden gevonden: ' + r.editableCount + (r.firstEditables.length ? ' — ' + r.firstEditables.join(' | ') : ''));
  });
  if (!reports.length) {
    lines.push('Geen enkel frame antwoordde: het script draait niet op deze pagina. Ververs de pagina (F5).');
  }
  var report = lines.join('\n');
  // Shown below the text box; the dictated text itself is left alone.
  setStatus(report + '\n', false, {
    label: 'Kopieer verslag',
    onClick: function () {
      navigator.clipboard.writeText(report).then(function () { setStatus('Verslag gekopieerd. Plak het in de chat met Claude.'); });
    },
  });
}

// ── Wiring ──

els.mic.addEventListener('click', toggleDictation);
els.insert.addEventListener('click', function () {
  var start = els.text.selectionStart, end = els.text.selectionEnd;
  var text = start !== end ? els.text.value.slice(start, end) : els.text.value;
  insertOrCopy(text.trim());
});
els.copy.addEventListener('click', function () {
  navigator.clipboard.writeText(els.text.value).then(function () { setStatus('Gekopieerd.'); });
});
els.clean.addEventListener('click', function () { processText('clean'); });
els.soepBtn.addEventListener('click', function () { processText('soep'); });
// Empty the SOEP block: report, parts, markings, checks, thinking along and
// patient instruction. Used when a consult is closed or a new one starts.
function wisSoepBlok() {
  soepConcept = [];
  setTimeout(verversAfsluiten, 0);
  els.soep.classList.add('hidden');
  els.soepRows.textContent = '';
  soepDelen = null;
  deelIdx = 0;
  soepAlgemeen = {};
  lastSoep = null;
  document.getElementById('soep-delen').textContent = '';
  ['soep-delen', 'soep-delen-hint', 'soep-decisief', 'soep-mark', 'soep-check', 'md', 'pi', 'ta', 'bt'].forEach(function (id) {
    var n = document.getElementById(id);
    if (n) n.classList.add('hidden');
  });
  document.getElementById('icpc-code').textContent = '';
  document.getElementById('icpc-titel').textContent = '';
}
window.svWisSoepBlok = wisSoepBlok;

// "Wissen" and "Consult afsluiten": everything about this patient goes, and
// the consult block is ready for the next recording.
async function nieuwConsult() {
  if (window.SVConsultUI && !(await window.SVConsultUI.afsluiten())) return;
  els.text.value = '';
  els.interim.textContent = '';
  wisSoepBlok();
  wisDicteerVragen();
  document.getElementById('mw').classList.add('hidden');
  if (window.SVTolkUI) window.SVTolkUI.wis();   // the interpreter conversation belongs to this consult
  if (window.SVEconsultUI) window.SVEconsultUI.wis();
  if (window.SVTelefoon) window.SVTelefoon.wisFotos();   // photos belong to this patient
  verversAfsluiten();
  setStatus('Klaar voor het volgende consult.');
}
els.clear.addEventListener('click', nieuwConsult);
els.text.addEventListener('input', verversAfsluiten);
document.getElementById('btn-consult-afsluiten').addEventListener('click', nieuwConsult);
// After inserting or copying: what the doctor changed is where VitaScribe learns (leren-ui.js).
function leerVanDeel(deel) {
  var concept = soepConcept[deel.index];
  if (!concept || concept.geleerd || !window.SVLerenUI) return;
  concept.geleerd = true;
  var mark = (soepAlgemeen && soepAlgemeen.markeringen || []).filter(function (m) { return (m.probleem || 0) === deel.index; }).length;
  window.SVLerenUI.naInvoegen(concept, deel.soep, mark);
}
els.soepInsert.addEventListener('click', async function () {
  var deel = huidigDeel();
  await insertSoepPerField();
  leerVanDeel(deel);
});
document.getElementById('btn-map-fields').addEventListener('click', startFieldMapping);
document.getElementById('map-fields-link').addEventListener('click', function (e) {
  e.preventDefault();
  startFieldMapping();
});
els.soepCopy.addEventListener('click', function () {
  leerVanDeel(huidigDeel());
  navigator.clipboard.writeText(soepAsText()).then(function () { setStatus('SOEP gekopieerd.'); });
});
document.getElementById('btn-fix').addEventListener('click', function () { openLearnForm('fix'); });
document.getElementById('btn-snippet').addEventListener('click', function () { openLearnForm('snippet'); });
document.getElementById('learn-save').addEventListener('click', saveLearnForm);
document.getElementById('learn-cancel').addEventListener('click', closeLearnForm);
document.getElementById('learn-input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') saveLearnForm();
  if (e.key === 'Escape') closeLearnForm();
});
document.getElementById('open-rules').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.tabs.create({ url: chrome.runtime.getURL('rules/rules.html') });
});
document.getElementById('run-diag').addEventListener('click', function (e) {
  e.preventDefault();
  runDiagnose();
});
document.getElementById('open-settings').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});
// Beheer: de beheerpagina van de eigen server (spraaktest, SOEP-test, licenties).
document.getElementById('open-beheer').addEventListener('click', async function (e) {
  e.preventDefault();
  var config = await getConfig();
  chrome.tabs.create({ url: config.apiUrl + '/beheer' });
});

chrome.storage.local.get('svLiveInsert').then(function (r) { els.live.checked = !!r.svLiveInsert; });
els.live.addEventListener('change', function () {
  chrome.storage.local.set({ svLiveInsert: els.live.checked });
});

// Dictating without the panel (Alt+Shift+D, "Dicteer in veld"): the text goes
// into the field, and also shows here, so both ways end in the same place.
chrome.runtime.onMessage.addListener(function (msg) {
  if (msg.action !== 'SV_QUICK_EVENT' || state !== 'idle') return false;
  if (msg.type === 'interim') {
    els.interim.textContent = msg.text || '';
  } else if (msg.type === 'final') {
    els.interim.textContent = '';
    els.text.value = joinText(els.text.value, msg.text || ''); verversAfsluiten();
  } else if (msg.type === 'stopped') {
    els.interim.textContent = '';
    if (msg.text) setStatus('Gedicteerd in het veld; de tekst staat ook hierboven.');
  }
  return false;
});

// Keyboard shortcut (Alt+Shift+D) arrives via the service worker. The port
// drops when Chrome stops the idle worker, so reconnect to stay reachable.
function connectPort() {
  var port;
  try { port = chrome.runtime.connect({ name: 'sv-sidepanel' }); } catch (e) { return; }
  port.onMessage.addListener(function (msg) {
    if (msg.action === 'SV_TOGGLE_DICTATION') toggleDictation();
  });
  port.onDisconnect.addListener(function () { setTimeout(connectPort, 250); });
  // Say in which window this panel is open: the page pill there steps aside.
  chrome.windows.getCurrent().then(function (w) {
    try { port.postMessage({ action: 'SV_PANEEL_VENSTER', windowId: w.id }); } catch (e) { /* gone */ }
  }).catch(function () {});
}
connectPort();


setState('idle');

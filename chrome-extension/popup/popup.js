/**
 * VitaScribe - Popup
 *
 * The starting point for a consult. "Consult opnemen" hands the recording to
 * the offscreen document via the service worker and closes this popup: the
 * recording keeps running on every page, with REC on the toolbar icon and a
 * small pill on the page. Reopening the popup shows the running recording,
 * the report or an error, all read from chrome.storage.session (svConsult).
 *
 * Also: quick dictation into the clicked field, side panel, letters and
 * pointing at the S/O/E/P fields.
 */

var STATES = ['idle', 'recording', 'processing', 'results', 'error'];
var consult = {};          // latest svConsult
var clockTimer = null;
var currentWindowId = null;
chrome.windows.getCurrent(function (w) { currentWindowId = w.id; });

// ── Helpers ──

function $(id) { return document.getElementById(id); }

function setState(name) {
  STATES.forEach(function (s) {
    var el = $('state-' + s);
    if (el) el.classList.toggle('hidden', s !== name);
  });
}

function showStatus(text, isError) {
  var bar = $('status-bar');
  bar.classList.remove('hidden');
  $('status-dot').classList.toggle('error', !!isError);
  $('status-text').textContent = text;
}

function hideStatus() {
  $('status-bar').classList.add('hidden');
}

function clock(ms) {
  var s = Math.max(0, Math.floor(ms / 1000));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

function cmd(name, extra) {
  var msg = { action: 'SV_CONSULT_CMD', cmd: name };
  for (var k in extra || {}) msg[k] = extra[k];
  return chrome.runtime.sendMessage(msg).catch(function () { return null; });
}

function activeTabId() {
  return new Promise(function (resolve) {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) { resolve(tabs[0] ? tabs[0].id : undefined); });
  });
}

// ── Consult state ──

function render(c) {
  consult = c || {};
  clearInterval(clockTimer);
  clockTimer = null;
  var st = consult.dismissed ? 'idle' : (consult.state || 'idle');

  if (st === 'recording') {
    var tick = function () { $('timer').textContent = clock(Date.now() - (consult.startedAt || Date.now())); };
    tick();
    clockTimer = setInterval(tick, 500);
    $('rec-label').textContent = (consult.label || 'Opname loopt') + (consult.taal ? ' · ' + consult.taal : '');
    $('btn-nadicteer').classList.toggle('hidden', !!consult.nadictaat);
    // Question suggestions (clinical support, when switched on): same as the side panel.
    var vragen = !consult.nadictaat && consult.suggesties && Array.isArray(consult.suggesties.vragen) ? consult.suggesties.vragen : [];
    var box = $('rec-vragen');
    box.textContent = '';
    vragen.forEach(function (v) {
      var chip = document.createElement('span');
      chip.className = 'rec-vraag' + (v.alarm ? ' alarm' : '');
      chip.textContent = v.tekst;
      if (v.waarom) chip.title = 'Waarom: ' + v.waarom;
      box.appendChild(chip);
    });
    box.classList.toggle('hidden', vragen.length === 0);
    setState('recording');
  } else if (st === 'processing') {
    $('processing-step').textContent = consult.step || 'Verslag wordt gemaakt…';
    setState('processing');
  } else if (st === 'results' && consult.result) {
    displayResults(consult.result);
  } else if (st === 'error') {
    $('error-message').textContent = consult.message || 'De consultopname is mislukt.';
    $('btn-resend').classList.toggle('hidden', !consult.retry);
    $('btn-error-settings').classList.toggle('hidden', consult.code !== 'key');
    setState('error');
  } else {
    $('btn-last').classList.toggle('hidden', !(consult.dismissed && consult.result));
    setState('idle');
  }
}

async function checkKey() {
  var cfg = await SVInstellingen.lees(['apiKey']);
  var missing = !(cfg.apiKey || '').trim();
  $('no-key').classList.toggle('hidden', !missing);
  return !missing;
}

async function startConsult() {
  hideStatus();
  if (!(await checkKey())) {
    showStatus('Vul eerst je VitaScribe-sleutel in bij Instellingen.', true);
    return;
  }
  var btn = $('btn-start');
  btn.disabled = true;
  showStatus('Opname starten…', false);
  var res = await cmd('start', { taal: $('consult-taal').value });
  btn.disabled = false;
  if (res && res.ok) {
    window.close();   // the recording runs on; REC on the icon, pill on the page
    return;
  }
  showStatus((res && res.message) || 'De opname kon niet starten.', true);
  if (res && res.code === 'key') $('no-key').classList.remove('hidden');
}

// ── Display results ──

// Several problems: the popup shows the part that goes in next.
function currentPart(data) {
  var top = data.soep || {};
  var parts = Array.isArray(top.problemen) && top.problemen.length ? top.problemen : [top];
  var index = Math.min(consult.inserted || 0, parts.length - 1);
  return { soep: parts[index], index: index, total: parts.length };
}

function displayResults(data) {
  $('decisief-text').textContent = data.decisief || '-';

  var part = currentPart(data);
  var soep = part.soep || {};
  $('deel-info').classList.toggle('hidden', part.total < 2);
  $('deel-info').textContent = part.total > 1
    ? 'Deel ' + (part.index + 1) + ' van ' + part.total + ': ' + (soep.titel || soep.icpc_titel || '') +
      '. Elk deel hoort in een eigen SOEP-regel.'
    : '';
  $('push-label').textContent = part.total > 1 ? 'Deel ' + (part.index + 1) + ' invoegen in Bricks' : 'Invoegen in Bricks';
  $('soep-s').textContent = soep.s || '-';
  $('soep-o').textContent = soep.o || '-';
  $('soep-e').textContent = soep.e || '-';
  $('soep-p').textContent = soep.p || '-';

  if (soep.icpc_code) {
    $('icpc-badge').classList.remove('hidden');
    $('icpc-code').textContent = soep.icpc_code;
    $('icpc-title').textContent = soep.icpc_titel || '';
  } else {
    $('icpc-badge').classList.add('hidden');
  }

  var corrEl = $('corrections-info');
  if (data.transcript_corrections && data.transcript_corrections > 0) {
    corrEl.textContent = data.transcript_corrections + ' medische woordcorrectie(s) toegepast';
    corrEl.classList.remove('hidden');
  } else {
    corrEl.classList.add('hidden');
  }
  setState('results');
}

// ── Clipboard ──

function formatSOEPText(soep) {
  var parts = [];
  if (soep.s) parts.push('S: ' + soep.s);
  if (soep.o) parts.push('O: ' + soep.o);
  if (soep.e) parts.push('E: ' + soep.e);
  if (soep.p) parts.push('P: ' + soep.p);
  if (soep.icpc_code) parts.push('\nICPC: ' + soep.icpc_code + (soep.icpc_titel ? ' - ' + soep.icpc_titel : ''));
  return parts.join('\n');
}

async function copyToClipboard(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch (e) {
    var ta = document.createElement('textarea'); ta.value = text;
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
  }
  if (btn) { btn.classList.add('copied'); setTimeout(function () { btn.classList.remove('copied'); }, 1500); }
}

function currentResult() {
  return (consult && consult.result) || {};
}

// ── Side panel ──
// sidePanel.open must be called directly in the click, so the window is resolved up front.

function openPanel(view) {
  if (currentWindowId === null) return;
  chrome.sidePanel.open({ windowId: currentWindowId });
  // The panel picks this up on load, or live when it is already open.
  Promise.resolve(view ? chrome.storage.session.set({ svOpenView: view }) : null)
    .finally(function () { window.close(); });
}

// ── Event listeners ──

$('btn-settings').addEventListener('click', function () { chrome.runtime.openOptionsPage(); });
$('btn-no-key').addEventListener('click', function () { chrome.runtime.openOptionsPage(); });
$('btn-error-settings').addEventListener('click', function () { chrome.runtime.openOptionsPage(); });
$('btn-start').addEventListener('click', startConsult);
$('btn-stop').addEventListener('click', function () {
  $('processing-step').textContent = 'Opname wordt afgerond…';
  setState('processing');
  cmd('stop');
});
$('btn-nadicteer').addEventListener('click', function () { cmd('nadictaat'); });
$('btn-resend').addEventListener('click', function () { cmd('retry'); });
$('btn-retry').addEventListener('click', function () { cmd('dismiss'); hideStatus(); setState('idle'); });
$('btn-new-consult').addEventListener('click', function () { cmd('dismiss'); hideStatus(); });
$('btn-last').addEventListener('click', function () { if (consult.result) displayResults(consult.result); });
$('btn-open-panel').addEventListener('click', function () { openPanel('dictate'); });

$('btn-copy-decisief').addEventListener('click', function () {
  copyToClipboard(currentResult().decisief || '', this);
});
$('btn-copy-soep').addEventListener('click', function () {
  copyToClipboard(formatSOEPText(currentPart(currentResult()).soep || {}), this);
});

$('btn-push-bricks').addEventListener('click', async function () {
  var res = await cmd('insert', { tabId: await activeTabId() });
  showStatus((res && res.message) || 'Invoegen lukte niet.', !(res && res.ok));
});

$('btn-dictate').addEventListener('click', function () { openPanel('dictate'); });
$('btn-letters').addEventListener('click', function () { openPanel('letters'); });
$('btn-dossier').addEventListener('click', function () { openPanel('dossier'); });
$('btn-post').addEventListener('click', function () { openPanel('post'); });
$('btn-expand').addEventListener('click', function () { openPanel(null); });

// Dictate straight into the clicked field, without the side panel.
$('btn-quick-dictate').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs[0]) chrome.runtime.sendMessage({ action: 'SV_QUICK_TOGGLE', tabId: tabs[0].id });
    window.close();
  });
});

// Point at the S/O/E/P fields once; the popup closes so the doctor can click in Bricks.
$('link-map-fields').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs[0]) chrome.runtime.sendMessage({ action: 'SV_CALIBRATE_START', tabId: tabs[0].id });
    window.close();
  });
});

// ── Live state ──

chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'session' && changes.svConsult) render(changes.svConsult.newValue);
});

chrome.storage.session.get('svConsult').then(function (r) { render(r.svConsult); });
checkKey();

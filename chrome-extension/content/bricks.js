/**
 * VitaScribe - Bricks HIS Content Script
 *
 * Fills a SOEP result into the Bricks fields when the popup or service worker
 * pushes one (INJECT_SOEP), and remembers the practice number from the URL
 * for the licence check.
 *
 * The floating recording widget that used to live here is gone: a recording
 * inside the page stopped as soon as the doctor opened another page. Consults
 * are now recorded in the offscreen document (offscreen/consult.js) and shown
 * in the side panel.
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

/* ── Message handler (for popup-initiated pushes) ── */

chrome.runtime.onMessage.addListener(function(msg, _sender, sendResponse) {
  if (msg.action === 'INJECT_SOEP') {
    var ok = injectSOEP(msg.data);
    if (!ok) navigator.clipboard.writeText(formatSOEPText(msg.data)).catch(function() {});
    sendResponse({ success: ok });
    showNotification(ok ? 'SOEP ingevoegd in Bricks!' : 'Velden niet gevonden; de tekst staat op het klembord.');
    return false;
  }
});

/* ── Init ── */

async function init() {
  await loadSelectors();
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

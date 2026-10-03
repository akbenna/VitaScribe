/**
 * VitaScribe - Service Worker
 *
 * Handles:
 * 1. PROCESS_AUDIO — receives base64 audio from popup/recorder, calls Cloud API,
 *    stores results in chrome.storage.local. Runs persistently even when popup closes.
 * 2. GET_STATE — popup asks for current state
 * 3. PUSH_TO_BRICKS — push results to Bricks content script
 * 4. RECORDER_AUDIO — legacy handler for recorder page
 */

importScripts('../lib/modus.js', '../lib/praktijk.js', '../lib/instellingen.js');

// ── Bricks-praktijknummer bijhouden (voor de licentie, zie lib/praktijk.js) ──
// Alleen Bricks-adressen leveren een nummer op; van andere tabbladen wordt niets bewaard.
chrome.tabs.onUpdated.addListener(function (_tabId, info, tab) {
  var url = info.url || (info.status === 'complete' && tab && tab.url);
  if (url) SVPraktijk.onthoud(url);
});
chrome.tabs.onActivated.addListener(function (active) {
  chrome.tabs.get(active.tabId, function (tab) {
    if (!chrome.runtime.lastError && tab && tab.url) SVPraktijk.onthoud(tab.url);
  });
});

// ── Icon click: always the side panel ──
// A click on the icon opens the side panel. "Minimaliseren" in the panel only
// closes it; the next click opens it again. Only a practice that chooses the
// compact popup in Instellingen (weergave) gets the popup on the icon.
// setPanelBehavior comes first: if setPopup ran first and the behaviour call
// then failed, the icon would do nothing at all. action.onClicked is the
// fallback for browsers that ignore the behaviour (it only fires without popup).

async function pasWeergaveToe() {
  const { weergave } = await chrome.storage.sync.get('weergave');
  const compact = weergave === 'compact';
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: !compact }).catch(() => {});
  await chrome.action.setPopup({ popup: compact ? 'popup/popup.html' : '' });
  return compact ? 'compact' : 'paneel';
}

// Version 2.8.0 kept a per-session "minimised" state; it no longer exists.
chrome.storage.session.remove('svWeergaveNu').catch(() => {});
pasWeergaveToe().catch(() => {});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'sync' && changes.weergave) pasWeergaveToe().catch(() => {});
});
chrome.action.onClicked.addListener((tab) => {
  // Must run inside the click (user gesture): no await before open().
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
});

// ── API call (runs in service worker — survives popup close) ──

async function callCloudAPI(base64Audio, mimeType) {
  const config = await SVInstellingen.lees(['apiUrl', 'apiKey', 'sttProvider', 'llmProvider']);
  const apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');
  const endpoint = apiUrl + '/api/v1/consult/process';

  // Convert base64 to Blob
  const byteChars = atob(base64Audio);
  const byteArray = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteArray[i] = byteChars.charCodeAt(i);
  }
  const blob = new Blob([byteArray], { type: mimeType });

  const ext = mimeType.includes('webm') ? 'webm' : 'wav';
  const formData = new FormData();
  formData.append('audio', blob, 'consult.' + ext);
  // Recording only starts after the consent box is ticked (popup / widget).
  formData.append('consent', 'true');
  if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
  if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

  const headers = {};
  const apiKey = (config.apiKey || '').trim();
  if (apiKey) headers['X-API-Key'] = apiKey;
  await SVPraktijk.metKop(headers);

  // Update state: processing
  await chrome.storage.local.set({
    sv_state: 'processing',
    sv_step: 'Audio wordt verzonden naar ' + apiUrl + '...',
    sv_error: null,
  });

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: headers,
    body: formData,
  });

  if (!response.ok) {
    const errText = await response.text();
    if (response.status === 403) {
      // Bij een licentie zegt de server waarom (verlopen, uitgezet, andere praktijk).
      const reden = (function () { try { return JSON.parse(errText).detail; } catch (e) { return ''; } })();
      if (reden && typeof reden === 'string' && reden.indexOf('Ongeldige') === -1) throw new Error(reden);
      throw new Error('API-sleutel klopt niet. Controleer of de sleutel in de ' +
        'extensie-instellingen exact overeenkomt met die op de server.');
    }
    if (response.status === 401) {
      throw new Error('API-sleutel ontbreekt. Vul de sleutel in bij de extensie-instellingen.');
    }
    throw new Error('API fout (' + response.status + '): ' + errText.substring(0, 200));
  }

  return await response.json();
}

// ── Message handler ──

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.action) {

    case 'PROCESS_AUDIO':
      // Popup/recorder sends base64 audio — we call the API from here
      // so the request survives popup close.
      (async () => {
        try {
          await chrome.storage.local.set({ sv_state: 'processing', sv_step: 'Audio wordt verwerkt...', sv_error: null });

          const result = await callCloudAPI(msg.audio, msg.mimeType);

          await chrome.storage.local.set({ sv_state: 'results', sv_data: result, sv_error: null });
          sendResponse({ success: true, data: result });
        } catch (err) {
          const config = await chrome.storage.sync.get(['apiUrl']);
          const apiUrl = config.apiUrl || 'http://localhost:8002';
          let errorMsg = err.message || 'Onbekende fout';

          // Verduidelijk "Failed to fetch" met API URL
          if (errorMsg === 'Failed to fetch') {
            errorMsg = 'Kan de API niet bereiken op: ' + apiUrl +
              '\n\nControleer:\n• Is de API URL correct in Instellingen?\n• Is de server actief?\n• Heb je internetverbinding?';
          }

          await chrome.storage.local.set({ sv_state: 'error', sv_error: errorMsg });
          sendResponse({ success: false, error: errorMsg });
        }
      })();
      return true; // async response

    case 'GET_STATE':
      // Popup asks for current state — read from storage
      chrome.storage.local.get(['sv_state', 'sv_data', 'sv_error', 'sv_step'], (stored) => {
        sendResponse({
          state: stored.sv_state || 'idle',
          data: stored.sv_data || null,
          error: stored.sv_error || null,
          step: stored.sv_step || null,
        });
      });
      return true; // async response

    case 'PUSH_TO_BRICKS':
      // Find Bricks tab and send INJECT_SOEP
      (async () => {
        try {
          const stored = await chrome.storage.local.get(['sv_data']);
          if (!stored.sv_data) {
            sendResponse({ error: 'Geen resultaten om te pushen.' });
            return;
          }

          const tabs = await chrome.tabs.query({
            url: [
              'https://*.bfrcloud.com/*',
              'https://*.bfrnet.nl/*',
              'https://*.bricks-huisarts.nl/*',
              'https://*.bfrw.nl/*',
              'https://*.bfrw.cloud/*',
              'https://*.brickshuisarts.nl/*',
              'https://*.bfrw-online.nl/*',
            ],
          });

          if (tabs.length === 0) {
            sendResponse({ error: 'Geen Bricks-tab gevonden.' });
            return;
          }

          // Prefer the fields the doctor pointed at (Velden koppelen).
          const soep = stored.sv_data.soep || {};
          const values = { s: soep.s, o: soep.o, e: soep.e, p: soep.p };
          if (soep.icpc_code && values.e && values.e.indexOf(soep.icpc_code) === -1) {
            values.e += ' (' + soep.icpc_code + ')';
          }
          const filledResult = await fillSoep(tabs[0].id, values, soep.icpc_code || '');
          if (filledResult.filled.length) {
            sendResponse({ success: true, filled: filledResult.filled, missing: filledResult.missing });
            return;
          }

          const response = await chrome.tabs.sendMessage(tabs[0].id, {
            action: 'INJECT_SOEP',
            data: stored.sv_data,
          });
          sendResponse(response || { success: true });
        } catch (err) {
          sendResponse({ error: err.message });
        }
      })();
      return true; // async response

    case 'RECORDER_AUDIO':
      // Legacy: recorder page sends base64 audio
      (async () => {
        try {
          await chrome.storage.local.set({ sv_state: 'processing', sv_error: null });

          const result = await callCloudAPI(msg.audio, msg.mimeType);

          await chrome.storage.local.set({ sv_state: 'results', sv_data: result, sv_error: null });

          // Notify recorder page
          chrome.runtime.sendMessage({ action: 'PROCESSING_COMPLETE', data: result });
        } catch (err) {
          const config = await chrome.storage.sync.get(['apiUrl']);
          const apiUrl = config.apiUrl || 'http://localhost:8002';
          let errorMsg = err.message || 'Onbekende fout';
          if (errorMsg === 'Failed to fetch') {
            errorMsg = 'Kan de API niet bereiken op: ' + apiUrl + '. Controleer de instellingen.';
          }

          await chrome.storage.local.set({ sv_state: 'error', sv_error: errorMsg });
          chrome.runtime.sendMessage({ action: 'PROCESSING_ERROR', error: errorMsg });
        }
      })();
      sendResponse({ received: true });
      return false;
  }
});

// ── Dictation side panel ──

// Remember the field the doctor last clicked, per tab and frame, so the side
// panel can insert text there. Session storage: cleared when Chrome closes.
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.action !== 'SV_TARGET_FOCUS' || !sender.tab) return false;
  // Warm up the recorder document now, so Alt+Shift+D starts instantly.
  ensureOffscreen().catch(() => {});
  chrome.storage.session.set({
    svTarget: {
      tabId: sender.tab.id,
      frameId: sender.frameId || 0,
      label: msg.label || 'veld',
      ts: Date.now(),
    },
  });
  return false;
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { svTarget } = await chrome.storage.session.get('svTarget');
  if (svTarget && svTarget.tabId === tabId) chrome.storage.session.remove('svTarget');
});

// Open side panels announce themselves over a port.
const sidePanelPorts = new Set();
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'sv-sidepanel') return;
  sidePanelPorts.add(port);
  port.onDisconnect.addListener(() => {
    sidePanelPorts.delete(port);
    // Panel closed while dictating: its microphone is gone, so is the pill.
    if (sidePanelPorts.size === 0) panelDictationState('idle');
  });
});

// Alt+Shift+D: with the side panel open it toggles the panel's dictation;
// otherwise it dictates straight into the clicked field (quick mode).
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== 'toggle-dictation') return;
  if (sidePanelPorts.size > 0) {
    sidePanelPorts.forEach((port) => port.postMessage({ action: 'SV_TOGGLE_DICTATION' }));
    return;
  }
  if (tab && tab.id !== undefined) quickToggle(tab.id);
});

// ── Dictating in the side panel shows the same pill on the page ──
// So the page always shows when the microphone is on, whichever way the
// doctor dictates, and Stop on the page stops the panel too.

async function panelDictationTab() {
  const { svPanelDictation } = await chrome.storage.session.get('svPanelDictation');
  return svPanelDictation && svPanelDictation.tabId !== undefined ? svPanelDictation.tabId : null;
}

async function panelDictationState(state) {
  let tabId = await panelDictationTab();
  if (tabId === null && state !== 'idle') {
    const { svTarget } = await chrome.storage.session.get('svTarget');
    if (svTarget) tabId = svTarget.tabId;
    else {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      tabId = tab ? tab.id : null;
    }
  }
  if (tabId === null) return;
  if (state === 'idle') {
    await chrome.storage.session.remove('svPanelDictation');
    pill(tabId, 'idle');
    return;
  }
  await chrome.storage.session.set({ svPanelDictation: { tabId } });
  pill(tabId, state === 'recording' ? 'listening' : state === 'stopping' ? 'stopping' : 'connecting', 'via zijpaneel');
}

// ── Quick dictation: no panel, text goes straight into the clicked field ──

const OFFSCREEN_URL = 'offscreen/dictation.html';
let quickTarget = null;           // { tabId, frameId } for the running session
let quickInsertQueue = Promise.resolve();
let quickInsertFailed = false;
let latestInterim = null;         // newest interim text not yet sent
let interimScheduled = false;

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ['USER_MEDIA', 'CLIPBOARD'],
    justification: 'Microfoon voor dicteren en consultopname, los van tabbladen en zijpaneel; dictaat naar klembord als terugval.',
  });
}

function toOffscreen(action, extra) {
  return chrome.runtime.sendMessage({ target: 'sv-offscreen', action, ...extra }).catch(() => null);
}

function pill(tabId, state, text, button) {
  if (tabId === undefined || tabId === null) return;
  chrome.tabs.sendMessage(tabId, { action: 'SV_PILL', state, text: text || '', button }, { frameId: 0 }).catch(() => {});
}

async function getQuickTarget() {
  if (!quickTarget) quickTarget = (await chrome.storage.session.get('svQuickTarget')).svQuickTarget || null;
  return quickTarget;
}

async function quickToggle(tabId) {
  await ensureOffscreen();
  const status = await toOffscreen('SV_QUICK_STATUS');
  if (status && status.active) {
    toOffscreen('SV_QUICK_STOP');
    return;
  }
  const { svTarget } = await chrome.storage.session.get('svTarget');
  if (!svTarget || svTarget.tabId !== tabId) {
    pill(tabId, 'error', 'Klik eerst in het veld waar de tekst moet komen, en druk dan Alt+Shift+D.');
    return;
  }
  quickTarget = { tabId: svTarget.tabId, frameId: svTarget.frameId };
  quickInsertFailed = false;
  await chrome.storage.session.set({ svQuickTarget: quickTarget });
  const sync = await SVInstellingen.lees(['apiUrl', 'apiKey', 'micDevice']);
  const local = await chrome.storage.local.get('svTextRules');
  toOffscreen('SV_QUICK_START', {
    config: {
      apiUrl: (sync.apiUrl || 'http://localhost:8002').replace(/\/$/, ''),
      apiKey: (sync.apiKey || '').trim(),
      micDevice: sync.micDevice || '',
      modus: await SVModus.lees(),
      versie: chrome.runtime.getManifest().version,
    },
    rules: local.svTextRules || null,
  });
}

// Interim text is shown in the field right away. Only the newest interim is
// sent; older ones still waiting in the queue are skipped.
function quickInterim(target, text) {
  latestInterim = text;
  if (interimScheduled) return;
  interimScheduled = true;
  quickInsertQueue = quickInsertQueue.then(async () => {
    interimScheduled = false;
    const t = latestInterim;
    latestInterim = null;
    if (t === null) return;
    await chrome.tabs.sendMessage(
      target.tabId, { action: 'SV_PROVISIONAL', text: t }, { frameId: target.frameId },
    ).catch(() => null);
  });
}

function quickInsert(target, text) {
  latestInterim = null;   // the final supersedes any pending interim
  quickInsertQueue = quickInsertQueue.then(async () => {
    const res = await chrome.tabs.sendMessage(
      target.tabId, { action: 'SV_INSERT_TEXT', text }, { frameId: target.frameId },
    ).catch(() => null);
    if (!res || !res.ok) {
      quickInsertFailed = true;
      pill(target.tabId, 'listening', 'Invoegen lukt niet; tekst gaat na stoppen naar het klembord.');
    }
  });
}

async function handleQuickEvent(msg) {
  const target = await getQuickTarget();
  const tabId = target ? target.tabId : null;
  switch (msg.type) {
    case 'state':
      pill(tabId, msg.state);
      break;
    case 'interim':
      if (target) quickInterim(target, msg.text);
      break;
    case 'final':
      if (target) quickInsert(target, msg.text);
      break;
    case 'error':
      if (msg.code === 'mic-permission') {
        chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel/mic-permission.html') });
      }
      pill(tabId, 'error', msg.message);
      break;
    case 'stopped':
      await quickInsertQueue;
      if (quickInsertFailed && msg.text) {
        pill(tabId, 'error', 'Het veld was niet bereikbaar. Het dictaat staat op het klembord: plak met Ctrl+V.');
      } else {
        pill(tabId, 'idle');
      }
      quickTarget = null;
      chrome.storage.session.remove('svQuickTarget');
      break;
  }
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.action === 'SV_QUICK_EVENT') {
    handleQuickEvent(msg);
  } else if (msg.action === 'SV_QUICK_TOGGLE') {
    // From the status pill (sender.tab) or the popup (msg.tabId). While the
    // side panel dictates, the pill's Stop stops the panel.
    const tabId = msg.tabId !== undefined ? msg.tabId : sender.tab && sender.tab.id;
    panelDictationTab().then((panelTab) => {
      if (panelTab !== null && sidePanelPorts.size > 0) {
        sidePanelPorts.forEach((port) => port.postMessage({ action: 'SV_TOGGLE_DICTATION' }));
      } else if (tabId !== undefined) {
        quickToggle(tabId);
      }
    });
  } else if (msg.action === 'SV_PANEL_DICTATION') {
    panelDictationState(msg.state);
  }
  return false;
});

// ── Consult recording ──
// The consult is recorded in the offscreen document, so it keeps running when
// the doctor opens another page, switches tabs, closes the popup or never
// opens the side panel at all. Start: popup, side panel or Alt+Shift+C.
//
// Where the doctor sees it:
//  - the toolbar icon: REC while recording, ✓ when the report is ready, ! on
//    an error;
//  - a small pill on the page (content/dictation-target.js) with the time and
//    Stop, and afterwards Invoegen / Bekijk. It follows the doctor to every
//    page in every tab. The pill gets only its state, never patient text;
//  - popup and side panel read the full state from chrome.storage.session
//    (memory only; gone when the browser closes).

const CONSULT_PREFLIGHT_MS = 4000;
let consultWrites = Promise.resolve();

async function consultGet() {
  return (await chrome.storage.session.get('svConsult')).svConsult || {};
}

// What the page pill may know: state and wording, no patient data.
// Several health problems give several SOEP parts; they go in one by one.
// Takes the "soep" object of a result: its parts, or itself as the only part.
function consultParts(soep) {
  const parts = soep && Array.isArray(soep.problemen) ? soep.problemen : [];
  return parts.length ? parts : [soep || {}];
}

function consultPillState(c) {
  if (!c || !c.state || c.dismissed) return { state: 'idle' };
  const soepParts = c.result ? consultParts(c.result.soep) : [];
  return {
    state: c.state, startedAt: c.startedAt || null, label: c.label || '', step: c.step || '',
    parts: soepParts.length, next: Math.min(c.inserted || 0, Math.max(0, soepParts.length - 1)),
    message: c.state === 'error' ? (c.message || '') : '', code: c.code || '', retry: !!c.retry,
    stil: c.state === 'recording' && !!c.stil,
    gehoord: c.state === 'recording' ? (c.gehoord || 0) : 0,
  };
}

async function consultBroadcast(c) {
  const pillState = consultPillState(c);
  const tabs = await chrome.tabs.query({}).catch(() => []);
  for (const tab of tabs) {
    if (!tab.id || !/^https?:/.test(tab.url || '')) continue;
    chrome.tabs.sendMessage(tab.id, { action: 'SV_CONSULT_PILL', pill: pillState }, { frameId: 0 }).catch(() => {});
  }
}

function consultBadge(c) {
  const st = c && !c.dismissed ? c.state : 'idle';
  const look = {
    recording: ['REC', '#dc2626'],
    processing: ['…', '#64748b'],
    results: ['✓', '#059669'],
    error: ['!', '#d97706'],
  }[st];
  chrome.action.setBadgeText({ text: look ? look[0] : '' }).catch(() => {});
  if (look) chrome.action.setBadgeBackgroundColor({ color: look[1] }).catch(() => {});
}

// All state changes go through here, one after the other.
function consultUpdate(patch, replace) {
  consultWrites = consultWrites.then(async () => {
    const next = Object.assign(replace ? {} : await consultGet(), patch);
    await chrome.storage.session.set({ svConsult: next });
    consultBadge(next);
    await consultBroadcast(next);
  }).catch(() => {});
  return consultWrites;
}

async function consultConfig() {
  const cfg = await SVInstellingen.lees(['apiUrl', 'apiKey', 'micDevice', 'llmProvider', 'sttProvider', 'consultLive', 'vraagsuggesties']);
  return {
    apiUrl: (cfg.apiUrl || 'http://localhost:8002').replace(/\/$/, ''),
    apiKey: (cfg.apiKey || '').trim(),
    micDevice: cfg.micDevice || '',
    llmProvider: cfg.llmProvider || '',
    sttProvider: cfg.sttProvider || '',
    consultLive: cfg.consultLive || '',
    // Question suggestions during the consult (Instellingen); the server must allow them too.
    vraagsuggesties: cfg.vraagsuggesties === true,
    praktijk: await SVPraktijk.nummers(),
    // Claude of EU, vastgelegd bij de start: een wissel tijdens het consult geldt voor het volgende.
    modus: await SVModus.lees(),
    versie: chrome.runtime.getManifest().version,
  };
}

// Is the key accepted? Checked before the microphone opens, so a doctor never
// records a whole consult that the server then refuses. Without network the
// recording still starts: it is kept and can be sent again afterwards.
async function consultPreflight(config) {
  const headers = { 'X-API-Key': config.apiKey };
  if (config.praktijk.length) headers['X-Bricks-Praktijk'] = config.praktijk.join(',');
  if (config.modus) headers[SVModus.KOP] = config.modus;
  let resp;
  try {
    resp = await fetch(config.apiUrl + '/api/v1/providers', { headers, signal: AbortSignal.timeout(CONSULT_PREFLIGHT_MS) });
  } catch (e) {
    return { ok: true, offline: true };
  }
  if (resp.status === 401 || resp.status === 403) {
    const detail = await resp.json().then((j) => j && j.detail).catch(() => '');
    const specific = typeof detail === 'string' && detail && !/ongeldige|ontbre/i.test(detail);
    return {
      ok: false, code: 'key',
      message: specific ? detail : 'De server accepteert de VitaScribe-sleutel niet. Controleer hem in Instellingen.',
    };
  }
  return { ok: true };
}

// Language of the conversation, chosen per consult (popup, side panel).
// Anything else, and the keyboard shortcut, means Dutch.
const CONSULT_TALEN = { nl: 'Nederlands', multi: 'Meertalig', en: 'Engels', tr: 'Turks', pl: 'Pools', uk: 'Oekraïens' };

async function consultStart(taal) {
  taal = Object.prototype.hasOwnProperty.call(CONSULT_TALEN, taal) ? taal : 'nl';
  const cur = await consultGet();
  if (cur.state === 'recording' || cur.state === 'processing') {
    return { ok: false, message: 'Er loopt al een consultopname.' };
  }
  // Dictating in the side panel holds the microphone too: one at a time.
  if ((await panelDictationTab()) !== null) {
    return { ok: false, message: 'Stop eerst het dicteren in het zijpaneel; daarna kun je het consult opnemen.' };
  }
  const config = await consultConfig();
  config.taal = taal;
  if (!config.apiKey) {
    return { ok: false, code: 'key', message: 'Er is nog geen VitaScribe-sleutel ingesteld. Vul hem in bij Instellingen.' };
  }
  const check = await consultPreflight(config);
  if (!check.ok) return check;
  await ensureOffscreen();
  const res = await toOffscreen('SV_CONSULT_START', { config });
  if (res && res.code === 'mic-permission') {
    chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel/mic-permission.html') });
  }
  if (res && res.ok) {
    await consultUpdate({ state: 'recording', startedAt: res.startedAt, label: 'Opname loopt', nadictaat: false,
      taal: taal === 'nl' ? '' : CONSULT_TALEN[taal] }, true);
  }
  return res || { ok: false, message: 'De opname kon niet starten. Probeer het opnieuw.' };
}

function handleConsultEvent(msg) {
  switch (msg.type) {
    case 'recording':
      // Keep the chosen language: consultStart already stored it.
      return consultUpdate({ state: 'recording', startedAt: msg.startedAt, label: msg.label, nadictaat: false, stil: false, gehoord: 0 });
    case 'suggesties':
      // Shown in the side panel and popup only; never on the page pill.
      return consultUpdate({ suggesties: { klacht: msg.klacht || '', vragen: msg.vragen || [], at: Date.now() } });
    case 'label':
      if ('gehoord' in msg) return consultUpdate({ label: msg.label, stil: !!msg.stil, gehoord: msg.gehoord || 0 });
      if ('stil' in msg) return consultUpdate({ label: msg.label, stil: !!msg.stil });
      return consultUpdate(msg.nadictaat ? { label: msg.label, nadictaat: true } : { label: msg.label });
    case 'processing':
      return consultUpdate({ state: 'processing', step: msg.step, startedAt: null });
    case 'result':
      return consultUpdate({ state: 'results', result: msg.data, inserted: 0, at: Date.now() }, true);
    case 'error':
      return consultUpdate({ state: 'error', message: msg.message, code: msg.code || '', retry: !!msg.retry, at: Date.now() }, true);
  }
  return null;
}

function consultValues(result, index) {
  const soep = consultParts(result && result.soep)[index || 0] || {};
  const values = { s: soep.s, o: soep.o, e: soep.e, p: soep.p };
  if (soep.icpc_code && values.e && values.e.indexOf(soep.icpc_code) === -1) values.e += ' (' + soep.icpc_code + ')';
  return { values, icpc: soep.icpc_code || '' };
}

// Invoegen: into the fields the doctor mapped, else from the clicked S line on.
async function consultInsert(tabId) {
  const c = await consultGet();
  if (c.state !== 'results' || !c.result) return { ok: false, message: 'Er is geen verslag om in te voegen.' };
  if (tabId === undefined || tabId === null) return { ok: false, message: 'Open het consult in Bricks.' };
  const total = consultParts(c.result.soep).length;
  const index = Math.min(c.inserted || 0, total - 1);
  const { values, icpc } = consultValues(c.result, index);
  const res = await fillSoep(tabId, values, icpc);
  if (!res.filled.length) {
    return { ok: false, message: total > 1
      ? 'Klik eerst in de S-regel voor deel ' + (index + 1) + ' en kies dan opnieuw Invoegen.'
      : 'Klik eerst in de S-regel van het consult en kies dan opnieuw Invoegen.' };
  }
  const missing = res.missing.length ? ' Niet gevonden: ' + res.missing.join(', ').toUpperCase() + '.' : '';
  return consultMarkInserted(index, missing);
}

// A part is in Bricks (from the pill, the popup or the side panel). The next
// part waits for its own SOEP line; after the last one everything clears.
async function consultMarkInserted(index, extra) {
  const c = await consultGet();
  if (c.state !== 'results' || !c.result) return { ok: false };
  const total = consultParts(c.result.soep).length;
  const inserted = Math.max(c.inserted || 0, index + 1);
  if (inserted >= total) {
    await consultUpdate({ inserted, dismissed: true });
    return { ok: true, done: true, message: (total > 1 ? 'Alle ' + total + ' delen ingevoegd.' : 'Verslag ingevoegd.') + (extra || '') };
  }
  await consultUpdate({ inserted });
  return {
    ok: true, done: false, next: inserted,
    message: 'Deel ' + inserted + ' ingevoegd.' + (extra || '') + ' Maak in Bricks een nieuwe SOEP-regel, klik in S en kies Invoegen voor deel ' + (inserted + 1) + '.',
  };
}

// "Bekijk": the side panel when Chrome allows it from here, otherwise the popup.
async function consultShow(sender) {
  const tab = sender && sender.tab;
  try {
    if (tab) { await chrome.sidePanel.open({ tabId: tab.id }); return { ok: true, where: 'panel' }; }
  } catch (e) { /* no user gesture reached us */ }
  try { await chrome.action.openPopup(); return { ok: true, where: 'popup' }; } catch (e) { /* not supported */ }
  return { ok: false, message: 'Klik op het VitaScribe-icoon rechtsboven om het verslag te zien.' };
}

async function consultCommand(cmd, sender, msg) {
  if (cmd === 'start') return consultStart(msg.taal);
  if (cmd === 'insert') return consultInsert(msg.tabId !== undefined ? msg.tabId : sender.tab && sender.tab.id);
  if (cmd === 'show') return consultShow(sender);
  if (cmd === 'dismiss') {
    const c = await consultGet();
    // Never dismiss a running recording from a pill's ×.
    if (c.state === 'recording' || c.state === 'processing') return { ok: false };
    await consultUpdate({ dismissed: true });
    return { ok: true };
  }
  if (cmd === 'pill') return consultPillState(await consultGet());
  if (cmd === 'edit') {
    // The doctor changed the report in the side panel: "Invoegen" on the pill
    // and in the popup must use that version, not the original.
    const c = await consultGet();
    if (c.state !== 'results' || !c.result || !msg.soep) return { ok: false };
    const index = msg.deel || 0;
    const soep = Object.assign({}, c.result.soep);
    const parts = consultParts(soep).map((d) => Object.assign({}, d));
    if (!parts[index]) return { ok: false };
    Object.assign(parts[index], msg.soep);
    if (Array.isArray(soep.problemen) && soep.problemen.length) soep.problemen = parts;
    if (index === 0) ['s', 'o', 'e', 'p', 'icpc_code'].forEach((k) => { if (k in msg.soep) soep[k] = msg.soep[k]; });
    await consultUpdate({ result: Object.assign({}, c.result, { soep }) });
    return { ok: true };
  }
  if (cmd === 'inserted') return consultMarkInserted(msg.deel || 0);
  if (cmd === 'options') { chrome.runtime.openOptionsPage(); return { ok: true }; }
  const action = { stop: 'SV_CONSULT_STOP', nadictaat: 'SV_CONSULT_NADICTAAT', status: 'SV_CONSULT_STATUS', retry: 'SV_CONSULT_RETRY' }[cmd];
  if (!action) return { ok: false };
  if (!(await chrome.offscreen.hasDocument())) {
    if (cmd === 'status') return { active: false };
    // Browser restarted or the extension was updated mid-consult.
    await consultUpdate({ state: 'error', message: 'De opname was al gestopt (browser of extensie opnieuw gestart).', at: Date.now() }, true);
    return { ok: false };
  }
  if (cmd === 'stop') await consultUpdate({ state: 'processing', step: 'Opname wordt afgerond…', startedAt: null });
  return (await toOffscreen(action)) || { ok: false };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'SV_CONSULT_EVENT') {
    handleConsultEvent(msg);
    return false;
  }
  if (msg.action !== 'SV_CONSULT_CMD') return false;
  consultCommand(msg.cmd, sender, msg).then(sendResponse, (e) => sendResponse({ ok: false, message: String(e && e.message || e) }));
  return true;
});

// Alt+Shift+C: start or stop the consult from any page. Starting with the
// shortcut confirms the patient's consent, as the start button does.
chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'toggle-consult') return;
  const c = await consultGet();
  if (c.state === 'recording') { consultCommand('stop', {}, {}); return; }
  if (c.state === 'processing') return;
  const res = await consultStart();
  if (!res.ok) {
    if (res.code === 'key') chrome.runtime.openOptionsPage();
    await consultUpdate({ state: 'error', message: res.message || 'De opname kon niet starten.', code: res.code || '', at: Date.now() }, true);
  }
});

// After an update the offscreen recorder is gone: never show a "running"
// recording that no longer exists.
chrome.runtime.onInstalled.addListener(async () => {
  const c = await consultGet();
  if (c.state === 'recording' || c.state === 'processing') {
    await consultUpdate({ state: 'error', message: 'De opname is gestopt door een update van VitaScribe.', at: Date.now() }, true);
  } else {
    consultBadge(c);
  }
});

// ── S/O/E/P field mapping ──
// The doctor points at the S, O, E and P fields once per HIS (host); after
// that a SOEP result is filled field by field. Stored per host in
// chrome.storage.local (field locations only, no patient data).

const SOEP_STEPS = [
  { key: 's', label: 'Klik in het S-veld (Subjectief)' },
  { key: 'o', label: 'Klik in het O-veld (Objectief)' },
  { key: 'e', label: 'Klik in het E-veld (Evaluatie)' },
  { key: 'p', label: 'Klik in het P-veld (Plan)' },
];
let calib = null;   // { tabId, host, step, result }

// The service worker is stopped after ~30 s idle; keep the calibration in
// session storage so "Overslaan" and field clicks still work afterwards.
async function loadCalib() {
  if (!calib) calib = (await chrome.storage.session.get('svCalib')).svCalib || null;
  return calib;
}
function saveCalib() {
  return calib ? chrome.storage.session.set({ svCalib: calib }) : chrome.storage.session.remove('svCalib');
}

async function hostOfTab(tabId) {
  try { return new URL((await chrome.tabs.get(tabId)).url).host; } catch (e) { return null; }
}

async function getFieldMap(host) {
  const { svSoepFields } = await chrome.storage.local.get('svSoepFields');
  return (svSoepFields && host && svSoepFields[host]) || null;
}

function broadcastCalibrate(tabId, active) {
  chrome.tabs.sendMessage(tabId, { action: 'SV_CALIBRATE', active }).catch(() => {});
}

function calibPrompt() {
  const step = SOEP_STEPS[calib.step];
  pill(calib.tabId, 'calibrate', step.label, { label: 'Overslaan', action: 'SV_CALIBRATE_SKIP', close: true });
}

// Stop pointing at fields; fields picked so far are kept.
async function calibCancel(tabId) {
  await loadCalib();
  const target = calib ? calib.tabId : tabId;
  if (calib && Object.keys(calib.result).length) {
    const { svSoepFields } = await chrome.storage.local.get('svSoepFields');
    const all = svSoepFields || {};
    all[calib.host] = Object.assign({}, all[calib.host] || {}, calib.result);
    await chrome.storage.local.set({ svSoepFields: all });
  }
  calib = null;
  await saveCalib();
  if (target !== undefined && target !== null) {
    broadcastCalibrate(target, false);
    pill(target, 'idle');
  }
}

async function calibAdvance() {
  calib.step += 1;
  if (calib.step < SOEP_STEPS.length) { await saveCalib(); calibPrompt(); return; }
  const { tabId, host, result } = calib;
  calib = null;
  await saveCalib();
  broadcastCalibrate(tabId, false);
  const { svSoepFields } = await chrome.storage.local.get('svSoepFields');
  const all = svSoepFields || {};
  all[host] = result;
  await chrome.storage.local.set({ svSoepFields: all });
  const n = Object.keys(result).length;
  pill(tabId, 'info', n ? `${n} velden gekoppeld. "Alles invoegen" vult ze voortaan per veld.` : 'Geen velden gekoppeld.');
}

async function startCalibration(tabId) {
  const host = await hostOfTab(tabId);
  if (!host) return { ok: false, error: 'Open eerst Bricks in dit tabblad.' };
  calib = { tabId, host, step: 0, result: {} };
  await saveCalib();
  broadcastCalibrate(tabId, true);
  calibPrompt();
  return { ok: true };
}

// Fill S/O/E/P into the mapped fields of a tab. Every frame fills what it can
// find and reports back; results are collected for a short moment.
const fillWaiters = new Map();

async function fillSoep(tabId, values, icpc) {
  const host = await hostOfTab(tabId);
  const mapping = await getFieldMap(host);
  const wanted = Object.keys(values).filter((k) => values[k]);
  if (!mapping) {
    // No mapped fields: S goes into the clicked field, O/E/P into the next ones.
    const { svTarget } = await chrome.storage.session.get('svTarget');
    if (!svTarget || svTarget.tabId !== tabId) return { mapped: false, filled: [], missing: wanted };
    const res = await chrome.tabs.sendMessage(
      tabId, { action: 'SV_FILL_SEQUENTIAL', values, icpc: icpc || '' }, { frameId: svTarget.frameId },
    ).catch(() => null);
    if (!res || !res.ok) return { mapped: false, filled: [], missing: wanted, error: res && res.error };
    return {
      mapped: false,
      sequential: true,
      filled: res.filled.map((f) => f.key),
      labels: res.filled,
      missing: res.missing,
    };
  }
  const requestId = Math.random().toString(36).slice(2);
  const filled = new Set();
  fillWaiters.set(requestId, filled);
  await chrome.tabs.sendMessage(tabId, { action: 'SV_FILL_SOEP', requestId, mapping, values }).catch(() => {});
  await new Promise((r) => setTimeout(r, 400));
  fillWaiters.delete(requestId);
  return { mapped: true, filled: [...filled], missing: wanted.filter((k) => !filled.has(k)) };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.action) {
    case 'SV_CALIBRATE_START':
      startCalibration(msg.tabId).then(sendResponse);
      return true;
    case 'SV_CALIBRATE_PICK':
      loadCalib().then((c) => {
        if (c && sender.tab && sender.tab.id === c.tabId) {
          c.result[SOEP_STEPS[c.step].key] = msg.desc;
          calibAdvance();
        }
      });
      return false;
    case 'SV_CALIBRATE_SKIP':
      loadCalib().then((c) => {
        if (c) calibAdvance();
        else calibCancel(sender.tab && sender.tab.id);   // stale pill: clear it
      });
      return false;
    case 'SV_CALIBRATE_CANCEL':
      calibCancel(sender.tab && sender.tab.id);
      return false;
    case 'SV_FILL_REPORT': {
      const set = fillWaiters.get(msg.requestId);
      if (set) (msg.filled || []).forEach((k) => set.add(k));
      return false;
    }
    case 'SV_FILL_SOEP_REQUEST': {
      const tabId = msg.tabId !== undefined ? msg.tabId : sender.tab && sender.tab.id;
      fillSoep(tabId, msg.values, msg.icpc).then(sendResponse);
      return true;
    }
    case 'SV_FIELD_MAP_STATUS':
      hostOfTab(msg.tabId).then(getFieldMap).then((m) => sendResponse({ mapped: !!m, keys: m ? Object.keys(m) : [] }));
      return true;
  }
  return false;
});


// ── After install/update: bring the field script back into open tabs ──
// Scripts already running in open pages are cut off by an update; re-inject
// so the doctor doesn't have to refresh Bricks (only where we have access).
chrome.runtime.onInstalled.addListener(async (details) => {
  // A new doctor starts with the manual; an update does not interrupt anyone.
  if (details && details.reason === 'install') {
    chrome.tabs.create({ url: chrome.runtime.getURL('help/handleiding.html') }).catch(() => {});
  }
  // The server key used to live in chrome.storage.sync; move it to this device.
  await SVInstellingen.migreer().catch(() => { /* settings stay readable as before */ });
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (!tab.id || !/^https?:/.test(tab.url || '')) continue;
    chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ['content/dictation-target.js'],
    }).catch(() => { /* no access to this tab: fine */ });
  }
});

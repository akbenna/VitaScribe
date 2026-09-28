/**
 * VitaScribe - Dictation without the side panel (offscreen document)
 *
 * Captures the microphone and streams it to the Cloud API, like the side
 * panel does, but invisibly. Transcript events go to the service worker,
 * which inserts them into the clicked field and updates the status pill.
 * Only chrome.runtime is available here (no chrome.storage).
 */

// Deepgram advises 20-100 ms per chunk for the lowest latency.
var CHUNK_MS = 100;
var STOP_TIMEOUT_MS = 6000;

var session = null;  // { ws, stream, recorder, stopTimer, text }

function emit(type, extra) {
  var msg = { action: 'SV_QUICK_EVENT', type: type };
  for (var k in extra || {}) msg[k] = extra[k];
  chrome.runtime.sendMessage(msg).catch(function () {});
}

function copyToClipboard(text) {
  // Offscreen documents have no focus, so navigator.clipboard is unavailable.
  var clip = document.getElementById('clip');
  clip.value = text;
  clip.select();
  document.execCommand('copy');
  clip.value = '';
}

// Offscreen documents can only use chrome.runtime, so the service worker
// passes settings and text rules along with the start message.
async function start(config, rules) {
  if (session) return;
  if (typeof consult !== 'undefined' && consult) {
    emit('error', { message: 'Er loopt een consultopname. Dicteren kan weer na het consult.' });
    return;
  }
  rules = SVTextRules.normalize(rules);

  // Open the server connection while the microphone starts: both take a few
  // hundred milliseconds, so doing them side by side shortens the start.
  var ws = new WebSocket(config.apiUrl.replace(/^http/, 'ws') + '/api/v1/dictation/stream');
  session = { ws: ws, stream: null, recorder: null, stopTimer: null, text: '', rules: rules,
              ready: false, pending: [] };
  var s = session;

  ws.onopen = async function () {
    var praktijk = await SVPraktijk.nummers();
    ws.send(JSON.stringify({ type: 'auth', api_key: config.apiKey, praktijk: praktijk, keyterms: SVTextRules.keyterms(rules) }));
  };
  ws.onmessage = function (msg) {
    var event;
    try { event = JSON.parse(msg.data); } catch (e) { return; }
    if (event.type === 'ready') flushPending();
    else if (event.type === 'transcript') handleTranscript(event);
    else if (event.type === 'error') emit('error', { message: event.message });
    else if (event.type === 'closed') teardown();
  };
  ws.onerror = function () {
    emit('error', { message: 'Kan de server niet bereiken op ' + config.apiUrl + '.' });
  };
  ws.onclose = function () { teardown(); };

  var audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  if (config.micDevice) audio.deviceId = { exact: config.micDevice };
  var stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: audio });
  } catch (err) {
    emit('error', {
      code: err.name === 'NotAllowedError' ? 'mic-permission' : 'mic',
      message: err.name === 'NotAllowedError'
        ? 'Geef eenmalig toestemming voor de microfoon (tabblad geopend) en probeer opnieuw.'
        : 'Microfoon niet beschikbaar: ' + err.message,
    });
    s.silent = true;   // keep the microphone error visible in the pill
    teardown();
    return;
  }
  if (session !== s) {   // stopped or failed while the microphone was opening
    stream.getTracks().forEach(function (t) { t.stop(); });
    return;
  }
  session.stream = stream;
  // Record from the first moment; audio is buffered until the server is
  // connected, so the first words are never lost or delayed.
  startRecorder();
}

function handleTranscript(event) {
  if (!session) return;
  if (event.is_final) {
    var text = SVTextRules.applyRules(event.text, session.rules);
    session.text += (session.text && !/\s$/.test(session.text) && !/^[\s.,;:!?)]/.test(text) ? ' ' : '') + text;
    emit('final', { text: text });
  } else {
    emit('interim', { text: event.text });
  }
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
    sendOrBuffer(JSON.stringify({ type: 'stop' }));
  };
  session.recorder = recorder;
  recorder.start(CHUNK_MS);
  emit('state', { state: 'listening' });
}

function stop() {
  if (!session) return;
  emit('state', { state: 'stopping' });
  if (session.recorder && session.recorder.state !== 'inactive') session.recorder.stop();
  else sendOrBuffer(JSON.stringify({ type: 'stop' }));
  if (session.stream) session.stream.getTracks().forEach(function (t) { t.stop(); });
  session.stopTimer = setTimeout(teardown, STOP_TIMEOUT_MS);
}

function teardown() {
  if (!session) return;
  var s = session;
  session = null;
  clearTimeout(s.stopTimer);
  if (s.recorder && s.recorder.state !== 'inactive') { s.recorder.onstop = null; s.recorder.stop(); }
  if (s.stream) s.stream.getTracks().forEach(function (t) { t.stop(); });
  if (s.ws.readyState === WebSocket.OPEN || s.ws.readyState === WebSocket.CONNECTING) s.ws.close();
  // Whole dictation also lands on the clipboard: a safety net when the field
  // could not be reached (e.g. Bricks Classic outside Chrome).
  if (s.text) copyToClipboard(s.text);
  if (!s.silent) emit('stopped', { text: s.text });
}

chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
  if (msg.target !== 'sv-offscreen') return false;
  if (msg.action === 'SV_QUICK_STATUS') {
    sendResponse({ active: !!session });
  } else if (msg.action === 'SV_QUICK_START') {
    start(msg.config, msg.rules);
    sendResponse({ ok: true });
  } else if (msg.action === 'SV_QUICK_STOP') {
    stop();
    sendResponse({ ok: true });
  }
  return false;
});

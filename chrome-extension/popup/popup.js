/**
 * VitaScribe - Popup Controller
 *
 * "Start opname" hands the consult to the offscreen recorder and opens the
 * side panel (see the btn-start handler). The popup also shows a result the
 * service worker left in chrome.storage.local, and starts quick dictation.
 */

var STATES = ['idle', 'recording', 'processing', 'results', 'error'];
var mediaRecorder = null;
var audioChunks = [];
var audioStream = null;
var timerInterval = null;
var recStartTime = null;

// ── State management ──

function setState(name) {
  STATES.forEach(function(s) {
    var el = document.getElementById('state-' + s);
    if (el) el.classList.toggle('hidden', s !== name);
  });
}

function showStatus(text, isError) {
  var bar = document.getElementById('status-bar');
  bar.classList.remove('hidden');
  document.getElementById('status-dot').classList.toggle('error', !!isError);
  document.getElementById('status-text').textContent = text;
}

function hideStatus() {
  document.getElementById('status-bar').classList.add('hidden');
}

// ── Timer ──

function updateTimer() {
  if (!recStartTime) return;
  var s = Math.floor((Date.now() - recStartTime) / 1000);
  document.getElementById('timer').textContent =
    String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

// ── Recording ──

async function checkMicPermission() {
  try {
    var result = await navigator.permissions.query({ name: 'microphone' });
    return result.state; // 'granted', 'denied', 'prompt'
  } catch (e) {
    return 'unknown';
  }
}

async function startRecording() {
  // KNMG (2026): consultopname alleen met toestemming van de patiënt.
  var consent = document.getElementById('consent-recording');
  if (consent && !consent.checked) {
    showStatus('Vink eerst aan dat de patiënt toestemming geeft voor de opname.', true);
    consent.focus();
    return;
  }
  // Check of microfoontoestemming al is verleend.
  // In een popup context kan de toestemmingsdialoog de popup sluiten,
  // waardoor "Permission dismissed" optreedt. Stuur de gebruiker naar
  // de instellingenpagina als toestemming nog niet is verleend.
  var permState = await checkMicPermission();

  if (permState === 'prompt' || permState === 'denied') {
    setState('error');
    document.getElementById('error-message').innerHTML =
      '<strong>Microfoontoegang vereist</strong><br>' +
      'Ga naar <a href="#" id="open-settings-link" style="color:#059669;text-decoration:underline;">Instellingen</a> ' +
      'en klik op "Test microfoon" om toestemming te verlenen.<br>' +
      '<span style="font-size:11px;color:#6b7280;">In een cloud-omgeving moet de toestemming vanuit een vast tabblad worden verleend, niet vanuit de popup.</span>';

    // Wacht even tot DOM is bijgewerkt
    setTimeout(function() {
      var link = document.getElementById('open-settings-link');
      if (link) {
        link.addEventListener('click', function(e) {
          e.preventDefault();
          chrome.runtime.openOptionsPage();
        });
      }
    }, 50);
    return;
  }

  try {
    var config = await chrome.storage.sync.get(['micDevice']);
    var audioConstraints = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (config.micDevice) audioConstraints.deviceId = { exact: config.micDevice };

    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints
    });
  } catch (err) {
    setState('error');

    if (err.message && err.message.toLowerCase().includes('dismiss')) {
      document.getElementById('error-message').innerHTML =
        '<strong>Microfoontoegang geweigerd (dismissed)</strong><br>' +
        'Dit gebeurt vaak in cloud-omgevingen. Ga naar ' +
        '<a href="#" id="open-settings-link2" style="color:#059669;text-decoration:underline;">Instellingen</a> ' +
        'en klik op "Test microfoon" om toestemming te verlenen.';
      setTimeout(function() {
        var link = document.getElementById('open-settings-link2');
        if (link) {
          link.addEventListener('click', function(e) {
            e.preventDefault();
            chrome.runtime.openOptionsPage();
          });
        }
      }, 50);
    } else {
      document.getElementById('error-message').textContent = 'Microfoon niet beschikbaar: ' + err.message;
    }
    return;
  }

  audioChunks = [];
  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus' : 'audio/webm';

  mediaRecorder = new MediaRecorder(audioStream, { mimeType: mimeType, audioBitsPerSecond: 128000 });

  mediaRecorder.ondataavailable = function(e) {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = function() {
    var mime = mediaRecorder ? mediaRecorder.mimeType : 'audio/webm';
    var blob = new Blob(audioChunks, { type: mime });

    if (audioStream) { audioStream.getTracks().forEach(function(t) { t.stop(); }); audioStream = null; }

    if (blob.size < 1000) {
      setState('idle');
      showStatus('Opname te kort. Probeer langer.', true);
      return;
    }

    setState('processing');
    showStatus('Verwerken...', false);
    updateProgress(10, 'Audio wordt verzonden...');

    // Converteer naar base64 en stuur naar service worker.
    // De service worker maakt de API call — die overleeft het sluiten van de popup.
    var reader = new FileReader();
    reader.onloadend = function() {
      var base64 = reader.result.split(',')[1];
      chrome.runtime.sendMessage({
        action: 'PROCESS_AUDIO',
        audio: base64,
        mimeType: mime,
        size: blob.size,
      }, function(response) {
        if (chrome.runtime.lastError) {
          // Service worker niet bereikbaar — fallback naar directe API call
          sendAudioToAPI(blob, mime);
          return;
        }
        if (response && response.success && response.data) {
          displayResults(response.data);
        } else if (response && response.error) {
          setState('error');
          document.getElementById('error-message').textContent = response.error;
          showStatus('Fout', true);
        }
        // Als popup al dicht is: resultaten staan in chrome.storage.local
        // en worden opgepikt bij heropenen (init functie + storage listener).
      });
    };
    reader.readAsDataURL(blob);
  };

  mediaRecorder.start();
  recStartTime = Date.now();
  timerInterval = setInterval(updateTimer, 500);
  setState('recording');
  showStatus('Opname actief...', false);
}

function stopRecording() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

// ── API call ──

async function sendAudioToAPI(blob, mimeType) {
  try {
    var config = await SVInstellingen.lees(['apiUrl', 'apiKey', 'sttProvider', 'llmProvider']);
    var apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');

    var formData = new FormData();
    var ext = mimeType.includes('webm') ? 'webm' : 'wav';
    formData.append('audio', blob, 'consult.' + ext);
    formData.append('consent', 'true');
    if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
    if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

    var headers = {};
    var apiKey = (config.apiKey || '').trim();
    if (apiKey) headers['X-API-Key'] = apiKey;
    await SVPraktijk.metKop(headers);

    updateProgress(30, 'Audio wordt getranscribeerd...');

    var response = await fetch(apiUrl + '/api/v1/consult/process', {
      method: 'POST',
      headers: headers,
      body: formData,
    });

    if (!response.ok) {
      var errText = await response.text();
      if (response.status === 403) {
        // Bij een licentie zegt de server waarom (verlopen, uitgezet, andere praktijk).
        var reden = (function () { try { return JSON.parse(errText).detail; } catch (e) { return ''; } })();
        if (reden && typeof reden === 'string' && reden.indexOf('Ongeldige') === -1) throw new Error(reden);
        throw new Error('API-sleutel klopt niet. Controleer of de sleutel in de ' +
          'extensie-instellingen exact overeenkomt met die op de server.');
      }
      if (response.status === 401) {
        throw new Error('API-sleutel ontbreekt. Vul de sleutel in bij de extensie-instellingen.');
      }
      throw new Error('API fout (' + response.status + '): ' + errText.substring(0, 200));
    }

    var result = await response.json();

    // Persist for widget pickup on Bricks
    chrome.storage.local.set({ sv_state: 'results', sv_data: result });

    displayResults(result);

  } catch (err) {
    setState('error');
    var errorMsg = err.message || 'Onbekende fout';

    if (errorMsg === 'Failed to fetch') {
      errorMsg = 'Kan de API niet bereiken op: ' + apiUrl +
        '\n\nControleer:\n• Is de API URL correct? (Instellingen → API URL)\n• Is de server actief?\n• Heb je internetverbinding?';
    }

    document.getElementById('error-message').textContent = errorMsg;
    showStatus('Fout', true);
  }
}

// ── Progress ──

function updateProgress(percent, step) {
  var fill = document.getElementById('progress-fill');
  if (fill) fill.style.width = percent + '%';
  var stepEl = document.getElementById('processing-step');
  if (stepEl && step) stepEl.textContent = step;
}

// ── Display results ──

function displayResults(data) {
  document.getElementById('decisief-text').textContent = data.decisief || '-';

  var soep = data.soep || {};
  document.getElementById('soep-s').textContent = soep.s || '-';
  document.getElementById('soep-o').textContent = soep.o || '-';
  document.getElementById('soep-e').textContent = soep.e || '-';
  document.getElementById('soep-p').textContent = soep.p || '-';

  if (soep.icpc_code) {
    document.getElementById('icpc-badge').classList.remove('hidden');
    document.getElementById('icpc-code').textContent = soep.icpc_code;
    document.getElementById('icpc-title').textContent = soep.icpc_titel || '';
  } else {
    document.getElementById('icpc-badge').classList.add('hidden');
  }

  // Show vocabulary corrections count if any
  var corrEl = document.getElementById('corrections-info');
  if (corrEl) {
    if (data.transcript_corrections && data.transcript_corrections > 0) {
      corrEl.textContent = data.transcript_corrections + ' medische woordcorrectie(s) toegepast';
      corrEl.classList.remove('hidden');
    } else {
      corrEl.classList.add('hidden');
    }
  }

  setState('results');
  showStatus('Verwerking voltooid', false);
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
  if (btn) { btn.classList.add('copied'); setTimeout(function() { btn.classList.remove('copied'); }, 1500); }
}

// ── Event listeners ──

document.getElementById('btn-settings').addEventListener('click', function() {
  chrome.runtime.openOptionsPage();
});

// The consult is recorded in the offscreen document, not in this popup: a
// popup closes (and would stop the recording) as soon as the doctor clicks
// the page. The side panel shows the small recording bar and the report.
document.getElementById('btn-start').addEventListener('click', function() {
  var consent = document.getElementById('consent-recording');
  if (consent && !consent.checked) {
    showStatus('Vink eerst aan dat de patiënt toestemming geeft voor de opname.', true);
    return;
  }
  if (currentWindowId !== null) chrome.sidePanel.open({ windowId: currentWindowId });
  chrome.storage.session.set({ svOpenView: 'dictate' });
  chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: 'start' }).then(function(res) {
    if (res && res.ok) { window.close(); return; }
    showStatus((res && res.message) || 'De opname kon niet starten.', true);
  }).catch(function() {
    showStatus('De opname kon niet starten.', true);
  });
});

document.getElementById('btn-stop').addEventListener('click', function() {
  stopRecording();
});

document.getElementById('btn-copy-decisief').addEventListener('click', function() {
  copyToClipboard(document.getElementById('decisief-text').textContent, this);
});

document.getElementById('btn-copy-soep').addEventListener('click', function() {
  var soep = {
    s: document.getElementById('soep-s').textContent,
    o: document.getElementById('soep-o').textContent,
    e: document.getElementById('soep-e').textContent,
    p: document.getElementById('soep-p').textContent,
    icpc_code: document.getElementById('icpc-code') ? document.getElementById('icpc-code').textContent : '',
    icpc_titel: document.getElementById('icpc-title') ? document.getElementById('icpc-title').textContent : '',
  };
  copyToClipboard(formatSOEPText(soep), this);
});

document.getElementById('btn-push-bricks').addEventListener('click', async function() {
  var result = await chrome.runtime.sendMessage({ action: 'PUSH_TO_BRICKS' });
  if (result && result.success) {
    showStatus('Naar Bricks gepusht!', false);
  } else {
    showStatus((result && result.error) || 'Bricks-tab niet gevonden.', true);
  }
});

document.getElementById('btn-new-consult').addEventListener('click', function() {
  hideStatus();
  setState('idle');
  chrome.storage.local.remove(['sv_state', 'sv_data', 'sv_error']);
});

document.getElementById('btn-retry').addEventListener('click', function() {
  // Clear the stored error too, or it reappears the next time the popup opens.
  chrome.storage.local.remove(['sv_state', 'sv_error']);
  hideStatus();
  setState('idle');
});

// ── Watch storage for service-worker / widget results ──

chrome.storage.onChanged.addListener(function(changes, area) {
  if (area !== 'local') return;

  if (changes.sv_state) {
    var newState = changes.sv_state.newValue;

    if (newState === 'results' && changes.sv_data && changes.sv_data.newValue) {
      displayResults(changes.sv_data.newValue);
    } else if (newState === 'error' && changes.sv_error && changes.sv_error.newValue) {
      setState('error');
      document.getElementById('error-message').textContent = changes.sv_error.newValue;
      showStatus('Fout', true);
    } else if (newState === 'processing') {
      setState('processing');
      var step = changes.sv_step ? changes.sv_step.newValue : 'Verwerken...';
      updateProgress(30, step || 'Verwerken...');
    }
  }
});

// ── Init: check for existing results / in-progress processing ──

async function init() {
  var stored = await chrome.storage.local.get(['sv_state', 'sv_data', 'sv_error']);
  if (stored.sv_state === 'results' && stored.sv_data) {
    displayResults(stored.sv_data);
  } else if (stored.sv_state === 'processing') {
    setState('processing');
    showStatus('Verwerken...', false);
    updateProgress(30, 'Wachten op resultaat van server...');
  } else if (stored.sv_state === 'error' && stored.sv_error) {
    setState('error');
    document.getElementById('error-message').textContent = stored.sv_error;
    showStatus('Fout', true);
  } else {
    setState('idle');
  }
}

init();

// ── Dictation side panel ──
// sidePanel.open must be called directly in the click, so resolve the window first.
var currentWindowId = null;
chrome.windows.getCurrent(function (w) { currentWindowId = w.id; });

function openPanel(view) {
  if (currentWindowId === null) return;
  chrome.sidePanel.open({ windowId: currentWindowId });
  // The panel picks this up on load, or live when it is already open.
  chrome.storage.session.set({ svOpenView: view }).finally(function () { window.close(); });
}
document.getElementById('btn-dictate').addEventListener('click', function () { openPanel('dictate'); });
document.getElementById('btn-letters').addEventListener('click', function () { openPanel('letters'); });

// Dictate straight into the clicked field, without the side panel.
document.getElementById('btn-quick-dictate').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs[0]) chrome.runtime.sendMessage({ action: 'SV_QUICK_TOGGLE', tabId: tabs[0].id });
    window.close();
  });
});

// Point at the S/O/E/P fields once; the popup closes so the doctor can click in Bricks.
document.getElementById('link-map-fields').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs[0]) chrome.runtime.sendMessage({ action: 'SV_CALIBRATE_START', tabId: tabs[0].id });
    window.close();
  });
});

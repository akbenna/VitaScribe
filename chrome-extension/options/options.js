/**
 * VitaScribe - Options Page Controller
 * Manages extension settings: chrome.storage.sync for most, chrome.storage.local
 * for the server key (see lib/instellingen.js).
 */

// delenPerMail is off by default: mailing is a decision of the practice, not
// a default of the software.
// Het adres dat een lege instelling krijgt. In de ontwikkelversie is dat de
// lokale testserver; scripts/pack_store.sh zet er in het winkelpakket de
// VitaScribe-server voor in de plaats, zodat een nieuwe praktijk het niet
// hoeft in te vullen.
var STANDAARD_SERVER = 'http://localhost:8002';

var FIELDS = ['apiUrl', 'apiKey', 'sttProvider', 'llmProvider', 'micDevice', 'delenPerMail', 'consultLive'];

var SELECTOR_FIELDS = {
  selJournaal: 'journaal',
  selSoepS: 'soep_s',
  selSoepO: 'soep_o',
  selSoepE: 'soep_e',
  selSoepP: 'soep_p',
};

function showToast(message, duration) {
  var toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(function() { toast.classList.remove('show'); }, duration || 2500);
}

// ── Load settings ──

async function loadSettings() {
  await SVInstellingen.migreer();
  var stored = await SVInstellingen.lees(FIELDS.concat(['bricksSelectors']));

  FIELDS.forEach(function(key) {
    var el = document.getElementById(key);
    if (el && stored[key]) el.value = stored[key];
  });
  if (!stored.apiUrl) document.getElementById('apiUrl').value = STANDAARD_SERVER;
  laadVraagsuggesties(stored.apiUrl || STANDAARD_SERVER);
  laadWeergave();

  if (stored.bricksSelectors) {
    try {
      var selectors = JSON.parse(stored.bricksSelectors);
      Object.keys(SELECTOR_FIELDS).forEach(function(inputId) {
        var selectorKey = SELECTOR_FIELDS[inputId];
        var el = document.getElementById(inputId);
        if (el && selectors[selectorKey]) {
          el.value = Array.isArray(selectors[selectorKey])
            ? selectors[selectorKey].join(', ')
            : selectors[selectorKey];
        }
      });
    } catch (e) {
      // Ignore parse errors
    }
  }
}

// ── Question suggestions during the consult (clinical support) ──
// A switch that takes effect at once (no "Opslaan" needed). The server has
// the last word (CLINICAL_DECISION_SUPPORT); its answer is shown underneath.

async function laadVraagsuggesties(apiUrl) {
  var box = document.getElementById('vraagsuggesties');
  var note = document.getElementById('vraagsuggesties-server');
  if (!box) return;
  var stored = await SVInstellingen.lees(['vraagsuggesties']);
  box.checked = stored.vraagsuggesties === true;
  try {
    var resp = await fetch(String(apiUrl).replace(/\/$/, '') + '/health');
    var policy = (await resp.json()).data_policy || {};
    note.textContent = policy.clinical_decision_support
      ? 'Deze server staat klinische ondersteuning toe.'
      : 'Deze server staat klinische ondersteuning (nog) niet toe: zet CLINICAL_DECISION_SUPPORT=true op de server.';
  } catch (e) {
    note.textContent = '';
  }
}

document.getElementById('vraagsuggesties').addEventListener('change', async function (e) {
  await SVInstellingen.bewaar({ vraagsuggesties: e.target.checked });
  showToast(e.target.checked ? 'Vraagsuggesties aan (vanaf het volgende consult).' : 'Vraagsuggesties uit.');
});

// ── What the toolbar icon opens ──
// Takes effect at once; also ends a "minimised" session so the choice is
// what the next click does.

async function laadWeergave() {
  var stored = await SVInstellingen.lees(['weergave']);
  document.getElementById('weergave').value = stored.weergave === 'compact' ? 'compact' : 'paneel';
}

document.getElementById('weergave').addEventListener('change', async function (e) {
  await SVInstellingen.bewaar({ weergave: e.target.value });
  await chrome.runtime.sendMessage({ action: 'SV_WEERGAVE', weergave: null }).catch(function () {});
  showToast(e.target.value === 'compact' ? 'Het icoon opent nu de compacte popup.' : 'Het icoon opent nu het zijpaneel.');
});

// ── Save settings ──

async function saveSettings() {
  var data = {};

  FIELDS.forEach(function(key) {
    var el = document.getElementById(key);
    if (el) data[key] = el.value.trim();
  });

  var selectors = {};
  Object.keys(SELECTOR_FIELDS).forEach(function(inputId) {
    var selectorKey = SELECTOR_FIELDS[inputId];
    var el = document.getElementById(inputId);
    if (el && el.value.trim()) {
      selectors[selectorKey] = el.value.trim();
    }
  });

  if (Object.keys(selectors).length > 0) {
    data.bricksSelectors = JSON.stringify(selectors);
  }

  await SVInstellingen.bewaar(data);
  showToast('Instellingen opgeslagen!');
}

// ── Test API connection ──

async function testConnection() {
  var apiUrl = document.getElementById('apiUrl').value.trim();

  if (!apiUrl) {
    showToast('Vul eerst de API URL in.');
    return;
  }

  var base = apiUrl.replace(/\/$/, '');

  try {
    var response = await fetch(base + '/health', { method: 'GET' });
    if (!response.ok) {
      showToast('Server bereikbaar maar fout: ' + response.status + ' ' + response.statusText);
      return;
    }

    // Show where the server sends data (set by the practice on the server).
    try {
      var policy = (await response.clone().json()).data_policy;
      var info = document.getElementById('policy-info');
      if (policy && info) {
        info.textContent = 'Deze server: patiëntgegevens naar ' + policy.patient_data_llm +
          (policy.patient_data_llm_in_eu ? ' (EU)' : ' (BUITEN DE EU)') +
          ', brieven naar ' + policy.letters_llm + ', spraak naar ' + policy.stt +
          ' (EU, zonder training). Klinische suggesties: ' + (policy.clinical_decision_support ? 'aan' : 'uit') + '.';
      }
    } catch (e) { /* older server */ }

    // Server bereikbaar — test nu of de API-sleutel geaccepteerd wordt.
    var apiKey = document.getElementById('apiKey').value.trim();
    var headers = {};
    if (apiKey) headers['X-API-Key'] = apiKey;
    await SVPraktijk.metKop(headers);

    var auth = await fetch(base + '/api/v1/providers', { method: 'GET', headers: headers });
    if (auth.ok) {
      // Save right away: the extension uses the stored key, not this field.
      await saveSettings();
      // Check that the server actually has a key for the chosen language model.
      var providers = await auth.json().catch(function () { return null; });
      var llm = document.getElementById('llmProvider').value;
      var names = { mistral: 'MISTRAL_API_KEY', anthropic: 'ANTHROPIC_API_KEY', gemini: 'GEMINI_API_KEY' };
      if (providers && providers.llm && providers.llm.available && providers.llm.available[llm] === false) {
        showToast('Verbinding OK, maar de server heeft geen ' + names[llm] + '. Voeg die toe in Railway ' +
          '(en klik daar op Deploy), of kies een ander taalmodel.', 9000);
      } else {
        showToast('Verbinding, API-sleutel en taalmodel OK — opgeslagen.');
      }
    } else if (auth.status === 403) {
      // De server zegt waarom: onbekende sleutel, uitgezet, licentie verlopen of andere praktijk.
      var reden = await auth.json().then(function (b) { return b && b.detail; }).catch(function () { return null; });
      showToast('Server OK, maar de sleutel wordt geweigerd: ' + (reden || 'onbekende sleutel (403).'), 9000);
    } else if (auth.status === 401) {
      showToast('Server OK, maar API-sleutel ontbreekt (401). Vul de sleutel in.');
    } else {
      showToast('Server OK, maar sleuteltest gaf: ' + auth.status + ' ' + auth.statusText);
    }
  } catch (err) {
    showToast('Verbindingsfout: ' + err.message);
  }
  await laadLicentie();
}

// ── Microphone enumeration ──

async function loadMicDevices() {
  var select = document.getElementById('micDevice');
  if (!select) return;

  try {
    // Vraag kort toestemming zodat labels zichtbaar worden
    var deviceList = await navigator.mediaDevices.enumerateDevices();
    var audioInputs = deviceList.filter(function(d) { return d.kind === 'audioinput'; });

    if (audioInputs.length > 0 && !audioInputs[0].label) {
      var tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      tempStream.getTracks().forEach(function(t) { t.stop(); });
      deviceList = await navigator.mediaDevices.enumerateDevices();
      audioInputs = deviceList.filter(function(d) { return d.kind === 'audioinput'; });
    }

    // Bewaar huidige selectie
    var current = select.value;

    // Reset opties (bewaar standaard optie)
    select.innerHTML = '<option value="">Standaard microfoon (systeem)</option>';

    audioInputs.forEach(function(device, i) {
      var opt = document.createElement('option');
      opt.value = device.deviceId;
      opt.textContent = device.label || ('Microfoon ' + (i + 1));
      select.appendChild(opt);
    });

    // Herstel selectie
    if (current) select.value = current;
  } catch (e) {
    var statusEl = document.getElementById('mic-test-status');
    if (statusEl) statusEl.textContent = 'Kan apparaten niet laden: ' + e.message;
  }
}

async function testMicrophone() {
  var statusEl = document.getElementById('mic-test-status');
  var deviceId = document.getElementById('micDevice').value;

  statusEl.textContent = 'Testen...';
  statusEl.style.color = 'var(--text-secondary)';

  try {
    var constraints = {
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
    };
    if (deviceId) constraints.audio.deviceId = { exact: deviceId };

    var stream = await navigator.mediaDevices.getUserMedia(constraints);

    // Controleer of er daadwerkelijk audio binnenkomt
    var ctx = new AudioContext();
    var source = ctx.createMediaStreamSource(stream);
    var analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    var data = new Uint8Array(analyser.frequencyBinCount);

    // Wacht kort en meet of er signaal is
    await new Promise(function(resolve) { setTimeout(resolve, 500); });
    analyser.getByteTimeDomainData(data);

    var hasSignal = data.some(function(v) { return v !== 128; });

    stream.getTracks().forEach(function(t) { t.stop(); });
    ctx.close();

    statusEl.style.color = 'var(--primary)';
    statusEl.textContent = hasSignal
      ? 'Microfoon werkt! Audiosignaal gedetecteerd.'
      : 'Microfoon verbonden (stil — spreek in de microfoon om te testen).';
  } catch (e) {
    statusEl.style.color = '#dc2626';
    if (e.name === 'NotFoundError') {
      statusEl.textContent = 'Microfoon niet gevonden. Controleer de aansluiting.';
    } else if (e.name === 'NotAllowedError') {
      statusEl.textContent = 'Microfoontoegang geweigerd. Sta dit toe in browserinstellingen.';
    } else {
      statusEl.textContent = 'Fout: ' + e.message;
    }
  }
}

// ── Licentie en eigen sleutels van de praktijk ──

var AANBIEDER_NAAM = { anthropic: 'Claude (Anthropic)', openai: 'ChatGPT (OpenAI)', deepgram: 'Deepgram' };

async function serverAanroep(pad, opties) {
  var apiUrl = document.getElementById('apiUrl').value.trim().replace(/\/$/, '');
  var apiKey = document.getElementById('apiKey').value.trim();
  if (!apiUrl || !apiKey) return null;
  var headers = { 'X-API-Key': apiKey };
  if (opties && opties.body) headers['Content-Type'] = 'application/json';
  await SVPraktijk.metKop(headers);
  return fetch(apiUrl + pad, {
    method: (opties && opties.methode) || 'GET',
    headers: headers,
    body: opties && opties.body ? JSON.stringify(opties.body) : undefined,
  });
}

function datumNL(iso) {
  if (!iso) return '';
  return new Date(iso.length === 10 ? iso + 'T12:00:00' : iso).toLocaleDateString('nl-NL');
}

function toonEigenSleutels(lic) {
  var kaart = document.getElementById('eigen-kaart');
  var mag = lic && lic.bron === 'register' && lic.eigen_sleutels_mogelijk;
  kaart.hidden = !mag;
  if (!mag) return;
  var beheerder = lic.rol === 'praktijkbeheerder';
  document.getElementById('eigen-alleen-beheerder').hidden = beheerder;
  ['brieven', 'spraak'].forEach(function (dienst) {
    var huidig = (lic.eigen_sleutels || {})[dienst];
    var status = document.getElementById('eigen-status-' + dienst);
    if (huidig) {
      status.textContent = 'Eigen sleutel ingesteld: ' + (AANBIEDER_NAAM[huidig.aanbieder] || huidig.aanbieder) +
        ', eindigend op …' + huidig.hint + ' (sinds ' + datumNL(huidig.ingesteld_op) + ').';
    } else {
      status.textContent = lic.eigen_sleutels_verplicht
        ? 'Geen eigen sleutel. Uw praktijk gebruikt alleen eigen sleutels: zonder sleutel werkt dit niet.'
        : 'Geen eigen sleutel: ' + dienst + ' loopt via de server.';
    }
    var invoer = kaart.querySelectorAll('#eigen-sleutel-' + dienst + ', #eigen-opslaan-' + dienst + ', #eigen-aanbieder-' + dienst);
    invoer.forEach(function (el) { el.hidden = !beheerder; });
    document.getElementById('eigen-weg-' + dienst).hidden = !(beheerder && huidig);
  });
  var brieven = (lic.eigen_sleutels || {}).brieven;
  var regel = document.getElementById('policy-brieven');
  if (regel && brieven) {
    regel.textContent = 'Brieven, na verwijdering van naam, BSN, adres en datums: ' +
      (AANBIEDER_NAAM[brieven.aanbieder] || brieven.aanbieder) + ', via de sleutel van uw praktijk';
  }
}

async function laadLicentie() {
  var info = document.getElementById('licentie-info');
  var r;
  try { r = await serverAanroep('/api/v1/licentie'); } catch (e) { r = null; }
  if (!r) return;
  var body = await r.json().catch(function () { return {}; });
  if (r.status === 404) { info.textContent = 'Deze server kent nog geen licenties.'; return; }
  if (!r.ok) {
    info.textContent = body.detail || ('De licentie kon niet worden opgehaald (' + r.status + ').');
    toonEigenSleutels(null);
    return;
  }
  if (body.bron === 'register') {
    var type = { pilot: 'gratis pilot', betaald: 'licentie', intern: 'eigen praktijk', kandidaat: 'kandidaat' }[body.licentietype] || body.licentietype;
    info.textContent = 'Voor ' + body.praktijk + ' (' + type + ')' +
      (body.geldig_tot ? ', geldig tot ' + datumNL(body.geldig_tot) : ', onbeperkt geldig') +
      '. Gebruiker: ' + body.gebruiker + (body.rol === 'praktijkbeheerder' ? ', praktijkbeheerder' : '') + '.';
  } else if (body.bron === 'omgeving') {
    info.textContent = 'Sleutel van de server zelf (' + body.gebruiker + '), zonder licentie per praktijk.';
  } else {
    info.textContent = 'De server draait zonder sleutels (ontwikkelmodus).';
  }
  toonEigenSleutels(body);
}

async function slaEigenSleutelOp(dienst) {
  var veld = document.getElementById('eigen-sleutel-' + dienst);
  var sleutel = veld.value.trim();
  if (!sleutel) { showToast('Plak eerst de sleutel.'); return; }
  var aanbieder = dienst === 'brieven' ? document.getElementById('eigen-aanbieder-brieven').value : 'deepgram';
  var knop = document.getElementById('eigen-opslaan-' + dienst);
  knop.disabled = true;
  try {
    var r = await serverAanroep('/api/v1/praktijk/sleutels/' + dienst, { methode: 'PUT', body: { aanbieder: aanbieder, sleutel: sleutel } });
    var body = await r.json().catch(function () { return {}; });
    if (!r.ok) { showToast(body.detail || ('Opslaan lukte niet (' + r.status + ').'), 9000); return; }
    veld.value = '';
    showToast('Sleutel gecontroleerd en versleuteld opgeslagen op de server.');
    await laadLicentie();
  } catch (e) {
    showToast('Verbindingsfout: ' + e.message);
  } finally {
    veld.value = '';
    knop.disabled = false;
  }
}

async function verwijderEigenSleutel(dienst) {
  if (!confirm('De eigen sleutel voor ' + dienst + ' verwijderen?')) return;
  var r = await serverAanroep('/api/v1/praktijk/sleutels/' + dienst, { methode: 'DELETE' });
  if (r && r.ok) { showToast('Verwijderd.'); await laadLicentie(); }
  else if (r) { var b = await r.json().catch(function () { return {}; }); showToast(b.detail || 'Verwijderen lukte niet.'); }
}

['brieven', 'spraak'].forEach(function (dienst) {
  document.getElementById('eigen-opslaan-' + dienst).addEventListener('click', function () { slaEigenSleutelOp(dienst); });
  document.getElementById('eigen-weg-' + dienst).addEventListener('click', function () { verwijderEigenSleutel(dienst); });
});

// ── Event listeners ──

document.getElementById('btn-save').addEventListener('click', saveSettings);
document.getElementById('btn-test').addEventListener('click', testConnection);
document.getElementById('btn-refresh-mic').addEventListener('click', loadMicDevices);
document.getElementById('btn-test-mic').addEventListener('click', testMicrophone);

// ── Initialize ──
loadSettings().then(laadLicentie).catch(function () { /* geen verbinding: dan pas bij Test verbinding */ });
loadMicDevices();

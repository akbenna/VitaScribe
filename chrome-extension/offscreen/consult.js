/**
 * VitaScribe - Consultopname in het offscreen-document
 *
 * Het consult werd eerst opgenomen in de zwevende knop op de Bricks-pagina.
 * Klikte de arts naar een andere pagina, dan verdween die knop en daarmee de
 * opname. Hier loopt de opname in het offscreen-document van de extensie: dat
 * blijft bestaan zolang de browser open is, wat er ook met tabbladen of het
 * zijpaneel gebeurt.
 *
 * Het gesprek gaat live naar de server (SVConsultLive). De stukjes geluid
 * blijven hier ook bewaard als reservekopie: lukt live niet, dan gaat de hele
 * opname na "stop" alsnog in één keer naar /api/v1/consult/process.
 *
 * Alleen chrome.runtime is hier beschikbaar. Instellingen en het
 * praktijknummer komen mee met het startbericht van de service worker; de
 * voortgang gaat als SV_CONSULT_EVENT terug naar de service worker.
 */

// Kleine stukjes, zodat het gesprek live mee kan. Samen vormen ze ook de
// reservekopie: dezelfde stukjes achter elkaar zijn een geldig webm-bestand.
var CONSULT_CHUNK_MS = 250;
var CONSULT_LIVE_WAIT_MS = 90000;

var consult = null;   // { config, stream, recorder, chunks, live, startedAt, nadictaatVanaf, afgebroken }
// A recording whose report could not be made (server unreachable). Kept in
// memory only, so the doctor can send it again; gone with the next consult.
var consultPending = null;   // { config, blob, mime, nadictaatVanaf }

function consultEmit(type, extra) {
  var msg = { action: 'SV_CONSULT_EVENT', type: type };
  for (var k in extra || {}) msg[k] = extra[k];
  chrome.runtime.sendMessage(msg).catch(function () {});
}

function consultHeaders(config) {
  var headers = {};
  if (config.apiKey) headers['X-API-Key'] = config.apiKey;
  if (config.praktijk && config.praktijk.length) headers['X-Bricks-Praktijk'] = config.praktijk.join(',');
  return headers;
}

async function consultStart(config) {
  if (consult) return { ok: false, message: 'Er loopt al een consultopname.' };
  if (typeof session !== 'undefined' && session) return { ok: false, message: 'Stop eerst het dicteren (Alt+Shift+D).' };
  consultPending = null;

  var constraints = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  if (config.micDevice) constraints.deviceId = { exact: config.micDevice };
  var stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: constraints });
  } catch (err) {
    if (err && err.name === 'NotAllowedError') {
      return { ok: false, code: 'mic-permission', message: 'VitaScribe heeft nog geen toegang tot de microfoon. Geef toestemming in het tabblad dat nu opent.' };
    }
    return { ok: false, message: 'Microfoon niet beschikbaar: ' + ((err && err.message) || err) };
  }

  var c = consult = {
    config: config, stream: stream, recorder: null, chunks: [], live: null,
    startedAt: Date.now(), nadictaatVanaf: null, afgebroken: null,
  };
  c.live = consultStartLive(c);

  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
  // 64 kbit/s opus is ruim voor spraak en houdt de stukjes klein.
  c.recorder = new MediaRecorder(stream, { mimeType: mimeType, audioBitsPerSecond: 64000 });
  c.recorder.ondataavailable = function (e) {
    if (e.data && e.data.size > 0) {
      c.chunks.push(e.data);   // reservekopie, blijft tot het verslag er is
      if (c.live) c.live.stuur(e.data);
    }
  };
  c.recorder.onstop = function () {
    var mime = c.recorder.mimeType || 'audio/webm';
    stopGeluidsmeter(c);
    c.stream.getTracks().forEach(function (t) { t.stop(); });
    consultRondAf(c, new Blob(c.chunks, { type: mime }), mime);
  };
  // The microphone can drop out on its own (another program takes it, a
  // headset is unplugged). That must not look like "Stop": say what happened.
  stream.getAudioTracks().forEach(function (t) {
    t.addEventListener('ended', function () {
      if (consult !== c || c.stopGevraagd) return;
      c.afgebroken = 'De microfoon viel weg na ' + Math.round((Date.now() - c.startedAt) / 1000) +
        ' s (headset los, of een ander programma nam hem over). Controleer de microfoon en start opnieuw.';
      c.afgebrokenCode = 'mic';
      consultStop();
    });
  });
  startGeluidsmeter(c);
  c.recorder.start(CONSULT_CHUNK_MS);
  consultEmit('recording', { startedAt: c.startedAt, label: c.live ? 'Luistert mee' : 'Opname loopt' });
  return { ok: true, startedAt: c.startedAt };
}

// Staat "consultLive" op "uit", dan wordt het consult zoals vroeger eerst
// opgenomen en na stop in zijn geheel verstuurd.
function consultStartLive(c) {
  if (c.config.consultLive === 'uit' || typeof SVConsultLive === 'undefined') return null;
  try {
    return SVConsultLive.start({
      apiUrl: c.config.apiUrl,
      apiKey: c.config.apiKey,
      praktijk: c.config.praktijk || [],
      llmProvider: c.config.llmProvider,
      vraagsuggesties: c.config.vraagsuggesties === true,
      onSuggesties: function (s) {
        if (c.nadictaatVanaf === null) consultEmit('suggesties', { klacht: s.klacht, vragen: s.vragen });
      },
      onVoortgang: function (seconden, sprekers) {
        if (c.nadictaatVanaf !== null) return;   // het label zegt dan "Nadicteren"
        consultEmit('label', { label: sprekers > 1 ? 'Luistert mee · ' + sprekers + ' stemmen' : 'Luistert mee' });
      },
      onFout: function (melding, terugval) {
        if (terugval) {
          // De opname loopt gewoon door; na stop gaat hij in zijn geheel naar de server.
          consultEmit('label', { label: 'Opname loopt (live verbinding weg)' });
        } else {
          // The server refuses this consult (key, licence, consent): stop now,
          // not after the whole consult.
          c.afgebroken = melding;
          c.afgebrokenCode = /sleutel|licentie/i.test(melding || '') ? 'key' : '';
          consultStop();
        }
      },
    });
  } catch (e) {
    return null;   // dan gewoon opnemen en achteraf versturen
  }
}

// De patiënt is weg. De arts dicteert nog kort onderzoek en beleid; alles
// vanaf dit moment is alleen de arts. De opname loopt gewoon door.
function consultNadictaat() {
  var c = consult;
  if (!c || !c.recorder || c.recorder.state === 'inactive' || c.nadictaatVanaf !== null) return;
  c.nadictaatVanaf = Math.round((Date.now() - c.startedAt) / 100) / 10;
  if (c.live) c.live.nadictaat(c.nadictaatVanaf);
  consultEmit('label', { label: 'Nadicteren: onderzoek en beleid', nadictaat: true });
}

function consultStop() {
  var c = consult;
  if (c && c.recorder && c.recorder.state !== 'inactive') {
    c.stopGevraagd = true;
    c.recorder.stop();
  }
}

// ── Geluidsmeter: waarschuw als de microfoon niets hoort ──
// Merkt de arts pas na het consult dat de verkeerde microfoon aanstond, dan is
// het consult verloren. Heeft de microfoon STIL_MS na de start nog helemaal
// niets gehoord, dan zegt het bolletje het meteen. Is er eenmaal geluid
// geweest, dan geen waarschuwing meer: een stilte in het gesprek is normaal,
// en een microfoon die wegvalt meldt zich zelf ("ended").
var STIL_MS = 8000;
var STIL_DREMPEL = 0.01;   // RMS; spraak op normale afstand ligt ruim hoger
var METER_MS = 100;        // vaak meten: korte klanken mogen niet tussendoor vallen

function startGeluidsmeter(c) {
  try {
    var ctx = new AudioContext();
    var bron = ctx.createMediaStreamSource(c.stream);
    var meter = ctx.createAnalyser();
    meter.fftSize = 2048;
    bron.connect(meter);
    var buf = new Float32Array(meter.fftSize);
    c.gehoord = false;
    c.stil = false;
    c.meter = { ctx: ctx, timer: setInterval(function () {
      meter.getFloatTimeDomainData(buf);
      var som = 0;
      for (var i = 0; i < buf.length; i++) som += buf[i] * buf[i];
      if (Math.sqrt(som / buf.length) > STIL_DREMPEL) {
        c.gehoord = true;
        if (c.stil) {
          c.stil = false;
          consultEmit('label', { label: 'Opname loopt', stil: false });
        }
        stopGeluidsmeter(c);   // de microfoon werkt; verder meten is niet nodig
      } else if (!c.stil && Date.now() - c.startedAt > STIL_MS) {
        c.stil = true;
        consultEmit('label', { label: 'Geen geluid: controleer de microfoon', stil: true });
      }
    }, METER_MS) };
  } catch (e) { /* geen Web Audio: dan zonder waarschuwing */ }
}

function stopGeluidsmeter(c) {
  if (!c.meter) return;
  clearInterval(c.meter.timer);
  try { c.meter.ctx.close(); } catch (e) { /* al dicht */ }
  c.meter = null;
}

// Hoe lang een opname minstens moet zijn om te verwerken; korter is bijna
// altijd per ongeluk gestart of gestopt.
var MIN_OPNAME_MS = 3000;

// A report without any speech is not a report: say so, with the likely cause.
function consultResultaat(data, c) {
  if (!String((data && (data.transcript_raw || data.transcript)) || '').trim()) {
    var sec = Math.round((data && data.duration_secs) || (Date.now() - c.startedAt) / 1000);
    consultEmit('error', {
      code: 'stil',
      message: 'Er is geen spraak gehoord in de opname (' + sec + ' s). Staat de goede microfoon aan ' +
        '(Instellingen) en is hij niet gedempt? Er is geen verslag gemaakt.',
    });
    return;
  }
  consultEmit('result', { data: data });
}

async function consultRondAf(c, blob, mime) {
  var verbinding = c.live;
  c.live = null;
  try {
    if (c.afgebroken) {
      if (verbinding) verbinding.sluit();
      consultEmit('error', { message: c.afgebroken, code: c.afgebrokenCode || '' });
      return;
    }
    var duur = Date.now() - c.startedAt;
    if (blob.size < 1000 || duur < MIN_OPNAME_MS) {
      if (verbinding) verbinding.sluit();
      consultEmit('error', { code: 'kort',
        message: 'De opname duurde maar ' + Math.max(1, Math.round(duur / 1000)) + ' s en is niet verwerkt. Per ongeluk gestopt? Start opnieuw.' });
      return;
    }
    if (verbinding) {
      consultEmit('processing', { step: 'Verslag wordt gemaakt…' });
      var uit = await verbinding.stop(CONSULT_LIVE_WAIT_MS);
      if (uit.ok) {
        consultResultaat(uit.data, c);
        return;
      }
      consultEmit('processing', { step: 'Live lukte niet; de opname wordt alsnog verwerkt…' });
    } else {
      consultEmit('processing', { step: 'Opname wordt verwerkt…' });
    }
    await consultSend({ config: c.config, blob: blob, mime: mime, nadictaatVanaf: c.nadictaatVanaf, startedAt: c.startedAt });
  } catch (err) {
    consultEmit('error', { message: (err && err.message) || 'Onbekende fout bij het verwerken.' });
  } finally {
    c.chunks = [];
    if (consult === c) consult = null;
  }
}

// Upload the whole recording. When that fails the recording is kept, and
// "Opnieuw versturen" (SV_CONSULT_RETRY) tries again.
async function consultSend(job) {
  try {
    var data = await consultUpload(job, job.blob, job.mime);
    consultPending = null;
    consultResultaat(data, job);
  } catch (err) {
    consultPending = err.permanent ? null : job;
    consultEmit('error', {
      message: ((err && err.message) || 'Verwerken mislukt.') + (consultPending ? ' De opname is bewaard.' : ''),
      code: err.code || '',
      retry: !!consultPending,
    });
  }
}

async function consultRetry() {
  if (!consultPending || consult) return { ok: false, message: 'Er is geen opname om opnieuw te versturen.' };
  consultEmit('processing', { step: 'Opname wordt opnieuw verstuurd…' });
  consultSend(consultPending);
  return { ok: true };
}

async function consultUpload(c, blob, mime) {
  var form = new FormData();
  form.append('audio', blob, 'consult.' + (mime.indexOf('webm') !== -1 ? 'webm' : 'wav'));
  form.append('consent', 'true');
  if (c.nadictaatVanaf !== null && c.nadictaatVanaf !== undefined) form.append('nadictaat_vanaf', String(c.nadictaatVanaf));
  if (c.config.sttProvider) form.append('stt_provider', c.config.sttProvider);
  if (c.config.llmProvider) form.append('llm_provider', c.config.llmProvider);
  var resp;
  try {
    resp = await fetch(c.config.apiUrl + '/api/v1/consult/process', {
      method: 'POST', headers: consultHeaders(c.config), body: form,
    });
  } catch (e) {
    throw new Error('Kan de server niet bereiken op ' + c.config.apiUrl + '. Controleer het adres in Instellingen.');
  }
  if (!resp.ok) {
    var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
    var fout;
    if (resp.status === 403 || resp.status === 401) {
      fout = new Error('De server accepteert de VitaScribe-sleutel niet. Controleer hem in Instellingen.');
      fout.code = 'key';
    } else {
      fout = new Error('Server gaf fout ' + resp.status + (typeof detail === 'string' && detail ? ': ' + detail : '') + '.');
    }
    throw fout;
  }
  return resp.json();
}

function consultStatus() {
  if (!consult) return { active: false };
  var recording = !!(consult.recorder && consult.recorder.state !== 'inactive');
  return { active: true, recording: recording, startedAt: consult.startedAt, nadictaat: consult.nadictaatVanaf !== null };
}

chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
  if (msg.target !== 'sv-offscreen') return false;
  if (msg.action === 'SV_CONSULT_START') {
    consultStart(msg.config).then(sendResponse);
    return true;
  }
  if (msg.action === 'SV_CONSULT_STOP') {
    consultStop();
    sendResponse({ ok: true });
  } else if (msg.action === 'SV_CONSULT_NADICTAAT') {
    consultNadictaat();
    sendResponse({ ok: true });
  } else if (msg.action === 'SV_CONSULT_RETRY') {
    consultRetry().then(sendResponse);
    return true;
  } else if (msg.action === 'SV_CONSULT_STATUS') {
    sendResponse(consultStatus());
  }
  return false;
});

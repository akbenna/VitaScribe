/**
 * VitaScribe - de telefoon of iPad als tweede apparaat (pagina /m)
 *
 * Geopend via de QR-code in het zijpaneel. Het koppelgeheim staat achter de #
 * (komt dus nooit in een serverlog), gaat daarna alleen als header mee en
 * blijft in sessionStorage tot het tabblad sluit.
 *
 * Tolk: één keer Start. Daarna luistert de telefoon handsfree (dezelfde
 * stemdetectie als de extensie, tolk.js), stuurt elke beurt als WAV naar de
 * server, en leest de vertaling voor met de stem van dit toestel. Tijdens het
 * voorlezen luistert hij niet, zodat hij zichzelf niet vertaalt. Elke beurt
 * staat ook in het zijpaneel.
 *
 * Foto: gaat direct naar het zijpaneel, niet naar de fotorol.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var geheim = '';
  var taal = null;               // {code, naam, eigen, verstaat}
  var actief = true;             // the pairing is alive
  var beurten = [];
  var laatste = null;
  var mic = null;                // {ctx, stream, proc}
  var vad = null;
  var pauze = false;
  var spreekt = false;
  var bezig = Promise.resolve();
  var wakeLock = null;
  var DOEL_RATE = 16000;

  // ── Pairing secret ──
  try {
    if (location.hash.length > 10) {
      geheim = decodeURIComponent(location.hash.slice(1));
      sessionStorage.setItem('svKoppel', geheim);
      history.replaceState(null, '', location.pathname);
    } else {
      geheim = sessionStorage.getItem('svKoppel') || '';
    }
  } catch (e) { geheim = location.hash.slice(1); }

  function pil(tekst, fout) {
    $('pil').textContent = tekst;
    $('pil').classList.toggle('fout', !!fout);
  }

  function melding(tekst, fout) {
    $('melding').textContent = tekst || '';
    $('melding').classList.toggle('fout', !!fout);
  }

  async function api(pad, opties) {
    opties = opties || {};
    var headers = Object.assign({ 'X-VitaScribe-Koppel': geheim }, opties.headers || {});
    var resp = await fetch(pad, Object.assign({}, opties, { headers: headers, cache: 'no-store' }));
    if (resp.status === 410) { einde('De koppeling is verlopen. Scan de QR-code in het zijpaneel opnieuw.'); throw new Error('verlopen'); }
    return resp;
  }

  async function fout(resp) {
    var d = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
    return new Error(typeof d === 'string' && d ? d : 'De server gaf fout ' + resp.status + '.');
  }

  function status(s) {
    api('/api/v1/telefoon/status', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: s }) }).catch(function () {});
  }

  function einde(tekst) {
    actief = false;
    stopMic();
    pil('niet gekoppeld', true);
    $('tolk').classList.add('hidden');
    $('alleen-foto').classList.add('hidden');
    $('koppelen').classList.remove('hidden');
    $('koppel-tekst').textContent = tekst;
    try { sessionStorage.removeItem('svKoppel'); } catch (e) { /* ignore */ }
  }

  // ── Hello and messages from the panel ──
  async function hallo() {
    if (!geheim) { einde('Geen koppeling gevonden. Scan de QR-code in het VitaScribe-zijpaneel.'); return; }
    try {
      var resp = await api('/api/v1/telefoon/hallo', { method: 'POST' });
      if (!resp.ok) throw await fout(resp);
      var d = await resp.json();
      taal = d.taal;
      pil(d.modus === 'eu' ? 'gekoppeld · EU' : 'gekoppeld');
      $('koppelen').classList.add('hidden');
      if (taal) {
        $('taal-eigen').textContent = taal.eigen;
        $('taal-naam').textContent = taal.eigen !== taal.naam ? '· ' + taal.naam : '';
        $('patient-tekst').dir = SVTolk.rtl(taal.code) ? 'rtl' : 'auto';
        $('patient-tekst').lang = SVTolk.spraakTag(taal.code);
        $('tolk').classList.remove('hidden');
        if (!taal.verstaat) melding('In deze modus verstaat de server geen ' + taal.naam + '. De arts kan wel spreken; het antwoord van de patiënt niet.', true);
      } else {
        $('alleen-foto').classList.remove('hidden');
      }
      luister();
    } catch (e) {
      if (actief) einde(e.message);
    }
  }

  async function luister() {
    while (actief) {
      try {
        var resp = await api('/api/v1/telefoon/ontvang?wacht=20');
        if (!resp.ok) throw new Error(String(resp.status));
        var d = await resp.json();
        for (var i = 0; i < d.berichten.length; i++) await bericht(d.berichten[i]);
      } catch (e) {
        if (!actief) return;
        await new Promise(function (r) { setTimeout(r, 2000); });
      }
    }
  }

  async function bericht(b) {
    if (b.type === 'stop') {
      einde('Het zijpaneel heeft de koppeling beëindigd. Je kunt dit tabblad sluiten.');
    } else if (b.type === 'spreek' && b.data && b.data.tekst) {
      // "Opnieuw" or "Eenvoudiger" in the panel: read it here.
      var t = b.data.taal || (taal && taal.code);
      if (t !== 'nl') toonTekst({ spreker: 'arts', vertaling: b.data.tekst, origineel: '' });
      await zeg(b.data.tekst, t);
    }
  }

  // ── Showing a turn ──
  function toonTekst(b) {
    $('leeg').classList.add('hidden');
    $('wie').classList.remove('hidden');
    var arts = b.spreker === 'arts';
    $('wie').textContent = arts ? 'Dokter' : 'Patiënt';
    $('wie').className = 'wie ' + (arts ? 'arts' : 'patient');
    // Large: what the patient reads. Small: Dutch.
    $('patient-tekst').textContent = arts ? (b.vertaling || '') : (b.origineel || '');
    $('nl-tekst').textContent = arts ? (b.origineel || '') : (b.vertaling || '');
    $('herhaal').disabled = false;
  }

  // ── Speaking with this device's voices ──
  function stemmen() {
    return new Promise(function (klaar) {
      var v = window.speechSynthesis ? speechSynthesis.getVoices() : [];
      if (v.length || !window.speechSynthesis) { klaar(v); return; }
      speechSynthesis.onvoiceschanged = function () { klaar(speechSynthesis.getVoices()); };
      setTimeout(function () { klaar(speechSynthesis.getVoices()); }, 700);
    });
  }

  function speelAf(blob) {
    return new Promise(function (klaar) {
      var url = URL.createObjectURL(blob);
      var a = new Audio(url);
      var af = function () { URL.revokeObjectURL(url); klaar(); };
      a.onended = af; a.onerror = af;
      a.play().catch(af);
    });
  }

  async function zeg(tekst, code) {
    if (!tekst || !code) return;
    spreekt = true;
    zetLuister('spreekt', 'Spreekt…');
    status('spreekt');
    try {
      var stem = window.speechSynthesis ? SVTolk.kiesStem(await stemmen(), code) : null;
      if (stem) {
        await new Promise(function (klaar) {
          var u = new SpeechSynthesisUtterance(tekst);
          u.voice = stem; u.lang = stem.lang; u.rate = 0.95;
          u.onend = klaar; u.onerror = klaar;
          speechSynthesis.cancel();
          speechSynthesis.speak(u);
        });
      } else {
        // No voice on this device for this language: the server's voice.
        var resp = await api('/api/v1/telefoon/spreek', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tekst: tekst, taal: code }) });
        if (resp.ok) await speelAf(await resp.blob());
        else melding('Geen stem voor deze taal op dit toestel. Laat de tekst lezen.', true);
      }
    } catch (e) { /* reading aloud is a help, not a must */ }
    // A short pause, so the end of our own voice is not heard as a new turn.
    await new Promise(function (r) { setTimeout(r, 450); });
    spreekt = false;
    vad = null;
    if (mic) { zetLuister(pauze ? '' : 'aan', pauze ? 'Pauze' : 'Luistert'); status(pauze ? 'pauze' : 'luistert'); }
  }

  function zetLuister(stand, tekst) {
    var l = $('luister');
    l.classList.remove('hidden', 'aan', 'hoort', 'spreekt');
    if (stand) l.classList.add(stand);
    $('luister-tekst').textContent = tekst;
  }

  // ── Listening hands-free ──
  function naar16k(frames, rate) {
    var n = frames.reduce(function (t, f) { return t + f.length; }, 0);
    var alles = new Float32Array(n);
    var o = 0;
    frames.forEach(function (f) { alles.set(f, o); o += f.length; });
    if (rate <= DOEL_RATE) return { samples: alles, rate: rate };
    var stap = rate / DOEL_RATE;
    var uit = new Float32Array(Math.floor(n / stap));
    for (var i = 0; i < uit.length; i++) {
      var a = Math.floor(i * stap), b = Math.min(n, Math.floor((i + 1) * stap)), som = 0;
      for (var j = a; j < b; j++) som += alles[j];
      uit[i] = som / Math.max(1, b - a);
    }
    return { samples: uit, rate: DOEL_RATE };
  }

  async function start() {
    melding('');
    // iOS: speech and audio may only start from a tap; this tap unlocks both.
    try { if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(' ')); } catch (e) { /* ignore */ }
    var stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      melding('Geen toegang tot de microfoon. Sta de microfoon toe voor deze pagina (Instellingen › Safari › Microfoon).', true);
      return;
    }
    var Ctx = window.AudioContext || window.webkitAudioContext;
    var ctx = new Ctx();
    await ctx.resume().catch(function () {});
    var bron = ctx.createMediaStreamSource(stream);
    var proc = ctx.createScriptProcessor(2048, 1, 1);
    var frameMs = 2048 / ctx.sampleRate * 1000;
    var voor = [];             // the last ~0.6 s before speech started
    var opname = null;
    proc.onaudioprocess = function (e) {
      if (!actief) return;
      var data = new Float32Array(e.inputBuffer.getChannelData(0));
      if (spreekt || pauze) { opname = null; voor = []; return; }
      var som = 0;
      for (var i = 0; i < data.length; i++) som += data[i] * data[i];
      var stap = SVTolk.vadStap(vad, Math.sqrt(som / data.length), Date.now(), { frameMs: frameMs });
      vad = stap.st;
      if (opname) opname.push(data);
      else { voor.push(data); if (voor.length * frameMs > 600) voor.shift(); }
      if (stap.gebeurtenis === 'begin') {
        opname = voor.slice();
        voor = [];
        zetLuister('hoort', 'Hoort…');
        status('hoort');
      } else if (stap.gebeurtenis === 'einde' && opname) {
        var frames = opname;
        opname = null;
        stuur(frames, ctx.sampleRate);
      }
    };
    bron.connect(proc);
    proc.connect(ctx.destination);
    mic = { ctx: ctx, stream: stream, proc: proc };
    vad = null;
    $('start').classList.add('hidden');
    $('pauze').disabled = false;
    $('stop').disabled = false;
    zetLuister('aan', 'Luistert');
    status('luistert');
    try { if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { /* ignore */ }
  }

  function stopMic() {
    if (!mic) return;
    try { mic.proc.disconnect(); } catch (e) { /* ignore */ }
    mic.stream.getTracks().forEach(function (t) { t.stop(); });
    mic.ctx.close().catch(function () {});
    mic = null;
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  function stuur(frames, rate) {
    var pcm = naar16k(frames, rate);
    var blob = new Blob([SVTolk.wav(pcm.samples, pcm.rate)], { type: 'audio/wav' });
    zetLuister('aan', 'Vertalen…');
    status('verwerkt');
    var eerder = SVTolk.eerder(beurten);
    bezig = bezig.then(async function () {
      try {
        var fd = new FormData();
        fd.append('audio', blob, 'beurt.wav');
        fd.append('spreker', 'auto');
        fd.append('eerder', JSON.stringify(eerder));
        var resp = await api('/api/v1/telefoon/beurt', { method: 'POST', body: fd });
        if (!resp.ok) throw await fout(resp);
        var b = await resp.json();
        if (b.leeg) { melding('Niet verstaan. Zeg het nog eens.'); zetLuister('aan', 'Luistert'); status('luistert'); return; }
        melding(b.onzeker ? '⚠ Misschien niet goed verstaan: vraag het na.' : '');
        beurten.push(b);
        laatste = b;
        toonTekst(b);
        var wat = SVTolk.voorlezen(b, taal.code);
        if (b.spreker === 'arts' || $('nl-voorlezen').checked) await zeg(wat.tekst, wat.taal);
        else { zetLuister('aan', 'Luistert'); status('luistert'); }
      } catch (e) {
        if (actief) { melding(e.message, true); zetLuister('aan', 'Luistert'); }
      }
    });
  }

  // ── Photo ──
  function verklein(bestand) {
    return new Promise(function (klaar) {
      var url = URL.createObjectURL(bestand);
      var img = new Image();
      img.onload = function () {
        var max = 1800, s = Math.min(1, max / Math.max(img.width, img.height));
        var c = document.createElement('canvas');
        c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob(function (b) { klaar(b || bestand); }, 'image/jpeg', 0.85);
      };
      img.onerror = function () { URL.revokeObjectURL(url); klaar(bestand); };
      img.src = url;
    });
  }

  async function stuurFoto(bestand) {
    var uit = taal ? $('melding') : $('klaar-foto');
    uit.textContent = 'Foto versturen…';
    try {
      var fd = new FormData();
      fd.append('foto', await verklein(bestand), 'foto.jpg');
      var resp = await api('/api/v1/telefoon/foto', { method: 'POST', body: fd });
      if (!resp.ok) throw await fout(resp);
      uit.textContent = 'Foto staat in het zijpaneel.';
    } catch (e) {
      uit.textContent = e.message;
    }
  }

  // ── Wiring ──
  $('start').addEventListener('click', start);
  $('pauze').addEventListener('click', function () {
    pauze = !pauze;
    this.textContent = pauze ? 'Verder' : 'Pauze';
    this.classList.toggle('hoofd', pauze);
    vad = null;
    zetLuister(pauze ? '' : 'aan', pauze ? 'Pauze' : 'Luistert');
    status(pauze ? 'pauze' : 'luistert');
  });
  $('herhaal').addEventListener('click', function () {
    if (!laatste) return;
    var wat = SVTolk.voorlezen(laatste, taal.code);
    zeg(wat.tekst, wat.taal);
  });
  $('stop').addEventListener('click', function () {
    stopMic();
    pauze = false;
    $('pauze').textContent = 'Pauze';
    $('pauze').disabled = true;
    $('stop').disabled = true;
    $('start').classList.remove('hidden');
    $('luister').classList.add('hidden');
    status('gestopt');
  });
  var kiesFoto = function () { $('foto-invoer').click(); };
  $('foto').addEventListener('click', kiesFoto);
  $('foto2').addEventListener('click', kiesFoto);
  $('foto-invoer').addEventListener('change', function () {
    var f = this.files && this.files[0];
    this.value = '';
    if (f) stuurFoto(f);
  });
  // Back from the background (screen locked): the wake lock is gone; ask again.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && mic && navigator.wakeLock && !wakeLock) {
      navigator.wakeLock.request('screen').then(function (w) { wakeLock = w; }).catch(function () {});
    }
  });

  hallo();
})();

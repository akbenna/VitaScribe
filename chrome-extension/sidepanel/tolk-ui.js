/**
 * VitaScribe - Tolk in de spreekkamer (tabblad Tolk)
 *
 * Arts en patiënt spreken om beurten. De arts tikt op "Ik spreek" (spatie)
 * of "Patiënt spreekt" (Enter); de beurt stopt vanzelf na een stilte, of met
 * dezelfde knop. Elke beurt gaat naar /api/v1/tolk/beurt: verstaan in de taal
 * van de spreker en vertalen naar die van de ander. Dan leest VitaScribe de
 * vertaling voor: met de stem van Mistral als de server die heeft, anders met
 * een stem die op deze computer staat (nooit een online stem). Zo hoeft de
 * patiënt niet te lezen en niet op het scherm te kijken.
 *
 * "Maak verslag" maakt uit de Nederlandse kant van het gesprek een SOEP, die
 * in het tabblad Consult verschijnt zoals bij een opgenomen consult.
 *
 * Het gesprek staat alleen in chrome.storage.session (werkgeheugen; weg als
 * de browser sluit) en wordt gewist met "Wissen" of "Consult afsluiten".
 *
 * Gebruikt uit sidepanel.js: getConfig(), openMicrophone(), state.
 */
window.SVTolkUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var talen = [];          // from the server: {code, naam, eigen, verstaat, stem, waarom}
  var nlStem = 'computer';
  var tk = { taal: '', gestart: false, beurten: [] };
  var opname = null;       // {spreker, recorder, stream, ctx, timer, stukken}
  var bezigMet = Promise.resolve();
  var speler = null;       // the Audio element that is playing
  var volgnummer = 0;

  function status(msg, isError) {
    $('tk-status').textContent = msg || '';
    $('tk-status').classList.toggle('error', !!isError);
  }

  function taalInfo(code) {
    return talen.filter(function (t) { return t.code === code; })[0] || null;
  }

  function bewaar() {
    chrome.storage.session.set({ svTolk: { taal: tk.taal, gestart: tk.gestart, beurten: tk.beurten } }).catch(function () {});
  }

  async function aanvraag(pad, opties) {
    var config = await getConfig();
    var headers = Object.assign({}, opties.headers || {});
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp;
    try {
      resp = await fetch(config.apiUrl + pad, Object.assign({}, opties, { headers: headers }));
    } catch (e) {
      throw new Error('Kan de server niet bereiken op ' + config.apiUrl + '.');
    }
    return resp;
  }

  async function fout(resp) {
    var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
    if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join('; ');
    if (resp.status === 401) detail = detail || 'Controleer de API-sleutel in Instellingen.';
    if (resp.status === 404 && !detail) detail = 'Deze server kent de tolk nog niet: de server moet eerst bijgewerkt worden.';
    return new Error(detail || ('Server gaf fout ' + resp.status + '.'));
  }

  // ── Languages (they depend on the mode: EU understands fewer) ──

  async function laadTalen() {
    var sel = $('tk-taal');
    try {
      var resp = await aanvraag('/api/v1/tolk/talen', { method: 'GET' });
      if (!resp.ok) throw await fout(resp);
      var d = await resp.json();
      talen = d.talen || [];
      nlStem = d.nl_stem || 'computer';
    } catch (e) {
      talen = [];
      $('tk-taal-uitleg').textContent = e.message;
      return;
    }
    var gekozen = tk.taal || sel.value;
    sel.textContent = '';
    talen.forEach(function (t) {
      var o = document.createElement('option');
      o.value = t.code;
      o.textContent = t.naam + ' · ' + t.eigen + (t.verstaat ? '' : ' (alleen de arts wordt verstaan)');
      sel.appendChild(o);
    });
    if (gekozen && taalInfo(gekozen)) sel.value = gekozen;
    toonTaal();
    teken();
  }

  function toonTaal() {
    var t = taalInfo($('tk-taal').value);
    if (!t) return;
    var regels = [];
    if (!t.verstaat) regels.push(t.waarom + ' U kunt wel spreken en laten voorlezen; voor antwoorden van de patiënt: Claude-modus of een tolk.');
    regels.push(t.stem === 'mistral' ? 'Voorlezen: stem van Mistral (EU).' : 'Voorlezen: met een stem op deze computer.');
    $('tk-taal-uitleg').textContent = regels.join(' ');
  }

  function toonGesprek() {
    var t = taalInfo(tk.taal) || { naam: tk.taal, eigen: '', verstaat: true };
    $('tk-start').classList.toggle('hidden', tk.gestart);
    $('tk-gesprek').classList.toggle('hidden', !tk.gestart);
    $('tk-kop-taal').textContent = 'Nederlands ⇄ ' + t.naam;
    $('tk-patient-wie').textContent = t.eigen ? t.eigen : 'Patiënt spreekt';
    $('tk-patient-taal').textContent = 'Patiënt · ' + t.naam + ' · Enter';
    $('tk-patient').disabled = !t.verstaat;
    $('tk-patient').title = t.verstaat ? 'Enter' : t.waarom;
    $('tk-verslag').disabled = SVTolk.verslagBeurten(tk.beurten).length === 0;
  }

  // ── Turns on screen ──

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function knop(label, title, fn) {
    var b = el('button', 'btn small', label);
    b.type = 'button';
    b.title = title;
    b.addEventListener('click', fn);
    return b;
  }

  function tekenBeurt(b) {
    var t = taalInfo(tk.taal) || {};
    var kaart = el('div', 'tk-beurt ' + b.spreker + (b.bezig ? ' bezig' : ''));
    kaart.dataset.id = b.id;
    kaart.appendChild(el('span', 'tk-wie', b.spreker === 'arts' ? 'Arts' : 'Patiënt · ' + (t.naam || '')));
    if (b.bezig) {
      kaart.appendChild(el('p', 'tk-orig', b.bezig));
      return kaart;
    }
    var orig = el('p', 'tk-orig', b.origineel);
    orig.dir = 'auto';
    var vert = el('p', 'tk-vert', b.vertaling);
    vert.dir = 'auto';
    kaart.append(orig, vert);
    if (b.terugvertaling) kaart.appendChild(el('p', 'tk-terug', b.terugvertaling));
    if (b.onzeker) kaart.appendChild(el('p', 'tk-twijfel', '⚠ ' + (b.twijfel || 'Mogelijk verkeerd verstaan; controleer.')));
    var acties = el('div', 'tk-acties');
    acties.appendChild(knop('▶ Opnieuw', 'Nog eens voorlezen', function () { leesVoor(b); }));
    if (b.spreker === 'arts') {
      acties.appendChild(knop('Eenvoudiger', 'Nog eenvoudiger zeggen', function () { eenvoudiger(b); }));
    }
    acties.appendChild(knop('✕', 'Verkeerd verstaan: deze beurt weghalen (gaat niet mee in het verslag)', function () {
      tk.beurten = tk.beurten.filter(function (x) { return x.id !== b.id; });
      bewaar();
      teken();
    }));
    kaart.appendChild(acties);
    return kaart;
  }

  function teken() {
    var lijst = $('tk-beurten');
    lijst.textContent = '';
    // Newest on top: the doctor looks at what was just said.
    tk.beurten.slice().reverse().forEach(function (b) { lijst.appendChild(tekenBeurt(b)); });
    toonGesprek();
  }

  // ── Reading aloud ──

  function stopVoorlezen() {
    if (speler) { try { speler.pause(); } catch (e) { /* ignore */ } speler = null; }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  async function serverStem(tekst, taal) {
    var resp = await aanvraag('/api/v1/tolk/spreek', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tekst: tekst, taal: taal }),
    });
    if (!resp.ok) return null;
    return resp.blob();
  }

  function speelAf(blob) {
    return new Promise(function (klaar) {
      var url = URL.createObjectURL(blob);
      var a = new Audio(url);
      speler = a;
      var einde = function () { URL.revokeObjectURL(url); if (speler === a) speler = null; klaar(true); };
      a.onended = einde;
      a.onerror = einde;
      a.play().catch(einde);
    });
  }

  function stemmen() {
    return new Promise(function (klaar) {
      var s = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
      if (s.length || !window.speechSynthesis) return klaar(s);
      window.speechSynthesis.onvoiceschanged = function () { klaar(window.speechSynthesis.getVoices()); };
      setTimeout(function () { klaar(window.speechSynthesis.getVoices()); }, 800);
    });
  }

  async function computerStem(tekst, taal) {
    var stem = SVTolk.kiesStem(await stemmen(), taal);
    if (!stem) return false;
    return new Promise(function (klaar) {
      var u = new SpeechSynthesisUtterance(tekst);
      u.voice = stem;
      u.lang = stem.lang;
      u.rate = 0.92;   // a little slower: a second language, often older patients
      u.onend = function () { klaar(true); };
      u.onerror = function () { klaar(true); };
      window.speechSynthesis.speak(u);
    });
  }

  async function leesVoor(b) {
    if (!b || !b.vertaling) return;
    var wat = SVTolk.voorlezen(b, tk.taal);
    stopVoorlezen();
    var info = wat.taal === 'nl' ? { stem: nlStem, naam: 'Nederlands' } : (taalInfo(wat.taal) || {});
    if (info.stem === 'mistral') {
      var blob = await serverStem(wat.tekst, wat.taal).catch(function () { return null; });
      if (blob && blob.size) { await speelAf(blob); return; }
    }
    var gelukt = await computerStem(wat.tekst, wat.taal);
    if (!gelukt) {
      status(SVTolk.stemHint(info.naam || wat.taal), true);
      if (b.spreker === 'arts') toonGroot(wat.tekst, wat.taal);
    }
  }

  // ── Recording a turn ──

  function knopVan(spreker) { return $(spreker === 'arts' ? 'tk-arts' : 'tk-patient'); }

  async function startBeurt(spreker) {
    if (opname) {
      var vorige = opname.spreker;
      stopBeurt();
      if (vorige === spreker) return;
    }
    if (spreker === 'patient' && $('tk-patient').disabled) return;
    if (window.SVConsultUI && window.SVConsultUI.bezig()) { status('Er loopt een consultopname; stop die eerst.', true); return; }
    if (typeof state !== 'undefined' && state !== 'idle') { status('Stop eerst het dicteren.', true); return; }
    stopVoorlezen();
    var config = await getConfig();
    var stream;
    try {
      stream = await openMicrophone(config.micDevice);   // sidepanel.js; echo cancellation on
    } catch (e) {
      status(e.message, true);
      return;
    }
    var stukken = [];
    var type = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    var recorder = new MediaRecorder(stream, { mimeType: type });
    recorder.ondataavailable = function (e) { if (e.data && e.data.size) stukken.push(e.data); };
    var ctx = new AudioContext();
    var analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    var buf = new Float32Array(analyser.fftSize);
    var st = null;
    var auto = $('tk-auto').checked;
    var timer = setInterval(function () {
      analyser.getFloatTimeDomainData(buf);
      var som = 0;
      for (var i = 0; i < buf.length; i++) som += buf[i] * buf[i];
      var stap = SVTolk.stilteStap(st, Math.sqrt(som / buf.length), Date.now(), { auto: auto });
      st = stap.st;
      if (stap.stop) stopBeurt();
    }, 50);
    recorder.onstop = function () {
      clearInterval(timer);
      stream.getTracks().forEach(function (t) { t.stop(); });
      ctx.close().catch(function () {});
      var blob = new Blob(stukken, { type: 'audio/webm' });
      var gesproken = st && st.spraak >= 200;
      if (!gesproken) { status('Niets gehoord. Tik opnieuw en spreek.', true); return; }
      verwerk(spreker, blob);
    };
    recorder.start(250);
    opname = { spreker: spreker, recorder: recorder };
    knopVan(spreker).classList.add('luistert');
    knopVan(spreker).querySelector('.tk-knop-wie').dataset.oud = knopVan(spreker).querySelector('.tk-knop-wie').textContent;
    knopVan(spreker).querySelector('.tk-knop-wie').textContent = 'Luistert…';
    status(auto ? 'Spreek; de beurt stopt vanzelf na een korte stilte.' : 'Spreek; tik nog eens om te stoppen.');
  }

  function stopBeurt() {
    if (!opname) return;
    var o = opname;
    opname = null;
    var k = knopVan(o.spreker);
    k.classList.remove('luistert');
    var wie = k.querySelector('.tk-knop-wie');
    if (wie.dataset.oud) wie.textContent = wie.dataset.oud;
    if (o.recorder.state !== 'inactive') o.recorder.stop();
  }

  // One turn after the other, so the context and the reading aloud keep their order.
  function verwerk(spreker, blob) {
    var b = { id: 'b' + (++volgnummer) + '-' + Date.now(), spreker: spreker, bezig: 'Vertalen…' };
    tk.beurten.push(b);
    teken();
    status('');
    var eerder = SVTolk.eerder(tk.beurten.filter(function (x) { return x !== b; }));
    bezigMet = bezigMet.then(async function () {
      try {
        var fd = new FormData();
        fd.append('audio', blob, 'beurt.webm');
        fd.append('spreker', spreker);
        fd.append('taal', tk.taal);
        fd.append('consent', 'true');
        fd.append('eerder', JSON.stringify(eerder));
        var resp = await aanvraag('/api/v1/tolk/beurt', { method: 'POST', body: fd });
        if (!resp.ok) throw await fout(resp);
        var d = await resp.json();
        delete b.bezig;
        if (d.leeg) {
          tk.beurten = tk.beurten.filter(function (x) { return x !== b; });
          status('Niets verstaan. Probeer het nog eens, iets dichter bij de microfoon.', true);
          teken();
          return;
        }
        Object.assign(b, { origineel: d.origineel, vertaling: d.vertaling, terugvertaling: d.terugvertaling || '',
          onzeker: !!d.onzeker, twijfel: d.twijfel || '' });
        bewaar();
        teken();
        if (spreker === 'arts' || $('tk-nl-voorlezen').checked) await leesVoor(b);
      } catch (e) {
        tk.beurten = tk.beurten.filter(function (x) { return x !== b; });
        teken();
        status(e.message, true);
      }
    });
  }

  async function eenvoudiger(b) {
    status('Eenvoudiger zeggen…');
    try {
      var fd = new FormData();
      fd.append('tekst', b.origineel);
      fd.append('spreker', b.spreker);
      fd.append('taal', tk.taal);
      fd.append('consent', 'true');
      fd.append('eenvoudiger', 'true');
      fd.append('eerder', JSON.stringify(SVTolk.eerder(tk.beurten.filter(function (x) { return x !== b; }))));
      var resp = await aanvraag('/api/v1/tolk/beurt', { method: 'POST', body: fd });
      if (!resp.ok) throw await fout(resp);
      var d = await resp.json();
      Object.assign(b, { vertaling: d.vertaling, terugvertaling: d.terugvertaling || '', onzeker: !!d.onzeker, twijfel: d.twijfel || '' });
      bewaar();
      teken();
      status('');
      await leesVoor(b);
    } catch (e) {
      status(e.message, true);
    }
  }

  // ── Large text for the patient ──

  function toonGroot(tekst, taal) {
    $('tk-scherm-tekst').textContent = tekst;
    $('tk-scherm-tekst').dir = SVTolk.rtl(taal) ? 'rtl' : 'auto';
    $('tk-scherm-tekst').lang = SVTolk.spraakTag(taal);
    $('tk-scherm').classList.remove('hidden');
  }

  // ── The report ──

  async function maakVerslag() {
    var beurten = SVTolk.verslagBeurten(tk.beurten);
    if (!beurten.length) return;
    var start = await chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: 'tolk', fase: 'bezig' }).catch(function () { return null; });
    if (!start || !start.ok) { status((start && start.message) || 'Het verslag kon niet starten.', true); return; }
    if (window.SVViews) window.SVViews.show('dictate');
    var bericht;
    try {
      var resp = await aanvraag('/api/v1/tolk/verslag', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ taal: tk.taal, consent: true, beurten: beurten }),
      });
      if (!resp.ok) throw await fout(resp);
      bericht = { fase: 'klaar', data: await resp.json() };
    } catch (e) {
      bericht = { fase: 'fout', message: e.message };
    }
    await chrome.runtime.sendMessage(Object.assign({ action: 'SV_CONSULT_CMD', cmd: 'tolk' }, bericht)).catch(function () {});
  }

  function wis() {
    stopBeurt();
    stopVoorlezen();
    tk = { taal: tk.taal, gestart: false, beurten: [] };
    chrome.storage.session.remove('svTolk').catch(function () {});
    status('');
    teken();
  }

  // ── Wiring ──

  $('tk-taal').addEventListener('change', toonTaal);
  $('tk-begin').addEventListener('click', function () {
    if (!taalInfo($('tk-taal').value)) { $('tk-taal-uitleg').textContent = 'Kies eerst een taal.'; return; }
    tk = { taal: $('tk-taal').value, gestart: true, beurten: [] };
    bewaar();
    teken();
    status('Tik op "Ik spreek" (spatie) of op de knop van de patiënt (Enter).');
  });
  // Blur after a click, so a later space or Enter does not press the button a second time.
  $('tk-arts').addEventListener('click', function () { this.blur(); startBeurt('arts'); });
  $('tk-patient').addEventListener('click', function () { this.blur(); startBeurt('patient'); });
  $('tk-verslag').addEventListener('click', maakVerslag);
  $('tk-stop').addEventListener('click', function () {
    if (!tk.beurten.length || window.confirm('Dit tolkgesprek wissen?')) wis();
  });
  $('tk-groot').addEventListener('click', function () {
    var laatste = tk.beurten.filter(function (b) { return b.spreker === 'arts' && b.vertaling; }).pop();
    if (laatste) toonGroot(laatste.vertaling, tk.taal);
    else status('Er is nog geen vertaling voor de patiënt.', true);
  });
  $('tk-scherm-dicht').addEventListener('click', function () { $('tk-scherm').classList.add('hidden'); });

  // Space and Enter, only in the Tolk view and not while typing somewhere.
  document.addEventListener('keydown', function (e) {
    if ($('view-tolk').classList.contains('hidden') || !tk.gestart || e.repeat) return;
    var doel = e.target;
    if (doel && (doel.tagName === 'TEXTAREA' || doel.tagName === 'INPUT' || doel.tagName === 'SELECT' || doel.isContentEditable)) return;
    if (e.key === 'Escape' && !$('tk-scherm').classList.contains('hidden')) { $('tk-scherm').classList.add('hidden'); return; }
    if (e.code === 'Space' || e.key === ' ') { e.preventDefault(); startBeurt('arts'); }
    else if (e.key === 'Enter') { e.preventDefault(); startBeurt('patient'); }
  });

  document.addEventListener('sv-view', function (e) {
    if (e.detail === 'tolk') laadTalen();
    else stopBeurt();
  });
  if (typeof SVModus !== 'undefined' && SVModus.bijWijziging) SVModus.bijWijziging(function () { laadTalen(); });

  chrome.storage.session.get('svTolk').then(function (r) {
    if (r && r.svTolk) {
      tk = r.svTolk;
      tk.beurten = (tk.beurten || []).filter(function (b) { return !b.bezig; });
    }
    teken();
    if (!$('view-tolk').classList.contains('hidden')) laadTalen();
  }).catch(function () { teken(); });

  return { wis: wis };
})();

/*
 * VitaScribe spraaktest: dezelfde opname door Deepgram en Voxtral.
 *
 * Gebruikt de beheersessie van /beheer (sessionStorage van dit tabblad). Alle
 * tekst uit de transcripten gaat als tekst de pagina in, nooit als HTML.
 */
(function () {
  'use strict';

  var OPSLAG = 'vs-beheersessie';
  var $ = function (id) { return document.getElementById(id); };
  var opname = null;      // { blob, naam }
  var recorder = null, stukken = [], startTijd = 0, timer = null;
  var laatste = null;     // the last comparison, for "Maak SOEP van beide"

  function sessie() { try { return sessionStorage.getItem(OPSLAG) || ''; } catch (e) { return ''; } }
  function status(t, fout) { $('status').textContent = t || ''; $('status').className = 'status klein' + (fout ? ' fout' : ''); }
  function el(tag, cls, tekst) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (tekst !== undefined) n.textContent = tekst;
    return n;
  }
  function klaar() { $('vergelijk').disabled = !opname; }

  if (!sessie()) status('Log eerst in op de beheerpagina in dit tabblad, en kom dan terug via "Spraaktest".', true);

  // ── Opnemen in de browser: microfoon, of geluid van een tabblad/de pc ──
  var bronnen = [];       // every captured track and audio context, stopped together
  function stopBronnen() {
    bronnen.forEach(function (b) { try { b.stop ? b.stop() : b.close(); } catch (e) { /* already stopped */ } });
    bronnen = [];
  }

  async function microfoon() {
    var s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach(function (t) { bronnen.push(t); });
    return s;
  }

  async function tabGeluid() {
    // Chrome/Edge only share audio together with a picture; the picture is dropped.
    var scherm = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      systemAudio: 'include', selfBrowserSurface: 'exclude'
    });
    scherm.getTracks().forEach(function (t) { bronnen.push(t); });
    scherm.getVideoTracks().forEach(function (t) { t.stop(); });
    var geluid = scherm.getAudioTracks();
    if (!geluid.length) {
      stopBronnen();
      throw new Error('Er werd geen geluid gedeeld. Kies een tabblad (of het hele scherm, op Windows) en zet "Geluid delen" aan.');
    }
    // The "Stop sharing" bar of the browser also ends the recording.
    geluid[0].addEventListener('ended', function () { if (recorder && recorder.state === 'recording') recorder.stop(); });
    if (!$('ookmic').checked) return new MediaStream(geluid);
    // Mix in the microphone, e.g. for a video consult: patient from the tab, doctor from the mic.
    var mic = await microfoon();
    var ctx = new AudioContext();
    bronnen.push(ctx);
    var mix = ctx.createMediaStreamDestination();
    ctx.createMediaStreamSource(new MediaStream(geluid)).connect(mix);
    ctx.createMediaStreamSource(mic).connect(mix);
    return mix.stream;
  }

  async function neemOp(knop, maakStroom) {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    var tekst = knop.textContent;
    try {
      var stream = await maakStroom();
      stukken = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (e) { if (e.data.size) stukken.push(e.data); };
      recorder.onstop = function () {
        stopBronnen();
        clearInterval(timer);
        opname = { blob: new Blob(stukken, { type: 'audio/webm' }), naam: 'opname.webm' };
        knop.textContent = tekst;
        $('opnemen').disabled = $('tabopname').disabled = false;
        status('Opname klaar (' + $('klok').textContent + '). Klik op Vergelijk.');
        klaar();
      };
      recorder.start(1000);
      startTijd = Date.now();
      knop.textContent = '■ Stop';
      (knop === $('opnemen') ? $('tabopname') : $('opnemen')).disabled = true;
      timer = setInterval(function () {
        var s = Math.round((Date.now() - startTijd) / 1000);
        $('klok').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
      }, 500);
      status('Bezig met opnemen…');
    } catch (e) {
      stopBronnen();
      if (e && e.name === 'NotAllowedError') status('Opnemen geannuleerd of niet toegestaan.', true);
      else status('Opnemen kon niet starten: ' + (e && e.message || e), true);
    }
  }

  $('opnemen').addEventListener('click', function () { neemOp(this, microfoon); });
  $('tabopname').addEventListener('click', function () { neemOp(this, tabGeluid); });
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) $('tabopname').disabled = true;

  $('bestand').addEventListener('change', function () {
    var f = this.files[0];
    if (f) { opname = { blob: f, naam: f.name }; status('Bestand gekozen: ' + f.name + '.'); }
    klaar();
  });

  // ── Vergelijken ──
  async function vergelijk(blob, naam) {
    var form = new FormData();
    form.append('audio', blob, naam);
    form.append('taal', $('taal').value);
    var r = await fetch('/api/v1/beheer/spraaktest', { method: 'POST', headers: { 'X-Beheer-Sessie': sessie() }, body: form });
    var body = await r.json().catch(function () { return {}; });
    if (r.status === 401 || r.status === 403) throw new Error('Niet ingelogd. Log in op /beheer in dit tabblad.');
    if (!r.ok) throw new Error(body.detail || ('Fout ' + r.status));
    return body;
  }

  $('vergelijk').addEventListener('click', async function () {
    if (!opname) return;
    var knop = this;
    knop.disabled = true;
    status('Bezig: beide diensten verwerken de opname tegelijk…');
    $('uitkomst').textContent = '';
    try {
      laatste = await vergelijk(opname.blob, opname.naam);
      toon(laatste);
      status('Klaar.');
    } catch (e) {
      status(e.message, true);
    } finally {
      knop.disabled = false;
    }
  });

  function dollar(paar) { return '$' + paar[0].toFixed(3) + (paar[1] !== paar[0] ? '–' + paar[1].toFixed(3) : ''); }

  function kolom(titel, d, alleen) {
    var k = el('div', 'kaart');
    k.appendChild(el('h3', '', titel));
    if (d.fout) {
      k.appendChild(el('p', 'fout', 'Mislukt na ' + d.seconden + ' s: ' + d.fout));
      return k;
    }
    var t = el('table');
    [['Verwerkingstijd', d.seconden + ' s'],
     ['Duur opname', d.duur_audio + ' s'],
     ['Sprekers herkend', String(d.sprekers)],
     ['Uitingen', String(d.uitingen)],
     ['Woorden', String(d.woorden)],
     ['Kosten deze opname', dollar(d.kosten_dollar)],
     ['Per consult van 10 min', dollar(d.per_consult_10_min_dollar)]].forEach(function (rij) {
      var tr = el('tr'); tr.appendChild(el('td', '', rij[0])); tr.appendChild(el('td', '', rij[1])); t.appendChild(tr);
    });
    k.appendChild(t);
    var termen = el('p', 'klein', 'Vaktermen herkend: ');
    (d.vaktermen || []).forEach(function (w) { termen.appendChild(el('span', 'term', w)); });
    if (!(d.vaktermen || []).length) termen.appendChild(document.createTextNode('geen'));
    k.appendChild(termen);
    k.appendChild(el('p', 'klein', 'Transcript met sprekers:'));
    k.appendChild(el('pre', '', d.met_sprekers || d.tekst || '(leeg)'));
    return k;
  }

  function toon(b) {
    var u = $('uitkomst');
    u.textContent = '';
    var samen = el('div', 'kaart');
    samen.appendChild(el('h2', '', 'Uitkomst'));
    samen.appendChild(el('p', '', b.overeenkomst === null ? 'Een van beide diensten gaf geen tekst.'
      : 'De twee transcripten komen voor ' + b.overeenkomst + '% overeen (woorden in dezelfde volgorde). Lees de verschillen: welke dienst verstond het gesprek beter?'));
    function verschil(label, lijst) {
      var p = el('p', 'klein', label);
      if (!lijst.length) p.appendChild(document.createTextNode('geen'));
      lijst.forEach(function (w) { p.appendChild(el('span', 'term mist', w)); });
      return p;
    }
    samen.appendChild(verschil('Vaktermen alleen door Deepgram herkend: ', b.alleen_deepgram || []));
    samen.appendChild(verschil('Vaktermen alleen door Voxtral herkend: ', b.alleen_voxtral || []));
    u.appendChild(samen);
    var naast = el('div', 'naast');
    naast.appendChild(kolom('Deepgram (VS, EU-endpoint)', b.deepgram, b.alleen_deepgram || []));
    naast.appendChild(kolom('Voxtral (Mistral, Frankrijk)', b.voxtral, b.alleen_voxtral || []));
    u.appendChild(naast);
    if (b.deepgram.met_sprekers || b.voxtral.met_sprekers) u.appendChild(soepKaart());
  }

  // ── SOEP van beide transcripten ──
  function soepKaart() {
    var k = el('div', 'kaart');
    k.id = 'soep';
    k.appendChild(el('h2', '', 'SOEP van beide transcripten'));
    k.appendChild(el('p', 'klein', 'Hetzelfde taalmodel en dezelfde woordenlijst als bij een echt consult. ' +
      'Blind beoordelen: je ziet "Verslag A" en "Verslag B" in willekeurige volgorde, en pas na je oordeel welke dienst welke is.'));
    var rij = el('div', 'rij');
    var label = el('label', 'klein');
    var blind = el('input'); blind.type = 'checkbox'; blind.checked = true; blind.id = 'blind';
    label.appendChild(blind); label.appendChild(document.createTextNode(' Blind beoordelen'));
    var knop = el('button', 'hoofd', 'Maak SOEP van beide');
    rij.appendChild(knop); rij.appendChild(label);
    k.appendChild(rij);
    var stat = el('p', 'status klein');
    var uit = el('div');
    k.appendChild(stat); k.appendChild(uit);
    knop.addEventListener('click', async function () {
      knop.disabled = true;
      uit.textContent = '';
      stat.className = 'status klein';
      stat.textContent = 'Bezig: het taalmodel schrijft twee verslagen (ongeveer een halve minuut)…';
      try {
        var r = await fetch('/api/v1/beheer/spraaktest/soep', {
          method: 'POST',
          headers: { 'X-Beheer-Sessie': sessie(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ deepgram: laatste.deepgram.met_sprekers || '', voxtral: laatste.voxtral.met_sprekers || '',
                                 taal: $('taal').value })
        });
        var body = await r.json().catch(function () { return {}; });
        if (r.status === 401 || r.status === 403) throw new Error('Niet ingelogd. Log in op /beheer in dit tabblad.');
        if (!r.ok) throw new Error(body.detail || ('Fout ' + r.status));
        toonSoep(uit, body, blind.checked);
        stat.textContent = 'Klaar. Taalmodel: ' + body.taalmodel + '.';
      } catch (e) {
        stat.className = 'status klein fout';
        stat.textContent = e.message;
      } finally {
        knop.disabled = false;
      }
    });
    return k;
  }

  function soepKolom(titel, d) {
    var k = el('div', 'kaart');
    var kop = el('h3', '', titel);
    k.appendChild(kop);
    if (d.fout) { k.appendChild(el('p', 'fout', 'Mislukt: ' + d.fout)); return { kaart: k, kop: kop }; }
    (d.problemen || []).forEach(function (p, i) {
      if ((d.problemen || []).length > 1) k.appendChild(el('p', 'klein', 'Probleem ' + (i + 1)));
      var t = el('table');
      [['S', p.s], ['O', p.o], ['E', p.e], ['P', p.p],
       ['ICPC', [p.icpc_code, p.icpc_titel].filter(Boolean).join(' ')]].forEach(function (rij) {
        var tr = el('tr'); tr.appendChild(el('td', '', rij[0])); tr.appendChild(el('td', 'soep', rij[1] || '—')); t.appendChild(tr);
      });
      k.appendChild(t);
    });
    k.appendChild(el('p', 'klein', 'Gemaakt in ' + d.seconden + ' s'));
    return { kaart: k, kop: kop };
  }

  function toonSoep(uit, b, blind) {
    var paren = [['Deepgram', b.deepgram], ['Voxtral', b.voxtral]];
    if (blind && Math.random() < 0.5) paren.reverse();
    var naast = el('div', 'naast');
    var koppen = paren.map(function (paar, i) {
      var titel = blind ? 'Verslag ' + 'AB'[i] : paar[0];
      var kol = soepKolom(titel, paar[1]);
      naast.appendChild(kol.kaart);
      return kol.kop;
    });
    uit.appendChild(naast);
    if (blind) {
      var onthul = el('button', '', 'Onthul welke dienst welke is');
      onthul.addEventListener('click', function () {
        koppen.forEach(function (kop, i) { kop.textContent = 'Verslag ' + 'AB'[i] + ': ' + paren[i][0]; });
        onthul.remove();
      });
      uit.appendChild(onthul);
    }
  }
  // ── Afspeellijst: elk filmpje een eigen opname en vergelijking ──
  // The page talks to the cookieless YouTube player with messages only (the
  // same messages YouTube's own iframe API uses); no YouTube script runs here.
  var YT = 'https://www.youtube-nocookie.com';
  var MIN_SEC = window.VS_MIN_SEC || 20;   // shorter pieces (an ad, a skipped video) are dropped
  var lijst = { stream: null, huidig: null, videoId: '', nummer: 0 };
  // The player only sends what changed, so remember what it told us.
  var yt = { staat: null, id: '', titel: '', index: null, lengte: null, gehoord: false, roep: null };

  function ytIds(tekst) {
    var lijstId = (tekst.match(/[?&]list=([\w-]+)/) || [])[1];
    var videos = [];
    tekst.split(/\s+/).forEach(function (t) {
      var m = t.match(/(?:v=|youtu\.be\/|\/embed\/|\/shorts\/)([\w-]{11})/);
      if (m && videos.indexOf(m[1]) < 0) videos.push(m[1]);
    });
    return { lijst: lijstId, videos: videos };
  }

  function ytBron(ids) {
    var p = 'enablejsapi=1&rel=0&playsinline=1&origin=' + encodeURIComponent(location.origin);
    if (ids.lijst) return YT + '/embed/videoseries?list=' + ids.lijst + '&' + p;
    return YT + '/embed/' + ids.videos[0] + '?' + p +
      (ids.videos.length > 1 ? '&playlist=' + ids.videos.slice(1).join(',') : '');
  }

  function naarSpeler(bericht) {
    var f = $('speler').querySelector('iframe');
    if (f && f.contentWindow) f.contentWindow.postMessage(JSON.stringify(Object.assign({ id: 'vs', channel: 'widget' }, bericht)), YT);
  }

  function lijstStatus(t, fout) { $('lijststatus').textContent = t; $('lijststatus').className = 'status klein' + (fout ? ' fout' : ''); }

  function nieuwDeel(titel, videoId) {
    sluitDeel();
    lijst.nummer += 1;
    var deel = { nummer: lijst.nummer, titel: titel || ('Filmpje ' + lijst.nummer), videoId: videoId || '',
                 start: Date.now(), stukken: [] };
    var rec = new MediaRecorder(lijst.stream);
    rec.ondataavailable = function (e) { if (e.data.size) deel.stukken.push(e.data); };
    rec.onstop = function () {
      deel.sec = Math.round((Date.now() - deel.start) / 1000);
      if (deel.sec < MIN_SEC) return;
      deel.blob = new Blob(deel.stukken, { type: 'audio/webm' });
      deel.stukken = null;
      wachtrij(deel);
    };
    rec.start(1000);
    deel.rec = rec;
    lijst.huidig = deel;
    lijst.videoId = deel.videoId;
    lijstStatus('Neemt op: ' + deel.titel);
  }

  function sluitDeel() {
    var deel = lijst.huidig;
    if (deel && deel.rec.state === 'recording') deel.rec.stop();
    lijst.huidig = null;
  }

  // Messages from the player: a new video playing means a new recording.
  window.addEventListener('message', function (e) {
    if (e.origin !== YT || !lijst.stream) return;
    var d; try { d = JSON.parse(e.data); } catch (x) { return; }
    if (!d || !d.event) return;
    if (!yt.gehoord) { yt.gehoord = true; clearInterval(yt.roep); }
    var info = d.info;
    if (info && typeof info === 'object') {
      var v = info.videoData;
      if (v && v.video_id) {
        yt.id = v.video_id;
        yt.titel = v.title || '';
        var deel = lijst.huidig;
        if (deel && deel.videoId === yt.id && v.title) { deel.titel = v.title; lijstStatus('Neemt op: ' + v.title); }
      }
      if (typeof info.playlistIndex === 'number') yt.index = info.playlistIndex;
      if (Array.isArray(info.playlist)) yt.lengte = info.playlist.length;
    }
    var staat = d.event === 'onStateChange' ? info : (info && info.playerState);
    if (typeof staat === 'number') yt.staat = staat;
    // State and video can come in either order; start once both say "new video playing".
    if (yt.staat === 1 && yt.id && yt.id !== lijst.videoId) nieuwDeel(yt.titel, yt.id);
    if (staat === 0) {                     // ended: close this one; the next starts by itself
      sluitDeel();
      lijst.videoId = '';
      yt.id = '';                          // wait for the next video's own data
      if (yt.lengte === null || yt.index === null || yt.index >= yt.lengte - 1) stopLijst('De afspeellijst is klaar.');
    }
  });

  async function startLijst() {
    var ids = ytIds($('ytlink').value);
    if (!ids.lijst && !ids.videos.length) { lijstStatus('Plak een link naar een YouTube-afspeellijst of naar filmpjes.', true); return; }
    try {
      // Record this tab: the player plays here. Chrome asks; choose "Dit tabblad".
      var scherm = await navigator.mediaDevices.getDisplayMedia({
        video: true, audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        preferCurrentTab: true, selfBrowserSurface: 'include'
      });
      scherm.getVideoTracks().forEach(function (t) { t.stop(); });
      var geluid = scherm.getAudioTracks();
      if (!geluid.length) { scherm.getTracks().forEach(function (t) { t.stop(); }); throw new Error('Er werd geen geluid gedeeld. Kies "Dit tabblad" en zet "Geluid delen" aan.'); }
      geluid[0].addEventListener('ended', function () { stopLijst('Delen gestopt.'); });
      lijst.stream = new MediaStream(geluid);
    } catch (e) {
      lijstStatus(e.name === 'NotAllowedError' ? 'Delen geannuleerd.' : e.message, true);
      return;
    }
    lijst.nummer = 0; lijst.videoId = '';
    yt = { staat: null, id: '', titel: '', index: null, lengte: null, gehoord: false, roep: null };
    var f = document.createElement('iframe');
    f.src = ytBron(ids);
    f.allow = 'autoplay; encrypted-media';
    f.title = 'YouTube';
    f.addEventListener('load', function () {
      // Ask the player to report its state until it answers, then start playing.
      yt.gehoord = false;
      clearInterval(yt.roep);
      var keer = 0;
      yt.roep = setInterval(function () {
        if (++keer > 40) { clearInterval(yt.roep); lijstStatus('De speler antwoordt niet. Speel af en knip met "Volgend filmpje".', true); return; }
        naarSpeler({ event: 'listening' });
      }, 250);
      naarSpeler({ event: 'listening' });
      setTimeout(function () {
        naarSpeler({ event: 'command', func: 'addEventListener', args: ['onStateChange'] });
        naarSpeler({ event: 'command', func: 'playVideo', args: [] });
      }, 600);
    });
    $('speler').textContent = '';
    $('speler').appendChild(f);
    $('lijststart').disabled = true;
    $('lijstknip').disabled = $('lijststop').disabled = false;
    lijstStatus('Speler geladen. Komt het filmpje niet vanzelf op gang, klik dan in de speler op afspelen.');
  }

  function stopLijst(reden) {
    if (!lijst.stream) return;
    sluitDeel();
    lijst.stream.getTracks().forEach(function (t) { t.stop(); });
    lijst.stream = null;
    clearInterval(yt.roep);
    naarSpeler({ event: 'command', func: 'pauseVideo', args: [] });
    $('lijststart').disabled = false;
    $('lijstknip').disabled = $('lijststop').disabled = true;
    lijstStatus((reden ? reden + ' ' : '') + 'De laatste filmpjes worden nog vergeleken; zie de tabel.');
  }

  // ── Wachtrij: one comparison at a time, results in a table ──
  var rij = [], rijBezig = false;
  function wachtrij(deel) {
    var tr = el('tr');
    deel.cellen = {};
    [['nr', String(deel.nummer)], ['titel', deel.titel], ['duur', Math.floor(deel.sec / 60) + ':' + String(deel.sec % 60).padStart(2, '0')],
     ['sprekers', '…'], ['overeenkomst', '…'], ['tijd', '…'], ['actie', 'in de wachtrij']].forEach(function (c) {
      var td = el('td', '', c[1]); deel.cellen[c[0]] = td; tr.appendChild(td);
    });
    $('lijsttabel').appendChild(tr);
    $('lijstuitkomst').hidden = false;
    rij.push(deel);
    volgende();
  }

  async function volgende() {
    if (rijBezig || !rij.length) return;
    rijBezig = true;
    var deel = rij.shift();
    deel.cellen.actie.textContent = 'bezig…';
    try {
      var b = await vergelijk(deel.blob, 'filmpje-' + deel.nummer + '.webm');
      var sp = function (x) { return x.fout ? 'fout' : String(x.sprekers); };
      deel.cellen.sprekers.textContent = sp(b.deepgram) + ' / ' + sp(b.voxtral);
      deel.cellen.overeenkomst.textContent = b.overeenkomst === null ? '—' : b.overeenkomst + '%';
      var tijd = function (x) { return x.seconden + ' s'; };
      deel.cellen.tijd.textContent = tijd(b.deepgram) + ' / ' + tijd(b.voxtral);
      deel.cellen.actie.textContent = '';
      var knop = el('button', '', 'Toon');
      knop.addEventListener('click', function () {
        laatste = b;
        toon(b);
        status('Filmpje ' + deel.nummer + ': ' + deel.titel);
        $('uitkomst').scrollIntoView({ behavior: 'smooth' });
      });
      deel.cellen.actie.appendChild(knop);
      deel.blob = null;
    } catch (e) {
      deel.cellen.actie.textContent = 'mislukt: ' + e.message;
      deel.cellen.actie.className = 'fout';
    } finally {
      rijBezig = false;
      volgende();
    }
  }

  $('lijststart').addEventListener('click', startLijst);
  $('lijststop').addEventListener('click', function () { stopLijst('Gestopt.'); });
  $('lijstknip').addEventListener('click', function () {
    // Manual cut, for when the player does not report a new video.
    if (lijst.stream) nieuwDeel('', lijst.videoId);
  });
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) $('lijststart').disabled = true;
})();

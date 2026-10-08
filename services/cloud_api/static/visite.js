/**
 * VitaScribe visite - de telefoonpagina (/v)
 *
 * De toestelsleutel komt uit de QR-code (na '#', dus nooit als adres naar een
 * server) en blijft op dit toestel. Hij kan alleen een visite insturen; lezen
 * kan alleen het zijpaneel in de praktijk.
 *
 * Verloop: Start (met toestemming) -> eventueel Nadicteren -> Stop -> foto's
 * toevoegen -> Versturen.
 *
 * Geen bereik bij de patiënt: de visite gaat eerst versleuteld in een
 * wachtrij op dit toestel (AES-256-GCM, met een sleutel die de browser niet
 * kan exporteren) en wordt verstuurd zodra er weer verbinding is: bij het
 * openen van de pagina, als het toestel weer online komt, en elke minuut.
 * Verstuurd = weg van dit toestel. Wat na 48 uur nog wacht, wordt gewist.
 */
(function () {
  'use strict';

  var SLEUTEL = 'vsVisiteToestel';
  var BEWAAR_MS = 48 * 3600 * 1000;
  var MAX_FOTOS = 6;
  var $ = function (id) { return document.getElementById(id); };
  var token = null;
  var rec = null, stukken = [], start = 0, klok = null, wekslot = null, nadVanaf = null;
  var huidig = null;        // {audio: Blob, naam, aanduiding, nadictaat_vanaf, opgenomen, fotos: [Blob]}
  var bezig = false;

  function lees() { try { return localStorage.getItem(SLEUTEL); } catch (e) { return null; } }
  function bewaar(t) { try { if (t) localStorage.setItem(SLEUTEL, t); else localStorage.removeItem(SLEUTEL); } catch (e) { /* ignore */ } }

  function melding(tekst, soort) {
    $('melding').textContent = tekst || '';
    $('melding').className = 'melding' + (soort ? ' ' + soort : '');
  }

  function scherm(naam) {
    ['geen', 'klaar', 'opname', 'na'].forEach(function (s) { $(s).classList.toggle('hidden', s !== naam); });
    $('ontkoppel').classList.toggle('hidden', naam === 'geen');
  }

  // ── Encrypted queue on this phone (IndexedDB) ──
  function db() {
    return new Promise(function (ok, fout) {
      var r = indexedDB.open('vitascribe-visite-telefoon', 1);
      r.onupgradeneeded = function () {
        r.result.createObjectStore('sleutel');
        r.result.createObjectStore('wachtrij', { keyPath: 'id' });
      };
      r.onsuccess = function () { ok(r.result); };
      r.onerror = function () { fout(r.error); };
    });
  }
  function tx(winkel, modus, werk) {
    return db().then(function (d) {
      return new Promise(function (ok, fout) {
        var t = d.transaction(winkel, modus);
        var uit = werk(t.objectStore(winkel));
        t.oncomplete = function () { ok(uit ? uit.result : undefined); };
        t.onerror = function () { fout(t.error); };
      });
    });
  }
  async function aesSleutel() {
    var k = await tx('sleutel', 'readonly', function (s) { return s.get('aes'); });
    if (k) return k;
    k = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    await tx('sleutel', 'readwrite', function (s) { s.put(k, 'aes'); });
    return k;
  }
  async function dicht(bytes) {
    var iv = crypto.getRandomValues(new Uint8Array(12));
    return { iv: iv, data: await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, await aesSleutel(), bytes) };
  }
  async function open(d) {
    return crypto.subtle.decrypt({ name: 'AES-GCM', iv: d.iv }, await aesSleutel(), d.data);
  }

  async function inWachtrij(v) {
    var meta = { aanduiding: v.aanduiding, nadictaat_vanaf: v.nadictaat_vanaf, opgenomen: v.opgenomen, naam: v.naam,
                 audio_type: v.audio.type, fotos: v.fotos.map(function (f) { return f.type; }) };
    var item = {
      id: 'v' + Date.now() + Math.random().toString(36).slice(2, 8),
      gemaakt: Date.now(),
      meta: await dicht(new TextEncoder().encode(JSON.stringify(meta))),
      audio: await dicht(await v.audio.arrayBuffer()),
      fotos: [],
    };
    for (var i = 0; i < v.fotos.length; i++) item.fotos.push(await dicht(await v.fotos[i].arrayBuffer()));
    await tx('wachtrij', 'readwrite', function (s) { s.put(item); });
    return item.id;
  }

  async function wachtend() {
    var alles = await tx('wachtrij', 'readonly', function (s) { return s.getAll(); });
    return (alles || []).sort(function (a, b) { return a.gemaakt - b.gemaakt; });
  }

  async function uitWachtrij(id) { await tx('wachtrij', 'readwrite', function (s) { s.delete(id); }); }

  async function toonWachtrij() {
    var lijst = await wachtend().catch(function () { return []; });
    $('wacht').classList.toggle('hidden', !lijst.length);
    $('wacht-tekst').textContent = lijst.length === 1 ? '1 visite wacht op bereik' : lijst.length + ' visites wachten op bereik';
  }

  // ── Server ──
  async function post(pad, body) {
    var r = await fetch(pad, { method: 'POST', headers: { 'X-VitaScribe-Visite': token }, body: body });
    var d = await r.json().catch(function () { return {}; });
    if (!r.ok) {
      var e = new Error(typeof d.detail === 'string' ? d.detail : 'Server gaf fout ' + r.status + '.');
      e.status = r.status;
      throw e;
    }
    return d;
  }

  async function stuurItem(item) {
    var meta = JSON.parse(new TextDecoder().decode(await open(item.meta)));
    var fd = new FormData();
    fd.append('audio', new Blob([await open(item.audio)], { type: meta.audio_type }), meta.naam);
    fd.append('toestemming', 'true');
    fd.append('aanduiding', meta.aanduiding || '');
    fd.append('opgenomen', String(meta.opgenomen / 1000));
    if (meta.nadictaat_vanaf != null) fd.append('nadictaat_vanaf', String(meta.nadictaat_vanaf));
    for (var i = 0; i < item.fotos.length; i++) {
      var type = meta.fotos[i] || 'image/jpeg';
      fd.append('fotos', new Blob([await open(item.fotos[i])], { type: type }), 'foto' + (i + 1) + (type === 'image/png' ? '.png' : '.jpg'));
    }
    await post('/api/v1/visite/opname', fd);
  }

  /** Send what waits; true when the queue is empty afterwards. */
  async function verstuurWachtrij(stil) {
    if (bezig || !token) return false;
    bezig = true;
    var fout = null, verstuurd = 0;
    try {
      var lijst = await wachtend();
      for (var i = 0; i < lijst.length; i++) {
        var item = lijst[i];
        if (Date.now() - item.gemaakt > BEWAAR_MS) {     // too old: never kept longer than the server would
          await uitWachtrij(item.id);
          fout = fout || new Error('Een visite die langer dan 48 uur wachtte, is gewist. Dicteer die zelf.');
          continue;
        }
        try {
          await stuurItem(item);
          await uitWachtrij(item.id);
          verstuurd++;
        } catch (e) {
          fout = e;
          if (!e.status || e.status >= 500 || e.status === 429) break;   // no signal or server busy: later
          if (e.status === 401) break;                                   // unpaired: keep, the doctor decides
          await uitWachtrij(item.id);                                    // refused for good (consent, size)
        }
      }
    } finally {
      bezig = false;
      await toonWachtrij();
    }
    var leeg = !(await wachtend()).length;
    if (verstuurd && leeg) melding(verstuurd === 1 ? 'Verstuurd. Het verslag staat zo klaar in het zijpaneel, onder Visites.'
      : verstuurd + ' visites verstuurd. De verslagen staan zo klaar in het zijpaneel.', 'goed');
    else if (fout && !stil) {
      var geenBereik = !fout.status || fout.status >= 500;
      melding(geenBereik ? 'Geen verbinding. De visite staat versleuteld op deze telefoon en wordt vanzelf verstuurd zodra er bereik is.'
        : fout.message, geenBereik ? '' : 'fout');
    }
    return leeg;
  }

  // ── Recording ──
  async function begin() {
    var uitHash = (location.hash || '').replace(/^#/, '');
    if (uitHash) {
      bewaar(uitHash);
      history.replaceState(null, '', location.pathname);   // the key out of the address bar
    }
    token = lees();
    if (!token) { $('pil').textContent = 'niet gekoppeld'; scherm('geen'); await toonWachtrij(); return; }
    scherm('klaar');
    try {
      var d = await post('/api/v1/visite/hallo');
      $('pil').textContent = (d.modus === 'eu' ? 'EU-modus' : 'Claude-modus') + (d.naam ? ' · ' + d.naam : '');
    } catch (e) {
      if (e.status === 401) { $('pil').textContent = 'niet gekoppeld'; scherm('geen'); melding(e.message, 'fout'); }
      else $('pil').textContent = 'geen bereik';
    }
    await toonWachtrij();
    verstuurWachtrij(true);
  }

  function mime() {
    var opties = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac'];
    for (var i = 0; i < opties.length; i++) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(opties[i])) return opties[i];
    }
    return '';
  }

  function klokTekst(ms) {
    var s = Math.floor(ms / 1000);
    return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }

  async function starten() {
    melding('');
    var stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      melding('Geen toegang tot de microfoon. Sta die toe in de instellingen van de browser.', 'fout');
      return;
    }
    var type = mime();
    rec = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    stukken = [];
    nadVanaf = null;
    $('nad-label').textContent = '';
    $('nadicteer').classList.remove('hidden');
    rec.ondataavailable = function (e) { if (e.data && e.data.size) stukken.push(e.data); };
    rec.onstop = function () {
      stream.getTracks().forEach(function (t) { t.stop(); });
      var soort = rec.mimeType || type || 'audio/webm';
      huidig = { audio: new Blob(stukken, { type: soort }), naam: 'visite.' + (/mp4|aac/.test(soort) ? 'm4a' : 'webm'),
                 aanduiding: $('aanduiding').value.trim(), nadictaat_vanaf: nadVanaf, opgenomen: start,
                 duur: Date.now() - start, fotos: [] };
      stukken = [];
      toonNa();
    };
    rec.start(1000);
    start = Date.now();
    var tik = function () { $('klok').textContent = klokTekst(Date.now() - start); };
    tik();
    klok = setInterval(tik, 1000);
    try { wekslot = navigator.wakeLock ? await navigator.wakeLock.request('screen') : null; } catch (e) { wekslot = null; }
    scherm('opname');
  }

  function nadicteren() {
    nadVanaf = Math.round((Date.now() - start) / 100) / 10;
    $('nad-label').textContent = 'Nadicteren sinds ' + klokTekst(nadVanaf * 1000);
    $('nadicteer').classList.add('hidden');
  }

  function stoppen() {
    clearInterval(klok);
    if (wekslot) { wekslot.release().catch(function () {}); wekslot = null; }
    if (rec && rec.state !== 'inactive') rec.stop();
  }

  function toonNa() {
    $('na-titel').textContent = 'Opname klaar · ' + klokTekst(huidig.duur) + (huidig.aanduiding ? ' · ' + huidig.aanduiding : '');
    $('na-sub').textContent = huidig.nadictaat_vanaf != null ? 'Met nadictaat vanaf ' + klokTekst(huidig.nadictaat_vanaf * 1000) + '.' : '';
    var div = $('fotos');
    div.textContent = '';
    huidig.fotos.forEach(function (f) {
      var img = document.createElement('img');
      img.alt = 'Foto bij de visite';
      img.src = URL.createObjectURL(f);
      div.appendChild(img);
    });
    $('foto').disabled = huidig.fotos.length >= MAX_FOTOS;
    scherm('na');
  }

  // A photo smaller (max 2000 px, JPEG): faster over a weak connection; the original if that fails.
  function verklein(bestand) {
    return new Promise(function (ok) {
      var img = new Image();
      var url = URL.createObjectURL(bestand);
      img.onload = function () {
        var schaal = Math.min(1, 2000 / Math.max(img.naturalWidth, img.naturalHeight));
        var c = document.createElement('canvas');
        c.width = Math.round(img.naturalWidth * schaal);
        c.height = Math.round(img.naturalHeight * schaal);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob(function (b) { ok(b || bestand); }, 'image/jpeg', 0.85);
      };
      img.onerror = function () { URL.revokeObjectURL(url); ok(bestand); };
      img.src = url;
    });
  }

  async function verstuur() {
    if (!huidig) return;
    $('verstuur').disabled = true;
    try {
      await inWachtrij(huidig);            // first safe on this phone (encrypted), then off it
    } catch (e) {
      $('verstuur').disabled = false;
      melding('Kon de visite niet veilig op de telefoon zetten: ' + e.message, 'fout');
      return;
    }
    huidig = null;
    $('fotos').textContent = '';
    $('aanduiding').value = '';
    $('toestemming').checked = false;
    $('start').disabled = true;
    $('verstuur').disabled = false;
    scherm('klaar');
    melding('Versturen…');
    await toonWachtrij();
    await verstuurWachtrij(false);
  }

  $('toestemming').addEventListener('change', function () { $('start').disabled = !this.checked; });
  $('start').addEventListener('click', starten);
  $('stop').addEventListener('click', stoppen);
  $('nadicteer').addEventListener('click', nadicteren);
  $('foto').addEventListener('click', function () { $('foto-invoer').click(); });
  $('foto-invoer').addEventListener('change', async function () {
    var f = this.files && this.files[0];
    this.value = '';
    if (!f || !huidig) return;
    huidig.fotos.push(await verklein(f));
    toonNa();
  });
  $('verstuur').addEventListener('click', verstuur);
  $('weggooien').addEventListener('click', function () {
    if (!window.confirm('Deze opname weggooien? Er komt dan geen verslag van deze visite.')) return;
    huidig = null;
    scherm('klaar');
    melding('Opname weggegooid.');
  });
  $('wacht-nu').addEventListener('click', function () { verstuurWachtrij(false); });
  $('ontkoppel').addEventListener('click', async function () {
    var n = (await wachtend().catch(function () { return []; })).length;
    if ((huidig || n) && !window.confirm('Er staat nog een visite die niet verstuurd is; die gaat verloren. Toch ontkoppelen?')) return;
    if (!window.confirm('Deze telefoon ontkoppelen? Je moet daarna opnieuw de QR-code scannen.')) return;
    var lijst = await wachtend().catch(function () { return []; });
    for (var i = 0; i < lijst.length; i++) await uitWachtrij(lijst[i].id);
    bewaar(null);
    token = null;
    huidig = null;
    $('pil').textContent = 'niet gekoppeld';
    scherm('geen');
    melding('');
    toonWachtrij();
  });
  window.addEventListener('online', function () { verstuurWachtrij(true); });
  setInterval(function () { if (!document.hidden) verstuurWachtrij(true); }, 60000);
  window.addEventListener('beforeunload', function (e) {
    if (huidig || (rec && rec.state === 'recording')) { e.preventDefault(); e.returnValue = ''; }
  });
  begin();
})();

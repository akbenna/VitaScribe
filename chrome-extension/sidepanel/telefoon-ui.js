/**
 * VitaScribe - Telefoon of iPad koppelen (zijpaneel)
 *
 * De knop met de telefoon in de kopbalk, of "Tolk via telefoon" in het
 * tabblad Tolk, vraagt de server om een koppeling en toont een QR-code. De
 * telefoon scant die en opent /m op de server (zie services/cloud_api/telefoon.py).
 * Daarna haalt dit paneel berichten van de telefoon op (long-poll):
 *   verbonden  de telefoon is er; de QR gaat dicht
 *   status     luistert / hoort / verwerkt / spreekt / pauze / gestopt
 *   beurt      een tolkbeurt die de telefoon hoorde (tolk-ui.js neemt hem op)
 *   foto       een foto: kopiëren, of in Brieven als schermafdruk uitlezen
 * Het paneel kan de telefoon laten voorlezen (spreek) en ontkoppelen.
 *
 * Alles staat alleen in het geheugen; bij een andere modus of "Consult
 * afsluiten" gaat de koppeling eraf.
 *
 * Uses from sidepanel.js: getConfig()
 */
window.SVTelefoon = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var k = null;              // {geheim, url, taal, verbonden}
  var luisteraars = {};
  var pollNr = 0;

  function on(type, fn) { (luisteraars[type] = luisteraars[type] || []).push(fn); }
  function emit(type, data) { (luisteraars[type] || []).forEach(function (fn) { try { fn(data); } catch (e) { /* ignore */ } }); }

  async function headers(extra) {
    var config = await getConfig();
    var h = Object.assign({}, extra || {});
    if (config.apiKey) h['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(h);
    if (k) h['X-VitaScribe-Koppel'] = k.geheim;
    return { url: config.apiUrl.replace(/\/$/, ''), headers: h };
  }

  async function foutVan(resp) {
    var d = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
    if (resp.status === 404) return new Error('Deze server kent de telefoonkoppeling nog niet: de server moet eerst bijgewerkt worden.');
    return new Error(typeof d === 'string' && d ? d : 'Server gaf fout ' + resp.status + '.');
  }

  function chip() {
    var c = $('tel-chip');
    c.classList.toggle('hidden', !(k && k.verbonden));
    $('btn-telefoon').classList.toggle('aan', !!(k && k.verbonden));
  }

  function qrSvg(url) {
    var qr = qrcode(0, 'M');
    qr.addData(url);
    qr.make();
    return qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
  }

  function toonQr() {
    $('tel-qr').innerHTML = qrSvg(k.url);
    $('tel-doel').textContent = k.taal ? 'Tolk via de telefoon' : 'Telefoon koppelen';
    $('tel-uitleg').textContent = k.taal
      ? 'Scan met de camera van de iPhone of iPad. Tik daar op Start: de telefoon luistert, vertaalt en leest voor met zijn eigen stem. De beurten verschijnen hier.'
      : 'Scan met de camera van de iPhone of iPad. Daarna kun je met de telefoon foto\'s maken die hier binnenkomen.';
    $('tel-status').textContent = 'Wacht op de telefoon…';
    $('tel-dialoog').classList.remove('hidden');
  }

  /** Pair a phone; opts {taal?, toestemming?}. An existing pairing for the same purpose is shown again. */
  async function koppel(opts) {
    opts = opts || {};
    if (k && (k.taal || null) === (opts.taal || null)) { toonQr(); return; }
    if (k) await ontkoppel(true);
    var h = await headers({ 'Content-Type': 'application/json' });
    // http only for a server on this computer (development; a host name without dots, or 127.x).
    var host = new URL(h.url).hostname;
    if (!/^https:/.test(h.url) && /\./.test(host) && !/^127\./.test(host)) {
      throw new Error('De telefoon kan de microfoon alleen gebruiken via https. Stel een https-adres van de server in.');
    }
    var resp;
    try {
      resp = await fetch(h.url + '/api/v1/telefoon/koppel', {
        method: 'POST', headers: h.headers, body: JSON.stringify({ taal: opts.taal || null, toestemming: !!opts.toestemming }),
      });
    } catch (e) { throw new Error('Kan de server niet bereiken.'); }
    if (!resp.ok) throw await foutVan(resp);
    var d = await resp.json();
    k = { geheim: d.geheim, url: h.url + d.pad, taal: opts.taal || null, verbonden: false };
    toonQr();
    peil(++pollNr);
  }

  async function peil(nr) {
    while (k && nr === pollNr) {
      try {
        var h = await headers();
        var resp = await fetch(h.url + '/api/v1/telefoon/paneel/ontvang?wacht=20', { headers: h.headers });
        if (nr !== pollNr) return;
        if (resp.status === 410 || resp.status === 403) { weg('De koppeling met de telefoon is verlopen.'); return; }
        if (!resp.ok) throw new Error(String(resp.status));
        var d = await resp.json();
        (d.berichten || []).forEach(bericht);
      } catch (e) {
        await new Promise(function (r) { setTimeout(r, 3000); });
      }
    }
  }

  function bericht(b) {
    if (b.type === 'verbonden') {
      k.verbonden = true;
      $('tel-dialoog').classList.add('hidden');
      chip();
    } else if (b.type === 'foto') {
      toonFoto(b.data);
    }
    emit(b.type, b.data);
  }

  async function stuur(type, data) {
    if (!k) return false;
    var h = await headers({ 'Content-Type': 'application/json' });
    var resp = await fetch(h.url + '/api/v1/telefoon/paneel', { method: 'POST', headers: h.headers,
      body: JSON.stringify({ type: type, data: data || {} }) }).catch(function () { return null; });
    return !!(resp && resp.ok);
  }

  function weg(reden) {
    k = null;
    pollNr++;
    $('tel-dialoog').classList.add('hidden');
    chip();
    emit('weg', { reden: reden || '' });
  }

  async function ontkoppel(stil) {
    if (!k) return;
    var h = await headers();
    fetch(h.url + '/api/v1/telefoon/koppel', { method: 'DELETE', headers: h.headers }).catch(function () {});
    weg(stil ? '' : 'Ontkoppeld.');
  }

  function actief() { return !!(k && k.verbonden); }
  function voorTolk() { return !!(k && k.taal); }

  // ── Photos from the phone ──
  var fotos = [];

  function toonFoto(d) {
    var url = 'data:' + d.media_type + ';base64,' + d.data;
    fotos.push({ url: url, media_type: d.media_type, data: d.data });
    var kaart = document.createElement('div');
    kaart.className = 'tel-foto';
    var img = document.createElement('img');
    img.src = url;
    img.alt = 'Foto van de telefoon';
    var acties = document.createElement('div');
    acties.className = 'tel-foto-acties';
    var knop = function (label, title, fn) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'btn small'; b.textContent = label; b.title = title;
      b.addEventListener('click', fn);
      acties.appendChild(b);
      return b;
    };
    knop('Kopieer', 'Op het klembord, om in Bricks of een bericht te plakken', async function () {
      var btn = this;
      try {
        var png = await naarPng(url);
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
        btn.textContent = 'Gekopieerd';
      } catch (e) { btn.textContent = 'Lukte niet'; }
      setTimeout(function () { btn.textContent = 'Kopieer'; }, 1500);
    });
    knop('In Bricks', 'In het uploadveld van Bricks zetten (open daar eerst "document of foto toevoegen"); opslaan doe je in Bricks', function () {
      inBricks(this, url, d.media_type);
    });
    knop('Naar brief', 'In Brieven als schermafdruk, om een medicijnlijst of brief uit te lezen', function () {
      if (window.SVViews) window.SVViews.show('letters');
      if (window.SVLetters) window.SVLetters.zetAfbeelding({ url: url, media_type: d.media_type, data: d.data });
    });
    knop('Weg', 'Foto weghalen; er wordt niets bewaard', function () { kaart.remove(); bijwerkFotos(); });
    kaart.append(img, acties);
    $('tel-fotos-lijst').prepend(kaart);
    bijwerkFotos();
  }

  // A photo into the dossier: the extension puts it in Bricks' open upload
  // field (content/foto-upload.js); the doctor saves it there. JPEG, because
  // an HIS rarely takes HEIC from an iPhone.
  async function inBricks(btn, url, soort) {
    var oud = btn.textContent;
    try {
      var bron = /^image\/(jpeg|png)$/.test(soort) ? url : await naarJpeg(url);
      var type = /^image\/(jpeg|png)$/.test(soort) ? soort : 'image/jpeg';
      var nu = new Date();
      var naam = 'foto-' + nu.getFullYear() + String(nu.getMonth() + 1).padStart(2, '0') + String(nu.getDate()).padStart(2, '0') +
        '-' + String(nu.getHours()).padStart(2, '0') + String(nu.getMinutes()).padStart(2, '0') + (type === 'image/png' ? '.png' : '.jpg');
      var tabId = await currentTabId();
      var res = tabId ? await chrome.tabs.sendMessage(tabId, { action: 'SV_FOTO_UPLOAD', naam: naam, type: type,
        data: bron.split(',')[1] }).catch(function () { return null; }) : null;
      if (res && res.ok) {
        btn.textContent = 'Geplaatst';
        setTimeout(function () { btn.textContent = oud; }, 1500);
        setStatus('Foto in het uploadveld van Bricks gezet (' + naam + '). Controleer de omschrijving en sla op in Bricks.');
      } else {
        try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': await naarPng(url) })]); } catch (e) { /* ignore */ }
        btn.textContent = oud;
        setStatus('Geen uploadveld gevonden. Open in Bricks bij de patiënt het venster om een document of foto toe te ' +
          'voegen en klik nog eens op "In Bricks". De foto staat ook op het klembord.', true);
      }
    } catch (e) {
      setStatus('De foto kon niet naar Bricks: ' + e.message, true);
    }
  }

  function naarJpeg(dataUrl) {
    return new Promise(function (klaar, fout) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement('canvas');
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext('2d').drawImage(img, 0, 0);
        klaar(c.toDataURL('image/jpeg', 0.9));
      };
      img.onerror = function () { fout(new Error('dit fotoformaat kan de browser niet lezen')); };
      img.src = dataUrl;
    });
  }

  function bijwerkFotos() {
    var n = $('tel-fotos-lijst').children.length;
    $('tel-fotos').classList.toggle('hidden', n === 0);
    $('tel-fotos-titel').textContent = n === 1 ? 'Foto van de telefoon' : n + " foto's van de telefoon";
  }

  function naarPng(dataUrl) {
    return new Promise(function (klaar, fout) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement('canvas');
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext('2d').drawImage(img, 0, 0);
        c.toBlob(function (b) { b ? klaar(b) : fout(new Error('png')); }, 'image/png');
      };
      img.onerror = fout;
      img.src = dataUrl;
    });
  }

  function wisFotos() {
    $('tel-fotos-lijst').textContent = '';
    fotos = [];
    bijwerkFotos();
  }

  // ── Wiring ──
  // Without the elements (an older sidepanel.html after a partial update) the
  // phone is simply not offered; nothing else breaks.
  if (!$('btn-telefoon') || !$('tel-dialoog') || !$('tel-fotos')) {
    var uit = function () { return false; };
    return { koppel: function () { return Promise.reject(new Error('Werk de extensie volledig bij om de telefoon te koppelen.')); },
      ontkoppel: function () {}, stuur: function () { return Promise.resolve(false); }, on: function () {},
      actief: uit, voorTolk: uit, wisFotos: function () {} };
  }
  $('btn-telefoon').addEventListener('click', function () {
    if (k) { toonQr(); return; }
    koppel({}).catch(function (e) { setStatus(e.message, true); });
  });
  $('tel-annuleer').addEventListener('click', function () {
    $('tel-dialoog').classList.add('hidden');
    if (k && !k.verbonden) ontkoppel(true);
  });
  $('tel-chip').addEventListener('click', function () {
    if (window.confirm('De telefoon ontkoppelen?')) ontkoppel();
  });
  $('tel-fotos-wis').addEventListener('click', wisFotos);
  // Another mode: the pairing was made in the old one. Pair again.
  if (typeof SVModus !== 'undefined' && SVModus.bijWijziging) {
    SVModus.bijWijziging(function () {
      if (k) { ontkoppel(true); setStatus('Andere modus: koppel de telefoon opnieuw.'); }
    });
  }

  return { koppel: koppel, ontkoppel: ontkoppel, stuur: stuur, on: on, actief: actief, voorTolk: voorTolk, wisFotos: wisFotos };
})();

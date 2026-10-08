/**
 * VitaScribe - Visites (zijpaneel)
 *
 * De kaart "Visites" in het tabblad Consult: de visites die de telefoon
 * instuurde, met hun korte aanduiding, en een knop om de telefoon te koppelen.
 * Openen haalt de envelop, opent hem met de sleutel van deze browser en zet
 * het verslag in het paneel zoals een consultverslag: controleren, invoegen.
 * "Consult afsluiten" haalt de geopende visite van de server.
 *
 * De geheime sleutel staat in IndexedDB van de extensie, niet exporteerbaar.
 * Komt een visite voor een andere pc, dan zegt het paneel dat.
 *
 * Uses: SVVisite (lib/visite.js), getConfig(), SVPraktijk, renderSoep(),
 * setStatus(), SVConsultUI, SVViews, qrcode()
 */
window.SVVisiteUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var sleutel = null;          // {kid, spki, privateKey}
  var aangemeld = {};          // server -> kid: public key known there this session
  var geopend = null;          // id of the visit shown in the panel
  var timer = null;
  var labels = {};             // id -> decrypted label (memory only)

  // ── The key of this browser ──
  function db() {
    return new Promise(function (ok, fout) {
      var r = indexedDB.open('vitascribe-visite', 1);
      r.onupgradeneeded = function () { r.result.createObjectStore('sleutel'); };
      r.onsuccess = function () { ok(r.result); };
      r.onerror = function () { fout(r.error); };
    });
  }
  async function leesSleutel() {
    var d = await db();
    return new Promise(function (ok) {
      var q = d.transaction('sleutel').objectStore('sleutel').get('browser');
      q.onsuccess = function () { ok(q.result || null); };
      q.onerror = function () { ok(null); };
    });
  }
  async function bewaarSleutel(s) {
    var d = await db();
    return new Promise(function (ok, fout) {
      var tx = d.transaction('sleutel', 'readwrite');
      tx.objectStore('sleutel').put(s, 'browser');
      tx.oncomplete = function () { ok(); };
      tx.onerror = function () { fout(tx.error); };
    });
  }
  async function mijnSleutel() {
    if (sleutel) return sleutel;
    sleutel = await leesSleutel();
    if (!sleutel) {
      sleutel = await SVVisite.nieuwSleutelpaar();
      await bewaarSleutel(sleutel);
    }
    return sleutel;
  }

  // ── Server ──
  async function vraag(pad, opties) {
    var config = await getConfig();
    var h = Object.assign({}, (opties && opties.headers) || {});
    if (config.apiKey) h['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(h);
    var url = config.apiUrl.replace(/\/$/, '');
    var resp = await fetch(url + pad, Object.assign({}, opties || {}, { headers: h }));
    var d = await resp.json().catch(function () { return {}; });
    if (!resp.ok) {
      var e = new Error(typeof d.detail === 'string' ? d.detail : 'Server gaf fout ' + resp.status + '.');
      e.status = resp.status;
      throw e;
    }
    return { url: url, data: d };
  }

  async function meldAan() {
    var s = await mijnSleutel();
    var config = await getConfig();
    if (aangemeld[config.apiUrl] === s.kid) return;
    await vraag('/api/v1/visite/ontvanger', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kid: s.kid, spki: s.spki }) });
    aangemeld[config.apiUrl] = s.kid;
  }

  // ── The list ──
  async function ververs() {
    var lijst;
    // First make sure the server knows this browser's public key, so a visit is encrypted for it.
    try { await meldAan(); } catch (e) { /* off on this server, or not allowed: the list call says which */ }
    try {
      lijst = (await vraag('/api/v1/visite/postbus')).data.visites || [];
    } catch (e) {
      // 404: visits are off on this server; 401/403: no key yet. Then no card,
      // and no more asking until the panel comes back or the mode changes.
      $('vis').classList.add('hidden');
      if (e.status === 404) { clearInterval(timer); timer = null; }
      return;
    }
    if (!timer) plan();
    $('vis').classList.remove('hidden');
    var s = await mijnSleutel().catch(function () { return null; });
    for (var i = 0; i < lijst.length; i++) {
      var v = lijst[i];
      if (labels[v.id] === undefined && v.kop && s) {
        try { labels[v.id] = (await SVVisite.open(v.kop, s)).aanduiding || ''; }
        catch (e) { labels[v.id] = null; }   // for another pc
      }
    }
    toon(lijst);
  }

  function toon(lijst) {
    var ul = $('vis-lijst');
    ul.textContent = '';
    lijst.forEach(function (v) {
      var li = document.createElement('li');
      li.className = 'vis-item' + (v.id === geopend ? ' open' : '');
      var tijd = document.createElement('span');
      tijd.className = 'vis-tijd';
      tijd.textContent = SVVisite.tijd(v.gemaakt);
      var wat = document.createElement('span');
      wat.className = 'vis-wat';
      var label = labels[v.id];
      wat.textContent = label === null ? '(andere pc)' : (label || 'visite');
      if (v.status === 'verwerken') wat.textContent += ' · verslag wordt gemaakt…';
      if (v.status === 'fout') { wat.textContent += ' · ' + (v.fout || 'mislukt'); li.classList.add('fout'); }
      var open = document.createElement('button');
      open.type = 'button';
      open.className = 'btn small';
      open.textContent = v.id === geopend ? 'Geopend' : 'Open';
      open.disabled = v.status !== 'klaar' || label === null;
      open.addEventListener('click', function () { openVisite(v.id); });
      var weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'icon-btn';
      weg.textContent = '✕';
      weg.title = 'Weghalen van de server';
      weg.setAttribute('aria-label', 'Visite weghalen');
      weg.addEventListener('click', function () {
        if (window.confirm('Deze visite weghalen? Het verslag is daarna weg.')) haalWeg(v.id);
      });
      li.append(tijd, wat, open, weg);
      ul.appendChild(li);
    });
    $('vis-aantal').textContent = lijst.length ? '(' + lijst.length + ')' : '';
    $('vis-leeg').classList.toggle('hidden', lijst.length > 0);
  }

  async function openVisite(id) {
    try {
      var s = await mijnSleutel();
      var env = (await vraag('/api/v1/visite/postbus/' + encodeURIComponent(id))).data.envelop;
      var data = await SVVisite.open(env, s);
      if (window.SVViews) window.SVViews.show('dictate');
      renderSoep(data.soep || {});
      var dec = $('soep-decisief');
      dec.textContent = data.decisief || '';
      dec.classList.toggle('hidden', !data.decisief);
      if (window.SVConsultUI) window.SVConsultUI.losgekoppeld();   // not the consult recording's report
      geopend = id;
      setStatus('Visiteverslag' + (labels[id] ? ' (' + labels[id] + ')' : '') +
        ' staat klaar. Open de patiënt in Bricks, controleer en voeg in. "Consult afsluiten" haalt de visite daarna van de server.');
      ververs();
    } catch (e) {
      setStatus(e.message, true);
    }
  }

  async function haalWeg(id) {
    try { await vraag('/api/v1/visite/postbus/' + encodeURIComponent(id), { method: 'DELETE' }); }
    catch (e) { setStatus(e.message, true); }
    delete labels[id];
    if (geopend === id) geopend = null;
    ververs();
  }

  // ── Pairing ──
  async function koppel() {
    try {
      await meldAan();
      var d = (await vraag('/api/v1/visite/koppel', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ naam: '' }) }));
      var url = d.url + d.data.pad;
      var qr = qrcode(0, 'M');
      qr.addData(url);
      qr.make();
      $('vis-qr').innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
      $('vis-modus').textContent = d.data.modus === 'eu' ? 'EU-modus' : 'Claude-modus';
      $('vis-dialoog').classList.remove('hidden');
    } catch (e) {
      setStatus(e.message, true);
    }
  }

  async function ontkoppel() {
    if (!window.confirm('Alle telefoons voor visites ontkoppelen? Ze moeten daarna opnieuw de QR-code scannen.')) return;
    try {
      var n = (await vraag('/api/v1/visite/koppel', { method: 'DELETE' })).data.ontkoppeld;
      setStatus(n ? n + (n === 1 ? ' telefoon' : ' telefoons') + ' ontkoppeld.' : 'Er was geen telefoon gekoppeld.');
    } catch (e) { setStatus(e.message, true); }
  }

  // ── Wiring ──
  if (!$('vis')) return { ververs: function () {}, afgerond: function () {} };
  $('vis-koppel').addEventListener('click', koppel);
  $('vis-ontkoppel').addEventListener('click', ontkoppel);
  $('vis-sluit').addEventListener('click', function () { $('vis-dialoog').classList.add('hidden'); ververs(); });
  function plan() {
    clearInterval(timer);
    timer = setInterval(function () { if (!document.hidden) ververs(); }, 30000);
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) ververs(); });
  if (typeof SVModus !== 'undefined' && SVModus.bijWijziging) SVModus.bijWijziging(function () { labels = {}; ververs(); });
  ververs();
  plan();

  return {
    ververs: ververs,
    /** "Consult afsluiten": the visit shown is done; take it off the server. */
    afgerond: function () { if (geopend) haalWeg(geopend); },
  };
})();

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
 * Visiteronde: met "+ patiënt in beeld" zet de arts de patiënten van de ronde
 * klaar (naam en geboortedatum zoals Bricks ze toont; dat blijft in deze
 * browser). "Naar telefoon" stuurt alleen een korte aanduiding per plek,
 * versleuteld voor de telefoon. Komt een visite terug met een plek, dan staat
 * erbij voor wie hij is, en bij openen controleert het paneel of die patiënt
 * in Bricks open staat. Zo niet: een duidelijke waarschuwing vóór iets
 * in het verkeerde dossier komt.
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
  var plekVan = {};            // visit id -> place in the round
  var ronde = { plekken: [] }; // [{plek, aanduiding, naam, geboren, gedaan}] (this browser only)
  var RONDE_DAGEN = 2;

  // ── The key of this browser ──
  function db() {
    return new Promise(function (ok, fout) {
      var r = indexedDB.open('vitascribe-visite', 2);
      r.onupgradeneeded = function () {
        if (!r.result.objectStoreNames.contains('sleutel')) r.result.createObjectStore('sleutel');
        if (!r.result.objectStoreNames.contains('ronde')) r.result.createObjectStore('ronde');
      };
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
  async function leesRonde() {
    var d = await db();
    var r = await new Promise(function (ok) {
      var q = d.transaction('ronde').objectStore('ronde').get('ronde');
      q.onsuccess = function () { ok(q.result || null); };
      q.onerror = function () { ok(null); };
    });
    // Older than two days: gone (the server keeps a visit 48 hours at most).
    if (!r || Date.now() - (r.gemaakt || 0) > RONDE_DAGEN * 86400000) return { plekken: [], gemaakt: Date.now() };
    return r;
  }
  async function bewaarRonde() {
    var d = await db();
    return new Promise(function (ok) {
      var tx = d.transaction('ronde', 'readwrite');
      tx.objectStore('ronde').put(ronde, 'ronde');
      tx.oncomplete = function () { ok(); };
      tx.onerror = function () { ok(); };
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
        try {
          var kop = await SVVisite.open(v.kop, s);
          var p = kop.plek ? rondePlek(kop.plek) : null;
          if (p) plekVan[v.id] = p.plek;
          labels[v.id] = (p ? 'voor ' + p.naam + (p.geboren ? ' (' + p.geboren + ')' : '') : (kop.aanduiding || ''))
            + (kop.fotos ? ' · ' + kop.fotos + (kop.fotos === 1 ? ' foto' : " foto's") : '');
        }
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
      wat.className = 'vis-wat' + (plekVan[v.id] ? ' vis-voor' : '');
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

  // The patient open in Bricks now (name and date of birth from the header).
  async function inBricks() {
    try {
      var d = await SVBricksDossier.lees(5000, true);
      return { naam: d.naam || '', geboren: d.geboren || '' };
    } catch (e) { return { naam: '', geboren: '' }; }
  }

  async function openVisite(id) {
    try {
      var p = plekVan[id] ? rondePlek(plekVan[id]) : null;
      if (p) {
        var nu = await inBricks();
        var zelfde = SVVisite.vergelijk(p, nu);
        if (zelfde === 'anders' && !window.confirm('LET OP: deze visite is voor ' + p.naam + (p.geboren ? ' (' + p.geboren + ')' : '') +
            '.\nIn Bricks staat nu ' + (nu.naam || 'iemand anders') + (nu.geboren ? ' (' + nu.geboren + ')' : '') + ' open.\n\n' +
            'Open eerst de juiste patiënt in Bricks. Toch openen?')) {
          setStatus('Niet geopend: open eerst ' + p.naam + ' in Bricks.', true);
          return;
        }
      }
      var s = await mijnSleutel();
      var env = (await vraag('/api/v1/visite/postbus/' + encodeURIComponent(id))).data.envelop;
      var data = await SVVisite.open(env, s);
      if (window.SVViews) window.SVViews.show('dictate');
      renderSoep(data.soep || {});
      var dec = $('soep-decisief');
      dec.textContent = data.decisief || '';
      dec.classList.toggle('hidden', !data.decisief);
      if (window.SVConsultUI) window.SVConsultUI.losgekoppeld();   // not the consult recording's report
      // Photos of the visit: in the photo list, with "In Bricks"; gone with "Consult afsluiten".
      if (window.SVTelefoon && Array.isArray(data.fotos)) {
        window.SVTelefoon.wisFotos();
        data.fotos.forEach(function (f) { window.SVTelefoon.toonFoto(f); });
      }
      geopend = id;
      setStatus(p ? 'Visiteverslag voor ' + p.naam + (zelfde === 'zelfde' ? ' — deze patiënt staat open in Bricks ✓' :
          zelfde === 'anders' ? ' — LET OP: in Bricks staat een andere patiënt open' : ' — controleer of deze patiënt open staat in Bricks') +
          '. Controleer en voeg in; "Consult afsluiten" haalt de visite daarna van de server.'
        : 'Visiteverslag' + (labels[id] ? ' (' + labels[id] + ')' : '') +
          ' staat klaar. Open de patiënt in Bricks, controleer en voeg in. "Consult afsluiten" haalt de visite daarna van de server.', zelfde === 'anders');
      ververs();
    } catch (e) {
      setStatus(e.message, true);
    }
  }

  // ── The round ──
  function rondePlek(plek) { return ronde.plekken.filter(function (p) { return p.plek === plek; })[0] || null; }

  function toonRonde() {
    var ol = $('vis-ronde-lijst');
    ol.textContent = '';
    ronde.plekken.forEach(function (p) {
      var li = document.createElement('li');
      li.className = p.gedaan ? 'gedaan' : '';
      li.textContent = p.naam + (p.geboren ? ' (' + p.geboren + ')' : '') + ' — telefoon: ' + p.aanduiding + ' ';
      var weg = document.createElement('button');
      weg.type = 'button'; weg.className = 'icon-btn'; weg.textContent = '✕'; weg.title = 'Uit de ronde halen';
      weg.addEventListener('click', async function () {
        ronde.plekken = ronde.plekken.filter(function (x) { return x.plek !== p.plek; });
        await bewaarRonde();
        toonRonde();
      });
      li.appendChild(weg);
      ol.appendChild(li);
    });
    var open = ronde.plekken.filter(function (p) { return !p.gedaan; }).length;
    $('vis-ronde-sub').textContent = ronde.plekken.length ? open + ' van ' + ronde.plekken.length + ' te doen' + (ronde.verstuurd ? ' · op de telefoon' : '') : '';
    $('vis-ronde-acties').classList.toggle('hidden', !ronde.plekken.length);
  }

  async function plusPatient() {
    var nu = await inBricks();
    if (!nu.naam) { setStatus('Open eerst de patiënt in Bricks (met de naam bovenaan) en klik dan op "+ patiënt in beeld".', true); return; }
    if (ronde.plekken.some(function (p) { return SVVisite.vergelijk(p, nu) === 'zelfde'; })) {
      setStatus(nu.naam + ' staat al in de ronde.'); return;
    }
    if (ronde.plekken.length >= 8) { setStatus('Een ronde heeft hooguit 8 visites.', true); return; }
    var reden = (window.prompt('Korte reden voor op de telefoon (optioneel, geen naam): bijv. "wond" of "COPD"') || '').trim().slice(0, 30);
    var n = ronde.plekken.length + 1;
    var plek = 'plek-' + SVVisite.b64(crypto.getRandomValues(new Uint8Array(9))).replace(/[^A-Za-z0-9]/g, 'x');
    ronde.plekken.push({ plek: plek, naam: nu.naam, geboren: nu.geboren,
      aanduiding: n + ' · ' + SVPrivacy.initialen(nu.naam) + (reden ? ' · ' + reden : ''), gedaan: false });
    ronde.verstuurd = false;
    await bewaarRonde();
    toonRonde();
    setStatus(nu.naam + ' staat in de ronde. Open de volgende patiënt en klik opnieuw, of stuur de ronde naar de telefoon.');
  }

  async function stuurRonde() {
    try {
      var tel = (await vraag('/api/v1/visite/toestellen')).data.toestellen || [];
      if (!tel.length) throw new Error('Er is nog geen telefoon met een sleutel. Open eerst de visitepagina op de telefoon (na het koppelen).');
      // Only the short labels go to the phone; names stay in this browser.
      var env = await SVVisite.versleutel({ plekken: ronde.plekken.filter(function (p) { return !p.gedaan; })
        .map(function (p) { return { plek: p.plek, aanduiding: p.aanduiding }; }) }, tel);
      await vraag('/api/v1/visite/ronde', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ envelop: env }) });
      ronde.verstuurd = true;
      await bewaarRonde();
      toonRonde();
      setStatus('De ronde staat op de telefoon. Open daar de visitepagina of tik op "Ronde vernieuwen".');
    } catch (e) { setStatus(e.message, true); }
  }

  async function wisRonde() {
    if (!window.confirm('De ronde wissen, hier en op de telefoon? Visites die al zijn ingestuurd blijven staan.')) return;
    ronde = { plekken: [], gemaakt: Date.now() };
    await bewaarRonde();
    vraag('/api/v1/visite/ronde', { method: 'DELETE' }).catch(function () {});
    toonRonde();
  }

  async function haalWeg(id) {
    try { await vraag('/api/v1/visite/postbus/' + encodeURIComponent(id), { method: 'DELETE' }); }
    catch (e) { setStatus(e.message, true); }
    delete labels[id];
    if (plekVan[id]) {
      var p = rondePlek(plekVan[id]);
      if (p) { p.gedaan = true; await bewaarRonde(); toonRonde(); }
      delete plekVan[id];
    }
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
  $('vis-ronde-plus').addEventListener('click', plusPatient);
  $('vis-ronde-stuur').addEventListener('click', stuurRonde);
  $('vis-ronde-wis').addEventListener('click', wisRonde);
  function plan() {
    clearInterval(timer);
    timer = setInterval(function () { if (!document.hidden) ververs(); }, 30000);
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) ververs(); });
  if (typeof SVModus !== 'undefined' && SVModus.bijWijziging) SVModus.bijWijziging(function () { labels = {}; ververs(); });
  leesRonde().then(function (r) { ronde = r; ronde.plekken = ronde.plekken || []; toonRonde(); }).catch(function () {}).then(ververs);
  plan();

  return {
    ververs: ververs,
    /** "Consult afsluiten": the visit shown is done; take it off the server. */
    afgerond: function () { if (geopend) haalWeg(geopend); },
  };
})();

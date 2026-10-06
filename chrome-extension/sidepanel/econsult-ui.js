/**
 * VitaScribe - E-consult (vijfde tabblad)
 *
 * De arts opent een e-consult in Bricks en klikt "Maak concept-antwoord", of
 * typt in de dossierbalk "beantwoord e-consult: <beleid>". Het paneel leest
 * het dossier dat in beeld staat (letters.js: SVBricksDossier, gefilterd met
 * lib/dossiervraag.js), en stuurt het met het beleid naar
 * /api/v1/econsult/concept. Terug komen: de vraag, de feiten uit het dossier
 * met gecontroleerde citaten, een concept-antwoord op B1-niveau en een
 * journaalregel.
 *
 * "NHG meedenken" is per e-consult een bewuste keuze: het vinkje staat steeds
 * uit, en gaat na elk concept, bij Wissen en bij een nieuw consult weer uit.
 * De server heeft het laatste woord (/api/v1/econsult/status).
 *
 * Waar het antwoord in Bricks hoort, wijst de arts één keer aan (bij het
 * eerste concept staat de uitleg er meteen bij): het antwoordveld en, als dat
 * er is, het journaalveld. De service worker onthoudt die velden per
 * Bricks-domein (svEconsultFields), net als de S/O/E/P-velden; daarna zet
 * "Zet in Bricks" de tekst er direct in.
 *
 * Alles staat alleen in het geheugen van dit paneel.
 *
 * Uses from sidepanel.js: getConfig()
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var huidig = null;
  var geleerd = false;       // learned from this concept already (once per concept)

  // The answer as the doctor sends it: learn from what was changed, once.
  function leer() {
    if (geleerd || !huidig || !huidig.antwoord || !window.SVLerenUI) return;
    geleerd = true;
    window.SVLerenUI.naEconsult(huidig.antwoord, $('ec-antwoord').innerText.trim());
  }
  var bezig = false;

  function status(msg, isError) {
    var el = $('ec-status');
    el.textContent = msg || '';
    el.classList.toggle('error', !!isError);
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  async function kop() {
    var config = await getConfig();
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    return { url: config.apiUrl, headers: headers };
  }

  // ── NHG: may it be ticked in this mode? ──
  async function verversNhg() {
    var box = $('ec-nhg');
    var uit = $('ec-nhg-uit');
    try {
      var k = await kop();
      var resp = await fetch(k.url + '/api/v1/econsult/status', { headers: k.headers });
      if (!resp.ok) throw new Error(String(resp.status));
      var s = await resp.json();
      box.disabled = !s.nhg_beschikbaar;
      if (!s.nhg_beschikbaar) box.checked = false;
      uit.textContent = s.nhg_beschikbaar ? ''
        : 'NHG meedenken staat in deze modus uit op de server. De praktijk kan het voor e-consulten toestaan (zie Beheer en de handleiding).';
      uit.classList.toggle('hidden', !!s.nhg_beschikbaar);
    } catch (e) {
      // Unknown: leave the box usable; the server refuses NHG if not allowed.
      uit.classList.add('hidden');
    }
  }
  document.addEventListener('sv-view', function (e) { if (e.detail === 'econsult') verversNhg(); });
  if (typeof SVModus !== 'undefined') SVModus.bijWijziging(function () { verversNhg(); });

  // ── Making the concept ──
  async function maak() {
    if (bezig) return;
    bezig = true;
    $('ec-go').disabled = true;
    var nhg = $('ec-nhg').checked && !$('ec-nhg').disabled;
    try {
      status('Dossier inlezen…');
      var d = await SVBricksDossier.lees(SVDossiervraag.MAX_TOTAAL, true);
      var b = SVDossiervraag.bouw(d.secties, d.naam, SVPrivacy, SVPrivacy.datum(d.geboren));
      var bericht = SVPrivacy.filter($('ec-bericht').value.trim(), { naam: d.naam || '', geboren: SVPrivacy.datum(d.geboren), datumsBehouden: true });
      if (b.tekst.length < 40 && !bericht) throw new Error('Geen dossier in beeld. Open het e-consult in Bricks, of plak het bericht.');
      status(nhg ? 'Concept maken, met NHG…' : 'Concept maken…');
      var k = await kop();
      var resp;
      try {
        resp = await fetch(k.url + '/api/v1/econsult/concept', {
          method: 'POST', headers: k.headers,
          body: JSON.stringify({ dossier: b.tekst, bericht: bericht, beleid: $('ec-beleid').value.trim(), nhg: nhg }),
        });
      } catch (e) {
        throw new Error('Kan de server niet bereiken op ' + k.url + '.');
      }
      if (!resp.ok) {
        var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
        if (Array.isArray(detail)) detail = detail.map(function (x) { return x.msg; }).join('; ');
        if (resp.status === 404) throw new Error('Deze server kent E-consult nog niet: de server moet eerst bijgewerkt worden.');
        throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
      }
      huidig = await resp.json();
      geleerd = false;
      toon(huidig, nhg);
      status(huidig.bericht ? '' : 'Geen e-consult gevonden in beeld: plak het bericht, of open het in Bricks.', !huidig.bericht);
    } catch (e) {
      status(e.message, true);
    } finally {
      // A conscious choice per e-consult: never carried over to the next one.
      $('ec-nhg').checked = false;
      bezig = false;
      $('ec-go').disabled = false;
    }
  }

  function toon(c, nhgGevraagd) {
    $('ec-uit').classList.remove('hidden');
    $('ec-vraag').textContent = c.vraag_kort || (c.bericht ? '' : 'Geen bericht gevonden.');
    $('ec-bericht-uit').textContent = c.bericht || '';
    $('ec-bericht-details').classList.toggle('hidden', !c.bericht);
    $('ec-bericht-details').classList.toggle('onzeker', !!c.bericht && !c.bericht_geverifieerd);
    $('ec-bericht-details').querySelector('summary').textContent = c.bericht && !c.bericht_geverifieerd
      ? 'Bericht (niet letterlijk teruggevonden: controleer in Bricks)' : 'Bericht';
    var letop = [c.let_op];
    if (nhgGevraagd && !c.nhg_gebruikt) letop.push('NHG meedenken is niet gebruikt: de server staat het in deze modus niet toe.');
    letop = letop.filter(Boolean).join(' ');
    $('ec-letop').textContent = letop;
    $('ec-letop').classList.toggle('hidden', !letop);

    var lijst = $('ec-feiten');
    lijst.textContent = '';
    (c.feiten || []).forEach(function (f) {
      var li = el('li', 'dv-bron' + (f.geverifieerd ? '' : ' onzeker'));
      var mark = el('span', 'dv-mark', f.geverifieerd ? '✓' : '?');
      mark.title = f.geverifieerd ? 'Letterlijk teruggevonden in het dossier' : 'Niet letterlijk teruggevonden: controleer in Bricks';
      var t = el('span');
      t.append(f.tekst);
      var meta = [f.datum, f.onderdeel].filter(Boolean).join(' · ');
      if (meta) t.appendChild(el('span', 'ec-meta', ' ' + meta));
      if (f.citaat) { t.appendChild(document.createElement('br')); t.appendChild(el('q', '', f.citaat)); }
      li.append(mark, t);
      lijst.appendChild(li);
    });
    $('ec-feiten-blok').classList.toggle('hidden', !(c.feiten || []).length);

    var n = c.nhg;
    $('ec-nhg-blok').classList.toggle('hidden', !n);
    if (n) {
      $('ec-richtlijn').textContent = n.richtlijn ? '(' + n.richtlijn + ')' : '';
      var p = $('ec-punten');
      p.textContent = '';
      (n.punten || []).forEach(function (x) { p.appendChild(el('li', '', x)); });
      $('ec-alarm').textContent = n.alarm && n.alarm.length ? 'Alarmsymptomen: ' + n.alarm.join('; ') : '';
      $('ec-alarm').classList.toggle('hidden', !(n.alarm && n.alarm.length));
      $('ec-niet-schriftelijk').classList.toggle('hidden', n.schriftelijk_geschikt !== false);
    }
    $('ec-antwoord').textContent = c.antwoord || '';
    $('ec-journaal').textContent = c.journaal || '';
    verversOpen();
    verversVeld();
  }

  // ── The Bricks fields for the answer and the journal ──
  async function actiefTab() {
    var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0] && /^https?:/.test(tabs[0].url || '') ? tabs[0] : null;
  }

  async function verversVeld() {
    var tab = await actiefTab();
    var s = tab ? await chrome.runtime.sendMessage({ action: 'SV_FIELD_MAP_STATUS', tabId: tab.id, set: 'econsult' }).catch(function () { return null; }) : null;
    var keys = (s && s.mapped && s.keys) || [];
    var antwoord = keys.indexOf('antwoord') !== -1;
    var journaal = keys.indexOf('journaal') !== -1;
    $('ec-zet-antwoord').classList.toggle('hidden', !antwoord);
    $('ec-zet-journaal').classList.toggle('hidden', !journaal);
    $('ec-kop-antwoord').classList.toggle('primary', !antwoord);
    // Not pointed at yet: show how, right with the (first) answer.
    $('ec-veld').classList.toggle('hidden', antwoord);
    $('ec-veld-info').classList.toggle('hidden', !antwoord);
    $('ec-veld-tekst').textContent = antwoord ? 'Gekoppeld: antwoordveld' + (journaal ? ' en journaalveld.' : '.') : '';
  }

  async function aanwijzen() {
    var tab = await actiefTab();
    if (!tab) { status('Open eerst Bricks in dit venster.', true); return; }
    var res = await chrome.runtime.sendMessage({ action: 'SV_CALIBRATE_START', tabId: tab.id, set: 'econsult' }).catch(function () { return null; });
    if (res && res.ok) status('Klik in Bricks in het antwoordveld, daarna in het journaalveld (of Overslaan). Het label rechtsonder wijst de weg.');
    else status((res && res.error) || 'Aanwijzen kon niet starten. Ververs Bricks en probeer opnieuw.', true);
  }
  $('ec-aanwijzen').addEventListener('click', aanwijzen);
  $('ec-opnieuw').addEventListener('click', function (e) { e.preventDefault(); aanwijzen(); });
  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === 'local' && changes.svEconsultFields) {
      verversVeld();
      if (huidig) status('Veld onthouden. "Zet in Bricks" zet het e-consult er voortaan direct in.');
    }
  });

  async function zet(key, btn) {
    var tekst = $(key === 'antwoord' ? 'ec-antwoord' : 'ec-journaal').innerText.trim();
    if (!tekst) return;
    if (key === 'antwoord' && SVEconsult.openPlekken(tekst).some(function (x) { return /beleid aanvullen/i.test(x); })) {
      status('Vul eerst [beleid aanvullen] in.', true);
      return;
    }
    var tab = await actiefTab();
    var vals = {};
    vals[key] = tekst;
    var res = tab ? await chrome.runtime.sendMessage({ action: 'SV_FILL_MAPPED_REQUEST', tabId: tab.id, set: 'econsult', values: vals }).catch(function () { return null; }) : null;
    if (res && res.filled && res.filled.indexOf(key) !== -1) {
      var label = btn.textContent;
      btn.textContent = 'Erin gezet';
      setTimeout(function () { btn.textContent = label; }, 1500);
      status(key === 'antwoord' ? 'Antwoord in Bricks gezet. Lees het daar na en verstuur het zelf.' : 'Journaal in Bricks gezet.');
      if (key === 'antwoord') leer();
      return;
    }
    // Field not on this page: copy, and say where it should be.
    await navigator.clipboard.writeText(tekst).catch(function () {});
    status((key === 'antwoord' ? 'Het antwoordveld' : 'Het journaalveld') + ' staat niet op deze pagina. Open die pagina in Bricks en klik opnieuw; de tekst staat al op het klembord.', true);
  }
  $('ec-zet-antwoord').addEventListener('click', function () { zet('antwoord', this); });
  $('ec-zet-journaal').addEventListener('click', function () { zet('journaal', this); });

  function verversOpen() {
    var open = SVEconsult.openPlekken($('ec-antwoord').textContent);
    $('ec-open').textContent = open.length ? 'Nog invullen: ' + open.join(', ') : '';
    $('ec-open').classList.toggle('hidden', !open.length);
  }
  $('ec-antwoord').addEventListener('input', verversOpen);

  function kopieer(btn, tekst) {
    var label = btn.textContent;
    navigator.clipboard.writeText(tekst).then(function () {
      btn.textContent = 'Gekopieerd';
      setTimeout(function () { btn.textContent = label; }, 1500);
    }).catch(function () { status('Kopiëren lukte niet.', true); });
  }
  $('ec-kop-antwoord').addEventListener('click', function () {
    kopieer(this, $('ec-antwoord').innerText.trim());
    leer();
  });
  $('ec-kop-journaal').addEventListener('click', function () { kopieer(this, $('ec-journaal').innerText.trim()); });
  $('ec-kop-alles').addEventListener('click', function () {
    if (!huidig) return;
    var c = Object.assign({}, huidig, { antwoord: $('ec-antwoord').innerText.trim(), journaal: $('ec-journaal').innerText.trim() });
    kopieer(this, SVEconsult.alsTekst(c));
  });

  function wis() {
    huidig = null;
    geleerd = false;
    ['ec-bericht', 'ec-beleid'].forEach(function (id) { $(id).value = ''; });
    $('ec-nhg').checked = false;
    $('ec-bericht-box').open = false;
    $('ec-uit').classList.add('hidden');
    $('ec-antwoord').textContent = '';
    $('ec-journaal').textContent = '';
    status('');
  }
  $('ec-wis').addEventListener('click', wis);
  $('ec-go').addEventListener('click', maak);

  /** From the dossier bar: open this tab and start, with policy if given. */
  function start(beleid) {
    if (window.SVViews) window.SVViews.show('econsult');
    if (beleid) $('ec-beleid').value = beleid;
    maak();
  }

  window.SVEconsultUI = { start: start, wis: wis };
})();

/**
 * VitaScribe - Leren van de arts (zijpaneel)
 *
 * Na "Invoegen" of "Kopieer" gaan het concept en de versie van de arts naar
 * /api/v1/leren/soep. De server bewaart die teksten niet: hij haalt er algemene
 * regels uit (stijl, verkeerd verstane woorden) en stuurt die als voorstel
 * terug. De arts kiest per voorstel "Onthoud" of "Nee"; alleen wat hij onthoudt
 * gaat voortaan mee. Ook de tolk geeft zijn voorstellen hier door.
 *
 * Gebruikt uit sidepanel.js: getConfig().
 */
window.SVLerenUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var SOORT = { soep: 'stijl', woord: 'woord', tolk: 'tolk' };

  async function aanvraag(pad, body) {
    var config = await getConfig();
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp = await fetch(config.apiUrl + pad, { method: 'POST', headers: headers, body: JSON.stringify(body) });
    if (!resp.ok) throw new Error('Server gaf fout ' + resp.status);
    return resp.json();
  }

  function knop(label, fn) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small';
    b.textContent = label;
    b.addEventListener('click', fn);
    return b;
  }

  function toon(voorstellen) {
    if (!voorstellen || !voorstellen.length) return;
    var lijst = $('leer-lijst');
    voorstellen.forEach(function (v) {
      var li = document.createElement('li');
      var soort = document.createElement('span');
      soort.className = 'leer-soort';
      soort.textContent = SOORT[v.soort] + (v.taal ? ' · ' + v.taal : '');
      var tekst = document.createElement('span');
      tekst.textContent = v.regel;
      tekst.dir = 'auto';
      var zet = function (status, label) {
        return async function () {
          li.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
          try {
            await aanvraag('/api/v1/leren/regel/' + v.id, { status: status });
            li.classList.add('klaar');
            li.querySelectorAll('button').forEach(function (b) { b.remove(); });
            tekst.textContent = label + ': ' + v.regel;
          } catch (e) {
            li.querySelectorAll('button').forEach(function (b) { b.disabled = false; });
          }
        };
      };
      li.append(soort, tekst, knop('✓ Onthoud', zet('actief', 'Onthouden')), knop('Nee', zet('afgewezen', 'Niet onthouden')));
      lijst.appendChild(li);
    });
    $('leer-kaart').classList.remove('hidden');
  }

  /** The doctor inserted or copied a part: learn from what changed (in the background). */
  function naInvoegen(concept, definitief, markeringen) {
    aanvraag('/api/v1/leren/soep', {
      concept: { s: concept.s, o: concept.o, e: concept.e, p: concept.p },
      definitief: { s: definitief.s || '', o: definitief.o || '', e: definitief.e || '', p: definitief.p || '' },
      markeringen: markeringen || 0,
    }).then(function (d) { toon(d.voorstellen); }).catch(function () { /* learning is a bonus */ });
  }

  function naTolk(taal, beurten, eenvoudiger, weggehaald) {
    aanvraag('/api/v1/leren/tolk', { taal: taal, beurten: beurten, eenvoudiger: eenvoudiger.slice(-20), weggehaald: weggehaald })
      .then(function (d) { toon(d.voorstellen); }).catch(function () {});
  }

  function sluit() {
    $('leer-kaart').classList.add('hidden');
    $('leer-lijst').textContent = '';
  }

  function openOverzicht(e) {
    if (e) e.preventDefault();
    chrome.tabs.create({ url: chrome.runtime.getURL('leren/leren.html') });
  }

  $('leer-dicht').addEventListener('click', sluit);
  $('leer-alles').addEventListener('click', openOverzicht);
  $('open-leren').addEventListener('click', openOverzicht);

  return { naInvoegen: naInvoegen, naTolk: naTolk, toon: toon, sluit: sluit };
})();

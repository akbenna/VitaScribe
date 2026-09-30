/**
 * VitaScribe - Meedenken onder de SOEP
 *
 * Na elke SOEP (dictaat of consult) vraagt het paneel de server op de
 * achtergrond om mee te kijken (/api/v1/soep/meedenken):
 * - medicatie (altijd): elk middel met de juiste Nederlandse naam; een
 *   verhaspelde naam krijgt een knop "Vervang";
 * - beleid (alleen met "Meedenken bij het beleid" in Instellingen, en als de
 *   server het toestaat): in lijn met de NHG-Standaard, en hooguit drie
 *   voorstellen die met "+ P" in het plan kunnen;
 * - Thuisarts.nl: zoekterm-links, nooit gegokte adressen.
 *
 * Niets verandert zonder klik. Een aanpassing gaat via een input-event, zodat
 * consult-ui.js hem net als een eigen bewerking doorgeeft aan bolletje en popup.
 *
 * Uses from sidepanel.js: getConfig(), els.soepRows
 */
window.SVMeedenkenUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var cache = {};          // SOEP text -> answer
  var getoond = '';        // key on screen
  var vraagNr = 0;         // only the newest request may paint

  var OORDEEL = {
    in_lijn: 'In lijn met',
    deels: 'Grotendeels in lijn met',
    afwijkend: 'Wijkt af van',
  };

  function sleutel(soep) {
    return ['s', 'o', 'e', 'p'].map(function (k) { return String(soep[k] || '').trim(); }).join('␞');
  }

  function huidigeTekst() {
    var soep = {};
    els.soepRows.querySelectorAll('.soep-text').forEach(function (n) { soep[n.dataset.key] = n.innerText.trim(); });
    soep.icpc_code = $('icpc-code').innerText.trim();
    return soep;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function knop(tekst, titel, onClick) {
    var b = el('button', 'btn small', tekst);
    b.type = 'button';
    if (titel) b.title = titel;
    b.addEventListener('click', onClick);
    return b;
  }

  // Replace or add text in a SOEP row, as if the doctor typed it.
  function veld(key) { return els.soepRows.querySelector('.soep-text[data-key="' + key + '"]'); }
  function bewerk(key, maak) {
    var n = veld(key);
    if (!n) return false;
    var oud = n.innerText;
    var nieuw = maak(oud);
    if (nieuw === null || nieuw === oud) return false;
    n.textContent = nieuw;
    n.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }
  function vervangIn(key, genoemd, vervang) {
    return bewerk(key, function (t) {
      var i = t.toLowerCase().indexOf(genoemd.toLowerCase());
      return i === -1 ? null : t.slice(0, i) + vervang + t.slice(i + genoemd.length);
    });
  }
  function voegToeAanP(zin) {
    return bewerk('p', function (t) {
      var basis = t.trim();
      var z = zin.trim().replace(/[.\s]+$/, '') + '.';
      if (!basis) return z;
      return basis + (/[.!?]$/.test(basis) ? ' ' : '. ') + z;
    });
  }
  // After a click the text changed; remember the answer under the new text
  // so switching parts does not ask again.
  function onthoud(data) {
    getoond = sleutel(huidigeTekst());
    cache[getoond] = data;
  }

  function render(data) {
    $('md').classList.remove('hidden');
    $('md-status').textContent = data.cds ? 'voorstel · jij beslist' : '';

    var lijst = $('md-med');
    lijst.textContent = '';
    (data.medicatie || []).forEach(function (m) {
      var li = el('li', m.vervang ? 'fout' : (m.zeker ? '' : 'twijfel'));
      if (m.vervang) {
        li.appendChild(el('span', 'md-mark', '?'));
        li.appendChild(el('span', 'md-oud', m.genoemd));
        li.appendChild(el('span', '', '→ ' + m.vervang));
        li.appendChild(knop('Vervang', 'Vervang in ' + m.veld.toUpperCase(), function () {
          if (vervangIn(m.veld, m.genoemd, m.vervang)) {
            m.genoemd = m.vervang;
            m.vervang = '';
            onthoud(data);
            render(data);
          }
        }));
      } else if (m.zeker) {
        li.appendChild(el('span', 'md-mark', '✓'));
        li.appendChild(el('span', '', m.middel + (m.middel.toLowerCase() === m.genoemd.toLowerCase() ? '' : ' (' + m.genoemd + ')')));
      } else {
        li.appendChild(el('span', 'md-mark', '?'));
        li.appendChild(el('span', '', '"' + m.genoemd + '": ' + (m.middel ? 'mogelijk ' + m.middel + ', ' : '') + 'controleer de naam'));
      }
      if (m.opmerking) li.appendChild(el('span', 'md-opm', m.opmerking));
      lijst.appendChild(li);
    });

    var blok = $('md-beleid');
    blok.textContent = '';
    blok.className = 'md-beleid hidden';
    var b = data.beleid;
    if (b && (OORDEEL[b.oordeel] && b.richtlijn || (b.suggesties || []).length)) {
      blok.className = 'md-beleid ' + b.oordeel;
      if (OORDEEL[b.oordeel] && b.richtlijn) {
        var o = el('span', 'md-oordeel');
        o.append(OORDEEL[b.oordeel] + ' ');
        o.appendChild(el('b', '', b.richtlijn));
        if (b.toelichting) o.append(': ' + b.toelichting);
        blok.appendChild(o);
      }
      (b.suggesties || []).forEach(function (s, i) {
        var rij = el('div', 'md-sug');
        rij.appendChild(el('span', '', '• ' + s));
        rij.appendChild(knop('+ P', 'Zet dit voorstel in het plan', function () {
          if (voegToeAanP(s)) {
            b.suggesties.splice(i, 1);
            onthoud(data);
            render(data);
          }
        }));
        blok.appendChild(rij);
      });
    }

    var ta = $('md-ta');
    ta.textContent = '';
    ta.classList.toggle('hidden', !(data.thuisarts || []).length);
    if ((data.thuisarts || []).length) {
      ta.appendChild(el('span', '', 'Voor de patiënt:'));
      data.thuisarts.forEach(function (term) {
        var a = el('a', 'ta-chip', 'Thuisarts: ' + term + ' ↗');
        a.href = SVThuisarts.zoekUrl(term);
        a.target = '_blank';
        a.rel = 'noreferrer';
        ta.appendChild(a);
      });
    }

    var leeg = !(data.medicatie || []).length && blok.classList.contains('hidden') && ta.classList.contains('hidden');
    if (leeg) $('md-status').textContent = data.cds ? 'geen opmerkingen' : 'geen medicatie gevonden';
  }

  async function vraag(soep, key) {
    var nr = ++vraagNr;
    $('md').classList.remove('hidden');
    $('md-med').textContent = '';
    $('md-beleid').classList.add('hidden');
    $('md-ta').classList.add('hidden');
    $('md-status').textContent = 'kijkt mee…';
    try {
      var config = await getConfig();
      var keuze = await SVInstellingen.lees(['meedenken']);
      var headers = { 'Content-Type': 'application/json' };
      if (config.apiKey) headers['X-API-Key'] = config.apiKey;
      await SVPraktijk.metKop(headers);
      var resp = await fetch(config.apiUrl + '/api/v1/soep/meedenken', {
        method: 'POST', headers: headers,
        body: JSON.stringify({
          soep: { s: soep.s || '', o: soep.o || '', e: soep.e || '', p: soep.p || '',
                  icpc_code: soep.icpc_code || '', icpc_titel: soep.icpc_titel || '' },
          cds: keuze.meedenken === true,
        }),
      });
      if (nr !== vraagNr) return;
      if (resp.status === 404) { $('md').classList.add('hidden'); return; }   // older server
      if (!resp.ok) throw new Error(String(resp.status));
      var data = await resp.json();
      if (nr !== vraagNr) return;
      cache[key] = data;
      render(data);
    } catch (e) {
      if (nr === vraagNr) $('md-status').textContent = 'meedenken lukte nu niet';
    }
  }

  function toon(soep) {
    var key = sleutel(soep || {});
    if (!soep || !(soep.s || soep.p || soep.e)) { $('md').classList.add('hidden'); return; }
    if (key === getoond && cache[key]) return;
    getoond = key;
    if (cache[key]) { vraagNr++; render(cache[key]); return; }
    vraag(soep, key);
  }

  $('md-opnieuw').addEventListener('click', function () {
    var soep = huidigeTekst();
    var key = sleutel(soep);
    delete cache[key];
    getoond = key;
    vraag(soep, key);
  });

  return { toon: toon };
})();

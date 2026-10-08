/**
 * VitaScribe - Afspraken uit dit consult (zijpaneel)
 *
 * Onder het verslag: wat de arts in de P afsprak, met per afspraak één knop
 * die het werk klaarzet. Een verwijzing opent de verwijsbrief met het
 * specialisme en de reden; voorlichting springt naar Thuisarts; de rest
 * gaat naar het klembord. Afvinken staat alleen in het geheugen en is weg
 * bij het volgende consult.
 *
 * Dit is verslaglegging: alleen wat in de P staat (de server gooit de rest
 * weg). VitaScribe stelt geen afspraak voor.
 *
 * Uses: SVAfspraken (lib/afspraken.js), SVViews, SVLetters, setStatus()
 */
window.SVAfsprakenUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  function knop(tekst, titel, fn) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small';
    b.textContent = tekst;
    b.title = titel;
    b.addEventListener('click', fn);
    return b;
  }

  async function kopieer(b, tekst) {
    try { await navigator.clipboard.writeText(tekst); b.textContent = 'Gekopieerd'; }
    catch (e) { b.textContent = 'Lukte niet'; }
    setTimeout(function () { b.textContent = 'Kopieer'; }, 1500);
  }

  function doe(a, b) {
    var act = SVAfspraken.actie(a);
    if (act.soort === 'verwijzing' && window.SVLetters && window.SVLetters.verwijzing) {
      window.SVLetters.verwijzing({ naar: a.naar, reden: a.tekst });
    } else if (act.soort === 'brief' && window.SVViews) {
      window.SVViews.show('letters');
    } else if (act.soort === 'thuisarts' && $('ta') && !$('ta').classList.contains('hidden')) {
      $('ta').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else {
      kopieer(b, SVAfspraken.kopieertekst(a));
      return;
    }
    vink(b.closest('li'));
  }

  function vink(li) {
    var v = li && li.querySelector('input[type=checkbox]');
    if (v) { v.checked = true; li.classList.add('gedaan'); }
  }

  /** Show the agreements of this consult (an empty or missing list hides the card). */
  function toon(afspraken) {
    var lijst = Array.isArray(afspraken) ? afspraken : [];
    var ul = $('afs-lijst');
    if (!ul) return;
    ul.textContent = '';
    lijst.forEach(function (a) {
      var li = document.createElement('li');
      li.className = 'afs-item';
      var v = document.createElement('input');
      v.type = 'checkbox';
      v.title = 'Gedaan';
      v.setAttribute('aria-label', 'Gedaan: ' + a.tekst);
      v.addEventListener('change', function () { li.classList.toggle('gedaan', v.checked); });
      var soort = document.createElement('span');
      soort.className = 'afs-soort afs-' + a.soort;
      soort.textContent = SVAfspraken.label(a);
      var tekst = document.createElement('span');
      tekst.className = 'afs-tekst';
      tekst.textContent = a.tekst + (a.wanneer && a.tekst.toLowerCase().indexOf(a.wanneer.toLowerCase()) === -1 ? ' · ' + a.wanneer : '');
      var act = SVAfspraken.actie(a);
      var b = knop(act.knop, act.soort === 'verwijzing' ? 'Open de verwijsbrief met specialisme en reden ingevuld'
        : act.soort === 'thuisarts' ? 'Naar de Thuisarts-informatie onder het verslag'
        : act.soort === 'brief' ? 'Naar Brieven' : 'Kopieer, bijvoorbeeld voor de agenda of een notitie', function () { doe(a, b); });
      li.append(v, soort, tekst, b);
      ul.appendChild(li);
    });
    $('afs').classList.toggle('hidden', lijst.length === 0);
  }

  return { toon: toon };
})();

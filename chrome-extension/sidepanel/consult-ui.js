/**
 * VitaScribe - Consultopname in het zijpaneel
 *
 * De opname zelf loopt in het offscreen-document (offscreen/consult.js) en
 * gaat dus door als de arts naar een andere pagina gaat of het zijpaneel
 * sluit. Dit bestand toont alleen de toestand uit chrome.storage.session
 * (svConsult) en stuurt start, nadicteren en stop naar de service worker.
 *
 * Tijdens de opname blijft alleen een klein balkje met de tijd staan; na
 * stop komt het verslag in het gewone SOEP-blok, met alle knoppen erbij.
 *
 * Gebruikt uit sidepanel.js: renderSoep(), setStatus(), state.
 */
window.SVConsultUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var huidig = {};        // laatst bekende svConsult
  var klok = null;
  var getoondOp = null;   // "at" van het verslag of de fout die al getoond is
  var gekoppeld = false;  // staat het consultverslag nu in het SOEP-blok?
  var bewerkTimer = null;

  function bezig() {
    return huidig.state === 'recording' || huidig.state === 'processing';
  }

  function tijd(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }

  function zetKlok(startedAt) {
    clearInterval(klok);
    klok = null;
    if (!startedAt) return;
    var tik = function () { $('consult-timer').textContent = tijd(Date.now() - startedAt); };
    tik();
    klok = setInterval(tik, 500);
  }

  // Vraagsuggesties (klinische ondersteuning, aan te zetten in Instellingen):
  // korte chips onder het opnamebalkje. Een chip aantikken = gevraagd; die
  // blijft doorgestreept, ook als de volgende ronde hem opnieuw noemt.
  var gevraagd = {};
  var vragenVan = null;   // startedAt van het consult waar "gevraagd" bij hoort

  function toonVragen(s) {
    var blok = $('consult-vragen');
    if (vragenVan !== huidig.startedAt) { gevraagd = {}; vragenVan = huidig.startedAt; }
    var vragen = s && Array.isArray(s.vragen) ? s.vragen : [];
    blok.classList.toggle('hidden', vragen.length === 0);
    if (!vragen.length) return;
    $('cv-klacht').textContent = s.klacht ? ' · ' + s.klacht : '';
    var chips = $('cv-chips');
    chips.textContent = '';
    vragen.forEach(function (v) {
      var sleutel = String(v.tekst || '').toLowerCase();
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'cv-chip' + (v.alarm ? ' alarm' : '') + (gevraagd[sleutel] ? ' gedaan' : '');
      b.textContent = v.tekst;
      b.title = (v.alarm ? 'Alarmsymptoom. ' : '') + 'Aantikken als gevraagd';
      b.addEventListener('click', function () {
        gevraagd[sleutel] = !gevraagd[sleutel];
        b.classList.toggle('gedaan', gevraagd[sleutel]);
      });
      chips.appendChild(b);
    });
  }

  function toon(c) {
    huidig = c || {};
    var st = huidig.state || 'idle';
    var opname = st === 'recording';
    var verwerken = st === 'processing';
    $('consult-idle').classList.toggle('hidden', opname || verwerken);
    $('consult-rec').classList.toggle('hidden', !opname);
    $('consult-busy').classList.toggle('hidden', !verwerken);
    document.body.classList.toggle('consult-running', opname || verwerken);
    zetKlok(opname ? huidig.startedAt : null);
    toonVragen(opname && !huidig.nadictaat ? huidig.suggesties : null);

    if (opname) {
      $('consult-label').textContent = huidig.label || 'Opname loopt';
      $('btn-nadicteer').classList.toggle('hidden', !!huidig.nadictaat);
      els.conn.className = 'conn live';
      els.conn.textContent = '● consult';
    } else if (verwerken) {
      $('consult-step').textContent = huidig.step || 'Verslag wordt gemaakt…';
      els.conn.className = 'conn';
      els.conn.textContent = 'verwerken…';
    } else if (state === 'idle') {
      els.conn.className = 'conn';
      els.conn.textContent = 'klaar';
    }

    if (st === 'results' && huidig.result && huidig.at !== getoondOp) {
      getoondOp = huidig.at;
      var data = huidig.result;
      renderSoep(data.soep || {});
      gekoppeld = true;
      var dec = $('soep-decisief');
      dec.textContent = data.decisief || '';
      dec.classList.toggle('hidden', !data.decisief);
      var n = Array.isArray((data.soep || {}).problemen) ? data.soep.problemen.length : 1;
      setStatus(n > 1
        ? 'Consultverslag klaar: ' + n + ' problemen, elk een eigen deel. Controleer en voeg ze één voor één in.'
        : 'Consultverslag klaar. Controleer het en voeg het in.');
    }
    // Parts inserted elsewhere (pill, popup) are ticked off here too.
    if (st === 'results' && gekoppeld && soepDelen) {
      var klaar = huidig.inserted || 0;
      var veranderd = false;
      soepDelen.forEach(function (d, i) {
        if (i < klaar && !d.__ingevoegd) { d.__ingevoegd = true; veranderd = true; }
      });
      if (veranderd) toonDeel(Math.min(klaar, soepDelen.length - 1));
    } else if (st === 'error' && huidig.at !== getoondOp) {
      getoondOp = huidig.at;
      setStatus(huidig.message || 'De consultopname is mislukt.', true);
    }
    var fout = st === 'error' && !huidig.dismissed;
    $('consult-err').classList.toggle('hidden', !fout);
    $('btn-consult-resend').classList.toggle('hidden', !(fout && huidig.retry));
    $('btn-consult-settings').classList.toggle('hidden', !(fout && huidig.code === 'key'));
  }

  async function start() {
    if (state !== 'idle') {
      setStatus('Stop eerst het dicteren.', true);
      return;
    }
    var knop = $('btn-consult');
    knop.disabled = true;
    setStatus('Opname starten…');
    var res = await chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: 'start' }).catch(function () { return null; });
    knop.disabled = false;
    if (!res || !res.ok) {
      setStatus((res && res.message) || 'De opname kon niet starten.', true);
      $('consult-err').classList.toggle('hidden', !(res && res.code === 'key'));
      $('btn-consult-settings').classList.toggle('hidden', !(res && res.code === 'key'));
      return;
    }
    setStatus('');
  }

  function opdracht(cmd) {
    return chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: cmd }).catch(function () { return null; });
  }

  // Na een herstart van de browser of extensie kan er nog een oude "opname"
  // in de opslag staan terwijl er niets meer loopt; vraag het na.
  async function controleer() {
    if (!bezig()) return;
    var st = await opdracht('status');
    if (st && st.active === false) {
      chrome.storage.session.set({ svConsult: { state: 'error', message: 'De opname was gestopt (browser of extensie herstart).', at: Date.now() } });
    }
  }

  $('btn-consult').addEventListener('click', start);
  $('btn-consult-stop').addEventListener('click', function () { opdracht('stop'); });
  $('btn-nadicteer').addEventListener('click', function () { opdracht('nadictaat'); });
  $('btn-consult-resend').addEventListener('click', function () { opdracht('retry'); });
  $('btn-consult-settings').addEventListener('click', function () { chrome.runtime.openOptionsPage(); });

  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === 'session' && changes.svConsult) toon(changes.svConsult.newValue);
  });
  chrome.storage.session.get('svConsult').then(function (r) {
    // Het laatste verslag opnieuw tonen als het paneel later weer opengaat.
    toon(r.svConsult);
    controleer();
  });

  // Aanpassingen in het SOEP-blok gaan terug naar het verslag, zodat
  // "Invoegen" in het bolletje en de popup dezelfde tekst gebruiken.
  function stuurAanpassing() {
    if (!gekoppeld || huidig.state !== 'results') return;
    var deel = huidigDeel();   // sidepanel.js: the part on screen, with its edits
    chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: 'edit', soep: deel.soep, deel: deel.index }).catch(function () {});
  }
  function bijBewerken(e) {
    if (!gekoppeld || !e.target.closest || !e.target.closest('.soep-text, #icpc-code')) return;
    clearTimeout(bewerkTimer);
    bewerkTimer = setTimeout(stuurAanpassing, 400);
  }
  document.getElementById('soep').addEventListener('input', bijBewerken);

  return {
    bezig: bezig,
    /** Het SOEP-blok toont nu iets anders dan het consultverslag. */
    losgekoppeld: function () { gekoppeld = false; },
    /** Een deel van het consultverslag is via het zijpaneel ingevoegd; na het
     *  laatste deel verdwijnen bolletje en ✓. */
    ingevoegd: function (deel) {
      if (gekoppeld && huidig.state === 'results') {
        chrome.runtime.sendMessage({ action: 'SV_CONSULT_CMD', cmd: 'inserted', deel: deel || 0 }).catch(function () {});
      }
    },
  };
})();

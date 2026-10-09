/**
 * VitaScribe - Post (vierde tabblad): labuitslagen en brieven beoordelen
 *
 * Zolang dit tabblad open is, leest het paneel om de paar seconden het
 * bericht dat in Bricks in beeld staat. Klikt de arts een ander bericht aan,
 * dan gaat het (gefilterd, zie lib/post.js) naar /api/v1/post/beoordeel. Het
 * antwoord geeft:
 * - een klinische samenvatting voor "Samenvatting (zichtbaar in journaal)";
 * - uitleg in eenvoudige woorden voor de patiënt, voor "Memo";
 * - bij lab de relevante waarden, een oordeel en een beleidsvoorstel (met
 *   klinische ondersteuning aan); bij een brief afzender, reden, conclusie en
 *   wat er van de huisarts verwacht wordt.
 * Beide teksten zijn aan te passen en gaan pas met een klik in Bricks.
 * Een bericht dat al beoordeeld is, komt uit het geheugen (geen nieuwe kosten).
 *
 * Uses from sidepanel.js: getConfig()
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var POLL_MS = 2000;
  var cache = new Map();     // raw message -> answer
  var laatst = '';           // raw message seen on the last read
  var getoond = '';          // raw message whose answer is on screen
  var bezig = false;
  var timer = null;
  var huidig = null;         // answer on screen

  function status(msg, isError) {
    var el = $('po-status');
    el.textContent = msg || '';
    el.classList.toggle('error', !!isError);
  }

  function zichtbaar() {
    return !$('view-post').classList.contains('hidden') && document.visibilityState === 'visible';
  }

  // ── Reading Bricks ──
  function paginaTekst() {
    return document.body ? document.body.innerText : '';
  }

  async function bricksTab() {
    var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    var tab = tabs[0];
    return tab && /^https?:/.test(tab.url || '') ? tab : null;
  }

  async function lees() {
    var tab = await bricksTab();
    if (!tab) return null;
    var res = await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, func: paginaTekst })
      .catch(function () { return []; });
    var tekst = (res || []).map(function (r) { return r && r.result || ''; }).join('\n');
    return SVPost.bouw(tekst, SVPrivacy, new Date());
  }

  // Runs in the Bricks page: put text in the field under a label
  // ("Samenvatting", "Memo"); existing text stays, the new text goes below.
  function zetInVeld(label, tekst) {
    var l = label.toLowerCase();
    var kop = Array.prototype.find.call(document.querySelectorAll('label,span,div,p,b,strong,h1,h2,h3,h4,h5,td,th'), function (e) {
      return !e.querySelector('*') && e.textContent.trim().toLowerCase().indexOf(l) === 0;
    });
    if (!kop) return false;
    var veld = Array.prototype.find.call(document.querySelectorAll('textarea,[contenteditable="true"]'), function (t) {
      return kop.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING;
    });
    if (!veld) return false;
    if (veld.tagName === 'TEXTAREA') {
      var oud = veld.value.replace(/\s+$/, '');
      var setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(veld, oud ? oud + '\n' + tekst : tekst);
    } else {
      veld.innerText = (veld.innerText.replace(/\s+$/, '') ? veld.innerText.replace(/\s+$/, '') + '\n' : '') + tekst;
    }
    veld.dispatchEvent(new Event('input', { bubbles: true }));
    veld.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  async function zetIn(label, tekst, knop) {
    var tab = await bricksTab();
    if (!tab || !tekst) return;
    var res = await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, func: zetInVeld, args: [label, tekst] })
      .catch(function () { return []; });
    var gelukt = (res || []).some(function (r) { return r && r.result; });
    if (gelukt) {
      var oud = knop.textContent;
      knop.textContent = 'Staat erin ✓';
      setTimeout(function () { knop.textContent = oud; }, 1500);
    } else {
      navigator.clipboard.writeText(tekst).catch(function () {});
      status('Veld "' + label + '" niet gevonden in Bricks; de tekst staat op het klembord.', true);
    }
  }

  // ── Asking ──
  async function beoordeel(d) {
    var config = await getConfig();
    var keuze = await SVInstellingen.lees(['meedenken']);
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp;
    try {
      resp = await fetch(config.apiUrl + '/api/v1/post/beoordeel', {
        method: 'POST', headers: headers,
        body: JSON.stringify({ tekst: d.tekst, leeftijd: d.leeftijd, problemen: d.problemen, cds: keuze.meedenken === true }),
      });
    } catch (e) {
      throw new Error('Kan de server niet bereiken op ' + config.apiUrl + '.');
    }
    if (resp.status === 404) throw new Error('Deze server kent Post nog niet: de server moet eerst bijgewerkt worden.');
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      throw new Error('Server gaf fout ' + resp.status + (typeof detail === 'string' && detail ? ': ' + detail : ''));
    }
    return resp.json();
  }

  async function verwerk(d, opnieuw) {
    if (bezig) return;
    if (!opnieuw && cache.has(d.vingerafdruk)) {
      toon(cache.get(d.vingerafdruk));
      getoond = d.vingerafdruk;
      status('');
      return;
    }
    bezig = true;
    $('po-lees').disabled = true;
    status('Nieuw bericht: VitaScribe leest mee…');
    try {
      var a = await beoordeel(d);
      cache.set(d.vingerafdruk, a);
      if (cache.size > 40) cache.delete(cache.keys().next().value);
      getoond = d.vingerafdruk;
      toon(a);
      status('');
    } catch (e) {
      status(e.message, true);
    } finally {
      bezig = false;
      $('po-lees').disabled = false;
    }
  }

  // Automatic: a message must read the same twice in a row (Bricks loads in
  // steps) before it is judged.
  async function tik() {
    if (!zichtbaar() || !$('po-auto').checked || bezig) return;
    var d = await lees().catch(function () { return null; });
    if (!d) {
      if (!getoond) status('Geen bericht in beeld. Klik in de Bricks-post een labuitslag of brief aan.');
      laatst = '';
      return;
    }
    if (d.vingerafdruk === getoond) { laatst = d.vingerafdruk; return; }
    if (d.vingerafdruk !== laatst) { laatst = d.vingerafdruk; return; }
    verwerk(d, false);
  }

  function start() {
    if (timer) return;
    timer = setInterval(tik, POLL_MS);
    tik();
  }
  function stop() { clearInterval(timer); timer = null; }

  // ── Showing ──
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  var SOORT = { lab: 'Lab', brief: 'Brief', overig: 'Bericht' };
  var OORDEEL = { normaal: 'Normaal', afwijkend: 'Afwijkend', niet_beoordeelbaar: 'Via aanvrager' };
  var PIJL = { hoog: '↑', laag: '↓', normaal: '·', afwijkend: '!' };

  function toon(a) {
    huidig = a;
    $('po-uit').classList.remove('hidden');
    $('po-soort').textContent = SOORT[a.soort] || 'Bericht';
    var lab = a.lab || null;
    var oordeel = lab && OORDEEL[lab.oordeel];
    $('po-oordeel').textContent = oordeel || '';
    $('po-oordeel').className = 'po-oordeel ' + (lab ? lab.oordeel : '');
    $('po-oordeel').classList.toggle('hidden', !oordeel);
    $('po-letop').textContent = a.let_op || '';
    $('po-letop').classList.toggle('hidden', !a.let_op);
    $('po-sam').textContent = a.samenvatting || '';
    $('po-pat').textContent = a.patient || '';
    $('po-pat-blok').classList.toggle('hidden', !a.patient);

    var lijst = $('po-lab');
    lijst.textContent = '';
    (lab ? lab.bevindingen : []).forEach(function (b) {
      var li = el('li', 'po-' + b.richting);
      li.appendChild(el('span', 'po-pijl', PIJL[b.richting] || '·'));
      var t = el('span', '');
      t.appendChild(el('b', '', b.bepaling));
      t.append(' ' + b.waarde + (b.duiding ? ': ' + b.duiding : ''));
      li.appendChild(t);
      lijst.appendChild(li);
    });
    lijst.classList.toggle('hidden', !(lab && lab.bevindingen.length));
    $('po-beleid').textContent = lab && lab.beleid ? 'Beleid: ' + lab.beleid : '';
    $('po-beleid').classList.toggle('hidden', !(lab && lab.beleid));
    $('po-verg').textContent = lab && lab.vergelijking ? 'Trend: ' + lab.vergelijking : '';
    $('po-verg').classList.toggle('hidden', !(lab && lab.vergelijking));

    var brief = $('po-brief');
    brief.textContent = '';
    var b = a.brief;
    if (b) {
      [['Van', b.afzender], ['Reden', b.reden], ['Conclusie', b.conclusie]].forEach(function (r) {
        if (!r[1]) return;
        brief.appendChild(el('dt', '', r[0]));
        brief.appendChild(el('dd', '', r[1]));
      });
      if (b.acties && b.acties.length) {
        brief.appendChild(el('dt', '', 'Voor jou'));
        var dd = el('dd', '');
        var ul = el('ul', 'po-acties');
        b.acties.forEach(function (x) { ul.appendChild(el('li', '', x)); });
        dd.appendChild(ul);
        brief.appendChild(dd);
      }
    }
    brief.classList.toggle('hidden', !b);
  }

  function kopieer(tekst, knop) {
    navigator.clipboard.writeText(tekst).then(function () {
      var oud = knop.textContent;
      knop.textContent = 'Gekopieerd';
      setTimeout(function () { knop.textContent = oud; }, 1500);
    }).catch(function () { status('Kopiëren lukte niet.', true); });
  }

  $('po-zet-sam').addEventListener('click', function () { zetIn('Samenvatting', $('po-sam').innerText.trim(), this); });
  $('po-zet-memo').addEventListener('click', function () { zetIn('Memo', $('po-pat').innerText.trim(), this); });
  $('po-kop-sam').addEventListener('click', function () { kopieer($('po-sam').innerText.trim(), this); });
  $('po-kop-pat').addEventListener('click', function () { kopieer($('po-pat').innerText.trim(), this); });
  $('po-lees').addEventListener('click', async function () {
    status('Bericht inlezen…');
    var d = await lees().catch(function () { return null; });
    if (!d) { status('Geen bericht in beeld. Open in de Bricks-post een labuitslag of brief.', true); return; }
    verwerk(d, true);
  });

  try { var auto = localStorage.getItem('svPostAuto'); if (auto !== null) $('po-auto').checked = auto === '1'; } catch (e) { /* ignore */ }
  $('po-auto').addEventListener('change', function () {
    try { localStorage.setItem('svPostAuto', this.checked ? '1' : '0'); } catch (e) { /* ignore */ }
    if (this.checked) tik();
  });

  document.addEventListener('sv-view', function (e) { if (e.detail === 'post') start(); else stop(); });
  document.addEventListener('visibilitychange', function () { if (zichtbaar()) tik(); });
  if (zichtbaar()) start();

  window.SVPostUI = { huidig: function () { return huidig; } };
})();

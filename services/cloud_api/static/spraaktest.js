/*
 * VitaScribe spraaktest: dezelfde opname door Deepgram en Voxtral.
 *
 * Gebruikt de beheersessie van /beheer (sessionStorage van dit tabblad). Alle
 * tekst uit de transcripten gaat als tekst de pagina in, nooit als HTML.
 */
(function () {
  'use strict';

  var OPSLAG = 'vs-beheersessie';
  var $ = function (id) { return document.getElementById(id); };
  var opname = null;      // { blob, naam }
  var recorder = null, stukken = [], startTijd = 0, timer = null;

  function sessie() { try { return sessionStorage.getItem(OPSLAG) || ''; } catch (e) { return ''; } }
  function status(t, fout) { $('status').textContent = t || ''; $('status').className = 'status klein' + (fout ? ' fout' : ''); }
  function el(tag, cls, tekst) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (tekst !== undefined) n.textContent = tekst;
    return n;
  }
  function klaar() { $('vergelijk').disabled = !opname; }

  if (!sessie()) status('Log eerst in op de beheerpagina in dit tabblad, en kom dan terug via "Spraaktest".', true);

  // ── Opnemen in de browser ──
  $('opnemen').addEventListener('click', async function () {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stukken = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (e) { if (e.data.size) stukken.push(e.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        clearInterval(timer);
        opname = { blob: new Blob(stukken, { type: 'audio/webm' }), naam: 'opname.webm' };
        $('opnemen').textContent = '● Opnemen';
        status('Opname klaar (' + $('klok').textContent + '). Klik op Vergelijk.');
        klaar();
      };
      recorder.start(1000);
      startTijd = Date.now();
      $('opnemen').textContent = '■ Stop';
      timer = setInterval(function () {
        var s = Math.round((Date.now() - startTijd) / 1000);
        $('klok').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
      }, 500);
      status('Bezig met opnemen…');
    } catch (e) {
      status('De microfoon kon niet starten: ' + e.message, true);
    }
  });

  $('bestand').addEventListener('change', function () {
    var f = this.files[0];
    if (f) { opname = { blob: f, naam: f.name }; status('Bestand gekozen: ' + f.name + '.'); }
    klaar();
  });

  // ── Vergelijken ──
  $('vergelijk').addEventListener('click', async function () {
    if (!opname) return;
    var knop = this;
    knop.disabled = true;
    status('Bezig: beide diensten verwerken de opname tegelijk…');
    $('uitkomst').textContent = '';
    var form = new FormData();
    form.append('audio', opname.blob, opname.naam);
    form.append('taal', $('taal').value);
    try {
      var r = await fetch('/api/v1/beheer/spraaktest', { method: 'POST', headers: { 'X-Beheer-Sessie': sessie() }, body: form });
      var body = await r.json().catch(function () { return {}; });
      if (r.status === 401 || r.status === 403) throw new Error('Niet ingelogd. Log in op /beheer in dit tabblad.');
      if (!r.ok) throw new Error(body.detail || ('Fout ' + r.status));
      toon(body);
      status('Klaar.');
    } catch (e) {
      status(e.message, true);
    } finally {
      knop.disabled = false;
    }
  });

  function dollar(paar) { return '$' + paar[0].toFixed(3) + (paar[1] !== paar[0] ? '–' + paar[1].toFixed(3) : ''); }

  function kolom(titel, d, alleen) {
    var k = el('div', 'kaart');
    k.appendChild(el('h3', '', titel));
    if (d.fout) {
      k.appendChild(el('p', 'fout', 'Mislukt na ' + d.seconden + ' s: ' + d.fout));
      return k;
    }
    var t = el('table');
    [['Verwerkingstijd', d.seconden + ' s'],
     ['Duur opname', d.duur_audio + ' s'],
     ['Sprekers herkend', String(d.sprekers)],
     ['Uitingen', String(d.uitingen)],
     ['Woorden', String(d.woorden)],
     ['Kosten deze opname', dollar(d.kosten_dollar)],
     ['Per consult van 10 min', dollar(d.per_consult_10_min_dollar)]].forEach(function (rij) {
      var tr = el('tr'); tr.appendChild(el('td', '', rij[0])); tr.appendChild(el('td', '', rij[1])); t.appendChild(tr);
    });
    k.appendChild(t);
    var termen = el('p', 'klein', 'Vaktermen herkend: ');
    (d.vaktermen || []).forEach(function (w) { termen.appendChild(el('span', 'term', w)); });
    if (!(d.vaktermen || []).length) termen.appendChild(document.createTextNode('geen'));
    k.appendChild(termen);
    k.appendChild(el('p', 'klein', 'Transcript met sprekers:'));
    k.appendChild(el('pre', '', d.met_sprekers || d.tekst || '(leeg)'));
    return k;
  }

  function toon(b) {
    var u = $('uitkomst');
    var samen = el('div', 'kaart');
    samen.appendChild(el('h2', '', 'Uitkomst'));
    samen.appendChild(el('p', '', b.overeenkomst === null ? 'Een van beide diensten gaf geen tekst.'
      : 'De twee transcripten komen voor ' + b.overeenkomst + '% overeen (woorden in dezelfde volgorde). Lees de verschillen: welke dienst verstond het gesprek beter?'));
    function verschil(label, lijst) {
      var p = el('p', 'klein', label);
      if (!lijst.length) p.appendChild(document.createTextNode('geen'));
      lijst.forEach(function (w) { p.appendChild(el('span', 'term mist', w)); });
      return p;
    }
    samen.appendChild(verschil('Vaktermen alleen door Deepgram herkend: ', b.alleen_deepgram || []));
    samen.appendChild(verschil('Vaktermen alleen door Voxtral herkend: ', b.alleen_voxtral || []));
    u.appendChild(samen);
    var naast = el('div', 'naast');
    naast.appendChild(kolom('Deepgram (VS, EU-endpoint)', b.deepgram, b.alleen_deepgram || []));
    naast.appendChild(kolom('Voxtral (Mistral, Frankrijk)', b.voxtral, b.alleen_voxtral || []));
    u.appendChild(naast);
  }
})();

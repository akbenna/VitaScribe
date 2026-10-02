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
  var laatste = null;     // the last comparison, for "Maak SOEP van beide"

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
      laatste = body;
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
    if (b.deepgram.met_sprekers || b.voxtral.met_sprekers) u.appendChild(soepKaart());
  }

  // ── SOEP van beide transcripten ──
  function soepKaart() {
    var k = el('div', 'kaart');
    k.id = 'soep';
    k.appendChild(el('h2', '', 'SOEP van beide transcripten'));
    k.appendChild(el('p', 'klein', 'Hetzelfde taalmodel en dezelfde woordenlijst als bij een echt consult. ' +
      'Blind beoordelen: je ziet "Verslag A" en "Verslag B" in willekeurige volgorde, en pas na je oordeel welke dienst welke is.'));
    var rij = el('div', 'rij');
    var label = el('label', 'klein');
    var blind = el('input'); blind.type = 'checkbox'; blind.checked = true; blind.id = 'blind';
    label.appendChild(blind); label.appendChild(document.createTextNode(' Blind beoordelen'));
    var knop = el('button', 'hoofd', 'Maak SOEP van beide');
    rij.appendChild(knop); rij.appendChild(label);
    k.appendChild(rij);
    var stat = el('p', 'status klein');
    var uit = el('div');
    k.appendChild(stat); k.appendChild(uit);
    knop.addEventListener('click', async function () {
      knop.disabled = true;
      uit.textContent = '';
      stat.className = 'status klein';
      stat.textContent = 'Bezig: het taalmodel schrijft twee verslagen (ongeveer een halve minuut)…';
      try {
        var r = await fetch('/api/v1/beheer/spraaktest/soep', {
          method: 'POST',
          headers: { 'X-Beheer-Sessie': sessie(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ deepgram: laatste.deepgram.met_sprekers || '', voxtral: laatste.voxtral.met_sprekers || '',
                                 taal: $('taal').value })
        });
        var body = await r.json().catch(function () { return {}; });
        if (r.status === 401 || r.status === 403) throw new Error('Niet ingelogd. Log in op /beheer in dit tabblad.');
        if (!r.ok) throw new Error(body.detail || ('Fout ' + r.status));
        toonSoep(uit, body, blind.checked);
        stat.textContent = 'Klaar. Taalmodel: ' + body.taalmodel + '.';
      } catch (e) {
        stat.className = 'status klein fout';
        stat.textContent = e.message;
      } finally {
        knop.disabled = false;
      }
    });
    return k;
  }

  function soepKolom(titel, d) {
    var k = el('div', 'kaart');
    var kop = el('h3', '', titel);
    k.appendChild(kop);
    if (d.fout) { k.appendChild(el('p', 'fout', 'Mislukt: ' + d.fout)); return { kaart: k, kop: kop }; }
    (d.problemen || []).forEach(function (p, i) {
      if ((d.problemen || []).length > 1) k.appendChild(el('p', 'klein', 'Probleem ' + (i + 1)));
      var t = el('table');
      [['S', p.s], ['O', p.o], ['E', p.e], ['P', p.p],
       ['ICPC', [p.icpc_code, p.icpc_titel].filter(Boolean).join(' ')]].forEach(function (rij) {
        var tr = el('tr'); tr.appendChild(el('td', '', rij[0])); tr.appendChild(el('td', 'soep', rij[1] || '—')); t.appendChild(tr);
      });
      k.appendChild(t);
    });
    k.appendChild(el('p', 'klein', 'Gemaakt in ' + d.seconden + ' s'));
    return { kaart: k, kop: kop };
  }

  function toonSoep(uit, b, blind) {
    var paren = [['Deepgram', b.deepgram], ['Voxtral', b.voxtral]];
    if (blind && Math.random() < 0.5) paren.reverse();
    var naast = el('div', 'naast');
    var koppen = paren.map(function (paar, i) {
      var titel = blind ? 'Verslag ' + 'AB'[i] : paar[0];
      var kol = soepKolom(titel, paar[1]);
      naast.appendChild(kol.kaart);
      return kol.kop;
    });
    uit.appendChild(naast);
    if (blind) {
      var onthul = el('button', '', 'Onthul welke dienst welke is');
      onthul.addEventListener('click', function () {
        koppen.forEach(function (kop, i) { kop.textContent = 'Verslag ' + 'AB'[i] + ': ' + paren[i][0]; });
        onthul.remove();
      });
      uit.appendChild(onthul);
    }
  }
})();

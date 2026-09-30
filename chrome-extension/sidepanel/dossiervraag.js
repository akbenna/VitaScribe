/**
 * VitaScribe - Dossiervraag (derde tabblad van het zijpaneel)
 *
 * De arts vraagt iets aan het dossier dat in Bricks open staat. Bij elke
 * vraag wordt het dossier opnieuw ingelezen (letters.js: SVBricksDossier),
 * gefilterd (lib/dossiervraag.js + lib/privacy.js) en met de vraag naar de
 * server gestuurd (/api/v1/dossier/vraag). Zo telt een pas geopend onderdeel
 * meteen mee en kan een antwoord nooit over de vorige patiënt gaan.
 *
 * Vragen en antwoorden staan alleen in het geheugen van dit paneel; bij een
 * andere patiënt of het sluiten van het paneel zijn ze weg.
 *
 * Uses from sidepanel.js: getConfig()
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var dv = { naam: '', eerder: [], bezig: false };

  function status(msg, isError) {
    var el = $('dv-status');
    el.textContent = msg || '';
    el.classList.toggle('error', !!isError);
  }

  // ── Quick questions ──
  SVDossiervraag.SNELVRAGEN.forEach(function (s) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = s.label;
    b.title = s.vraag;
    b.addEventListener('click', function () {
      $('dv-input').value = s.vraag;
      vraag(s.vraag);
    });
    $('dv-snel').appendChild(b);
  });

  // ── Reading the dossier ──
  async function leesDossier() {
    var d = await SVBricksDossier.lees(SVDossiervraag.MAX_TOTAAL);
    if (!SVDossiervraag.zelfdePatient(dv.naam, d.naam)) {
      dv.eerder = [];
      $('dv-antwoorden').textContent = '';
      status('Andere patiënt: de eerdere vragen zijn gewist.');
    }
    // Without a name we cannot tell patients apart: then follow-up context is
    // not carried over (each question stands on its own).
    if (!d.naam) dv.eerder = [];
    dv.naam = d.naam || dv.naam;
    var b = SVDossiervraag.bouw(d.secties, d.naam, SVPrivacy);
    var totaal = b.onderdelen.reduce(function (n, o) { return n + o.tekens; }, 0);
    $('dv-bron').textContent = 'Ingelezen (' + b.initialen + '): '
      + b.onderdelen.map(function (o) { return o.naam; }).join(', ')
      + ' · ' + SVDossiervraag.tekens(totaal)
      + (b.ingekort ? ' · ingekort, heel dik dossier' : '');
    $('dv-preview').textContent = b.tekst;
    $('dv-details').classList.remove('hidden');
    return b;
  }

  $('dv-lees').addEventListener('click', async function () {
    var btn = this;
    btn.disabled = true;
    status('Dossier inlezen…');
    try {
      await leesDossier();
      status('');
    } catch (e) {
      status(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  // ── Asking ──
  async function stuur(dossier, tekst) {
    var config = await getConfig();
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp;
    try {
      resp = await fetch(config.apiUrl + '/api/v1/dossier/vraag', {
        method: 'POST', headers: headers,
        body: JSON.stringify({ dossier: dossier, vraag: tekst, eerder: dv.eerder.slice(-3) }),
      });
    } catch (e) {
      throw new Error('Kan de server niet bereiken op ' + config.apiUrl + '.');
    }
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join('; ');
      if (resp.status === 401) detail = detail || 'Controleer de API-sleutel in Instellingen.';
      if (resp.status === 404) throw new Error('Deze server kent Dossiervraag nog niet: de server moet eerst bijgewerkt worden.');
      throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
    }
    return resp.json();
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function alsTekst(tekst, a) {
    var regels = [a.antwoord];
    (a.bronnen || []).forEach(function (b) {
      regels.push('- ' + [b.datum, b.onderdeel].filter(Boolean).join(' · ') + ': "' + b.citaat + '"');
    });
    return regels.join('\n');
  }

  function toonAntwoord(kaart, tekst, a) {
    kaart.classList.remove('bezig');
    kaart.classList.toggle('niet', !a.gevonden);
    kaart.textContent = '';
    kaart.appendChild(el('p', 'dv-vraag', tekst));
    kaart.appendChild(el('p', 'dv-antwoord', a.antwoord || '—'));
    if (a.let_op) kaart.appendChild(el('p', 'dv-letop', a.let_op));
    if (a.bronnen && a.bronnen.length) {
      var lijst = el('ul', 'dv-bronnen');
      a.bronnen.forEach(function (b) {
        var li = el('li', 'dv-bron' + (b.geverifieerd ? '' : ' onzeker'));
        var mark = el('span', 'dv-mark', b.geverifieerd ? '✓' : '?');
        mark.title = b.geverifieerd ? 'Letterlijk teruggevonden in het dossier' : 'Niet letterlijk teruggevonden: controleer in Bricks';
        var tekstEl = el('span');
        var meta = [b.datum, b.onderdeel].filter(Boolean).join(' · ');
        if (meta) tekstEl.append(meta + ' — ');
        tekstEl.appendChild(el('q', '', b.citaat));
        li.append(mark, tekstEl);
        lijst.appendChild(li);
      });
      kaart.appendChild(lijst);
    }
    var acties = el('div', 'dv-acties');
    var kopieer = el('button', 'btn small', 'Kopieer');
    kopieer.type = 'button';
    kopieer.addEventListener('click', function () {
      navigator.clipboard.writeText(alsTekst(tekst, a)).then(function () {
        kopieer.textContent = 'Gekopieerd';
        setTimeout(function () { kopieer.textContent = 'Kopieer'; }, 1500);
      }).catch(function () { status('Kopiëren lukte niet.', true); });
    });
    acties.appendChild(kopieer);
    kaart.appendChild(acties);
  }

  async function vraag(tekst) {
    tekst = String(tekst || '').trim();
    if (dv.bezig) return;
    if (tekst.length < 2) { status('Typ een vraag of kies er een hierboven.', true); $('dv-input').focus(); return; }
    dv.bezig = true;
    $('dv-go').disabled = true;
    var kaart = null;
    try {
      status('Dossier inlezen…');
      var b = await leesDossier();
      kaart = el('div', 'dv-item bezig');
      kaart.appendChild(el('p', 'dv-vraag', tekst));
      kaart.appendChild(el('p', 'dv-antwoord muted', 'Zoeken in het dossier…'));
      $('dv-antwoorden').prepend(kaart);
      status('');
      var a = await stuur(b.tekst, tekst);
      toonAntwoord(kaart, tekst, a);
      dv.eerder.push({ vraag: tekst, antwoord: String(a.antwoord || '').slice(0, 4000) });
      $('dv-input').value = '';
    } catch (e) {
      if (kaart) kaart.remove();
      status(e.message, true);
    } finally {
      dv.bezig = false;
      $('dv-go').disabled = false;
    }
  }

  $('dv-form').addEventListener('submit', function (e) {
    e.preventDefault();
    vraag($('dv-input').value);
  });
  $('dv-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      vraag($('dv-input').value);
    }
  });
  document.addEventListener('sv-view', function (e) {
    if (e.detail === 'dossier') setTimeout(function () { $('dv-input').focus(); }, 0);
  });
})();

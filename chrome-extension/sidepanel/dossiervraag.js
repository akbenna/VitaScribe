/**
 * VitaScribe - Dossiervraag (de balk onderaan het zijpaneel, in elk tabblad)
 *
 * De arts vraagt iets aan het dossier dat in Bricks open staat, ook midden in
 * een consult of bij een bericht in de post (dan leest de vraag dat bericht
 * mee, want het staat in beeld). De antwoorden schuiven boven de balk open. Bij elke
 * vraag wordt het dossier opnieuw ingelezen (letters.js: SVBricksDossier),
 * gefilterd (lib/dossiervraag.js + lib/privacy.js) en met de vraag naar de
 * server gestuurd (/api/v1/dossier/vraag). Zo telt een pas geopend onderdeel
 * meteen mee en kan een antwoord nooit over de vorige patiënt gaan.
 *
 * Vragen en antwoorden staan alleen in het geheugen van dit paneel; bij een
 * andere patiënt of het sluiten van het paneel zijn ze weg.
 *
 * "Denk mee": het stuk dat de arts aanwijst (geselecteerde tekst, of het blok
 * rond de laatste klik in Bricks: het lab met eerdere waarden, een uitslag,
 * een brief; anders alles in beeld) gaat naar dezelfde beoordeling als
 * in het tabblad Post (/api/v1/post/beoordeel, bron "scherm"), met een
 * getypte vraag als focus. Duiding en beleid alleen met klinische
 * ondersteuning aan (server én de keuze van de arts), net als bij Post.
 *
 * Uses from sidepanel.js: getConfig()
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var dv = { naam: '', eerder: [], bezig: false };

  function open(aan) {
    $('dv-paneel').classList.toggle('hidden', !aan);
    document.body.classList.toggle('dv-open', !!aan);
  }

  function status(msg, isError) {
    if (msg) open(true);
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
    // Broad: everything that is on screen in Bricks (journal, episodes,
    // medication, letters, notes), not only recognised sections.
    var d = await SVBricksDossier.lees(SVDossiervraag.MAX_TOTAAL, true);
    dv.leeftijd = leeftijdUit(d.geboren);
    dv.geboren = d.geboren || '';
    if (!SVDossiervraag.zelfdePatient(dv.naam, d.naam)) {
      dv.eerder = [];
      $('dv-antwoorden').textContent = '';
      status('Andere patiënt: de eerdere vragen zijn gewist.');
    }
    // Without a name we cannot tell patients apart: then follow-up context is
    // not carried over (each question stands on its own).
    if (!d.naam) dv.eerder = [];
    dv.naam = d.naam || dv.naam;
    var b = SVDossiervraag.bouw(d.secties, d.naam, SVPrivacy, SVPrivacy.datum(d.geboren));
    var totaal = b.onderdelen.reduce(function (n, o) { return n + o.tekens; }, 0);
    $('dv-bron').textContent = 'Ingelezen (' + b.initialen + '): '
      + b.onderdelen.map(function (o) { return o.naam === 'Dossier (in beeld)' ? 'alles wat in beeld staat' : o.naam; }).join(', ')
      + ' · ' + SVDossiervraag.tekens(totaal)
      + (b.ingekort ? ' · ingekort, heel dik dossier' : '');
    $('dv-preview').textContent = b.tekst;
    $('dv-details').classList.remove('hidden');
    // An e-consult on screen: offer the concept answer right here.
    $('dv-econsult').classList.toggle('hidden', !SVEconsult.inBeeld(b.tekst));
    return b;
  }

  function leeftijdUit(geboren) {
    var m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(String(geboren || '').trim());
    if (!m) return null;
    var nu = new Date(), jaren = nu.getFullYear() - Number(m[3]);
    if (nu.getMonth() + 1 < Number(m[2]) || (nu.getMonth() + 1 === Number(m[2]) && nu.getDate() < Number(m[1]))) jaren--;
    return jaren >= 0 && jaren <= 120 ? jaren : null;
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
    var zeker = a.zekerheid || (a.gevonden ? 'expliciet' : 'niet_gevonden');
    kaart.classList.toggle('niet', zeker === 'niet_gevonden');
    kaart.classList.toggle('indirect', zeker === 'indirect');
    kaart.textContent = '';
    var kop = el('div', 'dv-kop-item');
    kop.appendChild(el('p', 'dv-vraag', tekst));
    kop.appendChild(el('span', 'dv-zeker ' + zeker, { expliciet: 'Staat erin', indirect: 'Alleen aanwijzingen', niet_gevonden: 'Niet gevonden' }[zeker]));
    kop.appendChild(sluitKnop(kaart, tekst));
    kaart.appendChild(kop);
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

  // ── Thinking along about what is in view (same assessment as Post) ──
  var MAX_SCHERM = 30000;   // what /api/v1/post/beoordeel takes

  async function beoordeelScherm(dossier, focus) {
    var config = await getConfig();
    var keuze = await SVInstellingen.lees(['meedenken']);
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp;
    try {
      resp = await fetch(config.apiUrl + '/api/v1/post/beoordeel', {
        method: 'POST', headers: headers,
        body: JSON.stringify({ tekst: dossier.slice(0, MAX_SCHERM), leeftijd: dv.leeftijd, problemen: [],
          cds: keuze.meedenken === true, bron: 'scherm', vraag: focus || null }),
      });
    } catch (e) {
      throw new Error('Kan de server niet bereiken op ' + config.apiUrl + '.');
    }
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join('; ');
      if (resp.status === 422) throw new Error('Deze server kent meedenken over wat in beeld is nog niet: de server moet eerst bijgewerkt worden.');
      throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
    }
    return resp.json();
  }

  var PIJL = { hoog: '↑', laag: '↓', normaal: '', afwijkend: '!' };
  var OORDEEL = { normaal: 'Normaal', afwijkend: 'Afwijkend', niet_beoordeelbaar: 'Via aanvrager' };

  /** ✕ on an answer: gone from the panel (and from the follow-up context). */
  function sluitKnop(kaart, vraagTekst) {
    var b = el('button', 'icon-btn dv-weg', '✕');
    b.type = 'button';
    b.title = 'Dit antwoord wegklikken';
    b.setAttribute('aria-label', 'Dit antwoord wegklikken');
    b.addEventListener('click', function () {
      if (vraagTekst) dv.eerder = dv.eerder.filter(function (x) { return x.vraag !== vraagTekst; });
      kaart.remove();
      if (!$('dv-antwoorden').children.length) open(false);
    });
    return b;
  }

  function wisAlles() {
    dv.eerder = [];
    $('dv-antwoorden').textContent = '';
    status('');
    open(false);
  }

  function kopieerKnop(label, tekst) {
    var b = el('button', 'btn small', label);
    b.type = 'button';
    b.addEventListener('click', function () {
      navigator.clipboard.writeText(tekst).then(function () {
        b.textContent = 'Gekopieerd';
        setTimeout(function () { b.textContent = label; }, 1500);
      }).catch(function () { status('Kopiëren lukte niet.', true); });
    });
    return b;
  }

  function toonMeedenken(kaart, focus, a, ingekort) {
    kaart.classList.remove('bezig');
    kaart.classList.add('dv-md');
    kaart.textContent = '';
    var kop = el('div', 'dv-kop-item');
    kop.appendChild(el('p', 'dv-vraag', focus ? 'Meedenken: ' + focus : 'Meedenken'));
    var lab = a.lab || {};
    if (OORDEEL[lab.oordeel]) kop.appendChild(el('span', 'dv-zeker ' + (lab.oordeel === 'normaal' ? 'expliciet' : 'indirect'), OORDEEL[lab.oordeel]));
    kop.appendChild(sluitKnop(kaart));
    kaart.appendChild(kop);
    if (a.let_op) kaart.appendChild(el('p', 'dv-letop', a.let_op));
    if (a.antwoord) kaart.appendChild(el('p', 'dv-antwoord', a.antwoord));
    if ((lab.bevindingen || []).length) {
      var ul = el('ul', 'dv-md-waarden');
      lab.bevindingen.forEach(function (b) {
        ul.appendChild(el('li', '', (PIJL[b.richting] ? PIJL[b.richting] + ' ' : '') + b.bepaling + ' ' + b.waarde + (b.duiding ? ' — ' + b.duiding : '')));
      });
      kaart.appendChild(ul);
    }
    if (lab.vergelijking) kaart.appendChild(el('p', 'dv-md-regel', 'Verloop: ' + lab.vergelijking));
    if (lab.beleid) kaart.appendChild(el('p', 'dv-md-regel', 'Voorstel: ' + lab.beleid));
    if (a.brief) {
      [['Van', a.brief.afzender], ['Reden', a.brief.reden], ['Conclusie', a.brief.conclusie]].forEach(function (r) {
        if (r[1]) kaart.appendChild(el('p', 'dv-md-regel', r[0] + ': ' + r[1]));
      });
    }
    if (a.samenvatting) kaart.appendChild(el('p', 'dv-antwoord', a.samenvatting));
    if (!a.cds) kaart.appendChild(el('p', 'muted', 'Alleen de feiten: klinische duiding en beleid staan uit (Instellingen of de server).'));
    if (ingekort) kaart.appendChild(el('p', 'muted', 'Er stond veel in beeld; alleen het bovenste deel is beoordeeld. Open alleen het onderdeel dat telt.'));
    var acties = el('div', 'dv-acties');
    if (a.samenvatting) acties.appendChild(kopieerKnop('Kopieer samenvatting', a.samenvatting));
    if (a.patient) acties.appendChild(kopieerKnop('Kopieer uitleg patiënt', a.patient));
    kaart.appendChild(acties);
  }

  var MAX_FOCUS = 8000;

  /**
   * What "Denk mee" looks at: the text the doctor selected, or the block around
   * the last click in Bricks (a lab table, a letter, a result). Nothing pointed
   * at, or "alles in beeld" asked: everything on screen, as before. The same
   * privacy filter as every dossier question (SVDossiervraag.bouw).
   */
  async function leesVoorMeedenken(breed) {
    var b = await leesDossier();
    if (breed) return { b: b, waar: 'alles wat in beeld staat' };
    var f = await SVBricksDossier.focus(MAX_FOCUS).catch(function () { return null; });
    if (!f) return { b: b, waar: 'alles wat in beeld staat (nergens aangeklikt)' };
    var naam = f.soort === 'selectie' ? 'Geselecteerd in het dossier' : 'In beeld, waar de arts klikte';
    var secties = {};
    secties[naam] = f.tekst;
    var g = SVDossiervraag.bouw(secties, dv.naam, SVPrivacy, SVPrivacy.datum(dv.geboren));
    if (g.tekst.trim().length < 20) return { b: b, waar: 'alles wat in beeld staat' };
    $('dv-preview').textContent = g.tekst;
    return { b: g, waar: (f.soort === 'selectie' ? 'je selectie' : 'het blok waar je klikte') + ' (' + SVDossiervraag.tekens(g.tekst.length) + ')', gericht: true };
  }

  async function meedenken(breed) {
    if (dv.bezig) return;
    var focus = $('dv-input').value.trim();
    dv.bezig = true;
    $('dv-meedenken').disabled = true;
    var kaart = null;
    try {
      status('Inlezen wat je aanwijst…');
      var l = await leesVoorMeedenken(breed === true);
      open(true);
      kaart = el('div', 'dv-item bezig');
      kaart.appendChild(el('p', 'dv-vraag', focus ? 'Meedenken: ' + focus : 'Meedenken'));
      kaart.appendChild(el('p', 'dv-antwoord muted', 'VitaScribe beoordeelt ' + l.waar + '…'));
      $('dv-antwoorden').prepend(kaart);
      status('');
      var a = await beoordeelScherm(l.b.tekst, focus);
      toonMeedenken(kaart, focus, a, l.b.tekst.length > MAX_SCHERM);
      var waar = el('p', 'dv-waar muted', 'Gekeken naar: ' + l.waar + '.');
      if (l.gericht) {
        var breder = el('button', 'link-btn', 'Alles in beeld');
        breder.type = 'button';
        breder.title = 'Opnieuw, over alles wat in Bricks in beeld staat';
        breder.addEventListener('click', function () { if (focus) $('dv-input').value = focus; meedenken(true); });
        waar.appendChild(document.createTextNode(' '));
        waar.appendChild(breder);
      }
      kaart.insertBefore(waar, kaart.children[1] || null);
      $('dv-input').value = '';
    } catch (e) {
      if (kaart) kaart.remove();
      status(e.message, true);
    } finally {
      dv.bezig = false;
      $('dv-meedenken').disabled = false;
    }
  }

  async function vraag(tekst) {
    tekst = String(tekst || '').trim();
    if (dv.bezig) return;
    if (tekst.length < 2) { status('Typ een vraag of kies er een hierboven.', true); $('dv-input').focus(); return; }
    // "beantwoord e-consult: <beleid>" goes to the E-consult tab.
    if (SVEconsult.isOpdracht(tekst) && window.SVEconsultUI) {
      $('dv-input').value = '';
      open(false);
      window.SVEconsultUI.start(SVEconsult.beleidUit(tekst));
      return;
    }
    dv.bezig = true;
    $('dv-go').disabled = true;
    var kaart = null;
    try {
      status('Dossier inlezen…');
      var b = await leesDossier();
      open(true);
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
  // Focus shows the quick questions; ✕ hides the answers again (they stay
  // in memory until another patient or the panel closes).
  $('dv-input').addEventListener('focus', function () { open(true); });
  // Grows with a longer question, up to a few lines.
  $('dv-input').addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight + 2, 120) + 'px';
  });
  $('dv-dicht').addEventListener('click', function () { open(false); });
  $('dv-meedenken').addEventListener('click', function () { meedenken(false); });
  $('dv-wis').addEventListener('click', wisAlles);
  $('dv-econsult').addEventListener('click', function () {
    open(false);
    if (window.SVEconsultUI) window.SVEconsultUI.start('');
  });
  $('dv-input').addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { open(false); $('dv-input').blur(); }
  });
})();

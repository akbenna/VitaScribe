/**
 * VitaScribe - Brieven (informatiebrief en verwijsbrief)
 *
 * Voorheen de losse extensie BriefAssistent. Het dossier komt uit Bricks,
 * een schermafdruk of een PDF; de arts kiest per onderdeel wat meegaat en
 * ziet precies wat er verstuurd wordt (namen, BSN, geboortedatum, adres en
 * contactgegevens eruit). De brief schrijft de VitaScribe-server; er staat
 * geen AI-sleutel in de browser.
 *
 * Uses from sidepanel.js: getConfig(), insertOrCopy(), els.text
 */
(function () {
  'use strict';

  if (typeof pdfjsLib !== 'undefined') {
    pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL('lib/pdfjs/pdf.worker.min.js');
  }

  var $ = function (id) { return document.getElementById(id); };
  // Per section: enough for a long journal in view. Bricks lists the newest
  // first, so a cut keeps the recent part; the section shows that it was cut.
  var MAX_SECTIE = 20000;
  var DEFAULT_ON = ['journaal', 'medicatie', 'voorgeschied', 'lab', 'problemen', 'allergie', 'dossier', 'metingen'];

  var lt = {
    secties: {},       // name -> raw text
    aan: {},           // name -> bool
    naamRauw: '',
    initialen: 'P.X.',
    kind: 'verwijzing',
    aanvrager: 'advocaat',
    spec: 'cardioloog',
    urgentie: 'regulier',
    shot: null,        // { media_type, data }
    busy: false,
  };

  function status(msg, isError) {
    var el = $('lt-status');
    el.textContent = msg || '';
    el.classList.toggle('error', !!isError);
  }

  // ── Small UI helpers ──
  function segment(containerId, attr, onPick) {
    var c = $(containerId);
    c.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || !c.contains(b)) return;
      c.querySelectorAll('button').forEach(function (x) { x.classList.toggle('active', x === b); });
      onPick(b.dataset[attr], b);
    });
  }

  segment('lt-src', 'src', function (src) {
    document.querySelectorAll('.lt-src-pane').forEach(function (p) { p.classList.toggle('hidden', p.dataset.pane !== src); });
  });
  segment('lt-kind', 'kind', function (kind) {
    lt.kind = kind;
    document.querySelectorAll('#lt-kind button').forEach(function (b) { b.setAttribute('aria-checked', b.dataset.kind === kind ? 'true' : 'false'); });
    $('lt-info').classList.toggle('hidden', kind !== 'informatiebrief');
    $('lt-verw').classList.toggle('hidden', kind !== 'verwijzing');
    $('lt-verkl').classList.toggle('hidden', kind !== 'verklaring');
    $('lt-generate').textContent = { verwijzing: 'Schrijf verwijsbrief', informatiebrief: 'Schrijf informatiebrief',
      verklaring: 'Schrijf verklaring' }[kind];
  });
  $('lt-aanvrager').addEventListener('change', function () { lt.aanvrager = this.value; });
  segment('lt-urg', 'v', function (v) { lt.urgentie = v; });
  $('lt-spec').addEventListener('change', function () {
    var v = this.value;
    lt.spec = v;
    $('lt-spec-free').classList.toggle('hidden', v !== '');
    if (v === '') $('lt-spec-free').focus();
  });

  async function api(path, body) {
    var config = await getConfig();
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    await SVPraktijk.metKop(headers);
    var resp;
    try {
      resp = await fetch(config.apiUrl + path, { method: 'POST', headers: headers, body: JSON.stringify(body) });
    } catch (e) {
      throw new Error('Kan de server niet bereiken op ' + config.apiUrl + '.');
    }
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join('; ');
      throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
    }
    return resp;
  }

  // ── Dossier: loaded ──
  function setDossier(secties, naamRauw, bron, geboren) {
    lt.geboren = SVPrivacy.datum(geboren);
    lt.secties = {};
    lt.ingekort = {};
    Object.keys(secties || {}).forEach(function (k) {
      var t = String(secties[k] || '').trim();
      if (t.length < 5) return;
      lt.secties[k] = t.slice(0, MAX_SECTIE);
      lt.ingekort[k] = t.length > MAX_SECTIE;
    });
    lt.naamRauw = naamRauw || '';
    lt.initialen = SVPrivacy.initialen(lt.naamRauw);
    var few = Object.keys(lt.secties).length <= 2;
    lt.aan = {};
    Object.keys(lt.secties).forEach(function (k) {
      lt.aan[k] = few || DEFAULT_ON.some(function (kw) { return k.toLowerCase().indexOf(kw) !== -1; });
    });
    renderDossier(bron);
  }

  // A PDF or screenshot (a specialist letter, an older journal page) adds to
  // what was already fetched instead of replacing it: the patient stays the
  // same, so the name filter from Bricks keeps working. Returns true if added.
  function voegToe(secties, bron) {
    if (!Object.keys(lt.secties).length) { setDossier(secties, '', bron); return false; }
    var nieuw = {};
    Object.keys(lt.secties).forEach(function (k) { nieuw[k] = lt.secties[k]; });
    Object.keys(secties || {}).forEach(function (k) {
      var naam = (k === 'Dossier' ? bron : k + ' (' + bron + ')');
      nieuw[naam] = secties[k];
    });
    var aan = lt.aan, geboren = lt.geboren;
    setDossier(nieuw, lt.naamRauw, 'Bricks + ' + bron);
    lt.geboren = geboren;    // setDossier takes the text form; keep the date
    Object.keys(aan).forEach(function (k) { if (k in lt.aan) lt.aan[k] = aan[k]; });
    Object.keys(lt.aan).forEach(function (k) { if (!(k in aan)) lt.aan[k] = true; });
    renderDossier('Bricks + ' + bron);
    return true;
  }

  // One line about the dossier, so the doctor does not have to open the details.
  function dossierKort(bron) {
    var names = Object.keys(lt.secties);
    var kort = $('lt-dossier-kort');
    if (!names.length) {
      kort.innerHTML = 'Nog niet opgehaald. Bij <b>Schrijf</b> haalt VitaScribe op wat in Bricks open staat.';
      return;
    }
    var aan = names.filter(function (k) { return lt.aan[k]; });
    kort.textContent = 'Opgehaald (' + lt.initialen + (bron ? ', ' + bron : '') + '): ' + aan.join(', ')
      + (aan.length < names.length ? ' · ' + (names.length - aan.length) + ' uit' : '');
  }

  function renderDossier(bron) {
    var names = Object.keys(lt.secties);
    lt.bron = bron || lt.bron;
    dossierKort(lt.bron);
    $('lt-dossier').classList.toggle('hidden', names.length === 0);
    if (!names.length) return;
    var name = $('lt-name');
    name.textContent = '';
    if (lt.naamRauw) {
      var s = document.createElement('s'); s.textContent = lt.naamRauw;
      var b = document.createElement('b'); b.textContent = lt.initialen;
      name.append('Naam: ', s, ' → ', b);
    } else {
      var b2 = document.createElement('b'); b2.textContent = lt.initialen;
      name.append('Geen naam gevonden; patiënt heet in de brief ', b2);
    }
    if (bron) name.append(' · bron: ' + bron);

    var box = $('lt-sections');
    box.textContent = '';
    names.forEach(function (k) {
      var row = document.createElement('label');
      row.className = 'lt-sec';
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = !!lt.aan[k];
      cb.addEventListener('change', function () { lt.aan[k] = cb.checked; updatePreview(); dossierKort(lt.bron); });
      var title = document.createElement('span'); title.textContent = k;
      var meta = document.createElement('span'); meta.className = 'meta';
      var n = lt.secties[k].length;
      meta.textContent = (n < 1000 ? n + ' tekens' : (Math.round(n / 100) / 10) + 'k tekens')
        + (lt.ingekort && lt.ingekort[k] ? ' · ingekort: alleen het bovenste deel' : '');
      row.append(cb, title, meta);
      box.appendChild(row);
    });
    updatePreview();
  }

  function filterOpts() {
    return { naam: lt.naamRauw, geboren: lt.geboren, datumsBehouden: $('lt-keep-dates').checked };
  }

  function dossierTekst() {
    var out = 'PATIËNT: ' + lt.initialen + '\n\n';
    Object.keys(lt.secties).forEach(function (k) {
      if (!lt.aan[k]) return;
      out += '== ' + k.toUpperCase() + ' ==\n' + SVPrivacy.filter(lt.secties[k], filterOpts()) + '\n\n';
    });
    return out.trim();
  }

  function updatePreview() { $('lt-preview').textContent = dossierTekst(); }
  $('lt-keep-dates').addEventListener('change', updatePreview);

  $('lt-clear').addEventListener('click', function () {
    setDossier({}, '', '');
    lt.shot = null;
    $('lt-shot-img').classList.add('hidden');
    $('lt-shot-read').classList.add('hidden');
    status('');
  });

  // ── Dossier: Bricks ──
  // Runs inside every frame of the Bricks tab; returns the text per section.
  // Only what is actually on screen counts: Bricks keeps earlier patients and
  // closed tabs in the page (hidden), and reading those would mix patients.
  // breed: the whole visible page as one text (Dossiervraag), not per section.
  function scrapeFrame(maxPagina, breed) {
    var SECTIES = {
      'Journaal': ['journaal', 'journal', 'soep', 'episode', 'consult', 'icpc'],
      'Medicatie': ['medicatie', 'medication', 'recept', 'geneesmiddel'],
      'Voorgeschiedenis': ['voorgeschied', 'v.g.', 'history', 'probleemlijst'],
      'Lab': ['lab', 'bepaling', 'bloedwaarden', 'uitslag'],
      'Correspondentie': ['correspon', 'verwijz', 'specialist', 'ontslagbrief'],
      'Metingen': ['meting', 'bloeddruk', 'gewicht', 'bmi'],
      'Allergieën': ['allergie', 'intolerant', 'overgevoelig', 'contra-indicat'],
    };
    var out = { secties: {}, naam: '', geboren: '', top: window === window.top };
    // A frame that is not shown (display:none iframe) has no size.
    if (!document.body || window.innerWidth === 0 || window.innerHeight === 0) return out;
    function zichtbaar(el) {
      if (!el.getClientRects().length) return false;
      var st = (el.ownerDocument.defaultView || window).getComputedStyle(el);
      return st.visibility !== 'hidden' && st.display !== 'none';
    }
    // innerText of a rendered element keeps line breaks between blocks and
    // leaves out hidden children; of a hidden element it would be glued text.
    function text(el) {
      var t = el.innerText || '';
      return t.split('\n')
        .filter(function (line) { return !/^(opslaan|annuleren|sluiten|bewerken|verwijderen|nieuw|zoeken|print|afdrukken|meer|×|✕)$/i.test(line.trim()); })
        .join('\n')
        .replace(/\t+/g, ' ').replace(/ {3,}/g, '  ').replace(/\n{3,}/g, '\n\n').trim();
    }
    // Inline frames (srcdoc/about:blank) are not reached by executeScript;
    // read them through the parent. Frames with their own URL get their own run.
    var docs = [document];
    document.querySelectorAll('iframe,frame').forEach(function (f) {
      var src = f.getAttribute('src') || '';
      if (src && !/^about:/.test(src)) return;
      if (!zichtbaar(f)) return;
      try { if (f.contentDocument && f.contentDocument.body) docs.push(f.contentDocument); } catch (e) { /* cross-origin */ }
    });
    function all(sel) {
      var list = [];
      docs.forEach(function (d) { list = list.concat(Array.prototype.slice.call(d.querySelectorAll(sel))); });
      return list.filter(zichtbaar);
    }
    // The patient: Bricks shows "Naam (84) (03-06-1941)" at the top.
    var pagina = docs.map(function (d) { return text(d.body); }).join('\n');
    var kop = /([A-Z][A-Za-zÀ-ÿ'.\- ]{1,60}?)\s*\((\d{1,3})\)\s*\((\d{1,2}-\d{1,2}-\d{4})\)/.exec(pagina);
    if (kop) { out.naam = kop[1].trim(); out.geboren = kop[3]; }
    if (!out.naam) {
      var nameEl = all('[class*="patient" i] [class*="name" i], [class*="patientnaam" i], [class*="patient-name" i], [data-testid*="patient" i]')[0];
      if (nameEl) {
        var n = nameEl.textContent.trim();
        if (n.length >= 3 && n.length <= 60) out.naam = n;
      }
    }
    if (breed) {
      if (pagina.length > 40) out.secties['Dossier (in beeld)'] = pagina.slice(0, maxPagina || 150000);
      return out;
    }
    var gepakt = [];
    all('section,article,[class*="panel" i],[class*="widget" i],[class*="card" i],[class*="tab-content" i],[class*="module" i]').forEach(function (panel) {
      // A panel inside one we already took (or around it) is the same text.
      if (gepakt.some(function (g) { return g.contains(panel) || panel.contains(g); })) return;
      var hdr = panel.querySelector('h1,h2,h3,h4,h5,[class*="header" i],[class*="title" i],[class*="heading" i]');
      if (!hdr) return;
      var h = hdr.textContent.toLowerCase();
      Object.keys(SECTIES).some(function (s) {
        if (!SECTIES[s].some(function (kw) { return h.indexOf(kw) !== -1; })) return false;
        var t = text(panel);
        if (t.length > 20) {
          gepakt.push(panel);
          out.secties[s] = (out.secties[s] ? out.secties[s] + '\n' : '') + t;
        }
        return true;
      });
    });
    if (!Object.keys(out.secties).length) {
      var main = document.querySelector('main,[role="main"]');
      var rest = main && zichtbaar(main) ? text(main) : pagina;
      if (rest.length > 40) out.secties['Dossier (pagina)'] = rest.slice(0, maxPagina || 40000);
    }
    return out;
  }

  // Reads the open patient from the Bricks tab in this window, all frames
  // merged. Also used by Dossiervraag (with a larger page limit).
  async function leesBricks(maxPagina, breed) {
    var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    var tab = tabs[0];
    if (!tab || !/^https?:/.test(tab.url || '')) throw new Error('Open eerst de patiënt in Bricks in dit venster.');
    var results = await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, func: scrapeFrame, args: [maxPagina || 40000, !!breed] })
      .catch(function (e) { throw new Error('Geen toegang tot deze pagina (' + e.message + ').'); });
    var merged = {}, naam = '', geboren = '';
    (results || []).forEach(function (r) {
      var v = r && r.result;
      if (!v) return;
      if (v.naam && !naam) { naam = v.naam; geboren = v.geboren || ''; }
      Object.keys(v.secties).forEach(function (k) {
        if (merged[k] && merged[k].indexOf(v.secties[k]) !== -1) return;   // same frame read twice
        merged[k] = merged[k] ? merged[k] + '\n' + v.secties[k] : v.secties[k];
      });
    });
    // A section found by heading beats the whole-page fallback.
    if (Object.keys(merged).length > 1) delete merged['Dossier (pagina)'];
    if (!Object.keys(merged).length) throw new Error('Weinig tekst gevonden. Is het dossier volledig geladen?');
    return { secties: merged, naam: naam, geboren: geboren };
  }
  window.SVBricksDossier = { lees: leesBricks };

  // For a letter: the recognised sections, and when the journal is missing or
  // thin, also everything in view (like Dossiervraag), so history, findings and
  // policy are not lost. The doctor can switch either off under "Onderdelen".
  async function leesVoorBrief() {
    var d = await leesBricks().catch(function () { return { secties: {}, naam: '', geboren: '' }; });
    if (SVBrief.journaalGenoeg(d.secties)) return d;
    var breed = await leesBricks(40000, true).catch(function () { return null; });
    var alles = breed && breed.secties['Dossier (in beeld)'];
    if (!alles) {
      if (!Object.keys(d.secties).length) throw new Error('Weinig tekst gevonden. Is het dossier volledig geladen?');
      return d;
    }
    d.secties['Dossier (in beeld)'] = SVDossiervraag.ontdubbel(alles);
    return { secties: d.secties, naam: d.naam || breed.naam, geboren: d.geboren || breed.geboren };
  }

  $('lt-scrape').addEventListener('click', async function () {
    var btn = this;
    btn.disabled = true; status('Dossier ophalen…');
    try {
      var d = await leesVoorBrief();
      setDossier(d.secties, d.naam, 'Bricks', d.geboren);
      status('Dossier opgehaald: ' + Object.keys(d.secties).join(', ') + '. Controleer de naam en de onderdelen.');
    } catch (e) {
      status(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  // ── Dossier: screenshot ──
  function readImageFromClipboardEvent(e) {
    var items = (e.clipboardData && e.clipboardData.items) || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image/') === 0) return items[i].getAsFile();
    }
    return null;
  }
  function fileToImage(file) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () {
        var url = r.result;
        resolve({ url: url, media_type: url.slice(5, url.indexOf(';')), data: url.split(',')[1] });
      };
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }
  function zetAfbeelding(img) {
    lt.shot = img;
    $('lt-shot-img').src = img.url;
    $('lt-shot-img').classList.remove('hidden');
    $('lt-shot-read').classList.remove('hidden');
    $('lt-dossier-meer').open = true;
    var seg = document.querySelector('#lt-src [data-src="shot"]');
    if (seg) seg.click();
  }
  // A photo from the phone (telefoon-ui.js) lands here as a screenshot.
  window.SVLetters = { zetAfbeelding: function (img) {
    zetAfbeelding(img);
    status('Foto van de telefoon staat klaar. Klik "Lees schermafdruk" om hem uit te lezen.');
  } };
  $('lt-shot-drop').addEventListener('click', function () { this.focus(); });
  $('lt-shot-drop').addEventListener('paste', async function (e) {
    var f = readImageFromClipboardEvent(e);
    if (!f) { status('Geen afbeelding op het klembord.', true); return; }
    e.preventDefault();
    zetAfbeelding(await fileToImage(f));
    status('Schermafdruk geplakt. Klik "Lees schermafdruk".');
  });

  function parseSections(tekst) {
    var titels = ['Journaal', 'Medicatie', 'Voorgeschiedenis', 'Lab', 'Metingen', 'Allergieën', 'Correspondentie', 'Problemen'];
    var secties = {}, huidig = 'Dossier', buf = [];
    tekst.split('\n').forEach(function (lijn) {
      var kaal = lijn.replace(/[#*:=\-_]/g, '').trim().toLowerCase();
      var hit = kaal.length < 40 && titels.find(function (t) { return kaal.indexOf(t.toLowerCase()) === 0; });
      if (hit) {
        if (buf.join('').trim()) secties[huidig] = (secties[huidig] ? secties[huidig] + '\n' : '') + buf.join('\n').trim();
        huidig = hit; buf = [];
      } else {
        buf.push(lijn);
      }
    });
    if (buf.join('').trim()) secties[huidig] = (secties[huidig] ? secties[huidig] + '\n' : '') + buf.join('\n').trim();
    return secties;
  }

  async function extractImage(kind, img) {
    var resp = await api('/api/v1/letters/extract', { kind: kind, media_type: img.media_type, data: img.data });
    return (await resp.json()).text || '';
  }

  $('lt-shot-read').addEventListener('click', async function () {
    if (!lt.shot) return;
    var btn = this; btn.disabled = true; status('Schermafdruk lezen…');
    try {
      var tekst = await extractImage('dossier', lt.shot);
      var erbij = voegToe(parseSections(tekst), 'schermafdruk');
      status('Schermafdruk gelezen' + (erbij ? ' en toegevoegd aan het opgehaalde dossier' : '') + '. Controleer de onderdelen.');
    } catch (e) {
      status(e.message, true);
    } finally { btn.disabled = false; }
  });

  // ── PDF ──
  async function readPdf(file) {
    if (typeof pdfjsLib === 'undefined') throw new Error('PDF-lezer niet geladen.');
    var pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    var parts = [];
    for (var i = 1; i <= pdf.numPages; i++) {
      var page = await pdf.getPage(i);
      var content = await page.getTextContent();
      var line = [], lines = [], lastY = null;
      content.items.forEach(function (it) {
        var y = it.transform ? Math.round(it.transform[5]) : null;
        if (lastY !== null && y !== null && Math.abs(y - lastY) > 2) { lines.push(line.join(' ')); line = []; }
        line.push(it.str); lastY = y;
      });
      lines.push(line.join(' '));
      parts.push(lines.join('\n'));
    }
    return parts.join('\n\n').replace(/[ \t]+\n/g, '\n');
  }
  function wireDrop(zoneId, inputId, onFile) {
    var zone = $(zoneId), input = $(inputId);
    zone.addEventListener('click', function () { input.click(); });
    input.addEventListener('change', function () { if (input.files[0]) onFile(input.files[0]); input.value = ''; });
    ['dragenter', 'dragover'].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add('over'); });
    });
    zone.addEventListener('dragleave', function () { zone.classList.remove('over'); });
    zone.addEventListener('drop', function (e) {
      e.preventDefault(); zone.classList.remove('over');
      var f = e.dataTransfer.files[0];
      if (f && f.type === 'application/pdf') onFile(f);
      else status('Alleen PDF-bestanden.', true);
    });
  }
  wireDrop('lt-pdf-drop', 'lt-pdf-file', async function (file) {
    status('PDF lezen…');
    try {
      var tekst = await readPdf(file);
      if (tekst.replace(/\s/g, '').length < 30) throw new Error('Deze PDF bevat geen leesbare tekst (gescand?). Gebruik een schermafdruk.');
      var erbij = voegToe(parseSections(tekst), 'PDF ' + file.name);
      status('PDF gelezen (' + Math.round(tekst.length / 1000) + 'k tekens)' + (erbij ? ', toegevoegd aan het opgehaalde dossier.' : '.'));
    } catch (e) { status('PDF: ' + e.message, true); }
  });

  // ── Request (vraag) ──
  $('lt-vraag-pdf').addEventListener('click', function () { $('lt-vraag-file').click(); });
  $('lt-vraag-file').addEventListener('change', async function () {
    var f = this.files[0]; this.value = '';
    if (!f) return;
    status('Vraag-PDF lezen…');
    try {
      $('lt-vraag').value = await readPdf(f);
      status('Vraag geladen uit ' + f.name + '. Controleer en verwijder wat niet nodig is.');
    } catch (e) { status('PDF: ' + e.message, true); }
  });
  $('lt-vraag-shot').addEventListener('click', async function () {
    var btn = this; btn.disabled = true; status('Klembord lezen…');
    try {
      var items = await navigator.clipboard.read();
      var blob = null;
      for (var i = 0; i < items.length && !blob; i++) {
        var type = items[i].types.find(function (t) { return t.indexOf('image/') === 0; });
        if (type) blob = await items[i].getType(type);
      }
      if (!blob) throw new Error('Geen afbeelding op het klembord. Maak eerst een schermafdruk van de brief.');
      status('Schermafdruk lezen…');
      $('lt-vraag').value = await extractImage('vraag', await fileToImage(blob));
      status('Vraag gelezen. Controleer de tekst.');
    } catch (e) { status(e.message, true); } finally { btn.disabled = false; }
  });

  $('lt-reden-from-dictate').addEventListener('click', function () {
    var t = (els.text && els.text.value || '').trim();
    if (!t) { status('Er staat nog geen dictaat in het tabblad Consult.', true); return; }
    $('lt-reden').value = t;
  });

  // ── Generate ──
  $('lt-generate').addEventListener('click', async function () {
    if (lt.busy) return;
    // No dossier yet: fetch what is open in Bricks now, in the same click.
    if (!Object.keys(lt.secties).length) {
      status('Dossier ophalen uit Bricks…');
      try {
        var opgehaald = await leesVoorBrief();
        setDossier(opgehaald.secties, opgehaald.naam, 'Bricks', opgehaald.geboren);
      } catch (e) {
        status(e.message + ' Open de patiënt in Bricks, of voeg een PDF of schermafdruk toe.', true);
        $('lt-dossier-meer').open = true;
        return;
      }
    }
    var dossier = dossierTekst();
    if (!Object.keys(lt.aan).some(function (k) { return lt.aan[k]; })) {
      $('lt-dossier-meer').open = true;
      status('Er staat geen onderdeel van het dossier aan. Zet er minstens één aan.', true); return;
    }
    // The frame of an information letter (which complaints, which period) goes
    // to the letter as an explicit instruction, before any free remark.
    var kader = [];
    if (lt.kind === 'informatiebrief') {
      var onderwerp = $('lt-onderwerp').value.trim(), periode = $('lt-periode').value.trim();
      if (onderwerp) kader.push('Beperk de brief tot: ' + onderwerp + '. Noem niets over andere klachten.');
      if (periode) kader.push('Beperk de brief tot de periode ' + periode + '.');
    }
    var extra = SVPrivacy.filter(kader.concat([$('lt-extra').value.trim()]).filter(Boolean).join(' '), filterOpts()).trim();
    var body = { kind: lt.kind, initialen: lt.initialen, dossier: dossier, extra: extra || null };
    if (lt.kind === 'informatiebrief') {
      if (!$('lt-consent').checked) { status('Vink aan dat er een gerichte vraag en toestemming van de patiënt is.', true); return; }
      body.aanvrager = lt.aanvrager;
      body.vraag = SVPrivacy.filter($('lt-vraag').value, filterOpts()).trim() || null;
      body.toestemming = true;
    } else if (lt.kind === 'verklaring') {
      if (!$('lt-verkl-ok').checked) { status('Vink aan dat de patiënt om deze brief vraagt.', true); return; }
      body.doel = $('lt-doel').value;
      body.vraag = SVPrivacy.filter($('lt-verkl-vraag').value, filterOpts()).trim() || null;
      body.toestemming = true;
    } else {
      var spec = lt.spec || $('lt-spec-free').value.trim();
      var reden = SVPrivacy.filter($('lt-reden').value, filterOpts()).trim();
      if (!reden) { status('Vul de reden van verwijzing in.', true); return; }
      body.specialisme = spec || 'medisch specialist';
      body.urgentie = lt.urgentie;
      body.reden = reden;
    }

    var btn = this, label = btn.textContent;
    lt.busy = true; btn.disabled = true; btn.textContent = 'Bezig met schrijven…';
    status('');
    var out = $('lt-out');
    out.textContent = '';
    $('lt-output').classList.remove('hidden');
    try {
      var resp = await api('/api/v1/letters/generate', body);
      var reader = resp.body.getReader(), dec = new TextDecoder();
      for (;;) {
        var chunk = await reader.read();
        if (chunk.done) break;
        out.textContent += dec.decode(chunk.value, { stream: true });
        out.scrollTop = out.scrollHeight;
      }
      // Plain text for Bricks and mail; then say what is still open.
      out.textContent = SVBrief.schoon(out.textContent);
      lt.concept = { soort: body.kind, tekst: out.textContent };
      var open = SVBrief.openPlekken(out.textContent).filter(function (x) { return !/^\[Naam huisarts\]$/i.test(x); });
      status(open.length
        ? 'Concept klaar. Nog invullen: ' + open.join(' · ') + '. Controleer de brief voordat je hem verstuurt.'
        : 'Concept klaar. Controleer de brief voordat je hem verstuurt.', false);
    } catch (e) {
      if (!out.textContent) $('lt-output').classList.add('hidden');
      status(e.message, true);
    } finally {
      lt.busy = false; btn.disabled = false; btn.textContent = label;
    }
  });

  // The letter as the doctor sends it: learn from what was changed, once per concept.
  function leer() {
    var c = lt.concept;
    if (!c || c.geleerd || !window.SVLerenUI) return;
    c.geleerd = true;
    window.SVLerenUI.naBrief(c.soort, c.tekst, $('lt-out').innerText.trim());
  }

  $('lt-copy').addEventListener('click', async function () {
    leer();
    await navigator.clipboard.writeText($('lt-out').innerText);
    status('Gekopieerd.');
  });
  $('lt-insert').addEventListener('click', async function () {
    leer();
    var res = await insertOrCopy($('lt-out').innerText);
    if (res && res.ok) status('Ingevoegd in het veld.');
    else status(((res && res.error) || 'Invoegen lukte niet') + ' De brief staat op het klembord; plak met Ctrl+V.', true);
  });
  $('lt-new').addEventListener('click', function () {
    lt.concept = null;
    $('lt-output').classList.add('hidden');
    $('lt-out').textContent = '';
    ['lt-vraag', 'lt-reden', 'lt-extra', 'lt-onderwerp', 'lt-periode', 'lt-verkl-vraag'].forEach(function (id) { $(id).value = ''; });
    $('lt-consent').checked = false;
    $('lt-verkl-ok').checked = false;
    status('');
  });
})();

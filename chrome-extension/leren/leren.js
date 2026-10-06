/**
 * VitaScribe - Pagina "Wat VitaScribe leerde": de regels van deze arts, met
 * aan/uit en weghalen, zelf toevoegen, en de meting per week.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var TALEN = { 'ar-MA': 'Marokkaans-Arabisch', 'ar-SY': 'Syrisch-Arabisch', ar: 'Arabisch', tr: 'Turks', pl: 'Pools',
    uk: 'Oekraïens', de: 'Duits', fr: 'Frans', en: 'Engels' };

  function status(msg, fout) {
    $('status').textContent = msg || '';
    $('status').classList.toggle('fout', !!fout);
  }

  async function aanvraag(pad, body) {
    var c = await SVInstellingen.lees(['apiUrl', 'apiKey']);
    var url = (c.apiUrl || 'http://localhost:8002').replace(/\/$/, '');
    var headers = { 'Content-Type': 'application/json' };
    if (c.apiKey) headers['X-API-Key'] = c.apiKey.trim();
    await SVPraktijk.metKop(headers);
    var resp = await fetch(url + pad, body ? { method: 'POST', headers: headers, body: JSON.stringify(body) } : { headers: headers });
    if (!resp.ok) {
      var d = await resp.json().catch(function () { return {}; });
      throw new Error(typeof d.detail === 'string' ? d.detail : 'Server gaf fout ' + resp.status + '.');
    }
    return resp.json();
  }

  function el(tag, cls, tekst) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (tekst !== undefined) e.textContent = tekst;
    return e;
  }

  function knop(label, cls, fn) {
    var b = el('button', 'btn klein' + (cls ? ' ' + cls : ''), label);
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }

  async function zet(r, status_) {
    try {
      await aanvraag('/api/v1/leren/regel/' + r.id, { status: status_ });
      laad();
    } catch (e) { status(e.message, true); }
  }

  function regelItem(r) {
    var li = el('li', r.status === 'voorstel' ? 'voorstel' : '');
    var tekst = el('span', 'tekst', r.regel);
    tekst.dir = 'auto';
    li.appendChild(tekst);
    li.appendChild(el('span', 'tag', r.status === 'voorstel' ? 'voorstel · ' + r.aantal + '×' : r.aantal + '×'));
    if (r.status === 'voorstel') li.appendChild(knop('✓ Onthoud', 'aan', function () { zet(r, 'actief'); }));
    else li.appendChild(knop('Uit', '', function () { zet(r, 'afgewezen'); }));
    li.appendChild(knop('Weg', '', function () {
      if (window.confirm('Deze regel weghalen?')) zet(r, 'weg');
    }));
    return li;
  }

  function vul(lijst, regels, leeg) {
    lijst.textContent = '';
    if (!regels.length) { lijst.appendChild(el('li', 'leeg', leeg)); return; }
    regels.forEach(function (r) { lijst.appendChild(regelItem(r)); });
  }

  function grafiek(weken) {
    var met = weken.filter(function (w) { return w.gewijzigdGem !== null; }).slice(-16);
    var doos = $('grafiek');
    doos.textContent = '';
    if (!met.length) { doos.appendChild(el('p', 'leeg', 'Nog geen consulten gemeten.')); return; }
    var B = 640, H = 160, onder = 22, max = Math.max(10, Math.max.apply(null, met.map(function (w) { return w.gewijzigdGem; })));
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + B + ' ' + H);
    var stap = B / met.length;
    met.forEach(function (w, i) {
      var h = (w.gewijzigdGem / max) * (H - onder - 14);
      var r = document.createElementNS(ns, 'rect');
      r.setAttribute('class', 'staaf');
      r.setAttribute('x', i * stap + stap * 0.18);
      r.setAttribute('y', H - onder - h);
      r.setAttribute('width', stap * 0.64);
      r.setAttribute('height', Math.max(1, h));
      var t = document.createElementNS(ns, 'title');
      t.textContent = 'Week van ' + w.label + ': ' + w.gewijzigdGem + '% aangepast, ' + w.consulten + ' consulten';
      r.appendChild(t);
      svg.appendChild(r);
      var waarde = document.createElementNS(ns, 'text');
      waarde.setAttribute('x', i * stap + stap / 2);
      waarde.setAttribute('y', H - onder - h - 3);
      waarde.setAttribute('text-anchor', 'middle');
      waarde.textContent = w.gewijzigdGem + '%';
      svg.appendChild(waarde);
      var lab = document.createElementNS(ns, 'text');
      lab.setAttribute('x', i * stap + stap / 2);
      lab.setAttribute('y', H - 6);
      lab.setAttribute('text-anchor', 'middle');
      lab.textContent = w.label;
      svg.appendChild(lab);
    });
    var as = document.createElementNS(ns, 'line');
    as.setAttribute('class', 'as');
    as.setAttribute('x1', 0); as.setAttribute('x2', B);
    as.setAttribute('y1', H - onder); as.setAttribute('y2', H - onder);
    svg.appendChild(as);
    doos.appendChild(svg);
  }

  function tabel(weken) {
    var t = $('weken');
    t.textContent = '';
    if (!weken.length) return;
    var kop = el('tr');
    ['Week van', 'Consulten', '% aangepast', 'Markeringen', 'Tolkgesprekken', 'Eenvoudiger per gesprek'].forEach(function (k) { kop.appendChild(el('th', '', k)); });
    t.appendChild(kop);
    weken.slice(-12).reverse().forEach(function (w) {
      var rij = el('tr');
      [w.label, w.consulten, w.gewijzigdGem === null ? '–' : w.gewijzigdGem + '%', w.markeringenGem === null ? '–' : w.markeringenGem,
        w.gesprekken, w.eenvoudigerGem === null ? '–' : w.eenvoudigerGem].forEach(function (v) { rij.appendChild(el('td', '', String(v))); });
      t.appendChild(rij);
    });
  }

  async function laad() {
    try {
      var d = await aanvraag('/api/v1/leren/overzicht');
      var g = SVLeren.groepen(d.regels);
      vul($('lijst-soep'), g.soep, 'Nog niets geleerd. Pas een verslag aan en voeg het in; dan doet VitaScribe hier voorstellen.');
      vul($('lijst-woord'), g.woord, 'Nog geen woorden.');
      vul($('lijst-econsult'), g.econsult, 'Nog niets geleerd. Pas een concept-antwoord aan en zet het in Bricks; dan doet VitaScribe hier voorstellen.');
      var tolk = $('lijst-tolk');
      tolk.textContent = '';
      var talen = Object.keys(g.tolk);
      if (!talen.length) tolk.appendChild(el('p', 'leeg', 'Nog geen afspraken. Ze ontstaan als je de tolk iets eenvoudiger laat zeggen.'));
      talen.forEach(function (taal) {
        tolk.appendChild(el('p', 'taal', TALEN[taal] || taal));
        var ul = el('ul', 'regels');
        vul(ul, g.tolk[taal], '');
        tolk.appendChild(ul);
      });
      var weken = SVLeren.perWeek(d.meting);
      $('trend').textContent = SVLeren.trend(weken);
      grafiek(weken);
      tabel(weken);
      $('opslag').textContent = d.opslag === 'geheugen'
        ? 'Let op: de server heeft geen register; wat geleerd is, verdwijnt bij een herstart.' : '';
      status('');
    } catch (e) {
      status(e.message, true);
    }
  }

  document.querySelectorAll('form.toevoegen').forEach(function (f) {
    f.addEventListener('submit', async function (e) {
      e.preventDefault();
      var body = { soort: f.dataset.soort };
      new FormData(f).forEach(function (v, k) { body[k] = String(v).trim(); });
      try {
        await aanvraag('/api/v1/leren/regel', body);
        f.reset();
        laad();
      } catch (err) { status(err.message, true); }
    });
  });

  laad();
})();

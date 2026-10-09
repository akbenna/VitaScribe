/*
 * VitaScribe beheer: praktijken, gebruikers en licenties.
 *
 * Alles wat van een praktijk komt (een aanmelding kan iedereen doen) gaat als
 * tekst de pagina in, nooit als HTML: el() zet textContent, er is geen
 * innerHTML met gegevens. Inloggen geeft een sessie; alleen die staat in
 * sessionStorage van dit tabblad en verdwijnt als het tabblad sluit. De
 * beheersleutel zelf wordt nergens bewaard.
 */
(function () {
  'use strict';

  var API = '/api/v1/beheer';
  var OPSLAG = 'vs-beheersessie';
  var TYPES = { kandidaat: 'Kandidaat', pilot: 'Gratis pilot', betaald: 'Betaald', intern: 'Eigen praktijk / intern' };
  var STATUS = { aangemeld: 'Aangemeld', actief: 'Actief', uitgehaald: 'Uitgehaald', afgewezen: 'Afgewezen' };
  var AANBIEDER = { anthropic: 'Claude', openai: 'ChatGPT', deepgram: 'Deepgram' };

  var staat = { praktijken: [], vandaag: '', filter: 'aangemeld', zoek: '', gekozen: null, gebruikers: [], instellingen: {} };
  var app = document.getElementById('app');

  // ── Hulpjes ──

  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'tekst') node.textContent = v;
        else if (k === 'klik') node.addEventListener('click', v);
        else if (k === 'bij') node.addEventListener('change', v);
        else if (k === 'invoer') node.addEventListener('input', v);
        else if (k === 'klasse') node.className = v;
        else if (k === 'waarde') node.value = v;
        else if (k === 'aan') node.checked = !!v;
        else node.setAttribute(k, v === true ? '' : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) {
      var kind = arguments[i];
      if (kind === null || kind === undefined || kind === false) continue;
      if (Array.isArray(kind)) kind.forEach(function (k) { if (k) node.appendChild(typeof k === 'string' ? document.createTextNode(k) : k); });
      else node.appendChild(typeof kind === 'string' ? document.createTextNode(kind) : kind);
    }
    return node;
  }

  function leeg(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  var meldingTimer;
  function meld(tekst, fout) {
    var m = document.getElementById('melding');
    m.textContent = tekst;
    m.className = 'melding' + (fout ? ' fout' : '');
    m.style.display = 'block';
    clearTimeout(meldingTimer);
    meldingTimer = setTimeout(function () { m.style.display = 'none'; }, fout ? 6000 : 3000);
  }

  function datum(iso) {
    if (!iso) return '';
    var d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso);
    return d.toLocaleDateString('nl-NL', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }

  function moment(iso) {
    if (!iso) return 'nooit';
    var d = new Date(iso);
    return d.toLocaleDateString('nl-NL', { day: '2-digit', month: '2-digit' }) + ' ' +
      d.toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' });
  }

  function dagenTot(iso) {
    if (!iso) return null;
    var a = new Date(staat.vandaag + 'T12:00:00'), b = new Date(iso + 'T12:00:00');
    return Math.round((b - a) / 86400000);
  }

  function euro(n) { return '€ ' + Math.round(n).toLocaleString('nl-NL'); }

  function sessie() { try { return sessionStorage.getItem(OPSLAG) || ''; } catch (e) { return ''; } }

  async function vraag(pad, opties) {
    opties = opties || {};
    var kop = { 'X-Beheer-Sessie': sessie() };
    if (opties.body !== undefined) kop['Content-Type'] = 'application/json';
    var r = await fetch(API + pad, {
      method: opties.methode || 'GET',
      headers: kop,
      body: opties.body !== undefined ? JSON.stringify(opties.body) : undefined,
    });
    if (r.status === 401) {
      try { sessionStorage.removeItem(OPSLAG); } catch (e) { /* niets */ }
      if (pad !== '/praktijken') inlogscherm('De sessie is verlopen. Log opnieuw in.');
      throw new Error('sessie');
    }
    var body = await r.json().catch(function () { return {}; });
    if (!r.ok) {
      var d = body.detail;
      if (Array.isArray(d)) d = d.map(function (x) { return x.msg; }).join('; ');
      throw new Error(d || ('Fout ' + r.status));
    }
    return body;
  }

  // ── Inloggen ──

  function inlogscherm(fout) {
    document.getElementById('uitloggen').hidden = true;
    leeg(app);
    var invoer = el('input', { type: 'password', id: 'beheersleutel', autocomplete: 'current-password', placeholder: 'Beheersleutel' });
    var code = el('input', { type: 'text', id: 'beheercode', autocomplete: 'one-time-code', inputmode: 'numeric', placeholder: 'Code uit de app (6 cijfers)' });
    var knop = el('button', { klasse: 'hoofd', tekst: 'Openen' });
    async function probeer() {
      try {
        var r = await fetch(API + '/inloggen', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sleutel: invoer.value.trim(), code: code.value.trim() }),
        });
        var body = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(body.detail || ('Fout ' + r.status));
        try { sessionStorage.setItem(OPSLAG, body.sessie); } catch (e) { /* privévenster */ }
        await laad();
      } catch (e) { inlogscherm(e.message === 'sessie' ? 'De sessie is verlopen. Log opnieuw in.' : e.message); }
    }
    knop.addEventListener('click', probeer);
    [invoer, code].forEach(function (veld) { veld.addEventListener('keydown', function (e) { if (e.key === 'Enter') probeer(); }); });
    app.appendChild(el('div', { klasse: 'kaart inlog' },
      el('h2', { tekst: 'Beheer openen' }),
      el('p', { klasse: 'klein', tekst: 'Vul je beheersleutel in en, als tweestapsverificatie aan staat, de code uit je authenticator-app. De sleutel wordt niet bewaard; het tabblad krijgt een sessie die na een werkdag verloopt.' }),
      invoer, code,
      fout ? el('p', { klasse: 'klein', style: 'color:var(--rood);margin-top:8px', tekst: fout }) : null,
      el('div', { klasse: 'knoppen' }, knop)));
    invoer.focus();
  }

  document.getElementById('uitloggen').addEventListener('click', function () {
    fetch(API + '/uitloggen', { method: 'POST', headers: { 'X-Beheer-Sessie': sessie() } }).catch(function () { /* niets */ });
    try { sessionStorage.removeItem(OPSLAG); } catch (e) { /* niets */ }
    staat.gekozen = null;
    inlogscherm();
  });

  // ── Gegevens ──

  async function laad() {
    var r = await vraag('/praktijken');
    staat.praktijken = r.praktijken;
    staat.vandaag = r.vandaag;
    try { staat.instellingen = await vraag('/instellingen'); } catch (e) { staat.instellingen = {}; }
    document.getElementById('uitloggen').hidden = false;
    teken();
  }

  async function ververs() {
    var r = await vraag('/praktijken');
    staat.praktijken = r.praktijken;
    staat.vandaag = r.vandaag;
    if (staat.gekozen) {
      var g = await vraag('/praktijken/' + staat.gekozen + '/gebruikers');
      staat.gebruikers = g.gebruikers;
    }
    teken();
  }

  function praktijk(id) {
    return staat.praktijken.filter(function (p) { return p.id === id; })[0] || null;
  }

  // ── Tekenen ──

  function geldigheid(p) {
    if (p.status !== 'actief') return el('span', { klasse: 'label', tekst: STATUS[p.status] });
    if (!p.geldig_tot) return el('span', { klasse: 'label blauw', tekst: 'Onbeperkt' });
    var n = dagenTot(p.geldig_tot);
    if (n < 0) return el('span', { klasse: 'label rood', tekst: 'Verlopen ' + datum(p.geldig_tot) });
    if (n <= 30) return el('span', { klasse: 'label amber', tekst: 'Tot ' + datum(p.geldig_tot) });
    return el('span', { klasse: 'label groen', tekst: 'Tot ' + datum(p.geldig_tot) });
  }

  function tegels() {
    var ps = staat.praktijken;
    var aangemeld = ps.filter(function (p) { return p.status === 'aangemeld'; }).length;
    var actief = ps.filter(function (p) { return p.status === 'actief'; });
    var gebruikers = actief.reduce(function (s, p) { return s + (p.gebruikers_actief || 0); }, 0);
    var bijnaOp = actief.filter(function (p) { var n = dagenTot(p.geldig_tot); return n !== null && n <= 30; }).length;
    var tarief = staat.instellingen.tarief_per_fte;
    var omzet = 0, indicatief = 0;
    if (tarief) {
      actief.forEach(function (p) {
        var fte = p.fte || 0;
        if (p.licentietype === 'betaald') omzet += fte * tarief;
        else if (p.licentietype === 'pilot') indicatief += fte * tarief;
      });
    }
    return el('div', { klasse: 'tegels' },
      el('div', { klasse: 'tegel' }, el('b', { tekst: String(aangemeld) }), el('span', { tekst: 'nieuwe aanmeldingen' })),
      el('div', { klasse: 'tegel' }, el('b', { tekst: String(actief.length) }), el('span', { tekst: 'actieve praktijken' })),
      el('div', { klasse: 'tegel' }, el('b', { tekst: String(gebruikers) }), el('span', { tekst: 'actieve gebruikers' })),
      el('div', { klasse: 'tegel' }, el('b', { tekst: String(bijnaOp) }), el('span', { tekst: 'verlopen binnen 30 dagen' })),
      tarief ? el('div', { klasse: 'tegel' }, el('b', { tekst: euro(omzet) }),
        el('span', { tekst: 'licentie-omzet per jaar' + (indicatief ? ', pilots samen ' + euro(indicatief) : '') })) : null);
  }

  function lijst() {
    var zoek = staat.zoek.toLowerCase();
    var rijen = staat.praktijken.filter(function (p) {
      if (staat.filter === 'aangemeld' && p.status !== 'aangemeld') return false;
      if (staat.filter === 'actief' && p.status !== 'actief') return false;
      if (staat.filter === 'uit' && ['uitgehaald', 'afgewezen'].indexOf(p.status) === -1) return false;
      if (!zoek) return true;
      return [p.naam, p.plaats, (p.praktijknummers || []).join(' '), p.contact_naam, p.contact_email]
        .join(' ').toLowerCase().indexOf(zoek) !== -1;
    });
    function chip(waarde, tekst) {
      return el('button', { klasse: 'chip' + (staat.filter === waarde ? ' aan' : ''), tekst: tekst,
        klik: function () { staat.filter = waarde; teken(); } });
    }
    var zoekveld = el('input', { type: 'search', placeholder: 'Zoek op naam, plaats of praktijknummer', waarde: staat.zoek,
      invoer: function (e) { staat.zoek = e.target.value; tekenLijstAlleen(); } });
    var tabel = el('table', null,
      el('thead', null, el('tr', null, el('th', { tekst: 'Praktijk' }), el('th', { tekst: 'Type' }), el('th', { tekst: 'Licentie' }),
        el('th', { tekst: 'Gebruikers' }), el('th', { tekst: 'Laatst gebruikt' }))),
      el('tbody', null, rijen.map(function (p) {
        return el('tr', { klasse: 'rij' + (staat.gekozen === p.id ? ' gekozen' : ''), klik: function () { kies(p.id); } },
          el('td', null, el('div', { tekst: p.naam }), el('div', { klasse: 'klein', tekst: [p.plaats, (p.praktijknummers || []).join(', ')].filter(Boolean).join(' · ') })),
          el('td', null, el('span', { klasse: 'label', tekst: TYPES[p.licentietype] || p.licentietype })),
          el('td', null, geldigheid(p)),
          el('td', { tekst: (p.gebruikers_actief || 0) + ' / ' + (p.gebruikers_totaal || 0) }),
          el('td', { klasse: 'klein', tekst: moment(p.laatst_gebruikt) }));
      })));
    return el('div', { klasse: 'kaart', id: 'lijst' },
      el('div', { klasse: 'balk' }, chip('aangemeld', 'Aanmeldingen'), chip('actief', 'Actief'), chip('uit', 'Uitgehaald of afgewezen'), chip('alle', 'Alle'),
        el('span', { style: 'flex:1' }), zoekveld,
        el('button', { tekst: 'Nieuwe praktijk', klik: nieuwePraktijk })),
      rijen.length ? tabel : el('div', { klasse: 'leeg', tekst: staat.filter === 'aangemeld' ? 'Geen nieuwe aanmeldingen.' : 'Geen praktijken in deze lijst.' }));
  }

  function tekenLijstAlleen() {
    var oud = document.getElementById('lijst');
    if (!oud) return teken();
    var nieuw = lijst();
    oud.parentNode.replaceChild(nieuw, oud);
    var z = nieuw.querySelector('input[type=search]');
    z.focus();
    z.setSelectionRange(z.value.length, z.value.length);
  }

  function veld(label, invoer, breed) {
    return el('div', { klasse: breed ? 'breed' : null }, el('label', { tekst: label }), invoer);
  }

  function detail() {
    var p = praktijk(staat.gekozen);
    if (!p) return el('div', { klasse: 'kaart leeg', tekst: 'Kies een praktijk om de licentie en de gebruikers te beheren.' });

    var v = {};
    function invoer(naam, type, extra) {
      var ruw = p[naam] === null || p[naam] === undefined ? '' : String(p[naam]);
      if (naam === 'fte') ruw = ruw.replace('.', ',');
      var node = el('input', Object.assign({ type: type || 'text', waarde: ruw }, extra || {}));
      v[naam] = node;
      return node;
    }
    v.praktijknummers = el('input', { waarde: (p.praktijknummers || []).join(', '), placeholder: '2876' });
    v.licentietype = el('select', null, Object.keys(TYPES).map(function (k) { return el('option', { value: k, tekst: TYPES[k], selected: p.licentietype === k }); }));
    v.status = el('select', null, Object.keys(STATUS).map(function (k) { return el('option', { value: k, tekst: STATUS[k], selected: p.status === k }); }));
    v.geldig_tot = el('input', { type: 'date', waarde: p.geldig_tot || '' });
    v.onbeperkt = el('input', { type: 'checkbox', aan: !p.geldig_tot && p.licentietype === 'intern' });
    v.verplicht = el('input', { type: 'checkbox', aan: p.eigen_sleutels_verplicht });
    v.eu = el('input', { type: 'checkbox', aan: p.brieven_in_eu });
    v.alleenEu = el('input', { type: 'checkbox', aan: p.alleen_eu });
    v.notities = el('textarea', { rows: 3, waarde: p.notities || '' });

    async function opslaan(extra) {
      var nummers = v.praktijknummers.value.split(/[\s,;]+/).filter(Boolean);
      var body = {
        naam: v.naam.value.trim(), plaats: v.plaats.value.trim(), praktijknummers: nummers, agb: v.agb.value.trim(),
        contact_naam: v.contact_naam.value.trim(), contact_email: v.contact_email.value.trim(), telefoon: v.telefoon.value.trim(),
        fte: v.fte.value.trim() === '' ? null : Number(v.fte.value.trim().replace(',', '.')),
        werkplekken: v.werkplekken.value === '' ? null : Math.round(Number(v.werkplekken.value)),
        licentietype: v.licentietype.value, status: v.status.value, serienummer: v.serienummer.value.trim(),
        eigen_sleutels_verplicht: v.verplicht.checked, brieven_in_eu: v.eu.checked, alleen_eu: v.alleenEu.checked, notities: v.notities.value,
      };
      if (v.onbeperkt.checked) {
        if (body.licentietype !== 'intern' && !confirm('Een onbeperkte licentie is niet in te trekken door te laten verlopen. Alleen bedoeld voor de eigen praktijk. Toch opslaan?')) return;
        body.geldig_tot_leeg = true;
      } else if (v.geldig_tot.value) {
        body.geldig_tot = v.geldig_tot.value;
      }
      Object.assign(body, extra || {});
      if (body.status === 'actief' && !body.praktijknummers.length &&
          !confirm('Er staat geen praktijknummer bij. Dan werken de sleutels van deze praktijk bij elke praktijk in Bricks. Toch doorgaan?')) return;
      try { await vraag('/praktijken/' + p.id, { methode: 'PATCH', body: body }); meld('Opgeslagen.'); await ververs(); }
      catch (e) { meld(e.message, true); }
    }

    var acties = [el('button', { klasse: 'hoofd', tekst: 'Opslaan', klik: function () { opslaan(); } })];
    if (p.status !== 'actief') {
      acties.push(el('button', { tekst: 'Activeren als pilot (12 maanden)', klik: function () {
        v.licentietype.value = 'pilot'; v.status.value = 'actief';
        if (!v.geldig_tot.value) v.onbeperkt.checked = false;
        opslaan({ licentietype: 'pilot', status: 'actief' });
      } }));
    }
    if (p.status === 'actief' && p.geldig_tot) {
      acties.push(el('button', { tekst: 'Verlengen met 12 maanden', klik: async function () {
        try { await vraag('/praktijken/' + p.id + '/verlengen', { methode: 'POST' }); meld('Verlengd.'); await ververs(); }
        catch (e) { meld(e.message, true); }
      } }));
    }
    if (p.status === 'actief') {
      acties.push(el('button', { klasse: 'gevaar', tekst: 'Uithalen', klik: function () {
        if (confirm('Uithalen: alle sleutels van ' + p.naam + ' werken binnen een halve minuut niet meer. Doorgaan?')) opslaan({ status: 'uitgehaald' });
      } }));
    }
    if (p.status === 'aangemeld') {
      acties.push(el('button', { klasse: 'gevaar', tekst: 'Afwijzen', klik: function () {
        if (confirm('Deze aanmelding afwijzen?')) opslaan({ status: 'afgewezen' });
      } }));
    }

    var sleutels = (p.eigen_sleutels || []);
    return el('div', { klasse: 'kaart' },
      el('h2', { tekst: p.naam }),
      el('div', { klasse: 'klein', tekst: 'Aangemeld op ' + datum(p.aangemeld_op) + (p.serienummer ? ' · serienummer ' + p.serienummer : '') }),
      p.opmerking_aanmelding ? el('div', { klasse: 'aanmelding', tekst: 'Bij de aanmelding: ' + p.opmerking_aanmelding }) : null,
      el('div', { klasse: 'velden' },
        veld('Naam', invoer('naam')), veld('Plaats', invoer('plaats')),
        veld('Praktijknummer(s) in Bricks', v.praktijknummers), veld('AGB-code', invoer('agb')),
        veld('Contactpersoon', invoer('contact_naam')), veld('E-mail', invoer('contact_email', 'email')),
        veld('Telefoon', invoer('telefoon', 'tel')), veld('Serienummer', invoer('serienummer')),
        veld('Huisarts-FTE', invoer('fte', 'text', { inputmode: 'decimal' })), veld('Werkplekken', invoer('werkplekken', 'number', { step: '1', min: '0' })),
        veld('Licentietype', v.licentietype), veld('Status', v.status),
        veld('Geldig tot', v.geldig_tot),
        el('div', null, el('label', { tekst: ' ' }), el('label', { klasse: 'vink' }, v.onbeperkt, 'Onbeperkt (alleen eigen praktijk)')),
        el('div', { klasse: 'breed' }, el('label', { klasse: 'vink' }, v.verplicht, 'Eigen AI-sleutels verplicht: geen brieven of spraak op de sleutels van de server')),
        el('div', { klasse: 'breed' }, el('label', { klasse: 'vink' }, v.eu, 'Brieven in de EU: brieven naar Mistral (EU), ook als er een eigen sleutel in de VS is')),
        el('div', { klasse: 'breed' }, el('label', { klasse: 'vink' }, v.alleenEu, 'Alleen EU-modus: de Claude-modus wordt voor deze praktijk geweigerd (echte patiënten)')),
        veld('Notities', v.notities, true)),
      el('div', { klasse: 'knoppen' }, acties),
      el('h3', { tekst: 'Eigen AI-sleutels van de praktijk' }),
      sleutels.length
        ? el('table', null, el('tbody', null, sleutels.map(function (s) {
            return el('tr', null, el('td', { tekst: s.dienst === 'brieven' ? 'Brieven' : 'Spraak' }),
              el('td', { tekst: (AANBIEDER[s.aanbieder] || s.aanbieder) + ' …' + s.hint }),
              el('td', null, el('button', { klasse: 'gevaar', tekst: 'Verwijderen', klik: async function () {
                if (!confirm('De eigen ' + s.dienst + 'sleutel van deze praktijk verwijderen? Daarna loopt dit via de sleutel van de server' + (p.eigen_sleutels_verplicht ? ', maar eigen sleutels zijn verplicht, dus werkt het niet meer.' : '.'))) return;
                try { await vraag('/praktijken/' + p.id + '/sleutels/' + s.dienst, { methode: 'DELETE' }); await ververs(); }
                catch (e) { meld(e.message, true); }
              } })));
          })))
        : el('p', { klasse: 'klein', tekst: 'Geen. Brieven en spraak lopen via de sleutels van de server. De praktijkbeheerder stelt eigen sleutels in de extensie in.' }),
      gebruikersblok(p));
  }

  function gebruikersblok(p) {
    var naam = el('input', { placeholder: 'Naam, bijv. dr. J. Jansen' });
    var email = el('input', { type: 'email', placeholder: 'e-mail (optioneel)' });
    var rol = el('select', null, el('option', { value: 'gebruiker', tekst: 'Gebruiker' }), el('option', { value: 'praktijkbeheerder', tekst: 'Praktijkbeheerder' }));
    async function toevoegen() {
      if (!naam.value.trim()) { meld('Vul een naam in.', true); return; }
      try {
        var r = await vraag('/praktijken/' + p.id + '/gebruikers', { methode: 'POST', body: { naam: naam.value.trim(), email: email.value.trim(), rol: rol.value } });
        await ververs();
        toonSleutel(p, r.gebruiker, r.sleutel);
      } catch (e) { meld(e.message, true); }
    }
    return el('div', null,
      el('h3', { tekst: 'Gebruikers' }),
      staat.gebruikers.length ? el('table', null,
        el('thead', null, el('tr', null, el('th', { tekst: 'Naam' }), el('th', { tekst: 'Rol' }), el('th', { tekst: 'Sleutel' }), el('th', { tekst: 'Laatst' }), el('th'))),
        el('tbody', null, staat.gebruikers.map(function (g) {
          return el('tr', null,
            el('td', null, el('div', { tekst: g.naam }), g.email ? el('div', { klasse: 'klein', tekst: g.email }) : null),
            el('td', null, el('select', { bij: async function (e) {
                try { await vraag('/gebruikers/' + g.id, { methode: 'PATCH', body: { rol: e.target.value } }); meld('Rol gewijzigd.'); await ververs(); }
                catch (err) { meld(err.message, true); }
              } },
              el('option', { value: 'gebruiker', tekst: 'Gebruiker', selected: g.rol === 'gebruiker' }),
              el('option', { value: 'praktijkbeheerder', tekst: 'Praktijkbeheerder', selected: g.rol === 'praktijkbeheerder' }))),
            el('td', null, el('span', { klasse: 'label' + (g.actief ? ' groen' : ' rood'), tekst: (g.actief ? '…' + g.sleutel_hint : 'uit') })),
            el('td', { klasse: 'klein', tekst: moment(g.laatst_gezien) + (g.laatst_praktijknummer ? ' · ' + g.laatst_praktijknummer : '') }),
            el('td', null, el('div', { klasse: 'knoppen', style: 'margin:0' },
              el('button', { tekst: 'Nieuwe sleutel', klik: async function () {
                if (!confirm('Een nieuwe sleutel voor ' + g.naam + '? De huidige werkt dan niet meer.')) return;
                try { var r = await vraag('/gebruikers/' + g.id + '/nieuwe-sleutel', { methode: 'POST' }); await ververs(); toonSleutel(p, r.gebruiker, r.sleutel); }
                catch (e) { meld(e.message, true); }
              } }),
              el('button', { klasse: g.actief ? 'gevaar' : null, tekst: g.actief ? 'Uitzetten' : 'Aanzetten', klik: async function () {
                try { await vraag('/gebruikers/' + g.id, { methode: 'PATCH', body: { actief: !g.actief } }); await ververs(); }
                catch (e) { meld(e.message, true); }
              } }))));
        }))) : el('p', { klasse: 'klein', tekst: 'Nog geen gebruikers.' }),
      el('div', { klasse: 'velden', style: 'margin-top:8px' },
        veld('Nieuwe gebruiker', naam), veld('E-mail', email), veld('Rol', rol),
        el('div', null, el('label', { tekst: ' ' }), el('button', { klasse: 'hoofd', tekst: 'Toevoegen en sleutel maken', klik: toevoegen }))));
  }

  function bericht(p, g, s) {
    var server = staat.instellingen.serveradres || location.origin;
    var winkel = staat.instellingen.winkellink;
    return 'Beste ' + g.naam + ',\n\n' +
      'Uw toegang tot VitaScribe voor ' + p.naam + ' staat klaar.\n\n' +
      '1. Installeer de extensie' + (winkel ? ': ' + winkel : ' in Edge of Chrome.') + '\n' +
      '2. Open de instellingen van VitaScribe (rechtsklik op het icoon, Opties).\n' +
      '3. Vul in:\n   Serveradres: ' + server + '\n   API-sleutel: ' + s + '\n' +
      '4. Klik op Test verbinding en daarna op Opslaan.\n\n' +
      'De sleutel is persoonlijk: deel hem niet. Raakt hij kwijt, dan maken we een nieuwe en werkt deze niet meer.\n\n' +
      'Met vriendelijke groet,\n';
  }

  function toonSleutel(p, g, s) {
    var scherm = document.getElementById('scherm');
    var inhoud = document.getElementById('scherminhoud');
    leeg(inhoud);
    var tekst = bericht(p, g, s);
    function kopieer(waarde, wat) {
      navigator.clipboard.writeText(waarde).then(function () { meld(wat + ' gekopieerd.'); }, function () { meld('Kopiëren lukte niet; selecteer de tekst.', true); });
    }
    inhoud.appendChild(el('div', null,
      el('h2', { tekst: 'Sleutel voor ' + g.naam }),
      el('p', { klasse: 'klein', tekst: 'Deze sleutel wordt nu één keer getoond en staat nergens opgeslagen. Stuur hem via een beveiligde mail.' }),
      el('div', { klasse: 'sleutel', tekst: s }),
      el('h3', { tekst: 'Bericht voor de gebruiker' }),
      el('div', { klasse: 'sleutel', style: 'user-select:text' }, el('pre', { tekst: tekst })),
      el('div', { klasse: 'knoppen' },
        el('button', { tekst: 'Sleutel kopiëren', klik: function () { kopieer(s, 'Sleutel'); } }),
        el('button', { tekst: 'Bericht kopiëren', klik: function () { kopieer(tekst, 'Bericht'); } }),
        el('span', { style: 'flex:1' }),
        el('button', { klasse: 'hoofd', tekst: 'Klaar', klik: function () { scherm.style.display = 'none'; leeg(inhoud); } }))));
    scherm.style.display = 'flex';
  }

  function nieuwePraktijk() {
    var naam = prompt('Naam van de praktijk');
    if (!naam || !naam.trim()) return;
    vraag('/praktijken', { methode: 'POST', body: { naam: naam.trim() } })
      .then(async function (p) { staat.filter = 'alle'; await ververs(); kies(p.id); })
      .catch(function (e) { meld(e.message, true); });
  }

  async function kies(id) {
    staat.gekozen = id;
    try { staat.gebruikers = (await vraag('/praktijken/' + id + '/gebruikers')).gebruikers; }
    catch (e) { staat.gebruikers = []; meld(e.message, true); }
    teken();
  }

  // One compact row inside the settings block: the test tools switch.
  function testgereedschapveld() {
    var aan = !!staat.instellingen.testgereedschap;
    var link = document.getElementById('spraaktest-link');
    if (link) link.hidden = !aan;
    var vink = el('input', { type: 'checkbox', aan: aan, style: 'width:auto;margin:0;flex:none', bij: async function () {
      var nieuw = vink.checked;
      if (nieuw && !confirm('Testgereedschap aanzetten? Alleen voor gespeelde consulten: opnamen en tekst gaan naar Deepgram, Anthropic en Mistral, en testset-rapporten komen in het serverlog.')) {
        vink.checked = false; return;
      }
      try {
        staat.instellingen = await vraag('/instellingen', { methode: 'PUT', body: { testgereedschap: nieuw } });
        meld(nieuw ? 'Testgereedschap aan.' : 'Testgereedschap uit.'); teken();
      } catch (e) { vink.checked = !nieuw; meld(e.message, true); }
    } });
    return el('label', { style: 'display:flex;gap:8px;align-items:center;justify-content:flex-start;margin-top:12px;font-size:14px' }, vink,
      el('span', { tekst: 'Testgereedschap (spraaktest, SOEP-test), alleen voor gespeelde consulten' }));
  }

  function instellingenblok() {
    var tarief = el('input', { type: 'number', min: '0', step: '1', waarde: staat.instellingen.tarief_per_fte || '' });
    var server = el('input', { waarde: staat.instellingen.serveradres || location.origin });
    var winkel = el('input', { waarde: staat.instellingen.winkellink || '', placeholder: 'https://microsoftedge.microsoft.com/addons/detail/...' });
    var blok = el('details', { klasse: 'kaart', style: 'margin-top:16px', open: !!staat.instellingenOpen },
      el('summary', { tekst: 'Instellingen, export en logboek' }),
      el('div', { klasse: 'velden' },
        veld('Tarief per huisarts-FTE per jaar (€)', tarief), veld('Serveradres in het bericht', server), veld('Link naar de extensie in de winkel', winkel, true)),
      testgereedschapveld(),
      el('div', { klasse: 'knoppen' },
        el('button', { klasse: 'hoofd', tekst: 'Instellingen opslaan', klik: async function () {
          try {
            staat.instellingen = await vraag('/instellingen', { methode: 'PUT', body: {
              tarief_per_fte: tarief.value === '' ? null : Number(tarief.value), serveradres: server.value.trim(), winkellink: winkel.value.trim() } });
            meld('Instellingen opgeslagen.'); teken();
          } catch (e) { meld(e.message, true); }
        } }),
        el('button', { tekst: 'Register exporteren (JSON)', klik: exporteer }),
        el('button', { tekst: 'Logboek tonen', klik: toonLog })),
      el('div', { id: 'logboek' }));
    // Stays open across a redraw, so a setting changed here does not fold the block away.
    blok.addEventListener('toggle', function () { staat.instellingenOpen = blok.open; });
    return blok;
  }

  async function exporteer() {
    try {
      var r = await fetch(API + '/export', { headers: { 'X-Beheer-Sessie': sessie() } });
      if (!r.ok) throw new Error('Export mislukt (' + r.status + ').');
      var blob = await r.blob();
      var a = el('a', { href: URL.createObjectURL(blob), download: 'vitascribe-register-' + staat.vandaag + '.json' });
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { meld(e.message, true); }
  }

  async function toonLog() {
    var plek = document.getElementById('logboek');
    leeg(plek);
    try {
      var r = await vraag('/log');
      plek.appendChild(el('table', { style: 'margin-top:12px' }, el('tbody', null, r.log.map(function (l) {
        return el('tr', null, el('td', { klasse: 'klein', tekst: moment(l.op) }), el('td', { tekst: l.handeling }),
          el('td', { tekst: l.praktijk || '' }), el('td', { klasse: 'klein', tekst: l.door }));
      }))));
    } catch (e) { meld(e.message, true); }
  }

  // ── AI-gebruik en geschatte kosten (kosten.py) ──
  // Only what VitaScribe itself takes from the AI services; the invoice of each provider is leading.

  var DIENST = { anthropic: 'Anthropic', mistral: 'Mistral', bedrock: 'AWS Bedrock', deepgram: 'Deepgram (achteraf)',
    deepgram_live: 'Deepgram (live)', voxtral: 'Voxtral (Mistral)', gladia: 'Gladia', speechmatics: 'Speechmatics',
    azure_tts: 'Azure (voorlezen)', mistral_tts: 'Mistral (voorlezen)', groq: 'Groq', openai: 'OpenAI' };

  function geld(n, valuta) {
    if (n === null || n === undefined) return '—';
    var teken = valuta === 'EUR' ? '€ ' : '$ ';
    return teken + n.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 3 : 2 });
  }
  function geldregel(obj) {
    var delen = Object.keys(obj || {}).map(function (v) { return geld(obj[v], v); });
    return delen.length ? delen.join(' + ') : '—';
  }
  function hoeveel(r) {
    var d = [];
    if (r.in_tokens || r.uit_tokens) d.push(Math.round(r.in_tokens / 1000).toLocaleString('nl-NL') + 'k in · '
      + Math.round(r.uit_tokens / 1000).toLocaleString('nl-NL') + 'k uit');
    if (r.cache_r || r.cache_w) d.push('cache ' + Math.round(r.cache_w / 1000) + 'k gezet, ' + Math.round(r.cache_r / 1000) + 'k gelezen');
    if (r.minuten) d.push(r.minuten.toLocaleString('nl-NL') + ' min');
    if (r.tekens) d.push(r.tekens.toLocaleString('nl-NL') + ' tekens');
    return d.join(' · ') || '—';
  }

  function kostenblok() {
    var blok = el('details', { klasse: 'kaart', style: 'margin-top:16px', open: !!staat.kostenOpen },
      el('summary', { tekst: 'AI-gebruik en geschatte kosten' }), el('div', { id: 'kosten' }));
    blok.addEventListener('toggle', function () {
      staat.kostenOpen = blok.open;
      if (blok.open) laadKosten();
    });
    if (blok.open) setTimeout(laadKosten, 0);
    return blok;
  }

  async function laadKosten() {
    var plek = document.getElementById('kosten');
    if (!plek) return;
    var dagen = staat.kostenDagen || 30;
    try { staat.kosten = await vraag('/kosten?dagen=' + dagen); }
    catch (e) { leeg(plek); plek.appendChild(el('p', { klasse: 'klein', tekst: e.message })); return; }
    tekenKosten();
  }

  function tekenKosten() {
    var plek = document.getElementById('kosten');
    var k = staat.kosten;
    if (!plek || !k) return;
    leeg(plek);
    var keuze = el('select', { bij: function (e) { staat.kostenDagen = Number(e.target.value); laadKosten(); } },
      [7, 30, 90, 365].map(function (n) { return el('option', { value: String(n), tekst: 'laatste ' + n + ' dagen', selected: k.dagen === n }); }));
    plek.appendChild(el('div', { klasse: 'knoppen', style: 'justify-content:flex-start;align-items:center' }, keuze,
      el('span', { klasse: 'klein', tekst: 'Totaal: ' + geldregel(k.totaal) + ' · per maand (21 werkdagen): ' + geldregel(k.per_maand) })));
    if (k.opslag !== 'register') plek.appendChild(el('p', { klasse: 'klein', tekst: 'Zonder register telt de server alleen tot hij herstart.' }));
    plek.appendChild(el('table', { style: 'margin-top:8px' },
      el('thead', null, el('tr', null, ['Dienst', 'Model', 'Aanroepen', 'Hoeveelheid', 'Geschat'].map(function (h) { return el('th', { tekst: h }); }))),
      el('tbody', null, k.regels.length ? k.regels.map(function (r) {
        return el('tr', null, el('td', { tekst: DIENST[r.dienst] || r.dienst }), el('td', { klasse: 'klein', tekst: r.model || '' }),
          el('td', { tekst: String(r.aanroepen) }), el('td', { klasse: 'klein', tekst: hoeveel(r) }),
          el('td', { tekst: r.kosten === null ? 'prijs invullen' : geld(r.kosten, r.valuta) }));
      }) : [el('tr', null, el('td', { tekst: 'Nog geen gebruik in deze periode.' }))])));
    if (k.per_dag.length) {
      plek.appendChild(el('p', { klasse: 'klein', style: 'margin-top:8px', tekst: 'Per dag: ' + k.per_dag.slice(-14).map(function (d) {
        var b = {}; Object.keys(d).forEach(function (x) { if (x !== 'dag') b[x] = d[x]; });
        return datum(d.dag) + ' ' + geldregel(b);
      }).join(' · ') }));
    }
    plek.appendChild(prijsblok(k));
    plek.appendChild(el('p', { klasse: 'klein', tekst: 'Een schatting van wat VitaScribe zelf afnam (tokens, minuten spraak, tekens voorlezen), '
      + 'met de prijzen hieronder (stand ' + k.prijzen_per + '). Leidend is de factuur van elke aanbieder: daar staan ook kortingen, '
      + 'btw en de wisselkoers in. Ander gebruik op dezelfde sleutels (bijvoorbeeld Claude.ai) staat hier niet in.' }));
  }

  // Prices: the known ones are filled in; the rest from your own invoices.
  function prijsblok(k) {
    var sleutels = Object.keys(k.prijzen);
    k.regels.forEach(function (r) { if (sleutels.indexOf(r.sleutel) === -1) sleutels.push(r.sleutel); });
    sleutels.sort();
    var velden = {};
    var rijen = sleutels.map(function (s) {
      var p = k.prijzen[s] || {};
      var spraak = !/[:]/.test(s) && !/_tts$/.test(s);
      var stem = /_tts$/.test(s);
      var cel = function (veld, titel) {
        var i = el('input', { type: 'number', step: 'any', min: '0', waarde: p[veld] === undefined ? '' : String(p[veld]),
          title: titel, style: 'width:80px' });
        velden[s] = velden[s] || {};
        velden[s][veld] = i;
        return i;
      };
      var valuta = el('select', null, ['USD', 'EUR'].map(function (v) { return el('option', { value: v, tekst: v, selected: (p.valuta || 'USD') === v }); }));
      velden[s] = velden[s] || {};
      velden[s].valuta = valuta;
      var invoer = spraak ? [cel('minuut', 'per minuut')] : stem ? [cel('tekens', 'per miljoen tekens')]
        : [cel('in', 'per miljoen tokens erin'), cel('uit', 'per miljoen tokens eruit')];
      return el('tr', null, el('td', { klasse: 'klein', tekst: s }),
        el('td', null, el('span', { style: 'display:flex;gap:4px;align-items:center' }, invoer.concat([valuta]))),
        el('td', { klasse: 'klein', tekst: p.bron || (Object.keys(p).length ? '' : 'nog geen prijs') }));
    });
    var details = el('details', { style: 'margin-top:10px' }, el('summary', { tekst: 'Prijzen (tokens per miljoen, spraak per minuut, voorlezen per miljoen tekens)' }),
      el('table', null, el('tbody', null, rijen)),
      el('div', { klasse: 'knoppen' }, el('button', { klasse: 'hoofd', tekst: 'Prijzen opslaan', klik: async function () {
        var uit = {};
        Object.keys(velden).forEach(function (s) {
          var r = { valuta: velden[s].valuta.value }, iets = false;
          Object.keys(velden[s]).forEach(function (v) {
            if (v !== 'valuta' && velden[s][v].value !== '') { r[v] = velden[s][v].value; iets = true; }
          });
          if (iets) uit[s] = r;
        });
        try { await vraag('/kosten/prijzen', { methode: 'PUT', body: { prijzen: uit } }); meld('Prijzen opgeslagen.'); laadKosten(); }
        catch (e) { meld(e.message, true); }
      } })));
    return details;
  }

  function teken() {
    leeg(app);
    app.appendChild(tegels());
    app.appendChild(el('div', { klasse: 'indeling' }, lijst(), detail()));
    app.appendChild(kostenblok());
    app.appendChild(instellingenblok());
  }

  // ── Start ──
  if (sessie()) laad().catch(function (e) { inlogscherm(e.message === 'sessie' ? 'De sessie is verlopen. Log opnieuw in.' : e.message); });
  else inlogscherm();
})();

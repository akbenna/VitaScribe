/*
 * VitaScribe – de modusknop (Claude | EU) in het zijpaneel en de popup.
 *
 * Eén klik wisselt. Bij de wissel naar EU vraagt de knop de server of die de
 * EU-modus toestaat; zo niet, dan springt hij terug en zegt waarom. Een
 * wissel in het ene venster verschijnt meteen in het andere.
 */
var SVModusKnop = (function () {
  'use strict';

  async function serverModus(modus) {
    var c = await SVInstellingen.lees(['apiUrl', 'apiKey']);
    var url = (c.apiUrl || 'http://localhost:8002').replace(/\/$/, '');
    var headers = { 'X-API-Key': (c.apiKey || '').trim() };
    headers[SVModus.KOP] = modus;
    var r = await fetch(url + '/api/v1/providers', { headers: headers, signal: AbortSignal.timeout(5000) });
    if (!r.ok) throw new Error('server ' + r.status);
    var d = await r.json();
    return { modus: SVModus.geldig(d.modus), modi: d.modi || ['claude'] };
  }

  /** knoppen: element met twee knoppen [data-modus]; uitleg: element voor de toelichting. */
  function koppel(knoppen, uitleg) {
    if (!knoppen) return;
    var huidig = 'claude';

    function toon(modus, melding) {
      huidig = modus;
      knoppen.querySelectorAll('[data-modus]').forEach(function (b) {
        var aan = b.getAttribute('data-modus') === modus;
        b.classList.toggle('aan', aan);
        b.setAttribute('aria-checked', aan ? 'true' : 'false');
        b.title = SVModus.UITLEG[b.getAttribute('data-modus')].lang;
      });
      document.body.classList.toggle('modus-eu', modus === 'eu');
      if (uitleg) {
        uitleg.textContent = melding || (modus === 'eu' ? SVModus.UITLEG.eu.lang : '');
        uitleg.hidden = !uitleg.textContent;
        uitleg.classList.toggle('fout', !!melding);
      }
    }

    async function kies(modus) {
      if (modus === huidig) return;
      await SVModus.zet(modus);
      toon(modus);
      if (modus !== 'eu') return;
      try {
        var s = await serverModus('eu');
        if (s.modus !== 'eu') {
          await SVModus.zet('claude');
          toon('claude', 'De server staat de EU-modus (nog) niet toe. De beheerder zet hem aan met ALLOWED_MODI=claude,eu.');
        }
      } catch (e) {
        // Geen verbinding: de keuze blijft staan; de server beslist bij de volgende aanvraag.
      }
    }

    knoppen.querySelectorAll('[data-modus]').forEach(function (b) {
      b.addEventListener('click', function () { kies(b.getAttribute('data-modus')); });
    });
    SVModus.lees().then(function (m) { toon(m); });
    SVModus.bijWijziging(function (m) { if (m !== huidig) toon(m); });
  }

  return { koppel: koppel };
})();

// Extensiepagina's mogen geen inline scripts: de knop koppelt zichzelf.
SVModusKnop.koppel(document.getElementById('modus'), document.getElementById('modus-uitleg'));

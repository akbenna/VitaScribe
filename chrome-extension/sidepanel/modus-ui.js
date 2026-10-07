/*
 * VitaScribe – de modusknop (Claude | EU) in het zijpaneel en de popup.
 *
 * Eén klik wisselt; de arts beslist, binnen wat de praktijk toestaat. Bij het
 * openen vraagt de knop de server welke modi mogen (TOEGESTANE_MODI, of "alleen
 * EU-modus" in Beheer). Een modus die niet mag, staat grijs; staat de keuze op
 * zo'n modus, dan gaat hij naar een modus die wel mag, met uitleg. Bij de
 * wissel naar EU vraagt de knop ook of de EU-modus daar klaar is. Zo niet, dan
 * blijft de keuze staan en verschijnt een waarschuwing. Een wissel in het
 * ene venster verschijnt meteen in het andere.
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
    var modi = Array.isArray(d.modi) && d.modi.length ? d.modi.map(SVModus.geldig) : ['claude', 'eu'];
    return { modus: SVModus.geldig(d.modus), modi: modi, probleem: d.eu_probleem || teOud(d.min_versie) };
  }

  // "2.15.2" < "2.15.3": the EU mode relies on features of newer versions.
  function ouder(a, b) {
    var x = String(a).split('.').map(Number), y = String(b).split('.').map(Number);
    for (var i = 0; i < Math.max(x.length, y.length); i++) {
      if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) < (y[i] || 0);
    }
    return false;
  }

  function teOud(min) {
    if (!min || typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.getManifest) return '';
    var eigen = chrome.runtime.getManifest().version;
    return ouder(eigen, min)
      ? 'werk VitaScribe bij (nu ' + eigen + ', nodig ' + min + '). Oudere versies tonen de geluidscontrole en de markeringen niet.'
      : '';
  }

  /** knoppen: element met twee knoppen [data-modus]; uitleg: element voor de toelichting. */
  function koppel(knoppen, uitleg) {
    if (!knoppen) return;
    var huidig = 'eu';
    var toegestaan = ['claude', 'eu'];
    var NAAM = { claude: 'Claude-modus', eu: 'EU-modus' };

    function zetToegestaan(modi) {
      toegestaan = modi;
      knoppen.querySelectorAll('[data-modus]').forEach(function (b) {
        var mag = modi.indexOf(b.getAttribute('data-modus')) !== -1;
        b.disabled = !mag;
        b.classList.toggle('verboden', !mag);
        if (!mag) b.title = 'Je praktijk werkt alleen in de ' + NAAM[modi[0]] + '.';
      });
    }

    // Ask the server once which modes this practice allows; move away from one that is not.
    async function controleer() {
      try {
        var s = await serverModus(huidig);
        zetToegestaan(s.modi);
        if (s.modi.indexOf(huidig) === -1) {
          var nieuw = s.modi[0];
          await SVModus.zet(nieuw);
          toon(nieuw);
          if (uitleg) {
            uitleg.textContent = 'Je praktijk werkt alleen in de ' + NAAM[nieuw] + '; de schakelaar staat daarom op ' +
              (nieuw === 'eu' ? 'EU' : 'Claude') + '.' + (nieuw === 'eu' ? ' ' + SVModus.UITLEG.eu.lang : '');
            uitleg.hidden = false;
            uitleg.classList.remove('fout');
          }
        } else if (huidig === 'eu' && s.probleem) {
          toon('eu', s.probleem);
        }
      } catch (e) {
        // Geen verbinding: de keuze blijft staan; de server weigert zelf wat niet mag.
      }
    }

    function toon(modus, melding) {
      huidig = modus;
      knoppen.querySelectorAll('[data-modus]').forEach(function (b) {
        var aan = b.getAttribute('data-modus') === modus;
        b.classList.toggle('aan', aan);
        b.setAttribute('aria-checked', aan ? 'true' : 'false');
        if (!b.disabled) b.title = SVModus.UITLEG[b.getAttribute('data-modus')].lang;
      });
      document.body.classList.toggle('modus-eu', modus === 'eu');
      if (uitleg) {
        uitleg.textContent = modus === 'eu' ? SVModus.UITLEG.eu.lang + (melding ? ' Let op: ' + melding : '') : '';
        uitleg.hidden = !uitleg.textContent;
        uitleg.classList.toggle('fout', !!melding);
      }
    }

    async function kies(modus) {
      if (modus === huidig || toegestaan.indexOf(modus) === -1) return;
      await SVModus.zet(modus);
      toon(modus);
      if (modus !== 'eu') return;
      try {
        var s = await serverModus('eu');
        // Alleen advies: de keuze van de arts blijft altijd staan.
        if (s.probleem && huidig === 'eu') toon('eu', s.probleem);
      } catch (e) {
        // Geen verbinding: de keuze blijft staan.
      }
    }

    knoppen.querySelectorAll('[data-modus]').forEach(function (b) {
      b.addEventListener('click', function () { kies(b.getAttribute('data-modus')); });
    });
    SVModus.lees().then(function (m) {
      toon(m);
      // On opening: which modes may be used, and is the EU mode ready on the server?
      controleer();
    });
    SVModus.bijWijziging(function (m) { if (m !== huidig) toon(m); });
  }

  return { koppel: koppel };
})();

// Extensiepagina's mogen geen inline scripts: de knop koppelt zichzelf.
SVModusKnop.koppel(document.getElementById('modus'), document.getElementById('modus-uitleg'));

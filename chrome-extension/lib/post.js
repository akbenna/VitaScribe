/**
 * VitaScribe - Post: een bericht uit de Bricks-post klaarmaken
 *
 * Zonder DOM en zonder chrome.*, zodat het in Node te toetsen is
 * (tests/js/post.test.js). Het zijpaneel (sidepanel/post-ui.js) leest de
 * paginatekst van Bricks en gebruikt dit om:
 * - het bericht zelf te vinden (vanaf "Afzender" tot de knoppenbalk);
 * - de regel "Patiënt <naam> <geboortedatum> <adres>" eruit te halen; daaruit
 *   komt alleen de leeftijd mee;
 * - de episodelijst (ICPC + titel) als context mee te geven;
 * - de rest door het privacyfilter te halen (datums blijven: de datum van de
 *   uitslag doet ertoe).
 */
var SVPost = (function () {
  'use strict';

  var MAX_TEKST = 30000;
  var KNOPPEN = /^\s*(Verwijder|Export|Afdrukken|Nieuwe taak|Opslaan|Annuleren)\s*$/;
  var DATUM = /(\d{1,2})-(\d{1,2})-(\d{4})/;
  var ICPC_REGEL = /(?:^|\s)([A-Z]\d{2}(?:\.\d{2})?)\s+([^\t\n]{3,100})/g;

  /** The message: from "Afzender" up to the button bar, or '' if none. */
  function bericht(paginaTekst) {
    var t = String(paginaTekst || '');
    var m = /(^|\n)[ \t]*Afzender\b/.exec(t);
    if (!m) return '';
    var regels = t.slice(m.index + m[1].length).split('\n');
    var uit = [];
    for (var i = 0; i < regels.length; i++) {
      if (i > 0 && KNOPPEN.test(regels[i]) && KNOPPEN.test(regels[i + 1] || '')) break;
      uit.push(regels[i]);
    }
    return uit.join('\n').trim();
  }

  /** "Patiënt  MFH Gorris - Aarts 26-10-1961 De Eerensstraat 4 ..." */
  function patient(tekst) {
    var m = /(^|\n)[ \t]*Pati[eë]nt\b[ \t:]*([^\n]*)/.exec(tekst);
    if (!m) return { naam: '', geboren: null, regel: '' };
    var rest = m[2];
    var d = DATUM.exec(rest);
    return {
      naam: (d ? rest.slice(0, d.index) : rest).trim(),
      geboren: d ? new Date(+d[3], +d[2] - 1, +d[1]) : null,
      regel: m[0].replace(/^\n/, ''),
    };
  }

  function leeftijd(geboren, vandaag) {
    if (!geboren) return null;
    var nu = vandaag || new Date();
    var jaren = nu.getFullYear() - geboren.getFullYear();
    if (nu.getMonth() < geboren.getMonth() || (nu.getMonth() === geboren.getMonth() && nu.getDate() < geboren.getDate())) jaren--;
    return jaren >= 0 && jaren <= 120 ? jaren : null;
  }

  /** ICPC episodes from the "Episoden" block, e.g. "T90.02 Diabetes mellitus type 2". */
  function episodes(paginaTekst) {
    var t = String(paginaTekst || '');
    var start = t.search(/(^|\n)[ \t]*Episoden\b/);
    if (start === -1) return [];
    var blok = t.slice(start);
    var eind = blok.search(/\n[ \t]*(Portaal|Samenvatting|Afzender)\b/);
    if (eind !== -1) blok = blok.slice(0, eind);
    var uit = [];
    var m;
    ICPC_REGEL.lastIndex = 0;
    while ((m = ICPC_REGEL.exec(blok)) && uit.length < 40) {
      var titel = m[2].replace(/[⋮:\s]+$/, '').trim();
      if (titel) uit.push(m[1] + ' ' + titel);
    }
    return uit;
  }

  /**
   * Everything the server needs, filtered. Returns null when the page shows
   * no message. `vingerafdruk` is the raw message: it changes when the doctor
   * clicks another one.
   */
  function bouw(paginaTekst, privacy, vandaag) {
    var b = bericht(paginaTekst);
    if (b.length < 20) return null;
    var p = patient(b);
    var zonder = p.regel ? b.replace(p.regel, 'Patiënt: [weggelaten]') : b;
    var opts = { naam: p.naam, datumsBehouden: true };
    var tekst = privacy.filter(zonder, opts).slice(0, MAX_TEKST);
    return {
      vingerafdruk: b,
      tekst: tekst,
      leeftijd: leeftijd(p.geboren, vandaag),
      problemen: episodes(paginaTekst).map(function (e) { return privacy.filter(e, opts); }),
    };
  }

  return { bericht: bericht, patient: patient, leeftijd: leeftijd, episodes: episodes, bouw: bouw, MAX_TEKST: MAX_TEKST };
})();
if (typeof module !== 'undefined') module.exports = SVPost;

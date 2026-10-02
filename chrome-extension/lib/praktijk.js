/**
 * VitaScribe - Het Bricks-praktijknummer bij elke aanroep
 *
 * Een licentie hoort bij een praktijk, en in Bricks staat het praktijknummer in
 * de URL: https://groep06.brickshuisarts.nl/2876/s/consult/... -> 2876. Een
 * lokale installatie zet het in de hostnaam (2876.brickslokaal.nl). De server
 * vergelijkt dat nummer met de licentie, zodat een sleutel die bij een andere
 * praktijk terechtkomt daar niet werkt.
 *
 * Alleen de hostnaam en het EERSTE deel van het pad tellen. Dieper in het pad
 * staan dossier- en consultnummers, en die horen bij een patiënt: die gaan
 * nooit mee naar de server.
 *
 * Het laatst geziene nummer staat in chrome.storage.local, zodat ook dicteren
 * buiten Bricks het meestuurt. Is er nog nooit een nummer gezien, dan gaat er
 * niets mee en laat de server de aanroep door.
 */
var SVPraktijk = (function () {
  var NUMMER = /^\d{3,6}$/;
  var BRICKS = /(^|\.)(bfrcloud\.com|bfrnet\.nl|bricks-huisarts\.nl|bfrw\.nl|bfrw\.cloud|brickshuisarts\.nl|bfrw-online\.nl|bricks\.nl|bricks-his\.nl|brickslokaal\.nl)$/i;

  function nummersUit(url) {
    var u;
    try { u = new URL(url); } catch (e) { return []; }
    if (!BRICKS.test(u.hostname)) return [];
    var uit = [];
    u.hostname.split('.').forEach(function (deel) { if (NUMMER.test(deel) && uit.indexOf(deel) === -1) uit.push(deel); });
    var eerste = u.pathname.split('/').filter(Boolean)[0];
    if (eerste && NUMMER.test(eerste) && uit.indexOf(eerste) === -1) uit.push(eerste);
    return uit.slice(0, 4);
  }

  function opslag() {
    return (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) ? chrome.storage.local : null;
  }

  async function nummers() {
    var s = opslag();
    if (!s) return [];
    try {
      var r = await s.get('svPraktijk');
      return Array.isArray(r.svPraktijk) ? r.svPraktijk.filter(function (n) { return NUMMER.test(n); }) : [];
    } catch (e) {
      return [];
    }
  }

  async function onthoud(url) {
    var gevonden = nummersUit(url);
    var s = opslag();
    if (!gevonden.length || !s) return gevonden;
    try {
      var huidig = await nummers();
      if (huidig.join(',') !== gevonden.join(',')) await s.set({ svPraktijk: gevonden });
    } catch (e) { /* een licentiecontrole mag nooit een fout geven */ }
    return gevonden;
  }

  /** Zet X-Bricks-Praktijk op de koppen, als er een nummer bekend is. */
  async function metKop(headers) {
    var n = await nummers();
    if (n.length) headers['X-Bricks-Praktijk'] = n.join(',');
    // De modus (claude of eu) gaat met elke aanvraag mee; zie lib/modus.js.
    if (typeof SVModus !== 'undefined') await SVModus.metKop(headers);
    return headers;
  }

  return { nummersUit: nummersUit, nummers: nummers, onthoud: onthoud, metKop: metKop };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVPraktijk;

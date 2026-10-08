/**
 * VitaScribe - Bronnen bij de SOEP (zijpaneel)
 *
 * De server stuurt bij elke zin van het verslag mee waar die in het gesprek
 * gezegd werd (services/cloud_api/bronnen.py): {probleem, veld, zin, status,
 * score, bronnen: [{spreker, tekst}], ontbreekt: [woorden]}. Dit bestand zoekt
 * die zinnen terug in de tekst zoals hij in het paneel staat (de arts kan al
 * iets veranderd hebben) en rekent uit wat er onderstreept wordt.
 *
 * Zonder DOM en zonder chrome.* (tests/js/bronnen.test.js).
 */
var SVBronnen = (function () {
  'use strict';

  var LETTER = 'A-Za-z0-9À-ÿ';

  function voor(bronnen, probleem, veld) {
    return (Array.isArray(bronnen) ? bronnen : []).filter(function (b) {
      return b && b.zin && (b.probleem || 0) === (probleem || 0) && (veld == null || b.veld === veld);
    });
  }

  function escape(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  /** Where each sentence is in the text: [{item, start, end}], in order; edited-away sentences are left out. */
  function plaatsen(tekst, items) {
    var laag = String(tekst || '').toLowerCase();
    var vanaf = 0;
    var uit = [];
    items.forEach(function (it) {
      var zoek = String(it.zin || '').toLowerCase();
      if (!zoek) return;
      var pos = laag.indexOf(zoek, vanaf);
      if (pos < 0) pos = laag.indexOf(zoek);          // order changed by the doctor
      if (pos < 0) return;
      uit.push({ item: it, start: pos, end: pos + zoek.length });
      vanaf = pos + zoek.length;
    });
    return uit;
  }

  /**
   * Ranges to highlight in one field, without overlap:
   *   soort 'mark'      a marking of the control pass (first occurrence of its text)
   *   soort 'onbekend'  a word of the report that occurs nowhere in the conversation
   */
  function bereiken(tekst, markeringen, items) {
    tekst = String(tekst || '');
    var laag = tekst.toLowerCase();
    var uit = [];
    function vrij(a, b) { return uit.every(function (r) { return b <= r.start || a >= r.end; }); }
    (markeringen || []).forEach(function (mk) {
      var zoek = String(mk.tekst || '').toLowerCase();
      if (!zoek) return;
      var pos = laag.indexOf(zoek);
      if (pos >= 0 && vrij(pos, pos + zoek.length)) uit.push({ start: pos, end: pos + zoek.length, soort: 'mark', titel: mk.reden || '' });
    });
    plaatsen(tekst, items || []).forEach(function (p) {
      (p.item.ontbreekt || []).forEach(function (woord) {
        var re = new RegExp('(^|[^' + LETTER + '])(' + escape(woord) + ')(?![' + LETTER + '])', 'i');
        var m = re.exec(tekst.slice(p.start, p.end));
        if (!m) return;
        var a = p.start + m.index + m[1].length;
        var b = a + m[2].length;
        if (vrij(a, b)) uit.push({ start: a, end: b, soort: 'onbekend', titel: 'Niet gezegd in het gesprek' });
      });
    });
    return uit.sort(function (x, y) { return x.start - y.start; });
  }

  /** The sentence at a caret position in the field, or null. */
  function zinOp(tekst, items, offset) {
    var hit = null;
    plaatsen(tekst, items || []).forEach(function (p) {
      if (!hit && offset >= p.start && offset <= p.end) hit = p.item;
    });
    return hit;
  }

  function telling(items) {
    var t = { totaal: 0, bron: 0, deels: 0, geen: 0, woorden: 0 };
    (items || []).forEach(function (b) {
      t.totaal++;
      t[b.status === 'bron' ? 'bron' : b.status === 'deels' ? 'deels' : 'geen']++;
      t.woorden += (b.ontbreekt || []).length;
    });
    return t;
  }

  /** One line for the overview under the report. */
  function samenvatting(items) {
    var t = telling(items);
    if (!t.totaal) return '';
    var zin = t.bron + ' van de ' + t.totaal + ' zinnen staan duidelijk in het gesprek';
    if (t.deels) zin += ', ' + t.deels + ' deels';
    zin += '.';
    if (t.woorden) zin += ' ' + t.woorden + (t.woorden === 1 ? ' woord is' : ' woorden zijn') + ' nergens gezegd (onderstreept).';
    return zin + ' Klik op een zin voor de bron.';
  }

  return { voor: voor, bereiken: bereiken, zinOp: zinOp, telling: telling, samenvatting: samenvatting };
})();
if (typeof module !== 'undefined') module.exports = SVBronnen;

/**
 * VitaScribe - Wat dit consult aan AI kostte (geschat), voor onder het verslag
 *
 * De server telt per consult wat het gebruikte (services/cloud_api/kosten.py)
 * en geeft dat mee als "kosten": {totaal: {USD: 0.04}, onbekend: [...], aanroepen}.
 * Zonder DOM en zonder chrome.*: tests/js/kosten.test.js.
 */
var SVKosten = (function () {
  'use strict';

  function geld(n, valuta) {
    var teken = valuta === 'EUR' ? '€' : '$';
    var cijfers = n < 0.01 ? '< 0,01' : n.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return teken + ' ' + cijfers;
  }

  /** "AI-kosten van dit consult: ± $ 0,04 (schatting, 14 AI-aanroepen)", or '' without data. */
  function tekst(kosten) {
    if (!kosten || !kosten.totaal) return '';
    var delen = Object.keys(kosten.totaal).filter(function (v) { return typeof kosten.totaal[v] === 'number'; })
      .map(function (v) { return geld(kosten.totaal[v], v); });
    var onbekend = (kosten.onbekend || []).length;
    if (!delen.length && !onbekend) return '';
    var uit = 'AI-kosten van dit consult: ' + (delen.length ? '± ' + delen.join(' + ') : 'onbekend');
    var noot = ['schatting'];
    if (kosten.aanroepen) noot.push(kosten.aanroepen + (kosten.aanroepen === 1 ? ' AI-aanroep' : ' AI-aanroepen'));
    if (onbekend) noot.push((delen.length ? 'excl. ' : '') + onbekend + (onbekend === 1 ? ' dienst' : ' diensten') + ' zonder prijs');
    return uit + ' (' + noot.join(', ') + ')';
  }

  /** "spraakherkenning $ 0,03 · verslaglegging $ 0,03 · meedenken $ < 0,01", largest first, or ''. */
  function verdeling(kosten) {
    var d = (kosten && kosten.per_onderdeel) || {};
    var som = function (naam) { return Object.keys(d[naam]).reduce(function (t, v) { return t + (d[naam][v] || 0); }, 0); };
    // Largest first (storage may reorder the keys).
    var delen = Object.keys(d).sort(function (a, b) { return som(b) - som(a); }).map(function (naam) {
      var bedragen = Object.keys(d[naam]).map(function (v) { return geld(d[naam][v], v); });
      return naam + ' ' + bedragen.join(' + ');
    });
    return delen.length > 1 ? delen.join(' · ') : '';
  }

  return { tekst: tekst, verdeling: verdeling, geld: geld };
})();
if (typeof module !== 'undefined') module.exports = SVKosten;

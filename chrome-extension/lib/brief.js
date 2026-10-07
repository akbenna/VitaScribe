/**
 * VitaScribe - Brieven: het concept klaarmaken om te versturen
 *
 * Zonder DOM en zonder chrome.* (tests/js/brief.test.js).
 * - opmaak weg die in Bricks of een mail als losse tekens verschijnt
 *   (**vet**, # koppen);
 * - tellen wat de arts nog moet invullen ([aanvullen: ...], [Naam huisarts]);
 * - kiezen of het journaal goed genoeg is ingelezen, of dat alles wat in
 *   beeld staat mee moet;
 * - de bijlagen onder de brief (specialistenbrieven waarnaar de brief
 *   verwijst), als lijst om mee te sturen.
 */
var SVBrief = (function () {
  'use strict';

  function schoon(tekst) {
    return String(tekst || '')
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/__(.+?)__/g, '$1')
      .replace(/^\s{0,3}#{1,6}\s+/gm, '')
      .replace(/^\s*\*\s+(?=\S)/gm, '- ');
  }

  /** Placeholders still open, each once, in order. */
  function openPlekken(tekst) {
    var m = String(tekst || '').match(/\[[^\]\n]{2,160}\]/g) || [];
    return m.filter(function (x, i) { return m.indexOf(x) === i; });
  }

  /** Sections found by heading are enough only with a real journal in them;
   *  otherwise the letter would miss history and findings. */
  var MIN_JOURNAAL = 300;
  function journaalGenoeg(secties) {
    var j = (secties || {})['Journaal'] || '';
    return j.replace(/\s+/g, ' ').length >= MIN_JOURNAAL;
  }

  /** The enclosures listed under "Bijlagen:" at the end of a letter. */
  function bijlagen(tekst) {
    var regels = String(tekst || '').split('\n');
    var i = regels.map(function (r) { return r.trim().toLowerCase(); }).lastIndexOf('bijlagen:');
    if (i === -1) return [];
    var uit = [];
    for (var j = i + 1; j < regels.length; j++) {
      var r = regels[j].trim();
      if (!r) { if (uit.length) break; continue; }
      if (!/^[-•*]\s*/.test(r) && uit.length) break;
      r = r.replace(/^[-•*]\s*/, '').trim();
      if (r) uit.push(r);
    }
    return uit;
  }

  return { bijlagen: bijlagen, schoon: schoon, openPlekken: openPlekken, journaalGenoeg: journaalGenoeg, MIN_JOURNAAL: MIN_JOURNAAL };
})();
if (typeof module !== 'undefined') module.exports = SVBrief;

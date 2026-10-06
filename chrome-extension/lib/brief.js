/**
 * VitaScribe - Brieven: het concept klaarmaken om te versturen
 *
 * Zonder DOM en zonder chrome.* (tests/js/brief.test.js).
 * - opmaak weg die in Bricks of een mail als losse tekens verschijnt
 *   (**vet**, # koppen);
 * - tellen wat de arts nog moet invullen ([aanvullen: ...], [Naam huisarts]);
 * - kiezen of het journaal goed genoeg is ingelezen, of dat alles wat in
 *   beeld staat mee moet.
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

  return { schoon: schoon, openPlekken: openPlekken, journaalGenoeg: journaalGenoeg, MIN_JOURNAAL: MIN_JOURNAAL };
})();
if (typeof module !== 'undefined') module.exports = SVBrief;

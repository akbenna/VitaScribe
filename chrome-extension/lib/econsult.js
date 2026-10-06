/**
 * VitaScribe - E-consult: herkennen en klaarzetten
 *
 * Zonder DOM en zonder chrome.*, zodat het in Node te toetsen is
 * (tests/js/econsult.test.js). Het zijpaneel (sidepanel/econsult-ui.js en de
 * dossierbalk) gebruikt dit om:
 * - te zien dat er een e-consult in beeld staat (dan biedt de balk een
 *   concept-antwoord aan);
 * - te herkennen dat de arts in de balk om een e-consultantwoord vraagt;
 * - de uitkomst als tekst te kopiëren.
 */
var SVEconsult = (function () {
  'use strict';

  // Words Bricks, the practice app and the portals put above a patient
  // message. Broad on purpose: a false hit only shows a button.
  var IN_BEELD = /\be[- ]?consult\b|\beconsult\b|bericht van (de )?pati[eë]nt|vraag van (de )?pati[eë]nt|via (de )?(praktijk)?app|via (het )?(pati[eë]nten)?portaal/i;
  // A command, not a question about e-consults: "beantwoord e-consult: ...",
  // "concept-antwoord", or "e-consult" at the start without a question mark.
  var OPDRACHT = /^\s*(beantwoord|antwoord op|concept[- ]?antwoord)\b|^\s*e[- ]?consult\b[^?]*$/i;

  function inBeeld(tekst) {
    return IN_BEELD.test(String(tekst || ''));
  }

  function isOpdracht(vraag) {
    return OPDRACHT.test(String(vraag || ''));
  }

  /** Text of the policy the doctor typed in the bar after the command, if any:
   *  "beantwoord e-consult: paracetamol, geen ibuprofen" -> "paracetamol, geen ibuprofen". */
  function beleidUit(vraag) {
    var m = String(vraag || '').match(/(?::|\s[-–]\s)\s*(.+)$/s);
    return m && isOpdracht(vraag) ? m[1].trim() : '';
  }

  function feitRegel(f) {
    var meta = [f.datum, f.onderdeel].filter(Boolean).join(' · ');
    return '- ' + f.tekst + (meta ? ' (' + meta + ')' : '');
  }

  /** Everything as plain text, for the doctor's own notes or a colleague. */
  function alsTekst(c) {
    var delen = [];
    if (c.vraag_kort) delen.push('Vraag: ' + c.vraag_kort);
    if (c.feiten && c.feiten.length) delen.push('Uit het dossier:\n' + c.feiten.map(feitRegel).join('\n'));
    if (c.nhg) {
      var n = ['NHG' + (c.nhg.richtlijn ? ' (' + c.nhg.richtlijn + ')' : '') + ':']
        .concat((c.nhg.punten || []).map(function (p) { return '- ' + p; }));
      if (c.nhg.alarm && c.nhg.alarm.length) n.push('Alarmsymptomen: ' + c.nhg.alarm.join('; '));
      delen.push(n.join('\n'));
    }
    if (c.antwoord) delen.push('Antwoord:\n' + c.antwoord);
    if (c.journaal) delen.push('Journaal: ' + c.journaal);
    return delen.join('\n\n');
  }

  /** Placeholders still to fill in before sending. */
  function openPlekken(tekst) {
    var m = String(tekst || '').match(/\[[^\]\n]{2,40}\]/g) || [];
    return m.filter(function (x, i) { return m.indexOf(x) === i; });
  }

  return { inBeeld: inBeeld, isOpdracht: isOpdracht, beleidUit: beleidUit, alsTekst: alsTekst, openPlekken: openPlekken };
})();
if (typeof module !== 'undefined') module.exports = SVEconsult;

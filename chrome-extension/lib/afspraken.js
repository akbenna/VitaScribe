/**
 * VitaScribe - Afspraken uit dit consult
 *
 * De server haalt uit de P wat de arts afsprak (services/cloud_api/pipeline.py,
 * afspraken_uit): {soort, tekst, naar, wanneer}. Alleen wat er in de P staat;
 * VitaScribe stelt zelf niets voor. Hier: welke knop erbij hoort, welk
 * specialisme in het verwijsformulier past, en de tekst om te kopiëren.
 *
 * Zonder DOM en zonder chrome.* (tests/js/afspraken.test.js).
 */
var SVAfspraken = (function () {
  'use strict';

  var LABEL = { verwijzing: 'Verwijzing', controle: 'Controle', onderzoek: 'Onderzoek', recept: 'Recept',
                voorlichting: 'Voorlichting', brief: 'Brief', vangnet: 'Vangnet', overig: 'Afspraak' };

  // Words a doctor uses for the receiver, to the option in the referral form.
  var NAAR = [
    [/fysio/, 'fysiotherapeut'], [/di[eë]tist/, 'diëtist'], [/cardio/, 'cardioloog'], [/derma|huidarts/, 'dermatoloog'],
    [/orthop/, 'orthopedisch chirurg'], [/\bkno\b|keel-?neus-?oor/, 'KNO-arts'], [/oogarts|oftalm/, 'oogarts'],
    [/neurochir/, 'neurochirurg'], [/neurol/, 'neuroloog'], [/longarts|pulmo/, 'longarts'], [/mdl|maag-?darm/, 'maag-darm-leverarts'],
    [/reuma/, 'reumatoloog'], [/kinderarts|p[ae]diat/, 'kinderarts'], [/geriat/, 'klinisch geriater'], [/urolo/, 'uroloog'],
    [/gyn/, 'gynaecoloog'], [/vaatchir/, 'vaatchirurg'], [/plastisch/, 'plastisch chirurg'], [/kaakchir/, 'kaakchirurg'],
    [/chirurg/, 'chirurg'], [/psychiat/, 'psychiater'], [/ggz|psycholo/, 'GGZ'], [/revalid/, 'revalidatiearts'],
    [/sportarts/, 'sportarts'], [/radiol/, 'radioloog'], [/endocrin/, 'internist-endocrinoloog'], [/nefrol/, 'internist-nefroloog'],
    [/hematol/, 'internist-hematoloog'], [/oncol/, 'internist-oncoloog'], [/internist|interne/, 'internist'],
    [/allergol/, 'allergoloog'], [/verslav/, 'verslavingsarts'], [/ouderengenees/, 'specialist ouderengeneeskunde'],
  ];

  /** The option value in the referral form for "naar" (from the plan), or '' when unsure. */
  function specialisme(naar, opties) {
    var laag = String(naar || '').toLowerCase().trim();
    // The POH works in the practice itself: no referral letter, so no receiver to fill in.
    if (!laag || /\bpoh\b|praktijkondersteun/.test(laag)) return '';
    var waarden = (opties || []).map(String);
    var exact = waarden.filter(function (v) { return v.toLowerCase() === laag; })[0];
    if (exact) return exact;
    for (var i = 0; i < NAAR.length; i++) {
      if (NAAR[i][0].test(laag) && waarden.indexOf(NAAR[i][1]) !== -1) return NAAR[i][1];
    }
    return '';
  }

  /** What the button next to an agreement does. */
  function actie(a) {
    if (a.soort === 'verwijzing') return { soort: 'verwijzing', knop: 'Verwijsbrief' };
    if (a.soort === 'brief') return { soort: 'brief', knop: 'Naar Brieven' };
    if (a.soort === 'voorlichting') return { soort: 'thuisarts', knop: 'Thuisarts' };
    return { soort: 'kopieer', knop: 'Kopieer' };
  }

  function kopieertekst(a) {
    var t = String(a.tekst || '').trim();
    var w = String(a.wanneer || '').trim();
    if (w && t.toLowerCase().indexOf(w.toLowerCase()) === -1) t += ' (' + w + ')';
    return t;
  }

  function label(a) { return LABEL[a.soort] || LABEL.overig; }

  return { specialisme: specialisme, actie: actie, kopieertekst: kopieertekst, label: label };
})();
if (typeof module !== 'undefined') module.exports = SVAfspraken;

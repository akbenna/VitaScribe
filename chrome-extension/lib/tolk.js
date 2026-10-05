/**
 * VitaScribe - Tolk: logica zonder DOM (testbaar in Node)
 *
 * - welke stem op deze computer een taal kan voorlezen (alleen stemmen die op
 *   de computer zelf staan: een online stem stuurt de tekst naar Microsoft of
 *   Google, en die staan niet in de lijst van verwerkers);
 * - wanneer een beurt vanzelf stopt (stilte na spraak);
 * - welke tekst van een beurt Nederlands is (voor de context en het verslag).
 */
var SVTolk = (function () {
  'use strict';

  // Language tags of the voices that can read each language, best first.
  var STEMTALEN = {
    nl: ['nl-NL', 'nl-BE', 'nl'],
    tr: ['tr-TR', 'tr'],
    pl: ['pl-PL', 'pl'],
    uk: ['uk-UA', 'uk'],
    ar: ['ar-SA', 'ar-EG', 'ar'],
    'ar-SY': ['ar-SY', 'ar-LB', 'ar-JO', 'ar-SA', 'ar-EG', 'ar'],
    'ar-MA': ['ar-MA', 'ar-DZ', 'ar-TN', 'ar-SA', 'ar-EG', 'ar'],
    de: ['de-DE', 'de-AT', 'de-CH', 'de'],
    fr: ['fr-FR', 'fr-BE', 'fr-CA', 'fr'],
    en: ['en-GB', 'en-US', 'en'],
  };
  var RTL = { ar: true, 'ar-SY': true, 'ar-MA': true };
  var MAX_EERDER = 6;

  function norm(tag) { return String(tag || '').replace('_', '-').toLowerCase(); }

  /** A local voice for this language, or null. */
  function kiesStem(stemmen, code) {
    var lokaal = (stemmen || []).filter(function (s) { return s && s.localService; });
    var tags = STEMTALEN[code] || [code];
    for (var i = 0; i < tags.length; i++) {
      var t = norm(tags[i]);
      var gevonden = lokaal.filter(function (s) {
        var l = norm(s.lang);
        return t.indexOf('-') > 0 ? l === t : l.split('-')[0] === t;
      });
      if (gevonden.length) return gevonden[0];
    }
    return null;
  }

  function spraakTag(code) { return (STEMTALEN[code] || [code])[0]; }
  function rtl(code) { return !!RTL[code]; }

  /** How to add a voice to Windows, for a language without one. */
  function stemHint(naam) {
    return 'Op deze computer staat geen stem voor ' + naam + '. Voeg er een toe in Windows: Instellingen › Tijd en taal › '
      + 'Spraak › Stemmen toevoegen. Tot die tijd: laat de vertaling groot zien.';
  }

  /**
   * Silence detection, one step per audio frame.
   * st: {begin, spraak (ms of speech so far), laatsteGeluid}; niveau: RMS 0..1.
   * Stops after `stilteMs` of silence once there was at least `minSpraakMs` of
   * speech, or after `maxMs` in all cases. Returns {st, stop, reden}.
   */
  function stilteStap(st, niveau, nu, opties) {
    var o = Object.assign({ drempel: 0.02, minSpraakMs: 400, stilteMs: 1400, maxMs: 90000, frameMs: 50 }, opties || {});
    st = st || { begin: nu, spraak: 0, laatsteGeluid: null };
    if (niveau >= o.drempel) {
      st.spraak += o.frameMs;
      st.laatsteGeluid = nu;
    }
    if (nu - st.begin >= o.maxMs) return { st: st, stop: true, reden: 'max' };
    if (o.auto !== false && st.spraak >= o.minSpraakMs && st.laatsteGeluid !== null && nu - st.laatsteGeluid >= o.stilteMs) {
      return { st: st, stop: true, reden: 'stilte' };
    }
    return { st: st, stop: false, reden: '' };
  }

  /** The Dutch side of a turn: what the doctor said, or the translation of the patient. */
  function nl(beurt) {
    if (!beurt) return '';
    return String((beurt.spreker === 'arts' ? beurt.origineel : beurt.vertaling) || '').trim();
  }

  function verslagBeurten(beurten) {
    return (beurten || []).filter(function (b) { return !b.leeg && nl(b); })
      .map(function (b) { return { spreker: b.spreker, nl: nl(b) }; });
  }

  function eerder(beurten) { return verslagBeurten(beurten).slice(-MAX_EERDER); }

  /** The text the other party should hear, and in which language. */
  function voorlezen(beurt, taal) {
    return beurt.spreker === 'arts'
      ? { tekst: beurt.vertaling, taal: taal }
      : { tekst: beurt.vertaling, taal: 'nl' };
  }

  return {
    STEMTALEN: STEMTALEN, kiesStem: kiesStem, spraakTag: spraakTag, rtl: rtl, stemHint: stemHint,
    stilteStap: stilteStap, nl: nl, verslagBeurten: verslagBeurten, eerder: eerder, voorlezen: voorlezen,
  };
})();
if (typeof module !== 'undefined') module.exports = SVTolk;

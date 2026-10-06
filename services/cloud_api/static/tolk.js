/**
 * VitaScribe - Tolk: logica zonder DOM (testbaar in Node)
 *
 * - welke stem op deze computer een taal kan voorlezen (alleen stemmen die op
 *   de computer zelf staan: een online stem stuurt de tekst naar Microsoft of
 *   Google, en die staan niet in de lijst van verwerkers);
 * - wanneer een beurt vanzelf stopt (stilte na spraak), en in de handsfree-
 *   stand wanneer iemand begint en ophoudt met praten;
 * - een opname als WAV (handsfree);
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


  /**
   * Hands-free voice activity detection, one step per audio frame.
   * Keeps a slowly adapting noise floor, so a humming fan or a quiet street
   * does not count as speech. Returns {st, gebeurtenis: 'begin'|'einde'|null}.
   * 'einde' comes after `stilteMs` of silence following at least `minSpraakMs`
   * of speech, or when a turn reaches `maxMs`.
   */
  function vadStap(st, rms, nu, opties) {
    var o = Object.assign({ minDrempel: 0.012, factor: 3.2, minSpraakMs: 350, stilteMs: 1200, maxMs: 45000, frameMs: 64,
      kalibratieMs: 500 }, opties || {});
    st = st || { ruis: null, kalibratie: 0, inSpraak: false, begin: 0, spraak: 0, laatsteGeluid: 0 };
    // The first half second only measures the room: the quietest frame is the
    // noise floor (robust when someone already talks during part of it).
    if (st.kalibratie < o.kalibratieMs) {
      st.kalibratie += o.frameMs;
      st.ruis = Math.max(0.003, st.ruis === null ? rms : Math.min(st.ruis, rms));
      return { st: st, gebeurtenis: null };
    }
    var drempel = Math.max(o.minDrempel, st.ruis * o.factor);
    var luid = rms >= drempel;
    if (!st.inSpraak) {
      // Noise floor follows the room while nobody speaks.
      st.ruis = st.ruis * 0.95 + Math.min(rms, drempel) * 0.05;
      if (luid) {
        st.spraak += o.frameMs;
        if (st.spraak >= o.minSpraakMs) {
          st.inSpraak = true;
          st.begin = nu - st.spraak;
          st.laatsteGeluid = nu;
          return { st: st, gebeurtenis: 'begin' };
        }
      } else {
        st.spraak = Math.max(0, st.spraak - o.frameMs);
      }
      return { st: st, gebeurtenis: null };
    }
    if (luid) st.laatsteGeluid = nu;
    if (nu - st.laatsteGeluid >= o.stilteMs || nu - st.begin >= o.maxMs) {
      st.inSpraak = false;
      st.spraak = 0;
      return { st: st, gebeurtenis: 'einde' };
    }
    return { st: st, gebeurtenis: null };
  }

  /** 16-bit PCM WAV from float samples (-1..1). */
  function wav(samples, sampleRate) {
    var n = samples.length;
    var buf = new ArrayBuffer(44 + n * 2);
    var v = new DataView(buf);
    var tekst = function (o, t) { for (var i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
    tekst(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); tekst(8, 'WAVE');
    tekst(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    tekst(36, 'data'); v.setUint32(40, n * 2, true);
    for (var i = 0; i < n; i++) {
      var x = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
    }
    return new Uint8Array(buf);
  }

  return {
    STEMTALEN: STEMTALEN, kiesStem: kiesStem, spraakTag: spraakTag, rtl: rtl, stemHint: stemHint,
    stilteStap: stilteStap, vadStap: vadStap, wav: wav, nl: nl, verslagBeurten: verslagBeurten, eerder: eerder, voorlezen: voorlezen,
  };
})();
if (typeof module !== 'undefined') module.exports = SVTolk;

/**
 * VitaScribe - Privacy filter for letters (from BriefAssistent)
 *
 * Runs in the side panel before anything leaves the browser; the preview
 * shows exactly the filtered text. The server applies a second safety net.
 */
var SVPrivacy = (function () {
  var TUSSENVOEGSELS = ['van', 'de', 'den', 'der', 'ten', 'ter', 'op', 'in', 'het', "'t", 'le', 'la', 'el', 'al', 'bin', 'ben'];
  var TITELS = /\b(?:de heer|mevrouw|dhr\.?|mw\.?|mevr\.?|dr\.?|drs\.?)\s*/gi;

  function initialen(naam) {
    if (!naam) return 'P.X.';
    var schoon = naam.replace(TITELS, '').replace(/\(.*?\)/g, '').replace(/[,\d]/g, ' ').trim();
    var out = schoon.split(/\s+/)
      .filter(function (d) { return d && TUSSENVOEGSELS.indexOf(d.toLowerCase()) === -1 && /^[A-Za-zÀ-ÿ]/.test(d); })
      .map(function (d) {
        // "J.M." stays "J.M."; a word gives its first letter
        return /^([A-Za-z]\.)+$/.test(d) ? d.toUpperCase() : d[0].toUpperCase() + '.';
      })
      .join('');
    return out || 'P.X.';
  }

  var MAAND = '(?:jan(?:uari)?|feb(?:ruari)?|mrt|maa?rt|apr(?:il)?|mei|jun(?:i)?|jul(?:i)?|aug(?:ustus)?|sep(?:t(?:ember)?)?|okt(?:ober)?|nov(?:ember)?|dec(?:ember)?)';
  var DATUM = '(?:\\d{1,2}[-/.]\\d{1,2}[-/.]\\d{2,4}|\\d{1,2}\\s+' + MAAND + '\\.?\\s+\\d{4})';

  // Always removed: direct identifiers.
  var ALTIJD = [
    [/\bNL\d{2}[A-Z]{4}\d{10}\b/g, '[IBAN]'],
    [/(?<!\d)\d{9}(?!\d)/g, '[BSN]'],
    [/(?<!\d)\d{4}\.\d{2}\.\d{3}(?!\d)/g, '[BSN]'],
    [new RegExp('(geb(?:oren|oortedatum|\\.|\\s)*(?:op)?\\s*:?\\s*)' + DATUM, 'gi'), '$1[GEBOORTEDATUM]'],
    [/\b\d{4}\s?[A-Z]{2}\b/g, '[POSTCODE]'],
    [/(?<!\d)(?:\+31|0031|0)[\s-]?6[\s-]?\d(?:[\s-]?\d){7}(?!\d)/g, '[TEL]'],
    [/(?<!\d)0\d{2,3}[\s-]?\d{6,7}(?!\d)/g, '[TEL]'],
    [/[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]{1,255}\.[a-zA-Z]{2,24}/g, '[EMAIL]'],
    [/\b(?:de heer|mevrouw|dhr\.|mw\.|mevr\.)\s+[A-Z][a-zà-ÿ]+(?:[\s-][A-Z][a-zà-ÿ]+)*/g, '[NAAM]'],
  ];
  var DATUMS = [[new RegExp('(?<!\\d)' + DATUM + '(?!\\d)', 'gi'), '[DATUM]']];

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  /** opts: { naam: raw full name, datumsBehouden: bool } */
  function filter(tekst, opts) {
    opts = opts || {};
    var out = String(tekst || '');
    if (opts.naam && opts.naam.length > 2) {
      opts.naam.replace(TITELS, '').split(/[\s,]+/)
        .filter(function (d) { return d.length > 2 && TUSSENVOEGSELS.indexOf(d.toLowerCase()) === -1; })
        .forEach(function (deel) {
          out = out.replace(new RegExp('(?<![a-zà-ÿ])' + escapeRe(deel) + '(?![a-zà-ÿ])', 'gi'), '[NAAM]');
        });
    }
    ALTIJD.forEach(function (p) { out = out.replace(p[0], p[1]); });
    if (!opts.datumsBehouden) DATUMS.forEach(function (p) { out = out.replace(p[0], p[1]); });
    return out;
  }

  return { initialen: initialen, filter: filter };
})();
if (typeof module !== 'undefined') module.exports = SVPrivacy;

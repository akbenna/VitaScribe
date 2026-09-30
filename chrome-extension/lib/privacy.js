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
    // Postcode: on one line, not the year of a date ("20-10-2025 HA" is a date
    // plus the author code, not a postcode).
    [/(?<![\d\-\/.,])[1-9]\d{3} ?[A-Z]{2}(?![A-Za-z\/])/g, '[POSTCODE]'],
    [/(?<![\d\-\/.,])(?:\+31|0031|0)[ -]?6[ -]?\d(?:[ -]?\d){7}(?![\d\-\/])/g, '[TEL]'],
    [/(?<![\d\-\/.,])0\d{2,3}[ -]?\d{6,7}(?![\d\-\/])/g, '[TEL]'],
    [/[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]{1,255}\.[a-zA-Z]{2,24}/g, '[EMAIL]'],
    // "Mw. G. Kerkhofs-Hiddink", "Dhr J. de Vries", "Mevr Amer": title, optional
    // initials and prefixes, then the surname(s).
    [/\b(?:[Dd]e [Hh]eer|[Mm]evrouw|[Dd]hr\.?|[Mm]w\.?|[Mm]evr\.?|[Mm]ej\.?)[ \t]+(?:[A-Z]\.[ \t]*)*(?:(?:van|de|der|den|ter|ten|het|la|le|el|al)[ \t]+)*(?!(?:Is|Heeft|Gaat|Wil|Komt|Belt|Kan|Zegt|Geeft|Was|En|Wordt|Zou|Moet|Mag|Had|Ging|Krijgt|Voelt|Loopt|Neemt|Blijft|Vraagt|Geeft|Weet|Ziet|Zit|Ligt|Staat|Doet|Maakt)\b)[A-Z][a-zà-ÿ]+(?:[ \t]?-[ \t]?(?:(?:van|de|der|den|ter|ten)[ \t]+)*[A-Z][a-zà-ÿ]+|[ \t]+(?!(?:Is|Heeft|Gaat|Wil|Komt|Belt|Kan|Zegt|Was|En|Wordt)\b)[A-Z][a-zà-ÿ]+)*/g, '[NAAM]'],
  ];
  var DATUMS = [[new RegExp('(?<!\\d)' + DATUM + '(?!\\d)', 'gi'), '[DATUM]']];

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // A date of birth in every way a journal writes it: 3-6-1941, 03-06-1941,
  // 03/06/1941, 3.6.41 is not matched (too ambiguous).
  function geboortedatumPatroon(geboren) {
    if (!geboren) return null;
    var d = geboren.getDate(), m = geboren.getMonth() + 1, j = geboren.getFullYear();
    var dag = '0?' + d, maand = '0?' + m;
    return new RegExp('(?<!\\d)' + dag + '[-/.]' + maand + '[-/.]' + j + '(?!\\d)', 'g');
  }

  /** opts: { naam: raw full name, geboren: Date of birth, datumsBehouden: bool } */
  function filter(tekst, opts) {
    opts = opts || {};
    var out = String(tekst || '');
    var gp = geboortedatumPatroon(opts.geboren);
    if (gp) out = out.replace(gp, '[GEBOORTEDATUM]');
    if (opts.naam && opts.naam.length > 2) {
      opts.naam.replace(TITELS, '').split(/[\s,]+/)
        .filter(function (d) { return d.length > 2 && TUSSENVOEGSELS.indexOf(d.toLowerCase()) === -1 && !/^[A-Z]{1,4}$/.test(d); })
        .forEach(function (deel) {
          out = out.replace(new RegExp('(?<![a-zà-ÿ])' + escapeRe(deel) + '(?![a-zà-ÿ])', 'gi'), '[NAAM]');
        });
    }
    ALTIJD.forEach(function (p) { out = out.replace(p[0], p[1]); });
    if (!opts.datumsBehouden) DATUMS.forEach(function (p) { out = out.replace(p[0], p[1]); });
    return out;
  }

  /** "03-06-1941" -> Date, or null. */
  function datum(tekst) {
    var m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(String(tekst || '').trim());
    return m ? new Date(+m[3], +m[2] - 1, +m[1]) : null;
  }

  return { initialen: initialen, filter: filter, datum: datum };
})();
if (typeof module !== 'undefined') module.exports = SVPrivacy;

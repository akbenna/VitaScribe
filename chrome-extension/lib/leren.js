/**
 * VitaScribe - Wat VitaScribe leerde: logica zonder DOM (testbaar in Node)
 *
 * - de regels per groep (huisstijl, woorden, e-consult, brief per soort,
 *   tolk per taal);
 * - de dagmetingen samengevat per week, om te zien of het beter wordt.
 */
var SVLeren = (function () {
  'use strict';

  var MAANDEN = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

  /** Monday of the week of an ISO date (yyyy-mm-dd), as yyyy-mm-dd. */
  function maandag(dag) {
    var d = new Date(dag + 'T12:00:00Z');
    var wd = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - wd);
    return d.toISOString().slice(0, 10);
  }

  function weekLabel(maandagIso) {
    var d = new Date(maandagIso + 'T12:00:00Z');
    return d.getUTCDate() + ' ' + MAANDEN[d.getUTCMonth()];
  }

  /** Day measurements -> per week: consults, average % changed, markings per consult, tolk. */
  function perWeek(meting) {
    var weken = {};
    (meting || []).forEach(function (m) {
      var k = maandag(m.dag);
      var w = weken[k] || (weken[k] = { week: k, label: weekLabel(k), consulten: 0, gewijzigd: 0, markeringen: 0,
        gesprekken: 0, eenvoudiger: 0, weggehaald: 0, econsulten: 0, econsultGewijzigd: 0, brieven: 0, briefGewijzigd: 0 });
      if (m.soort === 'soep') {
        w.consulten += m.aantal;
        w.gewijzigd += m.gewijzigd;
        w.markeringen += m.markeringen;
      } else if (m.soort === 'tolk') {
        w.gesprekken += m.aantal;
        w.eenvoudiger += m.eenvoudiger;
        w.weggehaald += m.weggehaald;
      } else if (m.soort === 'econsult') {
        w.econsulten += m.aantal;
        w.econsultGewijzigd += m.gewijzigd;
      } else if (m.soort === 'brief') {
        w.brieven += m.aantal;
        w.briefGewijzigd += m.gewijzigd;
      }
    });
    return Object.keys(weken).sort().map(function (k) {
      var w = weken[k];
      return {
        week: w.week, label: w.label, consulten: w.consulten, gesprekken: w.gesprekken,
        gewijzigdGem: w.consulten ? Math.round(w.gewijzigd / w.consulten * 10) / 10 : null,
        markeringenGem: w.consulten ? Math.round(w.markeringen / w.consulten * 10) / 10 : null,
        eenvoudigerGem: w.gesprekken ? Math.round(w.eenvoudiger / w.gesprekken * 10) / 10 : null,
        econsulten: w.econsulten, brieven: w.brieven,
        econsultGem: w.econsulten ? Math.round(w.econsultGewijzigd / w.econsulten * 10) / 10 : null,
        briefGem: w.brieven ? Math.round(w.briefGewijzigd / w.brieven * 10) / 10 : null,
      };
    });
  }

  /** Rules in groups for the overview page. */
  function groepen(regels) {
    var uit = { soep: [], woord: [], econsult: [], tolk: {}, brief: {} };
    (regels || []).forEach(function (r) {
      if (r.soort === 'tolk' || r.soort === 'brief') (uit[r.soort][r.taal] = uit[r.soort][r.taal] || []).push(r);
      else if (uit[r.soort]) uit[r.soort].push(r);
    });
    return uit;
  }

  /** In one sentence: is it getting better? Compares the first and the last weeks with consults. */
  function trend(weken) {
    var met = weken.filter(function (w) { return w.gewijzigdGem !== null; });
    if (met.length < 2) return 'Nog te weinig weken om een trend te zien.';
    var eerst = met[0].gewijzigdGem, laatst = met[met.length - 1].gewijzigdGem;
    if (laatst < eerst - 1) return 'Je past minder aan dan in het begin: van ' + eerst + '% naar ' + laatst + '% per consult.';
    if (laatst > eerst + 1) return 'Je past meer aan dan in het begin: van ' + eerst + '% naar ' + laatst + '%. Kijk of er een regel niet klopt.';
    return 'Ongeveer gelijk: rond ' + laatst + '% aangepast per consult.';
  }

  return { maandag: maandag, perWeek: perWeek, groepen: groepen, trend: trend };
})();
if (typeof module !== 'undefined') module.exports = SVLeren;

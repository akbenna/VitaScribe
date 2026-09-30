/**
 * VitaScribe - Dossiervraag: het ingelezen dossier klaarmaken voor de vraag
 *
 * Zonder DOM en zonder chrome.*, zodat het in Node te toetsen is
 * (tests/js/dossiervraag.test.js). Het zijpaneel (sidepanel/dossiervraag.js)
 * leest Bricks in en gebruikt dit om er één tekst van te maken:
 * - naam, BSN, geboortedatum, adres en contactgegevens eruit (SVPrivacy);
 * - datums blijven staan: "wanneer was de laatste kweek" is de vraag;
 * - de onderdelen in een vaste volgorde, zodat dezelfde patiënt dezelfde
 *   tekst geeft en de server de prompt-cache kan gebruiken;
 * - begrensd, met melding als er is ingekort.
 */
var SVDossiervraag = (function () {
  'use strict';

  var MAX_SECTIE = 60000;
  var MAX_TOTAAL = 150000;
  var VOLGORDE = ['Allergieën', 'Medicatie', 'Voorgeschiedenis', 'Lab', 'Metingen', 'Correspondentie', 'Journaal'];

  // Vragen die een huisarts vaak aan een dik dossier stelt. Kort als chip,
  // volledig als vraag.
  var SNELVRAGEN = [
    { label: 'Kweken & resistentie', vraag: 'Welke kweken zijn er gedaan (datum, verwekker, resistentie en gevoeligheid), en welke antibioticakuren kreeg de patiënt de laatste jaren?' },
    { label: 'Beeldvorming', vraag: 'Welke beeldvorming is er gedaan (röntgen, echo, CT, MRI), wanneer en met welke uitslag?' },
    { label: 'Laatste lab', vraag: 'Wat zijn de meest recente labuitslagen, met datum? Noem afwijkende waarden eerst.' },
    { label: 'Allergieën & intoleranties', vraag: 'Welke allergieën, intoleranties en contra-indicaties staan er in het dossier?' },
    { label: 'Verwijzingen', vraag: 'Naar welke specialisten is de patiënt verwezen of wie behandelt mee, wanneer en waarvoor?' },
    { label: 'Medicatie gestopt', vraag: 'Welke medicatie is gestopt of gewisseld, wanneer en waarom?' },
  ];

  function rang(naam) {
    var i = VOLGORDE.indexOf(naam);
    return i === -1 ? VOLGORDE.length : i;
  }

  /**
   * secties: { naam: ruwe tekst }, naam: ruwe patiëntnaam (mag leeg),
   * filter: SVPrivacy.filter. Geeft { tekst, onderdelen: [{naam, tekens}],
   * ingekort, initialen }.
   */
  function bouw(secties, naam, privacy) {
    var namen = Object.keys(secties || {})
      .filter(function (k) { return String(secties[k] || '').trim().length >= 5; })
      .sort(function (a, b) { return rang(a) - rang(b) || a.localeCompare(b); });
    var initialen = privacy.initialen(naam || '');
    var tekst = 'PATIËNT: ' + initialen;
    var onderdelen = [];
    var ingekort = false;
    namen.forEach(function (k) {
      var t = privacy.filter(String(secties[k]).trim(), { naam: naam || '', datumsBehouden: true });
      if (t.length > MAX_SECTIE) { t = t.slice(0, MAX_SECTIE); ingekort = true; }
      var ruimte = MAX_TOTAAL - tekst.length - k.length - 12;
      if (ruimte < 200) { ingekort = true; return; }
      if (t.length > ruimte) { t = t.slice(0, ruimte); ingekort = true; }
      tekst += '\n\n== ' + k.toUpperCase() + ' ==\n' + t;
      onderdelen.push({ naam: k, tekens: t.length });
    });
    return { tekst: tekst, onderdelen: onderdelen, ingekort: ingekort, initialen: initialen };
  }

  /** Is dit nog dezelfde patiënt? Zonder naam aan een van beide kanten weten
   *  we het niet en gaan we uit van ja (het dossier zelf gaat toch opnieuw mee). */
  function zelfdePatient(a, b) {
    var na = String(a || '').trim().toLowerCase();
    var nb = String(b || '').trim().toLowerCase();
    return !na || !nb || na === nb;
  }

  function tekens(n) {
    return n < 1000 ? n + ' tekens' : (Math.round(n / 100) / 10).toString().replace('.', ',') + 'k tekens';
  }

  return {
    MAX_SECTIE: MAX_SECTIE, MAX_TOTAAL: MAX_TOTAAL, SNELVRAGEN: SNELVRAGEN,
    bouw: bouw, zelfdePatient: zelfdePatient, tekens: tekens,
  };
})();
if (typeof module !== 'undefined') module.exports = SVDossiervraag;

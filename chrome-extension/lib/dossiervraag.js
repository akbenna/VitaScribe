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
   * The same block shown twice on screen (a medication profile in a widget and
   * in a tab) is sent once: a run of RUN or more lines that already appeared,
   * in the same order, is left out. Short repeats stay: a repeat prescription
   * of the same five drugs under another date is information.
   */
  var RUN = 15;
  function ontdubbel(tekst) {
    var regels = String(tekst || '').split('\n');
    var gezien = new Map();
    var uit = [];
    var i = 0;
    while (i < regels.length) {
      var sleutel = regels.slice(i, i + RUN).join('\n');
      if (i + RUN <= regels.length && sleutel.replace(/\s/g, '').length > 120 && gezien.has(sleutel)) {
        // Skip for as long as it keeps repeating the earlier run.
        var j = gezien.get(sleutel);
        while (i < regels.length && j < i && regels[i] === regels[j]) { i++; j++; }
        continue;
      }
      if (i + RUN <= regels.length && !gezien.has(sleutel)) gezien.set(sleutel, i);
      uit.push(regels[i]);
      i++;
    }
    return uit.join('\n');
  }

  /**
   * secties: { naam: ruwe tekst }, naam: ruwe patiëntnaam (mag leeg),
   * privacy: SVPrivacy, geboren: Date of birth (mag leeg). Geeft { tekst,
   * onderdelen: [{naam, tekens}], ingekort, initialen }.
   */
  function bouw(secties, naam, privacy, geboren) {
    var namen = Object.keys(secties || {})
      .filter(function (k) { return String(secties[k] || '').trim().length >= 5; })
      .sort(function (a, b) { return rang(a) - rang(b) || a.localeCompare(b); });
    var initialen = privacy.initialen(naam || '');
    var tekst = 'PATIËNT: ' + initialen;
    var onderdelen = [];
    var ingekort = false;
    namen.forEach(function (k) {
      var t = privacy.filter(ontdubbel(String(secties[k]).trim()), { naam: naam || '', geboren: geboren || null, datumsBehouden: true });
      if (namen.length > 1 && t.length > MAX_SECTIE) { t = t.slice(0, MAX_SECTIE); ingekort = true; }
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

  // What changes on a Bricks page between two reads without the dossier
  // changing: a clock, "3 minuten geleden".
  var KLOK = /\b\d{1,2}:\d{2}(:\d{2})?\b/g;
  var GELEDEN = /\b\d+\s*(sec|seconde|seconden|s|min|minuut|minuten|uur)\.?\s+geleden\b/gi;
  function zonderKlok(t) { return String(t || '').replace(KLOK, '00:00').replace(GELEDEN, 'even geleden'); }

  /**
   * The text to send for a follow-up question. When the dossier read again
   * differs from the previous one only in a clock or "… geleden", send the
   * previous text exactly: then the server's prompt cache hits (a tenth of the
   * price for the dossier) and nothing of medical meaning is lost. Anything
   * else changed (a newly opened section, a new entry): the new text.
   */
  function hergebruik(vorige, nieuw) {
    if (!vorige || vorige === nieuw) return nieuw;
    return zonderKlok(vorige) === zonderKlok(nieuw) ? vorige : nieuw;
  }

  function tekens(n) {
    return n < 1000 ? n + ' tekens' : (Math.round(n / 100) / 10).toString().replace('.', ',') + 'k tekens';
  }

  return {
    MAX_SECTIE: MAX_SECTIE, MAX_TOTAAL: MAX_TOTAAL, SNELVRAGEN: SNELVRAGEN,
    bouw: bouw, ontdubbel: ontdubbel, zelfdePatient: zelfdePatient, tekens: tekens, hergebruik: hergebruik,
  };
})();
if (typeof module !== 'undefined') module.exports = SVDossiervraag;

/*
 * VitaScribe – herkent bijzonder gevoelige onderwerpen in een dossier.
 *
 * Alleen in de browser: er gaat niets naar de server om dit te bepalen. Het
 * zijpaneel gebruikt dit om in de Claude-modus te adviseren de EU-modus te
 * kiezen. Het is een advies; de arts beslist.
 *
 * Bewust een smalle lijst: niet het hele P-hoofdstuk van de ICPC (dan krijgt
 * elke oudere met dementie of slaapklachten een melding), maar codes en woorden
 * waarvan uitlekken een patiënt ernstig kan schaden.
 */
var SVGevoelig = (function () {
  'use strict';

  var CATEGORIEEN = [
    { id: 'psyche', naam: 'psychiatrie',
      codes: ['P72', 'P73', 'P74', 'P76', 'P79', 'P80', 'P82', 'P86', 'P98'],
      woorden: ['depressie', 'depressieve stoornis', 'angststoornis', 'paniekstoornis', 'psychose', 'psychotisch',
                'schizofrenie', 'bipolair', 'borderline', 'persoonlijkheidsstoornis', 'ptss', 'posttraumatische',
                'eetstoornis', 'anorexia nervosa', 'boulimia', 'ggz', 'poh-ggz', 'crisisdienst', 'opname psychiatrie'] },
    { id: 'suicide', naam: 'suïcidaliteit',
      codes: ['P77'],
      woorden: ['suïcide', 'suicide', 'suïcidaal', 'suicidaal', 'suïcidepoging', 'zelfmoord', 'doodswens',
                'tentamen suicidii', 'zelfbeschadiging', 'automutilatie'] },
    { id: 'verslaving', naam: 'verslaving',
      codes: ['P15', 'P16', 'P18', 'P19'],
      woorden: ['verslaving', 'verslaafd', 'alcoholmisbruik', 'alcoholafhankelijk', 'drugsgebruik', 'drugsmisbruik',
                'cocaïne', 'cocaine', 'heroïne', 'heroine', 'methadon', 'gokverslaving'] },
    { id: 'seksueel', naam: 'seksuele gezondheid en soa',
      codes: ['B90', 'X70', 'X71', 'X90', 'X92', 'Y70', 'Y71', 'Y72', 'P07', 'P08'],
      woorden: ['soa', 'chlamydia', 'gonorroe', 'syfilis', 'hiv', 'aids', 'prep', 'erectiestoornis',
                'seksueel misbruik'] },
    { id: 'zwangerschap', naam: 'zwangerschapsafbreking',
      codes: ['W83'],
      woorden: ['abortus provocatus', 'zwangerschapsafbreking', 'overtijdbehandeling', 'abortuskliniek'] },
    { id: 'geweld', naam: 'geweld of misbruik',
      codes: ['Z25'],
      woorden: ['huiselijk geweld', 'mishandeling', 'kindermishandeling', 'veilig thuis', 'verkrachting',
                'aanranding', 'meldcode'] },
    { id: 'gender', naam: 'genderidentiteit',
      codes: [],
      woorden: ['transgender', 'genderdysforie', 'genderincongruentie', 'genderteam'] },
    { id: 'justitie', naam: 'justitie',
      codes: [],
      woorden: ['detentie', 'gedetineerd', 'reclassering', 'tbs', 'strafzaak'] }
  ];

  function escape(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // Codes: "P76" or "P76.01", not part of a longer word. Words: whole words.
  var REGELS = CATEGORIEEN.map(function (c) {
    return {
      cat: c,
      code: c.codes.length ? new RegExp('(^|[^A-Za-z0-9])(' + c.codes.join('|') + ')(\\.\\d{1,2})?(?![A-Za-z0-9])', 'g') : null,
      woord: new RegExp('(^|[^a-zà-ÿ0-9])(' + c.woorden.map(escape).join('|') + ')(?![a-zà-ÿ0-9])', 'gi')
    };
  });

  /** { gevoelig, categorieen: [{ id, naam, gevonden: [...] }] } */
  function beoordeel(tekst) {
    var t = String(tekst || '');
    var uit = [];
    REGELS.forEach(function (r) {
      var gevonden = [];
      var m;
      if (r.code) {
        r.code.lastIndex = 0;
        while ((m = r.code.exec(t))) gevonden.push(m[2] + (m[3] || ''));
      }
      r.woord.lastIndex = 0;
      while ((m = r.woord.exec(t))) gevonden.push(m[2].toLowerCase());
      if (gevonden.length) {
        var uniek = gevonden.filter(function (g, i) { return gevonden.indexOf(g) === i; });
        uit.push({ id: r.cat.id, naam: r.cat.naam, gevonden: uniek.slice(0, 3) });
      }
    });
    return { gevoelig: uit.length > 0, categorieen: uit };
  }

  return { beoordeel: beoordeel, CATEGORIEEN: CATEGORIEEN };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVGevoelig;

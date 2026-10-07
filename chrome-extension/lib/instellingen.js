/**
 * VitaScribe - Instellingen lezen, met de serversleutel apart
 *
 * De meeste instellingen (serveradres, microfoon, keuzes van de praktijk) staan
 * in chrome.storage.sync. Is de gebruiker in Chrome ingelogd met een
 * Google-account, dan gaat die opslag via Google naar al zijn apparaten. Voor
 * een serveradres is dat handig; voor de serversleutel niet. Die sleutel geeft
 * toegang tot de verwerking van patiëntgegevens en blijft daarom op dit
 * apparaat, in chrome.storage.local.
 *
 * Een tweede server, naast de eerste (niet in plaats van): staat er bij
 * "Server voor de EU-modus" een adres, dan gaat alles in de EU-modus daarheen
 * (met de eigen sleutel van die server, of anders dezelfde). De Claude-modus
 * blijft op de gewone server. Zonder dat adres verandert er niets. Omdat alles
 * in de extensie het adres via lees() haalt, volgen het zijpaneel, de opname,
 * het dicteren, de telefoon en Beheer vanzelf. Het instellingenscherm leest de
 * velden zoals ze zijn ({ ruw: true }).
 *
 * Oudere versies zetten de sleutel wel in sync. migreer() haalt hem daar weg,
 * nadat hij lokaal staat. Wie VitaScribe op een tweede apparaat gebruikte via
 * Chrome-synchronisatie, vult de sleutel daar één keer opnieuw in.
 */
var SVInstellingen = (function () {
  var LOKAAL = ['apiKey', 'apiKeyEu'];
  var MODUS = 'svModus';   // lib/modus.js: de keuze van de arts, in chrome.storage.local

  function standaardOpslag() {
    return (typeof chrome !== 'undefined' && chrome.storage) ? chrome.storage : null;
  }

  /** Leest de gevraagde sleutels uit sync en, voor de serversleutel, uit local.
   *  apiUrl en apiKey volgen de modus (zie boven), tenzij opties.ruw. */
  async function lees(keys, opslag, opties) {
    var s = opslag || standaardOpslag();
    if (!s) return {};
    if (!(opties && opties.ruw) && (keys.indexOf('apiUrl') !== -1 || keys.indexOf('apiKey') !== -1)) {
      var basis = await lees(keys, s, { ruw: true });
      var modus = (await s.local.get(MODUS))[MODUS];
      // Same rule as SVModus.geldig: only an explicit 'claude' is the Claude mode;
      // nothing stored means the eu mode (since 2.23.1), so its server as well.
      if (modus !== 'claude') {
        var eu = await lees(['apiUrlEu', 'apiKeyEu'], s, { ruw: true });
        var adres = String(eu.apiUrlEu || '').trim();
        if (adres) {
          if (keys.indexOf('apiUrl') !== -1) basis.apiUrl = adres;
          if (keys.indexOf('apiKey') !== -1 && eu.apiKeyEu) basis.apiKey = eu.apiKeyEu;
        }
      }
      return basis;
    }
    var lokaal = keys.filter(function (k) { return LOKAAL.indexOf(k) !== -1; });
    var gedeeld = keys.filter(function (k) { return LOKAAL.indexOf(k) === -1; });
    var uit = gedeeld.length ? await s.sync.get(gedeeld) : {};
    if (lokaal.length) {
      var hier = await s.local.get(lokaal);
      // Is de overzetting nog niet gebeurd, dan werkt de oude sleutel tot die tijd.
      var oud = await s.sync.get(lokaal);
      lokaal.forEach(function (k) {
        if (hier[k]) uit[k] = hier[k];
        else if (oud[k]) uit[k] = oud[k];
      });
    }
    return uit;
  }

  /** Schrijft instellingen weg; de serversleutel gaat naar local, de rest naar sync. */
  async function bewaar(data, opslag) {
    var s = opslag || standaardOpslag();
    if (!s) return;
    var lokaal = {};
    var gedeeld = {};
    Object.keys(data).forEach(function (k) {
      (LOKAAL.indexOf(k) !== -1 ? lokaal : gedeeld)[k] = data[k];
    });
    if (Object.keys(gedeeld).length) await s.sync.set(gedeeld);
    if (Object.keys(lokaal).length) await s.local.set(lokaal);
    await s.sync.remove(LOKAAL);
  }

  /** Zet een serversleutel uit een oudere versie over van sync naar local. */
  async function migreer(opslag) {
    var s = opslag || standaardOpslag();
    if (!s) return;
    var oud = await s.sync.get(LOKAAL);
    var huidig = await s.local.get(LOKAAL);
    var over = {};
    LOKAAL.forEach(function (k) {
      if (oud[k] && !huidig[k]) over[k] = oud[k];
    });
    if (Object.keys(over).length) await s.local.set(over);
    await s.sync.remove(LOKAAL);
  }

  return { LOKAAL: LOKAAL, lees: lees, bewaar: bewaar, migreer: migreer };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVInstellingen;

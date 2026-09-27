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
 * Oudere versies zetten de sleutel wel in sync. migreer() haalt hem daar weg,
 * nadat hij lokaal staat. Wie VitaScribe op een tweede apparaat gebruikte via
 * Chrome-synchronisatie, vult de sleutel daar één keer opnieuw in.
 */
var SVInstellingen = (function () {
  var LOKAAL = ['apiKey'];

  function standaardOpslag() {
    return (typeof chrome !== 'undefined' && chrome.storage) ? chrome.storage : null;
  }

  /** Leest de gevraagde sleutels uit sync en, voor de serversleutel, uit local. */
  async function lees(keys, opslag) {
    var s = opslag || standaardOpslag();
    if (!s) return {};
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

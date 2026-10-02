/*
 * VitaScribe – modus: "claude" of "eu".
 *
 * Claude-modus: alle functies (live dicteren, vraagsuggesties), tekst via
 * Claude (Anthropic, VS) en spraak via Deepgram (EU-eindpunt).
 * EU-modus (formeel): alleen Europese bedrijven. Tekst via Mistral, het
 * consult via Voxtral na afloop. Live dicteren en vraagsuggesties kunnen dan
 * niet.
 *
 * De arts kiest; de keuze staat per computer in chrome.storage.local en gaat
 * met elke aanvraag mee (kopregel X-VitaScribe-Modus, of "modus" bij het
 * aanmelden op een WebSocket). De server volgt die keuze altijd en verandert
 * hem nooit; hij mag alleen adviseren. Kan de EU-modus niet werken, dan mislukt
 * de aanvraag met een melding, zonder stil terug te vallen op Claude.
 * Zonder chrome.storage (offscreen-documenten) geeft de service worker de
 * modus mee in de config.
 */
var SVModus = (function () {
  'use strict';

  var SLEUTEL = 'svModus';
  var KOP = 'X-VitaScribe-Modus';

  var UITLEG = {
    claude: { naam: 'Claude', kort: 'Alle functies',
              lang: 'Claude-modus: alle functies, ook live dicteren en vraagsuggesties. Tekst via Claude (Anthropic, VS), spraak via Deepgram (EU-eindpunt).' },
    eu: { naam: 'EU', kort: 'Alleen Europese diensten',
          lang: 'EU-modus: alleen Europese bedrijven. Tekst via Mistral (Frankrijk), het consult via Voxtral na afloop. Live dicteren en klinische ondersteuning (vraagsuggesties, NHG-toets, aandachtspunten) staan in deze modus uit: alleen verslaglegging.' }
  };

  function geldig(m) { return m === 'eu' ? 'eu' : 'claude'; }

  function opslag() {
    return (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) ? chrome.storage.local : null;
  }

  async function lees() {
    var s = opslag();
    if (!s) return 'claude';
    try {
      var r = await s.get(SLEUTEL);
      return geldig(r[SLEUTEL]);
    } catch (e) {
      return 'claude';
    }
  }

  async function zet(m) {
    var s = opslag();
    var waarde = geldig(m);
    if (s) {
      var obj = {};
      obj[SLEUTEL] = waarde;
      await s.set(obj);
    }
    return waarde;
  }

  /** Zet de modus op de koppen; zonder modus de opgeslagen keuze. */
  async function metKop(headers, modus) {
    headers[KOP] = modus ? geldig(modus) : await lees();
    return headers;
  }

  /** Roept terug als de modus ergens anders (zijpaneel, popup) verandert. */
  function bijWijziging(terug) {
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.onChanged) return;
    chrome.storage.onChanged.addListener(function (wijziging, gebied) {
      if (gebied === 'local' && wijziging[SLEUTEL]) terug(geldig(wijziging[SLEUTEL].newValue));
    });
  }

  return { SLEUTEL: SLEUTEL, KOP: KOP, UITLEG: UITLEG, geldig: geldig, lees: lees, zet: zet,
           metKop: metKop, bijWijziging: bijWijziging };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVModus;

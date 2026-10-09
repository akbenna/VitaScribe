/*
 * VitaScribe: melding bovenin het zijpaneel als de serversleutel ontbreekt.
 *
 * De sleutel staat alleen op dit apparaat (lib/instellingen.js). Wordt de
 * extensie opnieuw geladen of geïnstalleerd, dan is hij weg terwijl het
 * serveradres via synchronisatie blijft staan. De server weigert dan elk
 * verzoek, en zonder deze melding zag de arts alleen een lege taalbalk en
 * knoppen die niets deden. De melding verdwijnt zodra er een sleutel is.
 */
(function () {
  'use strict';

  async function toon() {
    var melding = document.getElementById('sleutel-melding');
    if (!melding) return;
    var c = await SVInstellingen.lees(['apiUrl', 'apiKey']);
    melding.hidden = !SVInstellingen.sleutelOntbreekt(c);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var link = document.getElementById('sleutel-opties');
    if (link) link.addEventListener('click', function (e) {
      e.preventDefault();
      if (chrome.runtime && chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
    });
    toon();
  });
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener(function () { toon(); });
  }
})();

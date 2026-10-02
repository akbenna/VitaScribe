/*
 * VitaScribe – advies bij een gevoelig dossier.
 *
 * In de Claude-modus kijkt het zijpaneel af en toe naar het geopende
 * Bricks-dossier (dezelfde lezing als bij brieven en dossiervraag, alleen wat
 * in beeld staat) en zoekt lib/gevoelig.js naar bijzonder gevoelige
 * onderwerpen. Dat gebeurt alleen in de browser; er gaat niets naar de server.
 * Vindt het iets, dan verschijnt een advies om de EU-modus te kiezen. De arts
 * beslist: wisselen gaat alleen met een klik, en "Niet voor deze patiënt"
 * verbergt het advies voor die patiënt tot het paneel sluit.
 */
(function () {
  'use strict';

  var ELKE_MS = window.VS_GEVOELIG_MS || 20000;
  // Same hosts as the Bricks content script in the manifest.
  var BRICKS = /^https:\/\/([^/]+\.)?(bfrcloud\.com|bfrnet\.nl|bricks-huisarts\.nl|bfrw\.nl|bfrw\.cloud|brickshuisarts\.nl|bfrw-online\.nl|bricks\.nl|bricks-his\.nl)\/|^http:\/\/localhost:8002\//;

  var vak = document.getElementById('gevoelig-advies');
  if (!vak || typeof SVGevoelig === 'undefined' || typeof SVModus === 'undefined') return;
  var weggeklikt = {};        // patient key -> true, only in memory
  var huidigePatient = '';
  var bezig = false;

  function verberg() { vak.hidden = true; vak.textContent = ''; }

  function toon(uitslag, sleutel) {
    vak.textContent = '';
    var namen = uitslag.categorieen.map(function (c) { return c.naam; });
    var gevonden = [];
    uitslag.categorieen.forEach(function (c) { gevonden = gevonden.concat(c.gevonden); });
    var p = document.createElement('p');
    p.textContent = 'Dit dossier bevat bijzonder gevoelige gegevens (' + namen.join(', ') + '). ' +
      'Advies: kies voor dit consult de EU-modus. Jij beslist.';
    vak.appendChild(p);
    var klein = document.createElement('p');
    klein.className = 'gevoelig-bron';
    klein.textContent = 'Gezien in het dossier: ' + gevonden.slice(0, 6).join(', ') + '. Alleen in je browser bekeken; er is niets verstuurd.';
    vak.appendChild(klein);
    var rij = document.createElement('div');
    rij.className = 'gevoelig-knoppen';
    var eu = document.createElement('button');
    eu.type = 'button'; eu.className = 'gevoelig-eu'; eu.textContent = 'Naar EU-modus';
    eu.addEventListener('click', function () { SVModus.zet('eu'); verberg(); });
    var niet = document.createElement('button');
    niet.type = 'button'; niet.textContent = 'Niet voor deze patiënt';
    niet.addEventListener('click', function () { weggeklikt[sleutel] = true; verberg(); });
    rij.appendChild(eu); rij.appendChild(niet);
    vak.appendChild(rij);
    vak.hidden = false;
  }

  async function kijk() {
    if (bezig || document.visibilityState !== 'visible' || !window.SVBricksDossier) return;
    bezig = true;
    try {
      if (await SVModus.lees() !== 'claude') { verberg(); return; }
      var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs[0] || !BRICKS.test(tabs[0].url || '')) { verberg(); return; }
      var d = await window.SVBricksDossier.lees(20000);
      var sleutel = (d.naam || '') + '|' + (d.geboren || '');
      if (sleutel !== huidigePatient) { huidigePatient = sleutel; }
      if (weggeklikt[sleutel]) { verberg(); return; }
      var tekst = Object.keys(d.secties).map(function (k) { return d.secties[k]; }).join('\n');
      var uitslag = SVGevoelig.beoordeel(tekst);
      if (uitslag.gevoelig) toon(uitslag, sleutel); else verberg();
    } catch (e) {
      verberg();   // no patient open, no access: no advice
    } finally {
      bezig = false;
    }
  }

  SVModus.bijWijziging(function (m) { if (m !== 'claude') verberg(); else kijk(); });
  if (chrome.tabs && chrome.tabs.onActivated) chrome.tabs.onActivated.addListener(function () { setTimeout(kijk, 300); });
  if (chrome.tabs && chrome.tabs.onUpdated) chrome.tabs.onUpdated.addListener(function (id, info) { if (info.status === 'complete') setTimeout(kijk, 500); });
  document.addEventListener('visibilitychange', kijk);
  setInterval(kijk, ELKE_MS);
  setTimeout(kijk, 800);
  window.SVGevoeligAdvies = { kijk: kijk };
})();

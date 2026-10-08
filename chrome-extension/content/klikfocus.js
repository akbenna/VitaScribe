/**
 * VitaScribe - Waar klikte de arts? (content script, alle frames)
 *
 * "Denk mee" kijkt naar het stuk van het dossier dat de arts aanwijst, niet
 * naar alles wat in beeld staat. Dit script onthoudt alleen het laatst
 * aangeklikte element en het tijdstip, in de eigen (afgeschermde) wereld van
 * de extensie: de pagina zelf ziet en verandert niets, en er gaat niets weg.
 * Het zijpaneel leest het bij "Denk mee" uit (sidepanel/letters.js, focusFrame).
 */
(function () {
  'use strict';
  if (window.__svKlikfocus) return;
  window.__svKlikfocus = true;
  document.addEventListener('pointerdown', function (e) {
    if (e.isTrusted && e.target && e.target.nodeType === 1) window.__svKlik = { el: e.target, t: Date.now() };
  }, true);
})();

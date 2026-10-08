/**
 * VitaScribe - Foto van de telefoon in het dossier (content script, alle frames)
 *
 * Het zijpaneel stuurt een foto (SV_FOTO_UPLOAD). Staat in Bricks het venster
 * open om een document of afbeelding toe te voegen, dan zet dit script de
 * foto in dat uploadveld, alsof de arts hem zelf koos. Opslaan doet de arts
 * daarna in Bricks; VitaScribe schrijft niets zelf weg.
 *
 * Geen uploadveld in een frame: dat frame zwijgt, zodat het frame waar het
 * venster wél open is antwoordt. Antwoordt niemand, dan zegt het paneel wat
 * te doen en staat de foto op het klembord.
 *
 * De keuze van het veld (kies) is los te toetsen: tests/js/foto-upload.test.js.
 */
var SVFotoUpload = (function () {
  'use strict';

  /** Does this file input take an image? (no accept = anything) */
  function neemtAfbeelding(accept) {
    var a = String(accept || '').toLowerCase().trim();
    if (!a) return true;
    return a.split(',').some(function (x) {
      x = x.trim();
      return x === '*/*' || x === 'image/*' || /^image\/(jpeg|jpg|png)$/.test(x) || /^\.(jpe?g|png)$/.test(x);
    });
  }

  /**
   * The upload field to use, from the file inputs of a page: enabled, takes an
   * image; a visible one or one inside an open dialog first; the last one in
   * the page (the most recently opened dialog) when several qualify.
   * Each input: {disabled, accept, zichtbaar, inDialoog}.
   */
  function kies(velden) {
    var goed = (velden || []).filter(function (v) { return v && !v.disabled && neemtAfbeelding(v.accept); });
    if (!goed.length) return -1;
    var score = function (v) { return (v.inDialoog ? 2 : 0) + (v.zichtbaar ? 1 : 0); };
    var beste = -1, besteScore = -1;
    (velden || []).forEach(function (v, i) {
      if (goed.indexOf(v) === -1) return;
      if (score(v) >= besteScore) { beste = i; besteScore = score(v); }
    });
    return beste;
  }

  function beschrijf(input) {
    var r = input.getBoundingClientRect();
    var stijl = window.getComputedStyle(input);
    return {
      disabled: input.disabled,
      accept: input.getAttribute('accept') || '',
      zichtbaar: r.width > 0 && r.height > 0 && stijl.visibility !== 'hidden' && stijl.display !== 'none',
      inDialoog: !!input.closest('dialog[open], [role="dialog"], .modal, .k-window, .dialog, [aria-modal="true"]'),
    };
  }

  function bestand(msg) {
    var s = atob(msg.data);
    var bytes = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i);
    return new File([bytes], msg.naam || 'foto.jpg', { type: msg.type || 'image/jpeg', lastModified: Date.now() });
  }

  function plaats(msg) {
    var velden = Array.prototype.slice.call(document.querySelectorAll('input[type="file"]'));
    var i = kies(velden.map(beschrijf));
    if (i < 0) return null;
    var input = velden[i];
    var dt = new DataTransfer();
    if (input.multiple && input.files) Array.prototype.forEach.call(input.files, function (f) { dt.items.add(f); });
    dt.items.add(bestand(msg));
    input.files = dt.files;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, naam: msg.naam };
  }

  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
      if (!msg || msg.action !== 'SV_FOTO_UPLOAD') return false;
      var uit = null;
      try { uit = plaats(msg); } catch (e) { uit = null; }
      if (!uit) return false;          // no field here: let another frame answer
      sendResponse(uit);
      return false;
    });
  }

  return { kies: kies, neemtAfbeelding: neemtAfbeelding };
})();
if (typeof module !== 'undefined') module.exports = SVFotoUpload;

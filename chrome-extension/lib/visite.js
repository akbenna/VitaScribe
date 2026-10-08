/**
 * VitaScribe - Visite: het sleutelpaar van deze browser en het openen van een envelop
 *
 * Het visiteverslag komt versleuteld van de server (services/cloud_api/visite.py):
 * AES-256-GCM voor de inhoud, de AES-sleutel per browser ingepakt met
 * RSA-OAEP-SHA-256. Alleen de geheime sleutel van deze browser kan hem openen;
 * die is niet exporteerbaar en verlaat de browser nooit.
 *
 * Zonder DOM en zonder chrome.*: alleen WebCrypto (tests/js/visite.test.js
 * draait met de WebCrypto van Node). Het bewaren van de sleutel (IndexedDB)
 * staat in sidepanel/visite-ui.js.
 */
var SVVisite = (function () {
  'use strict';

  var subtle = (typeof crypto !== 'undefined' && crypto.subtle) ? crypto.subtle : null;
  var RSA = { name: 'RSA-OAEP', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' };

  function b64(bytes) {
    var s = '';
    new Uint8Array(bytes).forEach(function (b) { s += String.fromCharCode(b); });
    return btoa(s);
  }
  function unb64(tekst) {
    var s = atob(tekst);
    var u = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
  }

  /** A new key pair: {privateKey (not extractable), spki (base64), kid}. */
  async function nieuwSleutelpaar() {
    var paar = await subtle.generateKey(RSA, false, ['decrypt', 'unwrapKey']);
    var spki = await subtle.exportKey('spki', paar.publicKey);
    return { privateKey: paar.privateKey, spki: b64(spki), kid: await kidVan(spki) };
  }

  /** A short, stable name for a public key: base64url of the first 16 bytes of its SHA-256. */
  async function kidVan(spki) {
    var h = new Uint8Array(await subtle.digest('SHA-256', spki)).slice(0, 16);
    return b64(h).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  /** Open an envelope from the server; throws when it is not for this browser. */
  async function open(envelop, sleutel) {
    if (!envelop || envelop.v !== 1 || !envelop.sleutels) throw new Error('Onbekende envelop.');
    var ingepakt = envelop.sleutels[sleutel.kid];
    if (!ingepakt) throw new Error('Deze visite is versleuteld voor een andere browser. Open hem op de pc waarmee je de telefoon koppelde.');
    var aes = await subtle.unwrapKey('raw', unb64(ingepakt), sleutel.privateKey, { name: 'RSA-OAEP' },
      { name: 'AES-GCM' }, false, ['decrypt']);
    var data = await subtle.decrypt({ name: 'AES-GCM', iv: unb64(envelop.iv) }, aes, unb64(envelop.data));
    return JSON.parse(new TextDecoder().decode(data));
  }

  /** "10:40" today, "gisteren 16:05", or a date. */
  function tijd(sec, nu) {
    var d = new Date(sec * 1000), n = nu ? new Date(nu) : new Date();
    var hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    var dag = function (x) { return new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(); };
    var verschil = Math.round((dag(n) - dag(d)) / 86400000);
    return verschil === 0 ? hm : verschil === 1 ? 'gisteren ' + hm : d.getDate() + '-' + (d.getMonth() + 1) + ' ' + hm;
  }

  return { nieuwSleutelpaar: nieuwSleutelpaar, kidVan: kidVan, open: open, tijd: tijd, b64: b64, unb64: unb64 };
})();
if (typeof module !== 'undefined') module.exports = SVVisite;

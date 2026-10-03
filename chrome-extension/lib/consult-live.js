/**
 * VitaScribe - Live consult (verbinding met /api/v1/consult/stream)
 *
 * Stuurt het geluid van het consult in kleine stukjes naar de server, die
 * het gesprek per spreker volgt en na "stop" het verslag maakt. De opname
 * zelf houdt bricks.js bij als reservekopie: gaat hier iets mis, dan geeft
 * stop() { ok: false } terug en stuurt bricks.js de kopie alsnog op de
 * gewone manier op. Een consult gaat dus nooit verloren door een haperende
 * verbinding.
 *
 * Geen DOM en geen chrome.*: de WebSocket wordt meegegeven, zodat dit met
 * node --test na te lopen is.
 */
var SVConsultLive = (function () {
  'use strict';

  var OPEN = 1;

  /**
   * opties: { apiUrl, apiKey, praktijk, llmProvider, WebSocket, vraagsuggesties, taal,
   *           onVoortgang(seconden, sprekers), onFout(melding, terugval),
   *           onSuggesties({ klacht, vragen: [{ tekst, alarm }] }) }
   */
  function start(opties) {
    var WS = opties.WebSocket || (typeof WebSocket !== 'undefined' ? WebSocket : null);
    var adres = String(opties.apiUrl || '').replace(/\/$/, '').replace(/^http/, 'ws') + '/api/v1/consult/stream';
    var ws = new WS(adres);
    var klaar = false;       // server gaf "ready"
    var mislukt = false;     // live werkt niet meer; bricks.js valt terug
    var stoppen = false;
    var wachtrij = [];
    var afronden = null;     // resolve van stop()
    var timer = null;
    var uitkomst = null;

    function einde(resultaat) {
      if (uitkomst) return;
      uitkomst = resultaat;
      clearTimeout(timer);
      if (afronden) afronden(resultaat);
      try { if (ws.readyState <= OPEN) ws.close(); } catch (e) { /* al dicht */ }
    }

    function faal(melding, terugval) {
      if (mislukt) return;
      mislukt = true;
      wachtrij = [];
      if (stoppen) einde({ ok: false, terugval: terugval !== false, melding: melding });
      else if (opties.onFout) opties.onFout(melding, terugval !== false);
    }

    function verstuur(data) {
      if (mislukt) return;
      if (klaar && ws.readyState === OPEN) ws.send(data);
      else wachtrij.push(data);
    }

    ws.onopen = function () {
      ws.send(JSON.stringify({ type: 'auth', api_key: opties.apiKey || '', praktijk: opties.praktijk || '',
                               consent: true, llm_provider: opties.llmProvider || null,
                               vraagsuggesties: opties.vraagsuggesties === true,
                               taal: opties.taal || 'nl', modus: opties.modus || null,
                               versie: (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.getManifest)
                                 ? chrome.runtime.getManifest().version : null }));
    };
    ws.onmessage = function (bericht) {
      var e;
      try { e = JSON.parse(bericht.data); } catch (err) { return; }
      if (e.type === 'ready') {
        klaar = true;
        var rij = wachtrij;
        wachtrij = [];
        rij.forEach(function (d) { ws.send(d); });
      } else if (e.type === 'voortgang') {
        if (opties.onVoortgang) opties.onVoortgang(e.seconden || 0, e.sprekers || 0);
      } else if (e.type === 'controle') {
        // EU mode: did the speech service hear a conversation so far? (a count, no text)
        if (opties.onControle) opties.onControle({ seconden: e.seconden || 0, woorden: e.woorden || 0, goed: !!e.goed });
      } else if (e.type === 'suggesties') {
        // Vraagsuggesties (alleen als server en arts ze aanzetten).
        if (opties.onSuggesties) opties.onSuggesties({ klacht: e.klacht || '', vragen: Array.isArray(e.vragen) ? e.vragen : [] });
      } else if (e.type === 'result') {
        if (e.leeg) einde({ ok: false, terugval: true, melding: 'Live werd geen spraak gehoord.' });
        else einde({ ok: true, data: e.data });
      } else if (e.type === 'error') {
        faal(e.message || 'Fout in het live consult.', e.terugval);
      }
    };
    ws.onerror = function () { faal('De live verbinding met de server viel weg.', true); };
    ws.onclose = function () {
      if (!uitkomst) {
        if (stoppen && mislukt) einde({ ok: false, terugval: true, melding: 'De live verbinding werd gesloten.' });
        else faal('De live verbinding werd gesloten.', true);
      }
    };

    return {
      /** Een stuk geluid van de recorder. */
      stuur: verstuur,
      /** De patiënt is weg: vanaf deze seconde van de opname spreekt alleen de arts. */
      nadictaat: function (vanaf) { verstuur(JSON.stringify({ type: 'nadictaat', vanaf: vanaf })); },
      /** Werkt live nog? Zo niet, dan loopt de opname alleen lokaal door. */
      gezond: function () { return !mislukt; },
      /**
       * Na de laatste audio: vraag het verslag. Levert { ok, data } of
       * { ok: false, terugval, melding }.
       */
      stop: function (wachtMs) {
        stoppen = true;
        return new Promise(function (resolve) {
          afronden = resolve;
          if (uitkomst) { resolve(uitkomst); return; }
          if (mislukt) { einde({ ok: false, terugval: true, melding: 'Live verbinding was al weggevallen.' }); return; }
          verstuur(JSON.stringify({ type: 'stop' }));
          timer = setTimeout(function () {
            einde({ ok: false, terugval: true, melding: 'Het live verslag bleef te lang weg.' });
          }, wachtMs || 90000);
        });
      },
      /** Afbreken zonder verslag. */
      sluit: function () { einde({ ok: false, terugval: false, melding: 'Afgebroken.' }); },
    };
  }

  return { start: start };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVConsultLive;

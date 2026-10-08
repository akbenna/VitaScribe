/**
 * VitaScribe visite - de telefoonpagina (/v)
 *
 * De toestelsleutel komt uit de QR-code (na '#', dus nooit naar een server
 * gestuurd als adres) en blijft op dit toestel bewaard. Hij kan alleen een
 * visite insturen; lezen kan alleen het zijpaneel in de praktijk.
 *
 * Start neemt op, Stop stuurt de opname met toestemming en aanduiding naar
 * de server en gooit hem hier weg. Lukt het versturen niet, dan blijft de
 * opname in het geheugen van deze pagina voor "Opnieuw versturen".
 */
(function () {
  'use strict';

  var SLEUTEL = 'vsVisiteToestel';
  var $ = function (id) { return document.getElementById(id); };
  var token = null;
  var rec = null, stukken = [], start = 0, klok = null, wekslot = null;
  var wachtend = null;   // {blob, naam, aanduiding}: not sent yet

  function lees() { try { return localStorage.getItem(SLEUTEL); } catch (e) { return null; } }
  function bewaar(t) { try { if (t) localStorage.setItem(SLEUTEL, t); else localStorage.removeItem(SLEUTEL); } catch (e) { /* ignore */ } }

  function melding(tekst, soort) {
    $('melding').textContent = tekst || '';
    $('melding').className = 'melding' + (soort ? ' ' + soort : '');
  }

  function scherm(naam) {
    ['geen', 'klaar', 'opname'].forEach(function (s) { $(s).classList.toggle('hidden', s !== naam); });
    $('ontkoppel').classList.toggle('hidden', naam === 'geen');
  }

  async function post(pad, body) {
    var r = await fetch(pad, { method: 'POST', headers: { 'X-VitaScribe-Visite': token }, body: body });
    var d = await r.json().catch(function () { return {}; });
    if (!r.ok) {
      var e = new Error(typeof d.detail === 'string' ? d.detail : 'Server gaf fout ' + r.status + '.');
      e.status = r.status;
      throw e;
    }
    return d;
  }

  async function begin() {
    var uitHash = (location.hash || '').replace(/^#/, '');
    if (uitHash) {
      bewaar(uitHash);
      history.replaceState(null, '', location.pathname);   // the key out of the address bar
    }
    token = lees();
    if (!token) { $('pil').textContent = 'niet gekoppeld'; scherm('geen'); return; }
    try {
      var d = await post('/api/v1/visite/hallo');
      $('pil').textContent = (d.modus === 'eu' ? 'EU-modus' : 'Claude-modus') + (d.naam ? ' · ' + d.naam : '');
      scherm('klaar');
    } catch (e) {
      if (e.status === 401) { bewaar(null); token = null; $('pil').textContent = 'niet gekoppeld'; scherm('geen'); }
      else { $('pil').textContent = 'geen verbinding'; scherm('klaar'); }
      melding(e.message, 'fout');
    }
  }

  function mime() {
    var opties = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac'];
    for (var i = 0; i < opties.length; i++) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(opties[i])) return opties[i];
    }
    return '';
  }

  function tik() {
    var s = Math.floor((Date.now() - start) / 1000);
    $('klok').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }

  async function starten() {
    melding('');
    var stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      melding('Geen toegang tot de microfoon. Sta die toe in de instellingen van de browser.', 'fout');
      return;
    }
    var type = mime();
    rec = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
    stukken = [];
    rec.ondataavailable = function (e) { if (e.data && e.data.size) stukken.push(e.data); };
    rec.onstop = function () {
      stream.getTracks().forEach(function (t) { t.stop(); });
      var soort = rec.mimeType || type || 'audio/webm';
      var blob = new Blob(stukken, { type: soort });
      stukken = [];
      wachtend = { blob: blob, naam: 'visite.' + (/mp4|aac/.test(soort) ? 'm4a' : 'webm'), aanduiding: $('aanduiding').value.trim() };
      verstuur();
    };
    rec.start(1000);
    start = Date.now();
    tik();
    klok = setInterval(tik, 1000);
    try { wekslot = navigator.wakeLock ? await navigator.wakeLock.request('screen') : null; } catch (e) { wekslot = null; }
    scherm('opname');
  }

  function stoppen() {
    clearInterval(klok);
    if (wekslot) { wekslot.release().catch(function () {}); wekslot = null; }
    if (rec && rec.state !== 'inactive') rec.stop();
    scherm('klaar');
    melding('Versturen…');
  }

  async function verstuur() {
    if (!wachtend) return;
    $('opnieuw').classList.add('hidden');
    var fd = new FormData();
    fd.append('audio', wachtend.blob, wachtend.naam);
    fd.append('toestemming', 'true');
    fd.append('aanduiding', wachtend.aanduiding);
    try {
      await post('/api/v1/visite/opname', fd);
      wachtend = null;   // nothing stays on this phone
      $('aanduiding').value = '';
      $('toestemming').checked = false;
      $('start').disabled = true;
      melding('Verstuurd. Het verslag staat zo klaar in het zijpaneel, onder Visites.', 'goed');
    } catch (e) {
      melding(e.message + ' De opname staat nog op deze pagina; sluit hem niet.', 'fout');
      $('opnieuw').classList.remove('hidden');
    }
  }

  $('toestemming').addEventListener('change', function () { $('start').disabled = !this.checked; });
  $('start').addEventListener('click', starten);
  $('stop').addEventListener('click', stoppen);
  $('opnieuw').addEventListener('click', verstuur);
  $('ontkoppel').addEventListener('click', function () {
    if (wachtend && !window.confirm('Er staat nog een opname die niet verstuurd is. Toch ontkoppelen?')) return;
    if (!window.confirm('Deze telefoon ontkoppelen? Je moet daarna opnieuw de QR-code scannen.')) return;
    bewaar(null);
    token = null;
    wachtend = null;
    $('pil').textContent = 'niet gekoppeld';
    scherm('geen');
    melding('');
  });
  window.addEventListener('beforeunload', function (e) {
    if (wachtend || (rec && rec.state === 'recording')) { e.preventDefault(); e.returnValue = ''; }
  });
  begin();
})();

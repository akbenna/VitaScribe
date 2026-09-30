/**
 * VitaScribe - Tabbladen van het zijpaneel en "Minimaliseren"
 *
 * Drie tabbladen: Dicteren & SOEP, Brieven en Dossiervraag. De laatste keuze
 * blijft bewaard; knoppen in de popup kunnen een tabblad kiezen (svOpenView).
 *
 * Minimaliseren sluit het zijpaneel en laat het icoon voor de rest van deze
 * browsersessie de compacte popup openen. Een lopende consultopname gaat door
 * (die zit in het offscreen-document, met het bolletje op de pagina); het
 * dicteren in het paneel niet, dus dat moet eerst stoppen.
 *
 * Uses from sidepanel.js: state, setStatus()
 */
(function () {
  'use strict';

  var VIEWS = ['dictate', 'letters', 'dossier'];
  var $ = function (id) { return document.getElementById(id); };

  function showView(view) {
    if (VIEWS.indexOf(view) === -1) view = 'dictate';
    document.querySelectorAll('.view-tab').forEach(function (t) {
      var aan = t.dataset.view === view;
      t.classList.toggle('active', aan);
      t.setAttribute('aria-selected', aan ? 'true' : 'false');
    });
    VIEWS.forEach(function (v) { $('view-' + v).classList.toggle('hidden', v !== view); });
    try { localStorage.setItem('svView', view); } catch (e) { /* ignore */ }
    document.dispatchEvent(new CustomEvent('sv-view', { detail: view }));
  }

  document.querySelectorAll('.view-tab').forEach(function (tab) {
    tab.addEventListener('click', function () { showView(tab.dataset.view); });
  });
  try {
    var bewaard = localStorage.getItem('svView');
    if (bewaard && bewaard !== 'dictate') showView(bewaard);
  } catch (e) { /* ignore */ }

  // Popup buttons ("Brief schrijven", "Dossiervraag") choose the view.
  function applyRequestedView(v) {
    if (VIEWS.indexOf(v) === -1) return;
    showView(v);
    chrome.storage.session.remove('svOpenView');
  }
  chrome.storage.session.get('svOpenView').then(function (r) { applyRequestedView(r.svOpenView); });
  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === 'session' && changes.svOpenView) applyRequestedView(changes.svOpenView.newValue);
  });

  $('btn-minimaliseer').addEventListener('click', async function () {
    if (typeof state !== 'undefined' && state !== 'idle') {
      setStatus('Stop eerst het dicteren; daarna kun je minimaliseren.', true);
      return;
    }
    await chrome.runtime.sendMessage({ action: 'SV_WEERGAVE', weergave: 'compact' }).catch(function () {});
    // sidePanel.close (Chrome 141+) closes the panel; window.close() is the
    // fallback for older versions and does nothing once the panel is gone.
    try {
      if (chrome.sidePanel && chrome.sidePanel.close) {
        var w = await chrome.windows.getCurrent();
        await chrome.sidePanel.close({ windowId: w.id });
      }
    } catch (e) { /* fall back to closing the page */ }
    window.close();
  });

  window.SVViews = { show: showView };
})();

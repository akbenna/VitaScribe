// content.js v4 - werkt op elke pagina inclusief Bricks
// Robuuste tekst-extractie met meerdere fallbacks

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'ping') {
    sendResponse({ ok: true, url: window.location.href, title: document.title });
  }
  if (msg.action === 'scrapeDossier') {
    try {
      const result = scrapePagina();
      sendResponse(result);
    } catch(e) {
      sendResponse({ error: e.message, secties: {}, patiëntNaamRauw: '' });
    }
  }
  return true;
});

function scrapePagina() {
  const result = { secties: {}, patiëntNaamRauw: '', url: window.location.href };

  // Patiëntnaam zoeken
  const naamCandidates = [
    ...document.querySelectorAll('[class*="patient" i] [class*="name" i]'),
    ...document.querySelectorAll('[class*="naam" i]'),
    ...document.querySelectorAll('[class*="patiënt" i]'),
    ...document.querySelectorAll('h1'),
    ...document.querySelectorAll('h2'),
  ];
  for (const el of naamCandidates) {
    const txt = el.textContent.trim();
    if (txt.length >= 3 && txt.length <= 60 && /[a-zA-Z]{2}/.test(txt)) {
      result.patiëntNaamRauw = txt;
      break;
    }
  }

  const sectieMap = {
    'Journaal':         ['journaal','journal','soep','episode','consult','icpc'],
    'Medicatie':        ['medicatie','medication','recept','geneesmiddel'],
    'Voorgeschiedenis': ['voorgeschied','v.g.','history','anamnese'],
    'Lab':              ['laborator','lab','bepaling','bloedwaarden','uitslag'],
    'Correspondentie':  ['correspon','verwijz','specialist','ontslagbrief'],
    'Metingen':         ['meting','bloeddruk','gewicht','bmi'],
    'Allergieën':       ['allergie','intolerant','overgevoelig'],
    'Problemen':        ['probleem','diagnose','aandoening'],
  };

  // Methode 1: panelen met headers
  const panelSels = [
    '[class*="panel"]','[class*="section"]','[class*="tab-content"]',
    '[class*="widget"]','[class*="card"]','[class*="dossier"]',
    '[class*="module"]','article','section'
  ];
  for (const sel of panelSels) {
    document.querySelectorAll(sel).forEach(panel => {
      const hdrEl = panel.querySelector('h1,h2,h3,h4,h5,[class*="header" i],[class*="title" i],[class*="heading" i]');
      if (!hdrEl) return;
      const hdrTxt = hdrEl.textContent.toLowerCase();
      for (const [sectie, kws] of Object.entries(sectieMap)) {
        if (kws.some(kw => hdrTxt.includes(kw))) {
          const tekst = extractText(panel);
          if (tekst.length > 20) result.secties[sectie] = (result.secties[sectie]||'') + '\n' + tekst;
          break;
        }
      }
    });
  }

  // Methode 2: volledige pagina als fallback
  if (Object.keys(result.secties).length === 0) {
    const mainEl = document.querySelector('main,[role="main"],[class*="content" i]') || document.body;
    const alleTekst = extractText(mainEl);
    let restTekst = alleTekst;
    for (const [sectie, kws] of Object.entries(sectieMap)) {
      for (const kw of kws) {
        const regex = new RegExp('(' + kw + '[^\\n]*\\n)([\\s\\S]{0,2000})', 'i');
        const match = restTekst.match(regex);
        if (match && match[2].trim().length > 20) {
          result.secties[sectie] = match[2].trim().substring(0, 2000);
          restTekst = restTekst.replace(match[0], '');
          break;
        }
      }
    }
    if (Object.keys(result.secties).length === 0) {
      result.secties['Dossier (volledig)'] = alleTekst.substring(0, 12000);
    }
  }

  // Trim
  for (const k of Object.keys(result.secties)) {
    result.secties[k] = result.secties[k].trim().substring(0, 4000);
    if (result.secties[k].length < 5) delete result.secties[k];
  }
  return result;
}

function extractText(el) {
  const clone = el.cloneNode(true);
  clone.querySelectorAll('button,input,select,svg,img,script,style,nav,header,footer,[class*="btn" i],[class*="icon" i],[class*="toolbar" i],[class*="menu" i]').forEach(e => e.remove());
  return (clone.innerText || clone.textContent || '')
    .replace(/\t+/g,' ').replace(/ {3,}/g,'  ').replace(/\n{4,}/g,'\n\n\n').trim();
}

// Indicator
if (!document.getElementById('ha-dot') && document.body) {
  const dot = document.createElement('div');
  dot.id = 'ha-dot';
  dot.style.cssText = 'position:fixed;bottom:14px;right:14px;width:10px;height:10px;background:#1a5c38;border-radius:50%;z-index:2147483647;box-shadow:0 0 0 3px rgba(26,92,56,0.25);pointer-events:none';
  document.body.appendChild(dot);
}

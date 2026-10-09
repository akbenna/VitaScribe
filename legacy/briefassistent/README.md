# BriefAssistent v4

Huisarts informatiebrief assistent - Chrome/Edge extensie met Bricks HIS integratie.

## Installatie

### Stap 1: PDF.js (eenmalig)
Dubbelklik: `download-pdfjs.bat`

### Stap 2: Laden in Edge/Chrome
1. `edge://extensions` (of `chrome://extensions`)
2. Ontwikkelaarsmodus AAN
3. "Niet-ingepakte extensie laden" → selecteer deze map

### Stap 3: API sleutel
`console.anthropic.com` → account → API Keys → kopieer sleutel

## Gebruik
1. Open patiënt in Bricks → klik door alle tabs
2. Klik de extensieknop
3. "Ophalen uit Bricks"
4. U ziet: welke naam gevonden → wordt initialen
5. U ziet: per sectie aan/uit schakelaar
6. U kunt op "Toon" klikken → ziet EXACT wat er naar server gaat
7. Sleep vraag-PDF erin (optioneel)
8. Genereer brief

## Privacy garanties
- Volledige naam: NOOIT verstuurd, alleen initialen
- BSN/geboortedata/telefoon: gefilterd
- U schakelt per sectie wat er wel/niet naartoe gaat
- Preview toont exact wat verstuurd wordt
- Niets opgeslagen na sluiten

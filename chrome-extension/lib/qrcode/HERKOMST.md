# qrcode-generator 2.0.4

Meegeleverd, niet via npm geladen, net als `lib/pdfjs`. De extensie heeft geen
bouwstap en mag onderweg niets ophalen.

- Bron: https://github.com/kazuhikoarase/qrcode-generator (`dist/qrcode.js`)
- Auteur: Kazuhiko Arase
- Licentie: MIT (de tekst staat boven in het bestand zelf)
- Versie: 2.0.4, ongewijzigd overgenomen

Waarom meegeleverd en niet een QR-dienst op internet: zo'n dienst krijgt de
URL te zien die op het papier van de patiënt komt, en die URL zegt welke
aandoening het is. Dat is een gezondheidsgegeven. De code wordt daarom in de
browser van de arts gemaakt en verlaat die niet.

Bijwerken: haal `dist/qrcode.js` van de nieuwe versie op, vervang dit bestand,
en draai `node --test tests/js/thuisarts.test.js` - de proef op de afdruk
controleert dat er nog een QR uit komt.

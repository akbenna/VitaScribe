# VitaScribe in de Edge Add-ons-winkel

Dit document hoort bij `scripts/pack_store.sh`. Het bevat wat je in Partner Center
invult, in de volgorde waarin Partner Center erom vraagt, en de afbeeldingen staan
in `docs/edge-winkel/`.

## Vooraf: de winkelversie is een andere extensie

De eigen uitrol (`pack_extension.sh`, `.crx` met de `.pem`-sleutel, `update.xml`,
beleid `ExtensionInstallForcelist`) blijft bestaan en verandert niet. De winkel
ondertekent zelf en geeft de extensie een eigen ID. Voor een werkplek betekent dat:

- Wie de winkelversie installeert, vult het serveradres en de serversleutel opnieuw
  in. Instellingen gaan niet mee van de ene versie naar de andere.
- Staan beide versies op één werkplek, dan zijn er twee knoppen en twee keer
  Alt+Shift+D. Kies per werkplek één versie. Wil je op termijn alleen de
  winkelversie, zet dan in het beleid het winkel-ID in plaats van het eigen ID.
- De server laat elke herkomst toe (zie `DEPLOY.md`), dus het nieuwe ID werkt
  zonder aanpassing op Railway.

## Stap 3: het pakket

```bash
scripts/pack_store.sh                                  # standaard: smartvoice-production.up.railway.app
scripts/pack_store.sh ander-adres.up.railway.app       # als de server ooit verhuist
```

Het script schrijft `dist/store/vitascribe-edge-<versie>.zip`. Het haalt de
ontwikkeladressen (`localhost:8002`) uit het manifest en vervangt de rechten op
elke Railway-app door het ene serveradres. `chrome-extension/` zelf blijft
ongewijzigd. Verhoog vóór elke volgende upload de versie in
`chrome-extension/manifest.json`; Partner Center weigert een versie die hij al kent.

Het pakket is gecontroleerd door het in Chromium te laden: de service worker start,
en de instellingen, het zijpaneel en de popup openen zonder fouten.

## Stap 4: privacyverklaring

Adres na publicatie: **https://www.provita-care.nl/vitascribe/privacy**
(bron: `public/vitascribe/privacy.html` in de repo provita-care; het oude adres op
hetroosendael.nl stuurt door).

## Stap 5: de winkelvermelding

**Taal:** Nederlands.

**Naam:** komt uit het manifest: *VitaScribe — AI Consultassistent*.

**Categorie:** Productiviteit.

**Korte beschrijving:** komt uit het manifest: *Dicteren, SOEP en brieven
(informatie- en verwijsbrief) voor Bricks Huisarts*.

**Beschrijving** (kopiëren):

> VitaScribe is een consultassistent voor huisartsen die werken met Bricks Huisarts.
>
> Je dicteert in het veld waar je klikt, in Bricks of in elk ander tekstveld. Met één
> klik maak je van het dictaat een SOEP-regel.
>
> Een consult kan VitaScribe live volgen, nadat je hebt bevestigd dat de patiënt is
> geïnformeerd en toestemming geeft. Het houdt de stemmen van arts en patiënt uit
> elkaar en maakt na afloop een SOEP-verslag. Onderzoek dat je zwijgend deed, dicteer
> je na met de knop Nadicteren. Het verslag is een concept dat je zelf controleert.
>
> Informatie- en verwijsbrieven schrijf je in het zijpaneel: je kiest per onderdeel
> wat meegaat, en naam, BSN, adres en geboortedatum worden verwijderd voordat er iets
> verstuurd wordt.
>
> VitaScribe werkt met een VitaScribe-server die je praktijk beheert. Spraak gaat naar
> een EU-eindpunt, dictaten en consultverslagen naar een taalmodel in de EU. Brieven
> gaan pas na pseudonimisering naar een taalmodel in de VS, of naar de eigen
> AI-aanbieder van de praktijk. De extensie bewaart geen dossiers of brieven, toont
> geen advertenties en gebruikt geen volgdiensten.
>
> VitaScribe stelt geen diagnose en geeft geen behandeladvies. Alles wat het maakt, is
> een concept dat de arts controleert en ondertekent.
>
> Voor gebruik heeft je praktijk een licentie nodig. In de testfase is die gratis:
> meld de praktijk aan via https://smartvoice-production.up.railway.app/aanmelden.
> Elke gebruiker krijgt daarna een eigen sleutel.

**Zoektermen:** huisarts, Bricks, dicteren, SOEP, spraakherkenning, verwijsbrief,
consultverslag (maximaal zeven termen).

**Afbeeldingen** (in `docs/edge-winkel/`):

| Bestand | Waarvoor |
|---|---|
| `logo-300.png` | Logo van de extensie (300 × 300) |
| `tegel-440x280.png` | Kleine promotietegel (440 × 280) |
| `tegel-1400x560.png` | Grote promotietegel (1400 × 560, optioneel) |
| `winkel-1-dicteren.png` | Schermafbeelding: zijpaneel (1280 × 800) |
| `winkel-2-consult.png` | Schermafbeelding: popup met toestemming (1280 × 800) |
| `winkel-3-instellingen.png` | Schermafbeelding: instellingen (1280 × 800) |

De schermafbeeldingen zijn gemaakt van de lege extensie, zonder patiëntgegevens.
Controleer in Partner Center of de gevraagde afmetingen nog kloppen; het
uploadscherm noemt ze.

**Privacy:** privacyverklaring-URL zoals bij stap 4. Op de vraag of de extensie
persoonsgegevens verwerkt: ja (gezondheidsgegevens, via de server van de praktijk).

**Website en ondersteuning:** https://www.provita-care.nl, info@provita-care.nl.

**Zichtbaarheid:** Verborgen. De extensie is dan niet vindbaar in de winkel, maar wel
te installeren via de link die je deelt.

## Stap 6: notities voor de keurder

Partner Center heeft een veld *Notes for certification*. De keurders lezen Engels.
De keurder heeft een eigen sleutel nodig die op elke pagina werkt, niet alleen in
Bricks. Er zijn twee manieren:

- **Zonder licentieregister** (werkt nu al): maak een sleutel met
  `openssl rand -hex 24` en zet in Railway bij `API_USERS` een extra gebruiker
  `keuring-microsoft:<sleutel>` (komma ertussen als er al gebruikers staan).
  Haal die regel weg zodra de keuring klaar is.
- **Met het licentieregister** (als `DATABASE_URL`, `ADMIN_KEY` en `SLEUTELKLUIS`
  in Railway staan): maak in `/beheer` een praktijk "Keuring Microsoft" aan, zonder
  praktijknummer, activeer die als pilot en maak één gebruiker. Haal de praktijk uit
  na de keuring. Zonder praktijknummer werkt de sleutel op elke pagina.

Vul de sleutel hieronder in bij `<TESTSLEUTEL>`.

```text
VitaScribe is a dictation and documentation assistant for Dutch general
practitioners who use the Bricks Huisarts EHR. It needs a VitaScribe server
account; a test account is below. Bricks itself requires a healthcare login
that we cannot share, but every feature can be tested on any web page with a
text field.

TEST ACCOUNT
  Server URL: https://smartvoice-production.up.railway.app
  API key:    <TESTSLEUTEL>
  Open the extension options, enter both, click "Test verbinding" (test
  connection).

HOW TO TEST
  1. Open any page with a text field (for example a search box), click in it.
  2. Open the side panel from the toolbar popup ("Zijpaneel openen").
  3. Click the microphone, speak a sentence, click it again, then
     "Invoegen in veld" (insert into field). The text appears in the field.
  4. "Maak SOEP" turns the dictation into a structured SOEP note.
  Alt+Shift+D starts and stops dictation without the side panel.

PERMISSIONS
  - Content script on <all_urls>, all frames: inserts dictated text into the
    text field the user clicked, including in the embedded frames Bricks uses
    across several domains. It only reacts to focus on text fields. It never
    reads page content and never sends it anywhere.
  - Host permissions: the Bricks EHR domains (field detection and insertion)
    and the practice's own VitaScribe server (API calls).
  - activeTab, tabs, scripting: find the Bricks tab and insert text in the
    chosen field.
  - offscreen (USER_MEDIA, CLIPBOARD): keep the microphone recording when the
    popup or side panel closes or the doctor opens another page; clipboard as
    fallback for dictated text.
  - sidePanel: the main user interface.
  - storage: settings (sync), user-defined text snippets and the last result
    (local). The server API key is kept in local storage only and never in
    sync storage, so it does not travel with the user's Google account.
  - clipboardWrite: copy results. clipboardRead: only when the user clicks
    "Uit schermafdruk (klembord)" (from screenshot on clipboard) to read an
    image of a referral letter they copied themselves.

CONSULT RECORDING (side panel)
  The side panel records a consultation only after the doctor ticks that the
  patient consents. The recording runs in the offscreen document, so it keeps
  going when the doctor opens another page or closes the panel; the toolbar
  badge shows REC meanwhile. Audio is streamed in small chunks over a
  WebSocket to the practice's server, which transcribes it and returns a
  draft note. It can be tested on any page with a microphone.

DATA
  Audio and text go only to the server configured by the practice. Speech
  recognition uses an EU endpoint, and dictations and consultation notes use a
  language model in the EU. Referral letters are pseudonymised first (name,
  date of birth, BSN, address removed) and then sent to a language model in
  the US, or to the practice's own AI provider. No analytics, no advertising,
  no remote code. Privacy policy: https://www.provita-care.nl/vitascribe/privacy
```

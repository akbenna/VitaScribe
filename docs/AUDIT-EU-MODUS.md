# Audit VitaScribe: privacy en wetgeving, EU-modus (5 oktober 2026)

Getoetst aan de code (server en extensie 2.15.5), de Railway-configuratie en de
serverlogs. Niet getoetst: de contracten en de instellingen bij de aanbieders
zelf (Mistral, Railway). Dit is een technische audit, geen juridisch advies; de
DPIA en de verwerkersovereenkomsten horen langs de functionaris
gegevensbescherming of een privacyjurist.

## Conclusie

Technisch is de EU-modus goed ingericht. Elke stap die patiëntgegevens
verwerkt, gaat in die modus naar Mistral in de EU:

- de spraakherkenning;
- het SOEP-verslag;
- de controleronde;
- de nazorg;
- de medicijncontrole;
- brieven, dossiervragen en de post.

De server bewaart geen audio en geen tekst. Klinische beslisondersteuning staat
in deze modus uit. Daarmee blijft VitaScribe in de EU-modus een hulpmiddel voor
verslaglegging.

Toch is hij **nog niet klaar voor echte patiënten**. Er ontbreken vier dingen,
en die zijn alle vier organisatorisch of contractueel, niet technisch:

1. de verwerkersovereenkomst met Mistral en de bevestiging van zero data
   retention (ZDR);
2. een juridische basis voor Railway, een Amerikaans bedrijf in de keten;
3. een DPIA;
4. persoonlijke inlogsleutels, zodat het auditlog per arts registreert.

Tijdens de audit vond ik ook één technisch lek: oude, ongebruikte code die het
laatste consult op schijf kon bewaren. Dat is in deze versie verwijderd.

## Wat er in de EU-modus waarheen gaat

| Gegevens | Waar naartoe | Bewaard? |
|---|---|---|
| Audio van het consult | Server (Railway, NL) in het werkgeheugen, dan Voxtral (Mistral, FR) | Server: nee, gewist na verwerking. Mistral: nee, ZDR actief sinds 6 oktober 2026 |
| Geluidscontrole (30 s, 2 min, 5 min) | Hetzelfde stuk audio naar Voxtral | Alleen het aantal woorden in het log |
| Transcript, SOEP, controleronde, nazorg, medicijncheck | Mistral Large | Server: nee |
| Dossier en post (vraag aan het dossier) | Eerst gefilterd in de browser (naam, geboortedatum, BSN, adres), dan Mistral | Nee |
| Brieven | Gepseudonimiseerd, dan Mistral | Nee |
| Auditlog | Wie, wat, wanneer, zonder inhoud (NEN 7513), stdout en database | 5 jaar |
| Versie van de extensie | Header naar de server, in het log | Kort (Railway-log) |
| Live dicteren | Geweigerd in de EU-modus | n.v.t. |

In de EU-modus gaat geen enkele aanroep naar Anthropic, Deepgram of een andere
Amerikaanse AI-dienst. Ook een eigen Amerikaanse sleutel van de praktijk wordt
dan genegeerd.

## Bevindingen

### Blokkerend voor gebruik met echte patiënten

**1. Mistral: verwerkersovereenkomst en ZDR** (AVG art. 28). Opgelost op
6 oktober 2026, met één nieuw punt.

Mistral heeft ZDR geactiveerd voor de organisatie van de praktijk en bevestigd
dat API-data niet voor training wordt gebruikt (ticket #37361256, afschrift in
`docs/wetgeving/bewijs/mistral-zdr-2026-10-06.md`). De online-DPA geldt via de
voorwaarden en wordt niet apart ondertekend. Verwerking vindt standaard in de
EER plaats; Mistral sluit niet uit dat subverwerkers bepaalde gegevens vanuit
derde landen verwerken, met SCC's. De subverwerkerslijst is niet meegestuurd en
moet uit het Trust Center worden vastgelegd.

Nieuw: ZDR geldt alleen voor stateless endpoints. Het klonen van een stem voor
de tolk (`POST /v1/audio/voices`) is stateful: Mistral bewaart de stem van een
medewerker, zonder verwijderpad in de code. Die functie hoort uit te staan tot
Mistral bewaartermijn en verwijdering bevestigt, of apart in register en DPIA
te komen.

**2. Railway is een Amerikaans bedrijf in de keten** (AVG hoofdstuk V; CLOUD Act)

De server draait in `europe-west4`, in Nederland, en de data staat dus in de
EU. Maar Railway Corp. is gevestigd in de VS. Alle audio en tekst gaat door
die server, ook al bewaart hij niets. Daarmee was de tekst "alleen Europese
bedrijven" in de extensie niet juist; die is in 2.15.5 aangepast. Er zijn twee
routes:

- **Railway houden.** Sluit dan een verwerkersovereenkomst met Railway en zorg
  voor een doorgiftebasis (EU-US Data Privacy Framework of
  standaardcontractbepalingen). Of Railway onder het DPF gecertificeerd is, heb
  ik niet kunnen vaststellen; controleer dat. Neem het risico van de CLOUD Act
  mee in de DPIA.
- **Een server bij een Europees bedrijf**, zoals Scaleway, OVHcloud, Hetzner of
  Clever Cloud. Dan is de EU-modus van begin tot eind Europees. Technisch is
  dat een kleine verhuizing: dezelfde container, met andere omgevingsvariabelen.

Voor een formele EU-modus raad ik de tweede route aan.

**3. DPIA** (AVG art. 35)

De praktijk verwerkt gezondheidsgegevens met een nieuwe technologie: AI
luistert mee in de spreekkamer. Een DPIA is daarbij verplicht of op zijn minst
sterk aangewezen; zie ook de lijst van de Autoriteit Persoonsgegevens. Deze
audit en de tabel hierboven zijn er de technische basis voor.

**4. Gedeelde sleutel: het auditlog weet niet welke arts het was** (NEN 7513)

In de logs staat bij elk consult `user=gedeeld`. NEN 7513 vraagt dat elke
handeling herleidbaar is tot één persoon. De server kan dat al: met
`API_USERS` krijgt elke arts een eigen sleutel. Geef elke gebruiker een eigen
sleutel en trek de gedeelde sleutel in.

### Hersteld in deze versie (2.15.5)

**5. Oude code kon het laatste consult op schijf bewaren.** In de service worker
stond nog een oud opnamepad (`PROCESS_AUDIO`, `RECORDER_AUDIO`, met de pagina
`recorder/`). Dat pad zette het complete resultaat, transcript en SOEP, in
`chrome.storage.local`, en dat wordt op schijf geschreven. Niemand riep het nog
aan, maar een winkelreviewer ziet het wel, en bij een oudere installatie kan er
nog iets staan. Het pad is verwijderd. Bij de start ruimt de extensie
achtergebleven gegevens (`sv_data` en verwante sleutels) op. Consultresultaten
staan nu alleen in `chrome.storage.session`: in het werkgeheugen, en gewist
zodra de browser sluit.

**6. De privacytekst en de uitleg van de modus** noemen Railway nu met land en
regio, en beschrijven de controleronde. De bewering dat het laatste verslag
"op het apparaat" blijft staan is gecorrigeerd naar: werkgeheugen.

### Aandachtspunten (geen blokkade)

**7. Het consulttranscript is niet gepseudonimiseerd.** Wat in het gesprek
gezegd wordt, bijvoorbeeld een naam, gaat mee naar Mistral. Dat valt niet te
voorkomen zonder het verslag te beschadigen. De maatregelen zijn:

- niets wordt bewaard;
- er is alleen een EU-verwerker;
- er is toestemming van de patiënt;
- het dossier en de post worden in de browser gefilterd.

Benoem dit in de DPIA als restrisico.

**8. Testgereedschap in productie.** Twee functies schrijven tekst in het
Railway-log:

- de knop "Naar testset sturen", die transcripten in het log zet;
- de testset-rapporten, die volledige verslagen in het log zetten.

Beide zijn alleen voor beheerders. Ze waarschuwen dat ze alleen voor gespeelde
consulten zijn, en de testset bestaat alleen uit gespeelde consulten. Een
vergissing met een echt consult zou wel in een Amerikaans log belanden. Het
advies: zet deze functies in productie uit met een omgevingsvariabele, of
draai ze op een aparte testserver. De spraaktest vergelijkt met Deepgram (VS),
ook als de EU-modus aanstaat; ook dat is alleen voor gespeelde opnames.

**9. MDR en AI-verordening.**

- *EU-modus.* Er zijn geen vraagsuggesties, geen NHG-toets, geen
  Thuisarts-onderwerpen en geen rode vlaggen. Die zijn in de code afgeschermd
  met `clinical_decision_support()`. Wat overblijft zijn hulpmiddelen voor de
  verslaglegging: de medicijnnamen, de markeringen en de waarschuwing bij een
  te kort transcript. Zo blijft het een hulpmiddel bij het documenteren en geen
  medisch hulpmiddel, op voorwaarde dat het beoogde gebruik overal zo
  omschreven staat: in de winkeltekst, de handleiding en het privacybeleid.
- *Claude-modus met klinisch meedenken.* Die valt waarschijnlijk onder MDR
  regel 11 (klasse IIa) en kan zonder CE-markering niet op de markt.
- *AI-verordening.* Een documentatiehulpmiddel is geen AI-systeem met een hoog
  risico. Wel geldt de plicht tot AI-geletterdheid (art. 4) voor de praktijk
  als gebruiker: artsen moeten weten dat het model kan verzinnen. De
  markeringen, de regel "niet in de opname" en de weigering bij te weinig spraak
  helpen daarbij, maar de arts blijft verantwoordelijk voor het verslag (WGBO).

**10. Extensiewinkel.**

- De extensie heeft een content script op `<all_urls>` om te kunnen dicteren in
  elk tekstveld, en de rechten `clipboardRead` (voor de schermafdruk) en
  `tabs`. Leg dat in de indiening bij Partner Center per recht uit.
- Geef bij "gegevensverzameling" aan dat de extensie gezondheidsgegevens
  verwerkt, met een link naar het privacybeleid. Vermeld dat er geen verkoop
  is, geen reclame, en geen gebruik buiten het doel.
- In het winkelpakket staat geen `localhost` meer; dat controleert
  `pack_store.sh`.

**11. Toestemming en bewaren.** De server weigert een opname zonder bevestigde
toestemming (`REQUIRE_RECORDING_CONSENT`, staat standaard aan). De audio wordt
na verwerking gewist: in de EU-modus staat hij nooit op schijf, en bij een
upload wordt het tijdelijke bestand direct verwijderd.

## De Claude-modus in het kort

Daar gaan gegevens naar Deepgram (EU-eindpunt, Amerikaans bedrijf) en Anthropic
(VS). De technische maatregelen zijn dezelfde: niets wordt bewaard, het dossier
wordt gefilterd, brieven worden gepseudonimiseerd, en het auditlog is zonder
inhoud. Voor gezondheidsgegevens van echte patiënten is daar ook een
doorgiftebasis nodig, plus de afspraken uit punt 1 met elke aanbieder. Zoals de
praktijk al besloot, is deze modus nu niet voor echte patiënten.

## Volgorde van werk

1. ~~De verwerkersovereenkomst en ZDR van Mistral binnenhalen.~~ Gedaan op
   6 oktober 2026. Nog: subverwerkerslijst vastleggen en de kloonstem regelen.
2. Besluiten: Railway met DPA en DPF/SCC, of verhuizen naar een EU-host.
3. Persoonlijke sleutels per arts (`API_USERS`), en de gedeelde sleutel
   intrekken.
4. De DPIA opstellen, met deze audit als technische bijlage.
5. ~~Het testgereedschap in productie uitzetten.~~ Gedaan in 2.23.3: de routes
   staan standaard uit; de beheerder zet ze zelf aan en uit in Beheer. De standaardmodus is sinds
   2.23.3 EU; het slot (`TOEGESTANE_MODI=eu`) blijft een instelling in Railway.
6. Indienen bij Partner Center, met de toelichting op de rechten en de
   gezondheidsgegevens.

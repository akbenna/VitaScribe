# 14 Werkplan: VitaScribe volledig binnen de Europese regels

Stand 6 oktober 2026, versie 2.20.0.

Dit werkplan zet de analyse van 6 oktober om in stappen die je één voor één
afwerkt. De volgorde is bewust: eerst wat echte patiënten nu tegenhoudt, dan
het fundament onder fase 2, dan wat extra waarde geeft zonder nieuwe
verplichtingen.

Bij elke stap staat:

- **Waarom:** het probleem dat hij oplost.
- **Wat je doet:** de concrete handelingen.
- **Wie:** jij, je jurist of accountant, of Claude in de code.
- **Klaar als:** wanneer je de stap mag afvinken.

Wat Claude bouwt, komt als pull request met tests. Jij beslist en tekent.

## Overzicht

| Stap | Onderwerp | Wie | Doorlooptijd | Blokkeert |
|---|---|---|---|---|
| 1 | Overeenkomst Mistral met ZDR afronden | jij | 1 tot 4 weken | echte patiënten |
| 2 | Persoonlijke sleutels, testgereedschap uit | jij | 1 uur | echte patiënten |
| 3 | Praktijkslot op de modus | Claude, dan jij | 1 dag | fase 2 |
| 4 | Europese server naast Railway | jij en Claude | 1 dag | – |
| 5 | Claude via AWS Bedrock in Frankfurt | jij en Claude | 1 week | – |
| 6 | Europese spraakherkenning voor alle talen | jij en Claude | 2 weken | – |
| 7 | NHG-naslag zonder MDR | Claude, dan jurist | 1 week | – |
| 8 | Minder dossier versturen bij e-consult en verwijsbrief | Claude | 2 dagen | – |
| 9 | AI-verordening: tolk meldt zelf dat hij AI is | Claude | 1 dag | – |
| 10 | Telefoon en iPad: afspraken in de praktijk | jij | 1 uur | gebruik van de telefoon |
| 11 | ProVitaCare in een eigen BV en NEN 7510 | jij, accountant, jurist | 6 tot 12 maanden | fase 2 |
| 12 | Jurist-toets en DPIA vaststellen | jij en jurist | 2 weken | echte patiënten, fase 2 |

## Stap 1. Overeenkomst Mistral met ZDR afronden

**Waarom.** Zonder getekende verwerkersovereenkomst en zero data retention
(ZDR) mag de EU-modus niet met echte patiënten draaien (DPIA, R5). Dit is nu
het enige wat het gebruik in de eigen praktijk tegenhoudt.

**Wat je doet.**

1. Log in op console.mistral.ai met het account dat op naam van de
   rechtspersoon staat. Controleer dat het een betaald account is.
2. Vraag via het formulier voor zakelijke klanten (of via sales) om:
   - het Data Processing Agreement;
   - ZDR voor de API;
   - schriftelijke bevestiging van verwerking in de EU en van geen training.
3. Bewaar de getekende stukken bij het dossier. Commit ze niet in de code.
4. Vul in stuk 05 de status in en vink de regel in de checklist van de
   README af.

**Wie.** Jij.

**Klaar als.** Het DPA is getekend en ZDR staat schriftelijk bevestigd aan.

## Stap 2. Persoonlijke sleutels, testgereedschap uit

**Waarom.** Handelingen moeten herleidbaar zijn tot een persoon (NEN 7513,
DPIA R6). Testgereedschap mag geen echt consult loggen (R7).

**Wat je doet.**

1. Zet op de server `API_USERS=naam:sleutel,...`, met één sleutel per
   gebruiker. Haal `API_KEYS` (de gedeelde sleutel) weg.
2. Zet in Beheer bij elke beheerder de tweede factor aan (`ADMIN_TOTP`).
3. Het testgereedschap (spraaktest, soeptest, "Naar testset sturen") zit
   achter beheerdersrechten. Geef die alleen aan wie het nodig heeft, en
   gebruik het alleen met gespeelde consulten. Leg dat vast in stuk 09.
4. Geef elke gebruiker zijn eigen sleutel in Instellingen.

**Wie.** Jij.

**Klaar als.** Het auditlog toont namen in plaats van "gedeeld".

## Stap 3. Praktijkslot op de modus

**Waarom.** Nu kiest elke arts zelf tussen Claude en EU. Voor de DPIA moet de
praktijkhouder kunnen afdwingen dat echte patiënten alleen in een
goedgekeurde modus gaan. In fase 2 is dat een eis van elke klantpraktijk.

**Wat Claude bouwt.**

- Een instelling `TOEGESTANE_MODI` (bijvoorbeeld `eu`), op de server en per
  praktijk in het register.
- De server weigert een aanvraag in een modus die niet mag.
- De schakelaar in het paneel staat dan grijs, met de uitleg: "Je praktijk
  gebruikt alleen de EU-modus".

**Gebouwd (versie 2.21.0).**

- Server: `TOEGESTANE_MODI` (`eu`, `claude` of beide; een tikfout betekent
  alleen EU).
- Per praktijk: het vinkje "Alleen EU-modus" in Beheer.
- De server weigert elke aanvraag en elke dicteerverbinding in een modus die
  niet mag, met de uitleg wat de arts moet doen. Alleen
  `/api/v1/providers` antwoordt altijd, zodat de extensie weet wat mag.
- In de extensie staat de verboden modus grijs. Staat de schakelaar op zo'n
  modus, dan gaat hij zelf naar de toegestane, met uitleg.

**Wat je nog doet.**

1. Zet op de server de variabele `TOEGESTANE_MODI=eu` (Railway: Variables).
   Doe dat zolang de Claude-modus niet is goedgekeurd voor echte patiënten,
   dus tot stap 5 af is.
2. Of zet in Beheer bij Huisartsenpraktijk Roosendael het vinkje "Alleen
   EU-modus" aan. Dat geldt dan alleen voor die praktijk.
3. Open het zijpaneel. De Claude-knop staat nu grijs.

**Klaar als.** Een poging in de Claude-modus geeft een nette melding, en de
DPIA noemt het slot als maatregel (gedaan, R3 en R7).

## Stap 4. Een Europese server naast Railway

**Waarom.** Railway is een Amerikaans bedrijf en valt onder de CLOUD Act (DPIA,
R4). De server bewaart niets, maar het verkeer gaat er wel doorheen. Een
tweede server bij een Europese host haalt dat restrisico weg voor de
EU-modus, zonder iets te sluiten. Het is een **alternatief, geen
vervanging**:

- Railway blijft draaien, met beide modi.
- De extensie stuurt de EU-modus naar de Europese server, zodra je die
  invult.
- Leeg laten betekent: alles zoals nu.

**Gebouwd (versie 2.22.0).**

- In de extensie: *Instellingen › Server voor de EU-modus*, met een eigen
  sleutel (optioneel) en *Test EU-server*. Alles in de EU-modus volgt dat
  adres: consult, dicteren, brieven, dossiervraag, e-consult, tolk,
  telefoon en Beheer. De Claude-modus blijft op de gewone server.
- `deploy/eu/`: een kant-en-klare installatie met dezelfde code als Railway.
  Die bestaat uit Docker Compose, PostgreSQL, Caddy met automatisch
  TLS-certificaat, `env.voorbeeld` en een back-upscript.
- `deploy/eu/README.md`: de handleiding voor Hetzner of Scaleway, stap voor
  stap.

**Wat je doet.**

1. Kies een host:
   - **Hetzner** (Duitsland): goedkoop en eenvoudig.
   - **Scaleway** (Frankrijk): werkt meer zoals Railway.
2. Maak een account op naam van de rechtspersoon en teken de
   verwerkersovereenkomst.
3. Maak een server (Ubuntu 24.04) en een domein, bijvoorbeeld
   `vitascribe-eu.provita-care.nl`.
4. Volg `deploy/eu/README.md`: installeren, `.env` invullen met de waarden
   uit Railway, starten. Reken op een kwartier.
5. Vul in de extensie de Server voor de EU-modus in en klik *Test
   EU-server*.
6. Laat Claude stuk 02, 03, 05 en 06 bijwerken met de gekozen host.

**Wie.** Jij voor het account, de overeenkomst, het domein en het starten.
Claude voor de stukken.

**Klaar als.** *Test EU-server* zegt "In orde" en een consult in de
EU-modus loopt via de nieuwe server. Railway blijft daarnaast gewoon werken.

## Stap 5. Claude via AWS Bedrock in Frankfurt

**Waarom.** De Claude-modus is nu uitgesloten voor echte patiënten, omdat
Anthropic in de VS zit. Hetzelfde model draait ook bij AWS Bedrock in
Frankfurt, met een EU-inferentieprofiel dat alleen EU-regio's gebruikt. Dan
heb je twee sporen met hetzelfde juridische profiel, en wordt de keuze
tussen Claude en Mistral een kwaliteitskeuze. De code kent die route al
(`PHI_LLM_PROVIDER=bedrock`).

**Gebouwd (versie 2.23.2).** De route zelf bestond al: dezelfde modellen
(Sonnet 5 voor het verslag, Haiku 4.5 voor de rest) via het
EU-inferentieprofiel in Frankfurt. De server weigert te verzenden als de
regio of een model-ID buiten de EU kan routeren. Nieuw:

- De SOEP-test in `/beheer › Spraaktest` heeft bij *EU-model* de keuze
  *Claude via Bedrock (Frankfurt)*. Zo test je Bedrock op de gespeelde
  consulten voordat je iets omzet. Zonder AWS-sleutels of met een niet-EU
  instelling geeft de test een melding en verstuurt hij niets.
- Het paneel waarschuwt als de EU-modus op Bedrock staat maar de sleutels
  ontbreken, en ook als de Mistral-sleutel voor de spraak (Voxtral) ontbreekt.

**Wat je doet.**

1. Maak een AWS-account op naam van de rechtspersoon. De AWS GDPR Data
   Processing Addendum maakt automatisch deel uit van de voorwaarden.
   Download hem en bewaar hem.
2. Vraag in de console, regio `eu-central-1`, toegang aan tot Claude Sonnet 5
   en Claude Haiku 4.5 (Bedrock › Model access). Laat *model invocation
   logging* uit.
3. Maak een IAM-gebruiker met alleen `bedrock-mantle:CreateInference`,
   beperkt tot die twee modellen, en maak een toegangssleutel. Zet in Railway
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` en `BEDROCK_REGION=eu-central-1`.
   Wijken de model-ID's in de console af van `eu.anthropic.claude-sonnet-5`
   en `eu.anthropic.claude-haiku-4-5`, zet dan ook `BEDROCK_SOEP_MODEL` en
   `BEDROCK_MODEL`. Er verandert dan nog niets voor de artsen.
4. Draai de SOEP-test: *Spraaktest › EU-model: Claude via Bedrock ›
   Hele testset*. Vergelijk de valkuilen en markeringen met Claude direct en
   met Mistral.
5. Is de test goed, kies dan:
   - `EU_LLM_PROVIDER=bedrock`: de EU-modus schrijft met Claude in
     Frankfurt. De spraak blijft Voxtral (Mistral), want Bedrock doet geen
     spraak.
   - en/of `PHI_LLM_PROVIDER=bedrock` en `LETTERS_LLM_PROVIDER=bedrock`: de
     Claude-modus gaat dan ook via Frankfurt. De live spraak blijft Deepgram
     (Amerikaans bedrijf, EU-endpoint), dus het modusslot blijft nodig zolang
     dat zo is.

   Terug kan altijd: zet de variabele weer op `mistral` of `anthropic`.
6. Laat Claude stuk 03 en 05 bijwerken: AWS EMEA SARL als verwerker, data in
   Frankfurt. Doe dat pas als stap 5 hierboven echt aan staat.

**Wie.** Jij voor het account en de sleutels. Claude voor de test en de
stukken.

**Klaar als.** De soeptest is groen via Bedrock en de DPIA is bijgewerkt.

## Stap 6. Europese spraakherkenning voor alle talen

**Waarom.** Voxtral verstaat geen Turks, Pools en Oekraïens, en live dicteren
gaat nu via Deepgram (VS). Een Europese aanbieder die alle talen verstaat,
haalt Deepgram eruit en maakt de tolk in de EU-modus compleet. Op de
iPhone-tolk merk je het verschil direct.

**Kandidaten.**

- Gladia (Parijs). Live en achteraf, veel talen, verwerking in de EU.
- Speechmatics (Cambridge, VK). Het VK heeft een adequaatheidsbesluit, dus
  juridisch gelijk aan de EU. Goed in accenten.

**Gebouwd (server, oktober 2026).** Beide zitten erin als aanbieder achter
één instelling, `EU_STT_PROVIDER` (`voxtral`, `gladia` of `speechmatics`),
met dezelfde woordenlijst als Voxtral. Ze werken achteraf, net als Voxtral:
consult, tolk en telefoon-tolk. De server wist de opdracht bij de dienst
zodra de tekst binnen is. Met Gladia of Speechmatics biedt de tolk in de
EU-modus alle negen talen aan. De spraaktest heeft een keuze *EU-dienst*,
zodat je elk van de drie naast Deepgram legt. Zonder sleutel geeft de test
een melding en verstuurt hij niets.

Nog niet gebouwd: live dicteren via een van beide (realtime). Dat is de
laatste plek waar Deepgram nodig is, en komt als stap 6b zodra de keuze
gemaakt is: dan hoeft maar één realtime-koppeling gebouwd te worden.

**Wat je doet.**

1. Vraag bij beide een proefsleutel en hun verwerkersovereenkomst aan. Zet
   de sleutels in Railway: `GLADIA_API_KEY` en `SPEECHMATICS_API_KEY`. Voor
   de artsen verandert er dan nog niets.
2. Draai de spraaktest met tien gespeelde consulten, en de tolk met een
   collega die Turks of Arabisch spreekt. Voor de tolk: zet tijdelijk
   `EU_STT_PROVIDER` op de dienst die je test, en de tolk in de EU-modus.
3. Kies er een (`EU_STT_PROVIDER`), teken de overeenkomst, en laat Claude
   stuk 05 bijwerken. Daarna bouwt Claude het live dicteren (6b).

**Wie.** Jij voor de proefsleutels, de keuze en het tekenen. Claude voor de
aanbieders en de test.

**Klaar als.** De tolk verstaat in de EU-modus alle negen talen, en Deepgram
staat niet meer in de lijst voor echte patiënten.

## Stap 7. NHG-naslag zonder MDR

**Waarom.** Klinisch meedenken op de patiënt is beslissingsondersteuning
(MDR, regel 11). Een naslag die bij de ICPC-code toont wat de NHG-Standaard
zegt, zonder het op deze patiënt toe te passen, is dat niet. Zo komt de
meeste klinische waarde terug in de EU-modus, zonder art. 5 lid 5 of een
CE-markering.

**Wat Claude bouwt.**

- Een kaart "NHG bij deze code" onder de SOEP en in het e-consult: kern van
  het beleid, alarmsymptomen, wanneer verwijzen.
- Er gaat uitsluitend de ICPC-code en de titel mee, geen gegeven van de
  patiënt.
- Een opdracht aan het model die verbiedt de patiënt erbij te betrekken.
- Een duidelijke scheiding in de code, die ook een toezichthouder kan lezen.

**Wat je doet.** De tekst in stuk 01 laten toetsen door de jurist. De
redenering is de MDCG-richtsnoer 2019-11: software die alleen kennis
ontsluit, zonder op de individuele patiënt te rekenen, is geen hulpmiddel.

**Klaar als.** De jurist akkoord is. Het patiëntspecifieke vinkje blijft
bestaan voor wie de MDR-route wél loopt.

## Stap 8. Minder dossier versturen bij e-consult en verwijsbrief

**Waarom.** Dataminimalisatie (AVG art. 5 lid 1 sub c). Nu gaat alles mee wat
in beeld staat, tot 160.000 tekens. Bij een e-consult en een verwijsbrief is
de klacht bekend.

**Wat Claude bouwt.**

- Een voorselectie in de browser, zonder AI: de regels die passen bij de
  ICPC-code en de woorden van de vraag, plus medicatie, allergieën en
  episodelijst.
- De rest gaat alleen mee als de arts op "hele dossier" klikt.
- Dossiervraag blijft het hele dossier lezen, want daar zit de waarde.

**Klaar als.** Een gemiddelde verwijsbrief verstuurt minder dan de helft van
de tekens, met dezelfde kwaliteit in de testset.

## Stap 9. AI-verordening: de tolk meldt zelf dat hij AI is

**Waarom.** Sinds 2 augustus 2026 moet AI die met mensen communiceert
kenbaar maken dat het AI is (AI-verordening art. 50). De patiëntinformatie
dekt het al. Laat de tolk het ook zelf zeggen, in de taal van de patiënt.

**Wat Claude bouwt.**

- Bij de eerste beurt leest de tolk een vaste zin voor in de taal van de
  patiënt, en toont die ook groot op de telefoon: "Ik ben een
  computertolk. De dokter controleert wat ik vertaal."
- Bij de eigen stem van een collega komt in het register te staan wie
  toestemming gaf en wanneer.

**Klaar als.** De zin klinkt in alle negen talen.

## Stap 10. Telefoon en iPad: afspraken in de praktijk

**Waarom.** De telefoon is nu een tweede apparaat in de keten (stuk 03, R14).
Er wordt niets op bewaard, maar het toestel moet wel beveiligd zijn.

**Wat je doet.**

1. Leg in de werkinstructie (stuk 09) vast:
   - de telefoon heeft een code of Face ID en een automatische vergrendeling;
   - foto's van patiënten maak je alleen via VitaScribe, niet met de gewone
     camera;
   - na het spreekuur sluit je het tabblad.
2. Voor praktijktoestellen: zet ze in een beheersysteem (Apple Business
   Manager met MDM), zodat je ze op afstand kunt wissen.

**Klaar als.** Elke gebruiker van de telefoonfunctie heeft stuk 09 afgetekend.

## Stap 11. ProVitaCare in een eigen BV en NEN 7510

**Waarom.** Voor fase 2 moet het risico van de software los staan van de
praktijk. Klantpraktijken, zorggroepen en verzekeraars vragen om een NEN
7510-certificaat voordat ze tekenen.

**Wat je doet.**

1. Met de accountant: ProVitaCare onderbrengen in een eigen BV onder de
   holding.
2. Daarna een verwerkersovereenkomst tussen de praktijk en die BV (stuk 04).
3. Een certificerende instelling kiezen, bijvoorbeeld een die ook
   huisartsensoftware certificeert. Een gap-analyse laten doen en het
   ISMS opzetten. Stukken 06, 07 en 13 zijn daarvoor het begin.
4. Een product- en cyberverzekering afsluiten (stuk 10).

**Klaar als.** Het certificaat er is. Reken op zes tot twaalf maanden; begin
op tijd.

## Stap 12. Jurist-toets en DPIA vaststellen

**Waarom.** De stukken in dit dossier zijn concepten. Pas na toetsing kun je
ze tekenen en, in fase 2, publiceren.

**Wat je doet.**

1. Stuur stuk 01, 03, 04, 05, 08 en 11 naar een jurist voor zorg en ICT.
2. Verwerk het commentaar. Claude kan daarbij helpen.
3. Stel de DPIA vast (hoofdstuk 5) en teken stuk 01.
4. Zet de datum van de volgende herziening in je agenda.

**Klaar als.** De DPIA is getekend en ligt bij het verwerkingsregister.

## Wat al klaar is

- Verwerkersovereenkomst met Railway en DPF-status gecontroleerd.
- EU-modus: alle spraak en tekst via Mistral, de server bewaart niets.
- Pseudonimiseren in de browser en een vangnet op de server.
- Onveranderbaar auditlog zonder inhoud.
- Klinisch meedenken uit in de EU-modus, met een bewuste uitzondering voor
  NHG bij het e-consult.
- Telefoonkoppeling zonder opslag, in de modus van de arts.

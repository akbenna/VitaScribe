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
| 4 | Server naar een Europese host | jij en Claude | 1 week | fase 2 |
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

**Wat je doet.** De pull request bekijken en samenvoegen. Daarna op de server
`TOEGESTANE_MODI=eu` zetten, zolang de Claude-modus niet is goedgekeurd.

**Klaar als.** Een poging in de Claude-modus geeft een nette melding, en de
DPIA noemt het slot als maatregel.

## Stap 4. Server naar een Europese host

**Waarom.** Railway is een Amerikaans bedrijf en valt onder de CLOUD Act (DPIA,
R4). De server bewaart niets, maar het verkeer gaat er wel doorheen. Met een
Europese host verdwijnt dat restrisico helemaal. Voor fase 2 is het verhaal
dan eenvoudig: alles in de EU, bij Europese bedrijven.

**Wat je doet.**

1. Kies een host. Alle drie zijn Europese bedrijven met een eigen
   verwerkersovereenkomst en draaien de Dockerfile die er al is:
   - Hetzner (Duitsland);
   - Scaleway (Frankrijk);
   - OVHcloud (Frankrijk).

   Advies: Scaleway of Hetzner. Bij beide kun je een beheerde PostgreSQL
   afnemen. Hetzner is goedkoper. Scaleway zit dichter bij hoe Railway nu
   werkt.
2. Maak een account op naam van de rechtspersoon en teken de
   verwerkersovereenkomst. Bij beide zit die in de voorwaarden; download hem
   en bewaar hem.
3. Laat Claude de uitrol klaarzetten: een `docker-compose` of een
   handleiding voor de gekozen host, met PostgreSQL, TLS en back-ups van het
   register.
4. Zet de omgevingsvariabelen over. Gebruik de namen uit Railway; de waarden
   kopieer je zelf.
5. Geef de server een eigen domein, bijvoorbeeld
   `vitascribe.provita-care.nl`. Pas daarna in de extensie het serveradres
   aan, of laat Claude de standaard aanpassen.
6. Draai een week naast elkaar. Zet daarna Railway uit en verwijder de
   database daar.
7. Werk de stukken 02, 03, 05 en 06 bij: Railway eruit, de nieuwe host erin.

**Wie.** Jij voor het account, de overeenkomst en het domein. Claude voor de
uitrolbestanden en de documentatie.

**Klaar als.** De extensie praat met de nieuwe host en Railway is opgezegd.

## Stap 5. Claude via AWS Bedrock in Frankfurt

**Waarom.** De Claude-modus is nu uitgesloten voor echte patiënten, omdat
Anthropic in de VS zit. Hetzelfde model draait ook bij AWS Bedrock in
Frankfurt, met een EU-inferentieprofiel dat alleen EU-regio's gebruikt. Dan
heb je twee sporen met hetzelfde juridische profiel, en wordt de keuze
tussen Claude en Mistral een kwaliteitskeuze. De code kent die route al
(`PHI_LLM_PROVIDER=bedrock`).

**Wat je doet.**

1. Maak een AWS-account op naam van de rechtspersoon. De AWS GDPR Data
   Processing Addendum maakt automatisch deel uit van de voorwaarden.
   Download hem en bewaar hem.
2. Vraag in de console, regio `eu-central-1`, toegang aan tot het
   Claude-model (Bedrock › Model access).
3. Maak een IAM-gebruiker met alleen `bedrock:InvokeModel` en zet de sleutels
   op de server.
4. Zet `EU_LLM_PROVIDER=bedrock` (of laat Mistral, en gebruik Bedrock in de
   Claude-modus).
5. Draai de soeptest: tien gespeelde consulten, met dezelfde markeringen als
   met Mistral.
6. Laat Claude stuk 03 en 05 bijwerken: AWS EMEA SARL als verwerker, data in
   Frankfurt.

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

**Wat je doet.**

1. Vraag bij beide een proefsleutel en hun verwerkersovereenkomst aan.
2. Claude voegt beide toe als aanbieder achter een instelling, met dezelfde
   woordenlijst als nu.
3. Draai de spraaktest met tien gespeelde consulten, en de tolk met een
   collega die Turks of Arabisch spreekt.
4. Kies er een, teken de overeenkomst, zet hem in stuk 05.

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

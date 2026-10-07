# Stappenplan wetgeving: vijf producten, één praktijk

Stand 7 oktober 2026. Dit bestand staat woordelijk gelijk in de repo's `bricks-companion-`, `VitaScribe`, `consultspiegel`, `Bennahuiswerk` en `provita-care`, in de map `docs/wetgeving/`. Wie het wijzigt, wijzigt het in alle vijf. Naast dit plan staan in dezelfde map de leveranciersdossiers (`leveranciers/`) en de bewijsstukken (`bewijs/`), eveneens gelijk in alle repo's.

Het plan is geschreven vanuit de code en de documenten zoals die op 7 oktober 2026 in de repo's en in de Claude-documenten staan, en vanuit de correspondentie met Mistral. Het is geen juridisch advies. Waar een stap een oordeel van een functionaris gegevensbescherming (FG), jurist of MDR-adviseur vraagt, staat dat erbij.

## 1. Waarom één plan

De vijf producten delen hun leveranciers. Mistral zit in VitaScribe en ConsultSpiegel. Anthropic zit in alle vier de producten met AI. Railway host VitaScribe, ConsultSpiegel en de SciencePulse-pipeline van ProVita. Supabase en Vercel dragen ProVita en BennaHealth. Resend mailt voor BennaHealth en ProVita. Elke verwerkersovereenkomst, elke doorgiftetoets en elke regiocontrole hoeft dus maar één keer, op naam van één rechtspersoon, en geldt daarna voor elk product dat die leverancier gebruikt. Dat is de efficiëntie die dit plan zoekt: een praktijkdossier en een leveranciersdossier die gedeeld worden, en per product alleen wat werkelijk productspecifiek is (doel, DPIA, privacyverklaring, patiëntinformatie, MDR-kwalificatie).

Het omgekeerde geldt ook. De documenten in de vijf repo's spreken elkaar nu op vier punten tegen, en die tegenspraak is op zichzelf een risico: wie de ene verklaring leest, mag de andere niet tegenkomen. De vier punten staan in hoofdstuk 3 als besluiten.

## 2. Waar elk product staat

| Product | Wat het doet | Welke gegevens, naar wie | Papier dat er ligt | Wat het gebruik nu blokkeert |
|---|---|---|---|---|
| **Bricks Companion** (Chrome-extensie) | Leest het Bricks-scherm, rekent CVRM, DM2, CNS, COPD en astma uit | Patiëntgegevens blijven in de browser (sessieopslag). Geen enkele netwerkverbinding. Geen AI. | Fase 1-dossier compleet in concept (beoogd gebruik, risicoanalyse, QMS-light, openbare verklaring, AVG-stuk, werkinstructie, incidentenlog), fase 2-voorbereiding (MDR-routekaart, EULA, leveranciers). Railway-DPA getekend 5 oktober 2026, maar Bricks gebruikt Railway niet. | Alleen vaststelling en handtekeningen (fase 1, art. 5(5) MDR). Belangrijkste juridische vraag: wie is de maker, de praktijk of ProVita. |
| **VitaScribe** (consultopname naar SOEP, tolk, brieven) | Audio en transcript van echte consulten naar Mistral (EU-modus) of Deepgram en Anthropic (Claude-modus); server op Railway (NL) bewaart niets | Gezondheidsgegevens, ongepseudonimiseerd bij spraak en consulttekst; gepseudonimiseerd bij brieven en dossiervragen | Dossier in `docs/dossier/` (register, DPIA, verwerkersovereenkomst, subverwerkers, beveiliging, patiëntinformatie, werkinstructie), DPIA en verwerkersovereenkomst ook als Claude-doc (27 september, versie 2.2.1, verouderd). Railway-DPA getekend. **Mistral: ZDR en geen training bevestigd op 6 oktober 2026.** | Standaardmodus van de code is nog `claude` (Deepgram en Anthropic in de VS); het modusslot staat niet aan; testgereedschap stuurt altijd naar de VS; DPIA niet vastgesteld; persoonlijke sleutels nog niet uitgerold. |
| **ConsultSpiegel** (opleidingstool, MAAS 2.0) | Opname van (simulatie)consulten; EU-modus Mistral, Claude-modus Deepgram en Anthropic; Railway (NL); audio direct gewist, sessies 30 dagen | Simulatie: acteurs en aios. Echte consulten sinds 6 oktober mogelijk, alleen EU-modus of lokaal, met schriftelijke toestemming | Niets in de repo. Als Claude-doc: privacyverklaring en DPIA-opzet, verwerkersovereenkomst (concept), toestemmingsformulier en patiëntinformatie (alle drie concept, 5 en 6 oktober). | Voor simulatie: AI-geletterdheid, informeren van aios en acteurs, SBOH. Voor echte patiënten: DPIA, FG-toets op het toestemmingsformulier, pseudonimisering getest. AI Act bijlage III-3 (beoordeling in onderwijs) vraagt vóór 2027 een art. 6(3)-afweging. |
| **ProVita Care** (patiëntenplatform, GLP-1, voeding, SignaalZorg, rooster) | Supabase (eu-west-1), Vercel, Railway; AI via Anthropic en OpenAI (VS), foto's van maaltijden; Resend, MessageBird, web push; wearables; HIS-import; Jitsi-videoconsult | Gezondheidsgegevens van echte patiënten, deels gepseudonimiseerd | Verwerkingsregister (18 september, niet vastgesteld, alle DPA's "te bepalen"), voedings-DPIA en foto-addendum (niet vastgesteld), AI-audit, toestemmingsontwerp, publiekstekst, concept-DPA SignaalZorg (ongetekend). | Geen platform-DPIA, geen MDR-kwalificatie (risicoscores, consultvoorbereiding met differentiaaldiagnose), geen AI Act-classificatie. De live privacypagina claimt verwerkersovereenkomsten, NEN 7510 en bewaartermijnen die er niet zijn. Vier AI-routes zonder toestemmingspoort. |
| **BennaHealth** (voedingsapp in `Bennahuiswerk`) | Supabase (eigen project, regio onbekend), Vercel; foto's en dagverslagen naar Anthropic (VS); Resend mailt gewichten naar de beheerder | Gezondheidsgegevens van testers (gewicht, bloeddruk, labwaarden), foto's | DPIA (concept 15 september, verouderd), privacyverklaring in de app (23 september), beoogd doel (15 september), strategie chronische zorg | Wie verantwoordelijke is (praktijk of persoon); patiënt of consument; gewichtsmail naar de beheerder; Resend, Google Fonts en de Claude-weektaak ontbreken in de verklaring; de medicatietrede is na het beoogde doel opengezet; sleutellek van 26 augustus zonder vastlegging. |

## 3. Vijf besluiten die alles bepalen

Deze besluiten zijn van de praktijkhouder. Zolang ze niet genomen zijn, blijft elk document met een open plek staan, want ze bepalen wie tekent, waar data heen mag en welk kader geldt.

**Besluit 1: de rechtspersoon.** In de vijf repo's komen vier namen voor als verantwoordelijke of verwerker: Groepspraktijk het Roosendael, ProVita Care, ProVita Care BV en Benmedical BV; de SignaalZorg-DPA heeft dezelfde persoon aan beide kanten. De Mistral-organisatie staat op naam van de praktijk; de Railway-DPA op naam van ProVita. Het hangt af van het handelsregister welke rechtspersonen er werkelijk zijn. Nodig: één tabel met per product de verwerkingsverantwoordelijke (vrijwel zeker de praktijk, want die heeft de WGBO-relatie) en de verwerker (de rechtspersoon die de software levert en de leverancierscontracten houdt). Zijn dat twee rechtspersonen, dan is er per product een verwerkersovereenkomst tussen beide nodig (art. 28 AVG) en hoort elke leveranciers-DPA op naam van de verwerker. Is het één rechtspersoon, dan vervalt die tussenlaag, en moeten de Mistral- en Railway-accounts op dezelfde naam komen. Dit besluit kan alleen de praktijkhouder nemen, met accountant of jurist.

**Besluit 2: Railway houden of verhuizen. Beantwoord door Railway op 5 oktober 2026.** Railway past bijlage A van de DPA ("Special Categories of Data: None") voor niemand aan, dus de DPA dekt geen gezondheidsgegevens, ook niet in doorstroom. De logs van elke service staan in US West, en een contractuele toezegging voor alleen-EU bestaat op geen enkel plan (afschrift in `bewijs/railway-dpa-2026-10-05.md`). Daarmee is de keuze gemaakt: echte consulten van VitaScribe en ConsultSpiegel gaan naar een server bij een Europese host. Voor VitaScribe is die al gebouwd (werkplan stap 4, `deploy/eu/`, instelling "Server voor de EU-modus" in de extensie); voor ConsultSpiegel moet hij nog komen. Railway blijft voor gespeelde consulten, simulatie en diensten zonder gezondheidsgegevens. Wat de praktijkhouder nog kiest, is alleen de host: Hetzner (Duitsland) of Scaleway (Frankrijk).

**Besluit 3: Amerikaanse AI alleen voor niet-patiëntdata.** Deepgram en Anthropic verwerken nu ongepseudonimiseerde consulttekst en audio (VitaScribe-standaard, ConsultSpiegel-simulatie, ProVita-coach en foto's). Verdedigbaar is: Amerikaanse partijen alleen voor simulatie, dictaat zonder patiëntgegevens en gepseudonimiseerde tekst, en voor echte gezondheidsgegevens de EU-route (Mistral met ZDR, of Claude via Bedrock in Frankfurt) of lokaal. ConsultSpiegel doet dat al in code; VitaScribe heeft het slot gebouwd maar niet aangezet; ProVita heeft geen EU-route. Wie Amerikaanse AI voor echte patiëntgegevens wil houden, heeft per partij een DPA, een doorgiftegrondslag (DPF of SCC's) en een TIA nodig, plus de bewaartermijn bij de aanbieder in de patiëntinformatie.

**Besluit 4: BennaHealth is een besloten test voor consumenten, of een zorgtoepassing voor patiënten van de praktijk.** De privacyverklaring zegt het eerste, de DPIA het tweede, de export naar ProVita suggereert het tweede. Het eerste maakt de praktijk geen verantwoordelijke en houdt het buiten WGBO en NEN 7510, maar dan moet de app ook geen klinische functies (SCORE2, FIB-4, medicatietrede) aan die testers tonen zonder MDR-kwalificatie. Het tweede brengt de app onder hetzelfde regime als ProVita.

**Besluit 5: een FG of privacyadviseur.** Een huisartsenpraktijk met grootschalige verwerking van gezondheidsgegevens via AI heeft een FG nodig, of op zijn minst een aangewezen privacyadviseur die de DPIA's vaststelt (art. 37 AVG; de AP rekent een praktijk met meerdere artsen en AI-verwerking doorgaans tot "grootschalig"). Elk vastgesteld document in dit plan vraagt die handtekening. Zonder FG blijft alles concept.

## 4. Deel A: gezamenlijke stappen

Elke stap noemt wat nodig is, de grond, wie het doet, en wat al in de repo's staat.

| Nr | Stap | Grond | Wie | Status 7 oktober |
|---|---|---|---|---|
| A1 | **Rechtspersoon en rollen vastleggen** (besluit 1): tabel product × verantwoordelijke × verwerker × wie welk leveranciersaccount houdt | Art. 4, 24, 26, 28 AVG | Praktijkhouder, accountant | Open. Handelsregister controleren is in VitaScribe al als taak genoemd. |
| A2 | **FG of privacyadviseur aanwijzen**, melden bij de AP | Art. 37-39 AVG | Praktijkhouder | Open (besluit 5). |
| A3 | **Verwerkingsregister van de praktijk**: één register met een regel per product. VitaScribe stuk 02 en ProVita-register als invoer; Bricks stuk 09; ConsultSpiegel en BennaHealth ontbreken nog | Art. 30 AVG | Praktijk, met FG | Deelregisters bestaan; samenvoegen en vaststellen. |
| A4 | **Leveranciersdossier**: per leverancier DPA-versie en -datum (PDF), doorgiftegrondslag, regio (schermafdruk), bewaartermijn, subverwerkerslijst, trainingsuitsluiting. Eén map, gedeeld door alle producten | Art. 28, 44-46 AVG | Verwerker (ProVita) | Aangelegd in `docs/wetgeving/leveranciers/`. Mistral: bevestigd 6 oktober (bewijs in `bewijs/`). Railway: DPA getekend, bijzondere categorieën open. Supabase, Vercel, Deepgram, Anthropic, OpenAI, Resend: niets vastgelegd. |
| A5 | **Transfer impact assessment** voor de Amerikaanse partijen die gezondheidsgegevens zien (Railway, Deepgram, Anthropic, Resend, web push). Eén document, per partij een paragraaf | Hoofdstuk V AVG, Schrems II, DPF-besluit 2023 | Verwerker, FG | Open. Railway valt voor gezondheidsgegevens af (besluit 2, 5 oktober 2026); blijft over voor Deepgram, Anthropic, Resend en web push, en besluit 3 kan die lijst nog verkorten. |
| A6 | **NEN 7510-beleid van de praktijk** (informatiebeveiligingsbeleid, toegangsbeheer, logging volgens NEN 7513, incidentprocedure). De software verwijst er steeds naar; het document zelf ligt in geen repo | Besluit elektronische gegevensverwerking door zorgaanbieders art. 3; Wabvpz | Praktijk | Open. Alle vijf de producten leunen erop. ProVita toont publiek "NEN 7510" en "ISO 27001" zonder dat er een ISMS is (stap PV3). |
| A7 | **Datalekprocedure** (intern melden, beoordelen, 72 uur AP, betrokkenen) en een **incidentenlogboek** per product | Art. 33-34 AVG | Praktijk | Bricks heeft een logboek; VitaScribe-DPA zegt 24 uur; verder niets. Eén procedure, in alle repo's gelinkt. |
| A8 | **AI-geletterdheid**: korte instructie voor artsen, POH, aios en beheerders, met datum en namen | AI Act art. 4 (sinds 2 februari 2025) | Praktijk | Open; VitaScribe stuk 09 en ConsultSpiegel-handleiding zijn bruikbaar als basis. |
| A9 | **Toestemmings- en informatiemodel**: één patiëntinformatietekst per product, één wachtkamertekst, en vastlegging wie wanneer toestemming gaf. Toestemming is bij VitaScribe een waarborg (grondslag is 9(2)(h) met WGBO), bij ConsultSpiegel-patiënten en BennaHealth de grondslag zelf (9(2)(a)) | Art. 7, 9, 13 AVG; KNMG-richtlijn opnemen van gesprekken; WGBO 7:448 | Praktijk, FG | VitaScribe stuk 08, ConsultSpiegel-formulier (concept), ProVita `ai_consent`. BennaHealth heeft geen aparte handeling. |
| A10 | **Bewaartermijnen** per gegevenssoort, en de opruimtaak die ze uitvoert | Art. 5(1)(e) AVG; WGBO 7:454 (20 jaar dossier) | Verwerker | VitaScribe (niets bewaard, auditlog 5 jaar) en ConsultSpiegel (30 dagen) kloppen in code. ProVita belooft termijnen zonder code; BennaHealth belooft 3 maanden zonder taak. |
| A11 | **Verzekeraar informeren** (beroepsaansprakelijkheid, software in eigen gebruik; vanaf 9 december 2026 ook de nieuwe productaansprakelijkheidsrichtlijn 2024/2853 voor software die in de handel komt) | BW 6:185; richtlijn 2024/2853 | Praktijkhouder | Genoemd in Bricks en VitaScribe, nog niet gedaan. |
| A12 | **Halfjaarlijkse herbeoordeling**: DPA-versies, subverwerkerslijsten, regio's, nieuwe AI-routes in de code. In de agenda, met dit plan als checklist | Art. 24, 32 AVG | Verwerker | Eerste datum: april 2027. |

## 5. Deel B: per product

### B-VS VitaScribe

Doel in fase 1: echte consulten van de eigen praktijk in de EU-modus, met Mistral als enige AI-verwerker en Railway als host.

| Nr | Stap | Grond | Status |
|---|---|---|---|
| VS1 | Mistral-bevestiging verwerken: ZDR actief, geen training, DPA online, EER-verwerking standaard zonder absolute garantie. Subverwerkerslijst ophalen, DPA-versie en schermafdruk van de console vastleggen | Art. 28 AVG | **Bevestigd 6 oktober.** Dossier bijgewerkt in deze ronde (stuk 05, FASERING, README, AUDIT, DPIA R5). Lijst en schermafdruk nog te doen. |
| VS2 | Het modusslot aanzetten in productie: `TOEGESTANE_MODI=eu`, en de standaardmodus in de code op `eu` zetten | Besluit 3 | **Standaardmodus EU gebouwd in 2.23.1 (7 oktober 2026)**, in server en extensie; een aanvraag zonder modus gaat nooit naar de VS. `TOEGESTANE_MODI=eu` nog zetten in Railway (instelling, geen code). |
| VS3 | Testgereedschap (spraaktest, soeptest, testset) in productie uit, tenzij de beheerder het bewust aanzet | DPIA R7 | **Gebouwd in 2.23.1**: standaard uit, met een schakelaar in Beheer (Instellingen) die de beheerder zelf aan- en uitzet; elke wijziging komt met naam en tijdstip in het beheerlog. Uit: de routes geven 404, ook voor een beheerder, en er gaat niets naar een dienst. |
| VS4 | De kloonstem (`POST /v1/audio/voices`) valt buiten ZDR: stateful opslag van de stem van een medewerker bij Mistral, zonder verwijderpad. Keuze: functie uitzetten tot Mistral bewaartermijn en verwijdering bevestigt, of opnemen in register, DPIA en toestemmingstekst van de collega | Art. 28, 17 AVG | Nieuw gevonden. Vervolgvraag aan Mistral staat in `bewijs/mistral-zdr-2026-10-06.md`. |
| VS5 | Niet-bedoelde routes uit de code: `PHI_LLM_PROVIDER=gemini`, Groq en OpenAI-Whisper in `ALLOWED_STT_PROVIDERS` weigeren; Azure in de EU-modus alleen met een vastgelegd besluit | Dataminimalisatie, art. 25 | Codewijziging. |
| VS6 | Stuk 05 aanvullen met AWS Bedrock (klaar, niet actief), OpenAI op eigen sleutel, Vercel (review-app), Azure; stuk 02 met Deepgram en Anthropic zolang de Claude-modus bestaat | Art. 30 | Deels in deze ronde (Mistral-rij, kloonstem). Rest open. |
| VS7 | De publieke privacypagina (`site/vitascribe/privacy.html`, ook gespiegeld in `provita-care/public/vitascribe/`) noemt Deepgram, Anthropic en Railway en niet Mistral; het dossier zegt het omgekeerde. Eén tekst, afgeleid van stuk 05 | Art. 13 | Open. |
| VS8 | Persoonlijke sleutels per gebruiker, gedeelde sleutel intrekken, TOTP voor beheer | NEN 7510/7513 | Open. |
| VS9 | DPIA (stuk 03) invullen vanuit de EU-modus, met de geluidscontrole-uploads (tot vier keer de audio naar Voxtral) en Railway-besluit erin; vaststellen met FG | Art. 35 | Concept; R5 bijgewerkt. |
| VS10 | MDR: stuk 01 tekenen; `CLINICAL_DECISION_SUPPORT` en `ECONSULT_NHG_IN_EU` uit, of de keuze vastleggen (art. 5(5) eigen gebruik voor klinisch meedenken) | MDR regel 11, art. 5(5) | Open. |
| VS11 | AI Act art. 50: de tolk meldt dat hij een computertolk is (werkplan stap 9, niet gebouwd) | AI Act art. 50 (sinds 2 augustus 2026) | Codewijziging. |
| VS12 | Fase 2 (andere praktijken): verwerkersovereenkomst per praktijk (stuk 04 na juridische toets), NEN 7510-certificaat of ISO 27001, EU-host, CE klasse IIa als klinisch meedenken aan gaat | Art. 28; MDR | Pas na fase 1. |

### B-CS ConsultSpiegel

Doel in fase 1: simulatieconsulten in de eigen praktijk in Roosendaal; echte consulten alleen in de EU-modus met schriftelijke toestemming.

| Nr | Stap | Grond | Status |
|---|---|---|---|
| CS1 | De drie Claude-documenten (privacyverklaring en DPIA-opzet, verwerkersovereenkomst, toestemmingsformulier) in de repo zetten onder `docs/wetgeving/`, zodat code en papier samen versiebeheer hebben | Art. 5(2) verantwoordingsplicht | Open; dit plan verwijst ernaar. |
| CS2 | Mistral-bevestiging verwerken: de DPIA-opzet en de verwerkersovereenkomst hebben "ZDR na te gaan"; dat is nu bevestigd. De citaatkwaliteit van Mistral (29-36 procent verworpen citaten tegen 0-1 procent bij Claude) blijft een kwaliteitsrisico, geen privacyrisico | Art. 28 | Bewijs staat in `bewijs/`. Claude-docs nog aan te passen. |
| CS3 | Simulatie vrijgeven: aios en acteurs informeren (zij zijn betrokkenen, grondslag 6(1)(e/f), geen toestemming door afhankelijkheid), SBOH en opleidingsinstituut informeren, vastleggen dat de uitkomst niet meetelt | Art. 13-14; AI Act bijlage III-3 | Open. |
| CS4 | Het algemene toestemmingsvinkje (`consent_given`) legt niet vast wie en wanneer; de tekst verschilt tussen extensie en dashboard. Eén tekst, en `consent_by/_at` zoals bij echte consulten | Art. 7(1) | Codewijziging, klein. |
| CS5 | Echte patiënten: DPIA voltooien, toestemmingsformulier door FG, pseudonimisering testen op 10-20 consulten (de module noemt zichzelf een ondergrens), 2FA, en vastleggen dat externe STT altijd ongepseudonimiseerde audio krijgt | Art. 35, 9(2)(a) | Open. Code blokkeert al Claude en Deepgram voor echte consulten. |
| CS6 | Upload van mp4/mov: het hele videobestand gaat naar Voxtral of Deepgram, met beeld. Audio uitpakken vóór verzending | Dataminimalisatie | Codewijziging. |
| CS7 | Railway-regio vastleggen (schermafdruk), back-upbewaartermijn van Postgres beschrijven | Art. 30, 32 | Open. |
| CS8 | Afspeellijst: YouTube-consulten van derden worden verwerkt. Vastleggen: alleen opleider, alleen simulatie, en de auteursrechtelijke basis (YouTube-voorwaarden staan automatisch verwerken niet zonder meer toe) | Auteurswet; YouTube ToS | Open. |
| CS9 | AI Act: ConsultSpiegel beoordeelt leerresultaten (bijlage III-3b). Art. 6(3)-afweging schrijven: het systeem beslist niets, de opleider stelt vast. Datum van toepassing van de hoog-risicoverplichtingen verifiëren (oorspronkelijk 2 augustus 2026; de Digital Omnibus verschuift dit volgens de eigen docs naar december 2027) | AI Act art. 6(3), 26 | Open; nodig vóór fase 2. |
| CS10 | Vastleggen dat bij Claude de server-side fallback aanstaat, zodat het opgeslagen model niet altijd het uitvoerende model is; `response.model` opslaan | Verantwoording | Codewijziging, klein. |

### B-PV ProVita Care

Doel: platform met echte patiënten, dus het zwaarste regime. De volgorde hieronder is eerst de claims kloppend maken, dan de verwerkingen in het register, dan de DPIA.

| Nr | Stap | Grond | Status |
|---|---|---|---|
| PV1 | **Onjuiste publieke claims weghalen**: "verwerkersovereenkomsten met alle verwerkers" (privacypagina §6 en het AI-toestemmingsscherm), "NEN 7510", "ISO 27001", "AVG geïmplementeerd", bewaartermijnen die niet in code staan, 2FA voor medewerkers. Vervangen door wat waar is | Art. 5(1)(a), 13; oneerlijke handelspraktijk (BW 6:193) | Open. Dit is de eerste stap, omdat een onjuiste claim erger is dan een ontbrekende. |
| PV2 | Verwerkingsregister aanvullen met de elf verwerkingen die wel in code staan en niet in het register: SignaalZorg, HIS-import (`bricks-api`), Jitsi-videoconsult, web push, screenshot-import, consultvoorbereiding, helpdeskbot, intakesamenvatting en narratief, Google Fonts en jsDelivr, BennaHealth-koppeling, de producten VitaScribe, Transcripta en Bricks Companion | Art. 30 | Open. |
| PV3 | Leveranciers-DPA's vastleggen: Supabase, Vercel (plan controleren, Hobby heeft geen DPA), Railway (al getekend), Anthropic, OpenAI, Resend (EU-regio), MessageBird, VIPLive, Jitsi/8x8 of een eigen videodienst | Art. 28 | Alles "te bepalen". Via het gedeelde leveranciersdossier (A4). |
| PV4 | Toestemmingspoort sluiten voor de vier AI-routes die eromheen lopen (`general`, `helpdesk`, `intake_summary`, `treatment_narrative`) en de fototekst aanvullen met ontvanger, land en bewaartermijn | Art. 7, 13 | Codewijziging. |
| PV5 | Videoconsult via de publieke `meet.jit.si` met voorspelbare kamernamen stopzetten of vervangen door een dienst met DPA en EU-verwerking | Art. 28, 32 | Codewijziging, klein (route uit). |
| PV6 | Rechten van betrokkenen: de exportknop werkt niet, zelf-verwijderen pseudonimiseert alleen de patiëntrij, beheerders kunnen dossierstukken hard wissen (spanning met WGBO). Eén consistent ontwerp: export, verwijderen buiten het dossier, dossierstukken 20 jaar met vergrendeling | Art. 15-20; WGBO 7:454-455 | Codewijziging. |
| PV7 | Bewaartermijnen buiten voeding in code (opruimtaak), of de belofte van de privacypagina aanpassen | Art. 5(1)(e) | Codewijziging. |
| PV8 | MDR-kwalificatie voor het platform: risicoscores (SCORE2, FINDRISC, EOSS), GLP-1-redenering en contra-indicaties in de intake, en vooral de AI-consultvoorbereiding met differentiaaldiagnose en urgentie. Advies van een MDR-adviseur; tot dan die functie uit voor patiënten | MDR regel 11 | Open. |
| PV9 | AI Act-classificatie: de coach en de consultvoorbereiding (bijlage III-5 gezondheidszorg is beperkt; bijlage I via MDR als een functie een hulpmiddel is); art. 50 transparantie voor de chatbot en helpdesk | AI Act art. 6, 50 | Open. |
| PV10 | Platform-DPIA (AI-coach, SignaalZorg met 3.700 patiënten, declaratiecontrole, telemonitoring, videoconsult), met de voedings-DPIA als hoofdstuk | Art. 35 | Open. |
| PV11 | SignaalZorg-DPA tekenen pas na besluit 1 (nu dezelfde persoon aan beide kanten); AI-gebruik in `suggestMapping` erin opnemen | Art. 28 | Open. |
| PV12 | Beveiliging die de DPIA raakt: `chat-ai` controleert gebruiker en rol niet voor niet-patiënttypes; `bricks-api` vergelijkt sleutels in platte tekst met CORS `*`; `AI_PII_STRICT` in productie onbekend | Art. 32 | Codewijziging. |

### B-BH BennaHealth

Doel hangt af van besluit 4. Onder beide uitkomsten geldt:

| Nr | Stap | Grond | Status |
|---|---|---|---|
| BH1 | Gewichtsmail naar de beheerder stoppen of het gewicht eruit (`kal_prikkel_bouwen`, `kal_coach_bouwen`); de privacyverklaring zegt dat de beheerder geen gewicht ziet | Art. 5(1)(a), 32 | Codewijziging, klein. |
| BH2 | Privacyverklaring (`privacy.ts`) aanvullen: Resend, Vercel (IP-logs), Google Fonts (of lokaal zetten), de Claude-weektaak, en dat gewicht, stappen en workouts via de screenshot-import wél naar Anthropic gaan; OpenAI-coachroute kloppend maken | Art. 13 | Codewijziging; de proef `privacy.proef.ts` bewaakt de tekst. |
| BH3 | Supabase-regio en plan vastleggen; DPA; de anon-rechten op `kal_dagstand` en `kal_weekcijfers` nalopen (ruw gebruikers-id zonder token) | Art. 28, 32 | Open; live database controleren met `controle-md5.sql`. |
| BH4 | Sleutellek 26 augustus 2026 (service_role van het ProVita-project): rotatie bevestigen en een beoordeling onder art. 33 vastleggen, ook als de uitkomst "geen melding" is | Art. 33 | Open; nergens vastgelegd. |
| BH5 | DPIA herschrijven naar de huidige code (export en wissen bestaan, bewaartermijn 3 maanden, foto's naar de VS) en de opruimtaak voor de 3 maanden bouwen | Art. 35, 5(1)(e) | Open. |
| BH6 | Toestemming als handeling: een vinkje met tijdstip en versie, en een melding vóór de eerste foto dat die naar de VS gaat | Art. 7, 9(2)(a) | Codewijziging. |
| BH7 | Persoonsgegevens van de eigenaar uit de vaste systeemprompt van `kal-ai` | Dataminimalisatie | Codewijziging, klein. |
| BH8 | MDR: BEOOGD-DOEL bijwerken met de medicatietrede (sinds 20 september open) en SCORE2/FIB-4/STOP-Bang, of die functies dicht voor testers tot een adviseur heeft gekeken; de stellige "geen medisch hulpmiddel" in de privacyverklaring afzwakken tot de tekst van BEOOGD-DOEL | MDR regel 11 | Open. |
| BH9 | Huiswerk-AI (vragen en roosterfoto's van kinderen naar Anthropic): aparte paragraaf in het register en een eigen korte DPIA, want het gaat om minderjarigen | Art. 8, 35 | Open. |

### B-BC Bricks Companion

Doel in fase 1: eigen gebruik in de praktijk onder art. 5(5) MDR. Het dossier is het verst; wat rest is vaststellen.

| Nr | Stap | Grond | Status |
|---|---|---|---|
| BC1 | Besluit 1 toepassen op de makersvraag (praktijk of ProVita); daarna stuk 10 tekenen en stuk 01, 02, 04 vaststellen, rollen in 03 invullen | MDR art. 5(5)(a) | Open; het dossier markeert dit zelf. |
| BC2 | Openbare verklaring (stuk 05) publiceren; registervermelding (stuk 09) en de DPIA-afweging door de FG laten bevestigen | MDR 5(5)(e); art. 30, 35 AVG | Open. |
| BC3 | Privacyverklaring bijwerken: vijf domeinen inclusief `http://brickslokaal.nl`, de licentiesleutel in browsersync (praktijkgegevens, geen patiëntgegevens), lokale opslag met contactgegevens in het licentieregister, de "geanonimiseerde" notitiesleutel is pseudoniem | Art. 13 | Open. Tekst in `docs/PRIVACYVERKLARING.md` en `docs/privacy.html`. |
| BC4 | Verouderde documenten die data-export naar ProVita beschrijven (`PROVITA-CARE-INTEGRATION-SPEC.md`, `PUBLICATIE-GIDS.md`) markeren als historisch; store-vermelding (Edge, hidden) controleren en de release-tekst zonder store-verwijzing | Verantwoording | Open. |
| BC5 | Verzekeraar informeren; werkinstructie aftekenen; eerste maandelijkse steekproef | Fase 1-afronding | Open. |
| BC6 | Fase 2 pas na de zes poorten (MDR-route, CE klasse IIa via notified body, EULA, verzekering, store). Geen pilots bij andere praktijken daarvóór | MDR | Vastgelegd in `docs/fase2/README.md`. |

## 6. Volgorde

Eerst de besluiten uit hoofdstuk 3; ze kosten geen techniek en zonder besluit 1 kan niets worden getekend. Daarna, in deze week, de stappen die onjuiste beweringen wegnemen of lopende verwerkingen stoppen die niemand bewust heeft gekozen: PV1, PV5, BH1, VS2, VS3. Dat zijn kleine ingrepen met het grootste effect op aansprakelijkheid. Vervolgens het gedeelde deel (A3, A4, A5, A7) in één beweging voor alle producten. Pas dan de DPIA's, want die beschrijven wat er na die stappen overblijft, en een DPIA van een situatie die nog verandert is een DPIA die meteen verouderd is.

Wat Mistral betreft is de volgorde omgekeerd: daar is het papier binnen en loopt de code nog achter. VitaScribe hoeft alleen nog het slot om te zetten (VS2, VS3) en de kloonstem te regelen (VS4) om de EU-modus voor echte consulten in overeenstemming te brengen met wat Mistral heeft toegezegd.

## 7. Wat in deze ronde is gedaan

- Dit plan, de leveranciersdossiers en het Mistral-bewijsstuk in alle vijf de repo's onder `docs/wetgeving/`.
- VitaScribe: stuk 05 (Mistral-rij bevestigd, kloonstem toegevoegd), FASERING en dossier-README (checklist), AUDIT-EU-MODUS (blokkade 1 opgelost, nieuwe blokkade kloonstem), DPIA (R5).
- Bricks Companion: leveranciersdocument fase 2 bijgewerkt met de Mistral-bevestiging.
- ConsultSpiegel: verwijzing in de README naar het dossier.
- VitaScribe 2.23.1 (7 oktober 2026): VS2 en VS3 gebouwd (standaardmodus EU in server en extensie; testgereedschap standaard uit, met een schakelaar in Beheer die de beheerder zelf bedient), met tests. De overige codewijzigingen staan als afzonderlijke taken, elk klein genoeg voor één commit met test.
- Google Drive, map "Digitale praktijk": heringedeeld (01 Wetgeving en privacy met leveranciers en bewijsstukken, 02 Producten per product, 03 Slimme Praktijk, 04 Tetra, 05 Praktijk 2.0 en 3.0) en de dossiers als Google Docs erin gezet.

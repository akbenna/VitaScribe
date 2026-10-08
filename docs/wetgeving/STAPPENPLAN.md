# Stappenplan wetgeving: VitaScribe

Stand 8 oktober 2026. Dit is het stappenplan voor VitaScribe, met in dezelfde map alleen de leveranciers die dit product gebruikt. Tot 8 oktober stond er in alle vijf de repo's één gedeeld plan met een gedeeld leveranciersdossier; nu heeft elk product zijn eigen. Twee hoofdstukken gelden voor de hele praktijk en staan in alle vijf de repo's gelijk: de besluiten (hoofdstuk 3) en de gezamenlijke stappen (hoofdstuk 4). Wie daar iets wijzigt, wijzigt het in alle vijf.

Het plan is geschreven vanuit de code en de documenten zoals die op 7 oktober 2026 in de repo's en in de Claude-documenten staan, en vanuit de correspondentie met Mistral. Het is geen juridisch advies. Waar een stap een oordeel van een functionaris gegevensbescherming (FG), jurist of MDR-adviseur vraagt, staat dat erbij.

## 1. Waar VitaScribe staat

| Product | Wat het doet | Welke gegevens, naar wie | Papier dat er ligt | Wat het gebruik nu blokkeert |
|---|---|---|---|---|
| **VitaScribe** (consultopname naar SOEP, tolk, brieven) | Audio en transcript van echte consulten naar Mistral (EU-modus) of Deepgram en Anthropic (Claude-modus); server op Railway (NL) bewaart niets | Gezondheidsgegevens, ongepseudonimiseerd bij spraak en consulttekst; gepseudonimiseerd bij brieven en dossiervragen | Dossier in `docs/dossier/` (register, DPIA, verwerkersovereenkomst, subverwerkers, beveiliging, patiëntinformatie, werkinstructie), DPIA en verwerkersovereenkomst ook als Claude-doc (27 september, versie 2.2.1, verouderd). Railway-DPA getekend. **Mistral: ZDR en geen training bevestigd op 6 oktober 2026.** | Sinds 2.27.1 is de EU-modus de standaard en staat het testgereedschap uit. Het modusslot (`TOEGESTANE_MODI=eu`) staat nog niet aan in Railway; echte consulten horen op een Europese host (besluit 2); DPIA niet vastgesteld; persoonlijke sleutels nog niet uitgerold. |

## 2. Leveranciers van VitaScribe

Alleen de leveranciers die de code van VitaScribe werkelijk aanroept. Elk dossier staat in `leveranciers/`; bewijsstukken staan in `bewijs/`.

| Leverancier | Dossier | Rol in VitaScribe |
|---|---|---|
| Mistral AI | `leveranciers/mistral.md` | Spraak (Voxtral), tekst (Mistral Large) en voorlezen in de EU-modus. ZDR bevestigd 6 oktober. |
| Deepgram | `leveranciers/deepgram.md` | Spraak in de Claude-modus. |
| Anthropic | `leveranciers/anthropic.md` | Tekst in de Claude-modus. |
| OpenAI | `leveranciers/openai.md` | Alleen gepseudonimiseerde brieven, op de eigen sleutel van een praktijk. |
| Railway | `leveranciers/railway.md` | Hosting van de server. Dekt geen gezondheidsgegevens (5 oktober). |
| Europese host | `leveranciers/hosting-hetzner-scaleway.md` | Voor echte consulten (besluit 2): Cyso Cloud, Hetzner of Scaleway. |
| Vercel | `leveranciers/vercel.md` | Statische hosting van de review-app. |
| Overige | `leveranciers/overige.md` | AWS Bedrock, Azure, Gladia, Speechmatics en routes die uit de code horen. |

Bewijsstukken: `bewijs/mistral-zdr-2026-10-06.md`, `bewijs/railway-dpa-2026-10-05.md`.

## 3. Vijf besluiten voor de hele praktijk

Deze besluiten zijn van de praktijkhouder. Zolang ze niet genomen zijn, blijft elk document met een open plek staan, want ze bepalen wie tekent, waar data heen mag en welk kader geldt.

**Besluit 1: de rechtspersoon.** In de vijf repo's komen vier namen voor als verantwoordelijke of verwerker: Groepspraktijk het Roosendael, ProVita Care, ProVita Care BV en Benmedical BV; de SignaalZorg-DPA heeft dezelfde persoon aan beide kanten. De Mistral-organisatie staat op naam van de praktijk; de Railway-DPA op naam van ProVita. Het hangt af van het handelsregister welke rechtspersonen er werkelijk zijn. Nodig: één tabel met per product de verwerkingsverantwoordelijke (vrijwel zeker de praktijk, want die heeft de WGBO-relatie) en de verwerker (de rechtspersoon die de software levert en de leverancierscontracten houdt). Zijn dat twee rechtspersonen, dan is er per product een verwerkersovereenkomst tussen beide nodig (art. 28 AVG) en hoort elke leveranciers-DPA op naam van de verwerker. Is het één rechtspersoon, dan vervalt die tussenlaag, en moeten de Mistral- en Railway-accounts op dezelfde naam komen. Dit besluit kan alleen de praktijkhouder nemen, met accountant of jurist.

**Besluit 2: Railway houden of verhuizen. Beantwoord door Railway op 5 oktober 2026.** Railway past bijlage A van de DPA ("Special Categories of Data: None") voor niemand aan, dus de DPA dekt geen gezondheidsgegevens, ook niet in doorstroom. De logs van elke service staan in US West, en een contractuele toezegging voor alleen-EU bestaat op geen enkel plan (afschrift in `docs/wetgeving/bewijs/railway-dpa-2026-10-05.md` bij VitaScribe, ConsultSpiegel en ProVita Care). Daarmee is de keuze gemaakt: echte consulten van VitaScribe en ConsultSpiegel gaan naar een server bij een Europese host. Voor VitaScribe is die al gebouwd (werkplan stap 4, `deploy/eu/`, instelling "Server voor de EU-modus" in de extensie); voor ConsultSpiegel moet hij nog komen. Railway blijft voor gespeelde consulten, simulatie en diensten zonder gezondheidsgegevens. Wat de praktijkhouder nog kiest, is alleen de host: Cyso Cloud (Nederland), Hetzner (Duitsland) of Scaleway (Frankrijk). Vergelijking in `docs/wetgeving/leveranciers/hosting-hetzner-scaleway.md` bij VitaScribe en ConsultSpiegel (7 oktober 2026); dat advies (Hetzner) is op 8 oktober herzien: een Nederlandse host met NEN 7510-claim, Cyso Cloud, kost vergelijkbaar geld. Eerst het certificaat en de DPA van Cyso opvragen. Zie `docs/bedrijf/BLAUWDRUK.md` in de VitaScribe-repo, met ook de benchmark van de markt, de kostprijs per functie en de vraag wat als EU telt.

**Besluit 3: Amerikaanse AI alleen voor niet-patiëntdata.** Deepgram en Anthropic verwerken nu ongepseudonimiseerde consulttekst en audio (VitaScribe in de Claude-modus, ConsultSpiegel-simulatie, ProVita-coach en foto's). Verdedigbaar is: Amerikaanse partijen alleen voor simulatie, dictaat zonder patiëntgegevens en gepseudonimiseerde tekst, en voor echte gezondheidsgegevens de EU-route (Mistral met ZDR, of Claude via Bedrock in Frankfurt) of lokaal. ConsultSpiegel doet dat al in code; VitaScribe heeft sinds 2.27.1 de EU-modus als standaard, maar het slot dat de Claude-modus weigert staat nog niet aan; ProVita heeft geen EU-route. Wie Amerikaanse AI voor echte patiëntgegevens wil houden, heeft per partij een DPA, een doorgiftegrondslag (DPF of SCC's) en een TIA nodig, plus de bewaartermijn bij de aanbieder in de patiëntinformatie.

**Besluit 4: BennaHealth is een besloten test voor consumenten, of een zorgtoepassing voor patiënten van de praktijk.** De privacyverklaring zegt het eerste, de DPIA het tweede, de export naar ProVita suggereert het tweede. Het eerste maakt de praktijk geen verantwoordelijke en houdt het buiten WGBO en NEN 7510, maar dan moet de app ook geen klinische functies (SCORE2, FIB-4, medicatietrede) aan die testers tonen zonder MDR-kwalificatie. Het tweede brengt de app onder hetzelfde regime als ProVita.

**Besluit 5: een FG of privacyadviseur.** Een huisartsenpraktijk met grootschalige verwerking van gezondheidsgegevens via AI heeft een FG nodig, of op zijn minst een aangewezen privacyadviseur die de DPIA's vaststelt (art. 37 AVG; de AP rekent een praktijk met meerdere artsen en AI-verwerking doorgaans tot "grootschalig"). Elk vastgesteld document in dit plan vraagt die handtekening. Zonder FG blijft alles concept.

## 4. Gezamenlijke stappen

Elke stap noemt wat nodig is, de grond, wie het doet, en wat al in de repo's staat.

| Nr | Stap | Grond | Wie | Status 7 oktober |
|---|---|---|---|---|
| A1 | **Rechtspersoon en rollen vastleggen** (besluit 1): tabel product × verantwoordelijke × verwerker × wie welk leveranciersaccount houdt | Art. 4, 24, 26, 28 AVG | Praktijkhouder, accountant | Open. Handelsregister controleren is in VitaScribe al als taak genoemd. |
| A2 | **FG of privacyadviseur aanwijzen**, melden bij de AP | Art. 37-39 AVG | Praktijkhouder | Open (besluit 5). |
| A3 | **Verwerkingsregister van de praktijk**: één register met een regel per product. VitaScribe stuk 02 en ProVita-register als invoer; Bricks stuk 09; ConsultSpiegel en BennaHealth ontbreken nog | Art. 30 AVG | Praktijk, met FG | Deelregisters bestaan; samenvoegen en vaststellen. |
| A4 | **Leveranciersdossier**: per leverancier DPA-versie en -datum (PDF), doorgiftegrondslag, regio (schermafdruk), bewaartermijn, subverwerkerslijst, trainingsuitsluiting. Per product in `docs/wetgeving/leveranciers/`, met alleen de leveranciers die dat product gebruikt; een leverancier die twee producten delen staat in beide | Art. 28, 44-46 AVG | Verwerker (ProVita) | Sinds 8 oktober per product aangelegd. Mistral: bevestigd 6 oktober (bewijsstuk bij VitaScribe en ConsultSpiegel). Railway: DPA getekend, bijzondere categorieën open. Supabase, Vercel, Deepgram, Anthropic, OpenAI, Resend: niets vastgelegd. |
| A5 | **Transfer impact assessment** voor de Amerikaanse partijen die gezondheidsgegevens zien (Railway, Deepgram, Anthropic, Resend, web push). Eén document, per partij een paragraaf | Hoofdstuk V AVG, Schrems II, DPF-besluit 2023 | Verwerker, FG | Open. Railway valt voor gezondheidsgegevens af (besluit 2, 5 oktober 2026); blijft over voor Deepgram, Anthropic, Resend en web push, en besluit 3 kan die lijst nog verkorten. |
| A6 | **NEN 7510-beleid van de praktijk** (informatiebeveiligingsbeleid, toegangsbeheer, logging volgens NEN 7513, incidentprocedure). De software verwijst er steeds naar; het document zelf ligt in geen repo | Besluit elektronische gegevensverwerking door zorgaanbieders art. 3; Wabvpz | Praktijk | Open. Alle vijf de producten leunen erop. ProVita toont publiek "NEN 7510" en "ISO 27001" zonder dat er een ISMS is (stap PV3). |
| A7 | **Datalekprocedure** (intern melden, beoordelen, 72 uur AP, betrokkenen) en een **incidentenlogboek** per product | Art. 33-34 AVG | Praktijk | Bricks heeft een logboek; VitaScribe-DPA zegt 24 uur; verder niets. Eén procedure, in alle repo's gelinkt. |
| A8 | **AI-geletterdheid**: korte instructie voor artsen, POH, aios en beheerders, met datum en namen | AI Act art. 4 (sinds 2 februari 2025) | Praktijk | Open; VitaScribe stuk 09 en ConsultSpiegel-handleiding zijn bruikbaar als basis. |
| A9 | **Toestemmings- en informatiemodel**: één patiëntinformatietekst per product, één wachtkamertekst, en vastlegging wie wanneer toestemming gaf. Toestemming is bij VitaScribe een waarborg (grondslag is 9(2)(h) met WGBO), bij ConsultSpiegel-patiënten en BennaHealth de grondslag zelf (9(2)(a)) | Art. 7, 9, 13 AVG; KNMG-richtlijn opnemen van gesprekken; WGBO 7:448 | Praktijk, FG | VitaScribe stuk 08, ConsultSpiegel-formulier (concept), ProVita `ai_consent`. BennaHealth heeft geen aparte handeling. |
| A10 | **Bewaartermijnen** per gegevenssoort, en de opruimtaak die ze uitvoert | Art. 5(1)(e) AVG; WGBO 7:454 (20 jaar dossier) | Verwerker | VitaScribe (niets bewaard, auditlog 5 jaar) en ConsultSpiegel (30 dagen) kloppen in code. ProVita belooft termijnen zonder code; BennaHealth belooft 3 maanden zonder taak. |
| A11 | **Verzekeraar informeren** (beroepsaansprakelijkheid, software in eigen gebruik; vanaf 9 december 2026 ook de nieuwe productaansprakelijkheidsrichtlijn 2024/2853 voor software die in de handel komt) | BW 6:185; richtlijn 2024/2853 | Praktijkhouder | Genoemd in Bricks en VitaScribe, nog niet gedaan. |
| A12 | **Halfjaarlijkse herbeoordeling**: DPA-versies, subverwerkerslijsten, regio's, nieuwe AI-routes in de code. In de agenda, met dit plan als checklist | Art. 24, 32 AVG | Verwerker | Eerste datum: april 2027. |

## 5. Stappen voor VitaScribe

Doel in fase 1: echte consulten van de eigen praktijk in de EU-modus, met Mistral als enige AI-verwerker. Railway dekt geen gezondheidsgegevens (besluit 2); echte consulten horen op de Europese host uit `deploy/eu/`.

| Nr | Stap | Grond | Status |
|---|---|---|---|
| VS1 | Mistral-bevestiging verwerken: ZDR actief, geen training, DPA online, EER-verwerking standaard zonder absolute garantie. Subverwerkerslijst ophalen, DPA-versie en schermafdruk van de console vastleggen | Art. 28 AVG | **Bevestigd 6 oktober.** Dossier bijgewerkt (stuk 05, FASERING, README, AUDIT, DPIA R5). Subverwerkers van het EU-endpoint en bewaring van de kloonstem beantwoord op 7 oktober. Vervolgvragen van 8 oktober (endpoint, voorlezen, toegang van buiten de EER) staan open; zie `leveranciers/mistral.md`. Lijst en schermafdruk nog te doen. |
| VS2 | Het modusslot aanzetten in productie: `TOEGESTANE_MODI=eu`, en de standaardmodus in de code op `eu` zetten | Besluit 3 | **Standaardmodus EU gebouwd in 2.27.1 (7 oktober 2026)**, in server en extensie; een aanvraag zonder modus gaat nooit naar de VS. `TOEGESTANE_MODI=eu` nog zetten in Railway (instelling, geen code). |
| VS3 | Testgereedschap (spraaktest, soeptest, testset) in productie uit, tenzij de beheerder het bewust aanzet | DPIA R7 | **Gebouwd in 2.27.1**: standaard uit, met een schakelaar in Beheer (Instellingen) die de beheerder zelf aan- en uitzet; elke wijziging komt met naam en tijdstip in het beheerlog. Uit: de routes geven 404, ook voor een beheerder, en er gaat niets naar een dienst. |
| VS4 | De kloonstem (`POST /v1/audio/voices`) valt buiten ZDR: stateful opslag van de stem van een medewerker bij Mistral, zonder verwijderpad. Keuze: functie uitzetten tot Mistral bewaartermijn en verwijdering bevestigt, of opnemen in register, DPIA en toestemmingstekst van de collega | Art. 28, 17 AVG | Mistral antwoordde op 7 oktober: ongeveer 30 dagen bewaring, verwijderen met `DELETE /v1/audio/voices/{voice_id}`. De functie blijft uit tot de code de stem na gebruik zelf verwijdert. |
| VS5 | Niet-bedoelde routes uit de code: `PHI_LLM_PROVIDER=gemini`, Groq en OpenAI-Whisper in `ALLOWED_STT_PROVIDERS` weigeren; Azure in de EU-modus alleen met een vastgelegd besluit | Dataminimalisatie, art. 25 | Codewijziging. |
| VS6 | Stuk 05 aanvullen met AWS Bedrock (klaar, niet actief), OpenAI op eigen sleutel, Vercel (review-app), Azure; stuk 02 met Deepgram en Anthropic zolang de Claude-modus bestaat | Art. 30 | Deels in deze ronde (Mistral-rij, kloonstem). Rest open. |
| VS7 | De publieke privacypagina (`site/vitascribe/privacy.html`, ook gespiegeld in `provita-care/public/vitascribe/`) noemt Deepgram, Anthropic en Railway en niet Mistral; het dossier zegt het omgekeerde. Eén tekst, afgeleid van stuk 05 | Art. 13 | Open. |
| VS8 | Persoonlijke sleutels per gebruiker, gedeelde sleutel intrekken, TOTP voor beheer | NEN 7510/7513 | Open. |
| VS9 | DPIA (stuk 03) invullen vanuit de EU-modus, met de geluidscontrole-uploads (tot vier keer de audio naar Voxtral) en Railway-besluit erin; vaststellen met FG | Art. 35 | Concept; R5 bijgewerkt. |
| VS10 | MDR: stuk 01 tekenen; `CLINICAL_DECISION_SUPPORT` en `ECONSULT_NHG_IN_EU` uit, of de keuze vastleggen (art. 5(5) eigen gebruik voor klinisch meedenken) | MDR regel 11, art. 5(5) | Open. |
| VS11 | AI Act art. 50: de tolk meldt dat hij een computertolk is (werkplan stap 9, niet gebouwd) | AI Act art. 50 (sinds 2 augustus 2026) | Codewijziging. |
| VS12 | Fase 2 (andere praktijken): verwerkersovereenkomst per praktijk (stuk 04 na juridische toets), NEN 7510-certificaat of ISO 27001, EU-host, CE klasse IIa als klinisch meedenken aan gaat | Art. 28; MDR | Pas na fase 1. |

## 6. Volgorde

Eerst de besluiten uit hoofdstuk 3: ze kosten geen techniek, en zonder besluit 1 kan niets worden getekend. Daarna `TOEGESTANE_MODI=eu` in Railway (VS2): een instelling, geen code, en daarna kan geen arts per ongeluk de Claude-modus kiezen. Dan de kleine codewijzigingen die routes dichtzetten (VS5, VS11) en het papier dat de code moet volgen (VS6, VS7). Echte consulten pas op de Europese host (besluit 2), en de DPIA (VS9) pas als die keten vaststaat.

## 7. De andere producten

Elk product heeft een eigen stappenplan in `docs/wetgeving/STAPPENPLAN.md` van zijn repo.

| Product | Repo |
|---|---|
| ConsultSpiegel | `akbenna/consultspiegel` |
| ProVita Care | `akbenna/provita-care` |
| BennaHealth | `akbenna/Bennahuiswerk` |
| Bricks Companion | `akbenna/bricks-companion-` |

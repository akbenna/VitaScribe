# VitaScribe: blauwdruk voor compliance, hosting en prijs

Stand 8 oktober 2026. Gebaseerd op een benchmark van de Nederlandse aanbieders
van AI-verslaglegging, een onderzoek naar zorgwaardige hosting, de regels die
op dit moment gelden, en een kostprijsberekening uit de eigen code
(`kostprijsmodel.py`). Dit stuk beslist niets; het legt de keuzes voor met wat
er onder ligt. Volgens de taakverdeling uit de overdracht van 8 oktober beslist
het compliance-spoor, en voert de VitaScribe-repo uit.

**Over de bronnen.** De sites van de leveranciers waren vanuit de werkomgeving
niet te openen. Alles komt uit zoekresultaten. Bij elke bewering staat wat
voor bron het is: **[O]** officieel document of certificaat, **[L]** bewering
van de leverancier, **[D]** derde partij, **[N]** niet gevonden. Geen enkel
certificaat is zelf ingezien, behalve via een fragment van het Kiwa-register.
Wie een punt hard wil hebben, vraagt het certificaat, de DPA en de
subverwerkerslijst rechtstreeks op.

## 1. Wat de markt heeft gedaan

Vijf aanbieders zijn vergelijkbaar. Ask Aletta valt af: dat is een zoekmachine
voor richtlijnen, geen scribe, en zegt zelf niet gecertificeerd te zijn voor
medische gegevens [L].

| | Juvoly (Tandem) | Autoscriber | Medendo | Wellcom | G2 Speech |
|---|---|---|---|---|---|
| NEN 7510 | 7510-1:2024 [L] | Kiwa K-0215024/1, versie 2017+A1:2020, geldig tot 5-12-2026 [O, fragment] | ja, versie onbekend [L] | 7510:2024 [L] | niet geclaimd [N] |
| ISO 27001 | 2022 [L]; Tandem via Insight Assurance (VS, geen RvA) [L] | Kiwa K 0225872/1, tot 5-12-2026 [L] | ja, via Brand Compliance (RvA C548) [L] | 2022 [L] | ja [L] |
| Overig | ISO 13485, 42001, 14001; Tandem ook 27701, C5, HDS [L] | scope: "AI-based SaaS products that process personal healthcare information" [O] | | | ISO 27701, Britse normen [L] |
| Hosting | Juvoly: eigen GPU's bij NorthC Rotterdam; Tandem: Azure EU (Zweden) [L] | Azure NL/EER en Google EER [L] | Azure EU [L] | Azure NL en Zweden [L] | Azure, VK/EU [L] |
| Spraak en taal | eigen spraakmodel; Tandem: Azure en ElevenLabs [L] | Speechmatics, Google [L] | "leveranciersonafhankelijk" [L] | niet genoemd | eigen engine [L] |
| CLOUD Act | sleutels per praktijk bij een EU-partij buiten Azure [L] | "customer managed keys" [L] | niets gevonden | niets gevonden | niets gevonden |
| Openbaar | DPA en subverwerkers (Tandem) | Trust Centre, BoZ-model, DPA, subverwerkers, Intended Use | compliancepagina | Intended Use Statement | securitypagina |
| MDR | Tandem: scribe klasse IIa sinds 21-5-2026 [L] | "geen medisch hulpmiddel", Intended Use v2.0 [L] | niets gevonden | "geen medisch hulpmiddel", Intended Use v1 [L] | Brits klasse I, in de EU niets [N] |
| Digizo.nu | huisartsenzorg, geslaagd | huisartsenzorg en MSZ, geslaagd | ggz, geslaagd | huisartsenzorg, afgerond | niets gevonden |
| Prijs (ex btw) | €65 per gebruiker per maand, of €0,65 per ION per jaar voor de hele praktijk, onbeperkt [L] | €75 (500 gesprekken) of €150 (praktijk, 1000 gesprekken); via Medicom €65 en €125 [L] | €65 (100 gesprekken) [L] | €24,99 (60 chats) of €59,99 onbeperkt [L] | niet openbaar |

**Het patroon.** Wie AI-verslaglegging verkoopt aan Nederlandse huisartsen
heeft:
- een eigen NEN 7510- en ISO 27001-certificaat, via een RvA-geaccrediteerde
  instelling (Kiwa, Brand Compliance, DigiTrust);
- de hosting bij Microsoft Azure in de EU, met eigen sleutelbeheer als
  antwoord op de CLOUD Act. Juvoly is de uitzondering met eigen hardware in
  Rotterdam;
- een openbaar Intended Use-document dat de MDR-grens trekt;
- de BoZ Model Verwerkersovereenkomst of een eigen DPA;
- een Digizo.nu-toetsing als ingang bij de huisartsenzorg.

De HIS-leveranciers zelf (Medicom, Bricks, CGM) zitten niet bij Azure maar in
Nederlandse datacenters [L].

**Correcties op eerdere aannames.** Platform AI in de Zorg toont 34
leveranciers en 13 of 14 scribes, geen 39 [D]. G2 Speech claimt geen NEN 7510.
Ask Aletta is geen scribe. Digizo.nu is geen onafhankelijke toetser maar een
initiatief van de IZA-partijen, met het NHG [D].

## 2. Wat de regels werkelijk vragen

**NEN 7510 is een contracteis, geen wettelijke plicht voor de leverancier.**
De plicht ligt bij de zorgaanbieder (Wabvpz en het bijbehorende besluit; ook
voor die aanbieder is aantonen verplicht, een certificaat niet) [O, IGJ]. De
minister schreef op 24 april 2026, in antwoord op Kamervragen over de hack bij
ChipSoft, dat zorgaanbieders van softwareleveranciers eisen dat ook zij aan
NEN 7510 voldoen [O, 2026Z07496]. De Cyberbeveiligingswet geldt sinds
15 augustus 2026; volgens de toelichting bij de regeling voor de zorg
(Staatscourant 2026, 28763) vragen zorgentiteiten "in bijna alle gevallen"
aan te tonen dat de leverancier gecertificeerd is of werkt volgens NEN 7510
of ISO 27001 [O, alleen fragment]. Voor een leverancier is het certificaat
dus de toegangskaart tot de markt.

**NEN 7510 kan ook voor een softwarebedrijf.** NEN noemt "alle andere
organisaties die persoonlijke gezondheidsinformatie verwerken" [O]. Ga direct
voor NEN 7510-1:2024: bestaande certificaten moeten vóór 20 februari 2027 naar
die versie [D].

**De MDR is de grote open vraag.** De markt is verdeeld:
- Autoscriber en Wellcom noemen zich geen medisch hulpmiddel en leggen dat vast
  in een gedateerd Intended Use-document met een lijst van wat het product niet
  doet: diagnose, triage, beslisondersteuning [L].
- Tandem liet zijn scribe in mei 2026 als klasse IIa certificeren. Volgens
  Tandem oordeelde de Zweedse toezichthouder bij een inspectie dat een
  AI-scribe minstens klasse IIa is [L, Tandems eigen weergave; Tandem heeft
  belang bij een hoge lat]. Een Nederlandse ICT-jurist (Iusmentis, juli 2026)
  komt tot dezelfde conclusie [D].
- VitaScribe doet meer dan verslaglegging: rode vlaggen, ICPC-voorstellen,
  differentiaaldiagnose in de E, vraagsuggesties, meedenken, NHG bij het
  e-consult. Elk daarvan duwt richting MDR regel 11.

**Wat de huisartsenzorg zelf vraagt.** De LHV en het CMIO-netwerk (februari
2026) adviseren "alleen gevalideerde, bij voorkeur CE-gemarkeerde tools", een
pilot, en kritische vragen aan de leverancier over validatie en privacy [O].
Digizo.nu toetst pas bij schaal: 12 maanden in gebruik bij minstens 3
organisaties en 120 betalende gebruikers [O]. De IZA-partijen gaven
spraakgestuurd rapporteren in december 2025 de status "Kansrijk voor
opschaling", met Juvoly en Autoscriber als de twee getoetste tools [O].

**De CLOUD Act is actueel.** Op 7 oktober 2026 erkende het kabinet in
antwoorden op Kamervragen dat de CLOUD Act kan botsen met de AVG en toegang kan
geven tot Nederlandse zorgdata [D, Computable].

## 3. Antwoord op de vier vragen uit de overdracht

**1. AWS Bedrock in Frankfurt.** AWS EMEA SARL is een dochter van een
Amerikaans bedrijf, dus de CLOUD Act speelt, net als bij Azure en Railway. Het
verschil met Railway zit in de overeenkomst: Railway sluit gezondheidsgegevens
uit, de grote clouds (AWS, Microsoft) laten ze toe. Juridisch kan Bedrock-EU
dus, met DPA, SCC's of DPF, en een transferrisicoanalyse. Of het "EU" heet,
is een keuze. Advies: noem het niet EU, maar "EU-regio, Amerikaanse moeder".

**2. Speechmatics (VK).** Het VK heeft een adequaatheidsbesluit van de
Europese Commissie, dus doorgifte is rechtmatig zonder extra waarborgen. Wel
moet dat besluit bij elke controle nog gelden; leg de datum vast. Speechmatics
heeft geen Amerikaanse moeder voor zover gevonden. Advies: toegestaan in de
EU-modus, met de categorie "adequaat land".

**3. Deepgram.** Amerikaans bedrijf, EU-endpoint. Voor echte patiënten alleen
met een DPA die gezondheidsgegevens toelaat, een TIA en een DPIA-aanvulling.
Zolang die er niet zijn: alleen gespeelde consulten, zoals het dossier al zegt.
Gladia (Frankrijk) is het Europese alternatief voor live tekst, als dat later
gebouwd wordt.

**4. Wat telt als EU.** Een nieuwe bevinding maakt dit scherper: ook Mistral
heeft Amerikaanse moederbedrijven in de keten. De subverwerkerslijst noemt
Microsoft (Zweden, Noorwegen), Google (Nederland, België) en CoreWeave
(inferentie in de EER) [O, trust.mistral.ai]. "EU-bedrijf" en "geen
Amerikaanse partij in de keten" zijn dus niet hetzelfde. Voorstel voor drie
niveaus, vast te leggen in het compliance-spoor en daarna in `data_policy.py`:

| Niveau | Betekenis | Nu |
|---|---|---|
| EU-soeverein | EU-bedrijf, verwerking in de EER, geen Amerikaanse subverwerker voor deze dienst | nog geen; kandidaten: Nebul, Fundaments, eigen GPU |
| EU | EU- of adequaat bedrijf, verwerking in de EER of adequaat land, DPA staat gezondheidsgegevens toe | Mistral (met ZDR), Voxtral, Gladia, Speechmatics |
| EU-regio | verwerking in de EER, Amerikaanse moeder | Bedrock Frankfurt, Azure EU |

De EU-modus staat dan alleen niveau "EU" en hoger toe. Bij Mistral moet nog
worden nagevraagd welke subverwerkers het ZDR-verkeer via `api.mistral.ai`
werkelijk raken. Is dat Google of CoreWeave, dan hoort dat in het register en
de DPIA, en is het eerlijke woord voor de EU-modus "Europese aanbieders",
niet "geen Amerikaanse partijen".

## 4. Kostprijs per functie

Berekend uit de code: welk model, hoe vaak, met hoeveel tekst. Prijzen in
dollar, omgerekend tegen €0,87. Schatting, geen meting.

| Handeling | EU-modus (Mistral) | Claude-modus |
|---|---|---|
| Consult van 8 minuten, compleet | 5,2 dollarcent | 11,1 dollarcent |
| waarvan spraakherkenning | 4,7 | 4,6 |
| Brief (dossier 30.000 tekens) | 0,7 | 3,3 |
| Dossiervraag | 0,6 | 2,5 |
| Klinisch meedenken | 0,2 | 1,2 |
| E-consult | 0,7 | 3,6 |
| Specialistenbrief analyseren | 0,4 | 1,8 |
| Tolk, 15 minuten | 15 (waarvan 10 voorlezen) | 15 |
| Thuisarts | 0 | 0 |

Per arts per maand (400 consulten, 40 brieven, 40 dossiervragen, 20 keer
meedenken, 20 e-consulten, 40 specialistenbrieven, 40 dictaten, 4 keer tolk):
**ongeveer €20 in de EU-modus en €43 in de Claude-modus.** In de EU-modus is
93 procent daarvan het consult zelf; alle extra functies samen kosten minder
dan €1,50.

Drie gevolgen:

1. **De meerwaarde van VitaScribe is bijna gratis te leveren.** Brieven,
   dossiervragen, correspondentie en e-consult kosten fracties van een cent.
   Een prijs per handeling of AI-credits zijn daarom niet nodig. Alleen de tolk
   kost per keer iets merkbaars.
2. **Een besparing ligt klaar.** De drie tussentijdse controles van de opname
   (na 30 seconden, 2 en 5 minuten) transcriberen telkens vanaf het begin en
   zijn bijna de helft van de spraakkosten. Een lichtere controle scheelt
   ongeveer 30 procent per consult.
3. **De vaste kosten bepalen de prijs.** Zie hieronder.

## 5. Hosting: drie routes

Het advies van 7 oktober (Hetzner) is achterhaald. Er zijn Nederlandse hosts
met een NEN 7510-claim voor vergelijkbaar geld.

**A. Budget, tot ongeveer €500 per maand.**
- Cyso Cloud (Alkmaar, Nederlands, geen Amerikaanse moeder): NEN 7510 en
  ISO 27001 [L], een virtuele server van 2 vCPU en 4 GB voor €22 per maand
  [L], datacenters in Noord-Holland en Frankfurt. Beheerde PostgreSQL is in
  bèta [D]. Self-service, per uur.
- Mistral met ZDR voor spraak en tekst.
- `deploy/eu/` werkt er zonder aanpassing.
- **Eerst te controleren:** het certificaat van Cyso (instelling, versie,
  scope moet de cloudservers dekken) en of de DPA gezondheidsgegevens toelaat.
  Dat laatste was bij Railway en Scaleway precies het probleem.
- Reserve: TransIP. Het DNV-certificaat dekte "VPS by TransIP", maar liep tot
  24 mei 2026 [O]; een verlenging is niet gevonden.

**B. Professioneel en zorgwaardig, ongeveer €600 tot €2.000 per maand.**
- Een beheerde NEN 7510-host met beheerde database en 24/7-ondersteuning:
  Rootnet (beheerde server €265 per maand [L]), Intermax (bedient ongeveer 30
  procent van de ziekenhuizen [L]), Previder of TrueFullstaq (offerte).
- Mistral, of de taal via Nebul (Leiden, claimt NEN 7510 [L]).
- Patchen, back-ups en logging liggen dan bij de host, met een SLA.

**C. Enterprise en ziekenhuisklaar, enkele duizenden euro's per maand.**
- C1, het marktpatroon: Azure EU met klantsleutels in een HSM, Customer
  Lockbox, Azure OpenAI in de EU-datazone (met aangepaste misbruikmonitoring,
  alleen via een Microsoft-accountteam) en Azure Speech. Microsofts DPA laat
  gezondheidsgegevens toe [O]; Microsoft zelf is niet NEN 7510-gecertificeerd
  maar levert een dekkingsrapport onder NDA [O]. De CLOUD Act blijft.
- C2, soeverein: Intermax of Fundaments met eigen GPU, met Voxtral (open
  gewichten) en een open Mistral-model daarop. Geen Amerikaanse partij in de
  keten.

**Advies.** Fase 1 (eigen praktijk): route A bij Cyso, mits het certificaat en
de DPA kloppen. Fase 2 (verkopen): route A of B voor de server, en voor de AI
een keuze die past bij hoe VitaScribe zich wil onderscheiden. Kiest VitaScribe
voor "Europees", dan is Azure (C1) juist geen voordeel: daar zitten alle
concurrenten al, en het kabinet erkent het risico nu zelf.

## 6. Prijs: een rekenvoorbeeld

**Vaste kosten** (schattingen uit de bronnen):

| Post | Jaar 1 | Daarna per jaar |
|---|---|---|
| NEN 7510:2024 + ISO 27001, begeleiding en audit | €8.000 tot €20.000 | €2.000 tot €4.000 (toezichtaudit) |
| Pentest | €3.000 tot €10.000 | idem |
| Hosting (route A tot B) | €600 tot €24.000 | idem |
| Product- en cyberverzekering | offerte | offerte |
| Eigen tijd: support, onderhoud, releases | niet in geld uitgedrukt | |

**Wat de markt vraagt.** Juvoly vraagt per praktijk €0,65 per ION per jaar,
onbeperkt en met integratie. Voor een praktijk van 2.100 patiënten is dat
ongeveer €1.365 per jaar, of €114 per maand voor het hele team. Dat is het
scherpste anker in de markt. Wellcom zit op €59,99 per arts onbeperkt,
Autoscriber op €150 per maand voor een praktijk tot 1.000 gesprekken.

**Wat VitaScribe kost om te leveren.** Een praktijk met twee artsen gebruikt
in de EU-modus voor ongeveer €40 per maand aan AI. Per ION is dat ongeveer
€0,23 per jaar.

**Rekenvoorbeeld, geen advies over de hoogte.** Een praktijkprijs van €0,95
per ION per jaar (€165 per maand voor 2.100 patiënten) laat na de AI-kosten
ongeveer €125 per maand over. Bij vaste kosten van rond de €2.000 per maand in
het eerste jaar zijn dan ongeveer 16 praktijken nodig om quitte te spelen, en
daarna, als de certificering staat, ongeveer 6 tot 8. De vraag die de prijs
bepaalt is dus hoe snel die praktijken er komen, niet wat een handeling kost.

**De pakketgrens hoort langs de MDR te lopen, niet langs de kosten.**
- Zonder CE-markering te verkopen, als het Intended Use-document het zo
  vastlegt: opnemen, transcriberen, SOEP als concept, dicteren, brieven,
  dossiervraag als zoekfunctie met bronvermelding, specialistenbrief
  samenvatten, tolk (met de AI-melding uit stap 9), Thuisarts.
- Pas met CE-markering (klasse IIa): klinisch meedenken, rode vlaggen als
  advies, ICPC- en differentiaalvoorstellen, vraagsuggesties, NHG bij het
  e-consult.

Een betaald "Intelligence"-pakket met meedenken is dus pas te verkopen na een
MDR-traject. Reken daarvoor op ISO 13485, een notified body en een tot twee
jaar.

## 7. Wat letterlijk over te nemen is

1. **Een Intended Use-document, nu al.** Versie en datum, beoogd gebruik,
   doelgroep, en een lijst van wat VitaScribe níet doet. Dit kost niets en
   trekt de MDR-grens waar Autoscriber en Wellcom hem trekken. Stuk 01 van het
   dossier is de basis.
2. **Een Trust Centre naar de opbouw van Autoscriber**, aangevuld met wat daar
   ontbreekt: overzicht, Intended Use, NEN 7510, ISO 27001, AVG, AI-verordening,
   BoZ-model verwerkersovereenkomst, DPA, algemene voorwaarden,
   privacyverklaring, subverwerkers (met juridische entiteit, land,
   datalocatie, doel), DPIA, CVD-beleid met `security.txt`, samenvatting van de
   pentest, statuspagina, bewaartermijnen.
3. **De BoZ Model Verwerkersovereenkomst** in plaats van een eigen tekst. De
   branche kent hem en hij vraagt van de verwerker aantoonbaar NEN 7510 of
   ISO 27001.
4. **Eén waarheid over bewaren.** Juvoly, Medendo en Autoscriber spreken
   zichzelf tegen tussen privacypagina, FAQ en voorwaarden. VitaScribe schrijft
   de termijnen één keer op, in getallen, en verwijst er overal naar.
5. **Een openbare subverwerkerslijst** met meldtermijn en bezwaarprocedure,
   zoals Tandem (14 dagen).
6. **Een model-DPIA voor klantpraktijken.** Stuk 03 bestaat al; maak er een
   versie van die een praktijk kan overnemen, zoals Juvoly via de regionale
   inkoop deed.
7. **Inkopen via zorggroepen en ROS'en.** Juvoly groeide via raamovereenkomsten
   met regionale korting.
8. **Niet overnemen:** "GPAI-modelaanbieder" (Autoscriber; een scribe is een
   AI-systeem, geen GPAI-model), "HIPAA compliant", "C5-providers" zonder
   namen, een Brits keurmerk als bewijs voor de EU.

## 8. Volgorde

| Wanneer | Wat | Wie |
|---|---|---|
| Nu | Intended Use-document (stuk 01 aanscherpen) en de pakketgrens langs de MDR | compliance-spoor, daarna instellingen in VitaScribe |
| Nu | Cyso: certificaat en DPA opvragen; bij ja, de EU-server daar | praktijkhouder |
| Nu | Mistral: welke subverwerkers het ZDR-verkeer raken | praktijkhouder (vervolgmail) |
| Nu | Besluit 1: op welke rechtspersoon contracten en certificaat komen | praktijkhouder, accountant |
| Fase 1 | ISMS opzetten en NEN 7510:2024 + ISO 27001 aanvragen bij Kiwa, Brand Compliance of DigiTrust; begeleiding licht houden (Ateron of een pakket voor kleine bedrijven, met de gratis NEN-compliancetool) | praktijkhouder |
| Fase 1 | Trust Centre, subverwerkerslijst, BoZ-model, model-DPIA | compliance-spoor |
| Fase 2 | Pentest, verzekering, eerste praktijken via een zorggroep | praktijkhouder |
| Fase 2 | Digizo.nu na 12 maanden, 3 organisaties, 120 gebruikers | praktijkhouder |
| Later | MDR-traject voor meedenken en rode vlaggen, als de markt erom vraagt | besluit |

## Bronnen

Leveranciers: [Juvoly prijzen](https://juvoly.nl/product/prijzen), [Juvoly overname](https://juvoly.nl/persbericht-fusie-tandem-health/), [NorthC over Juvoly](https://www.northcdatacenters.com/en/cases/ai-startup-juvoly-relies-on-northc-for-sovereign-hosting/), [Tandem TOM](https://tandemhealth.ai/legal/technical-and-organisational-measures), [Tandem subverwerkers](https://tandemhealth.ai/legal/sub-processors), [Tandem scribe klasse IIa](https://tandemhealth.ai/resources/news/tandem-s-ai-scribe-is-now-mdr-class-iia-certified), [Tandem over de Zweedse inspectie](https://tandemhealth.ai/resources/news/mdr-class-i-is-not-enough-for-an-ai-medical-scribe-a-summary-of-sweden-s-medical-products-agency-s-inspection-findings), [Autoscriber Trust Centre](https://resources.autoscriber.com/trust-centre), [Autoscriber subverwerkers](https://resources.autoscriber.com/trust-centre/list-of-sub-processors), [Autoscriber Intended Use](https://resources.autoscriber.com/trust-centre/intended-use), [Kiwa-certificaat Autoscriber](https://www.kiwa.com/api/certificatefinder/download/BCE5D05F-4CF0-4212-B750-8C6B2C4ACE0E), [Autoscriber prijzen](https://nl.autoscriber.com/nl/pricing), [Medendo FAQ](https://www.medendo.com/faq), [Medendo prijzen](https://www.medendo.com/pricing), [Wellcom AI-informatie](https://wellcom-health.nl/ai-informatie), [Wellcom prijzen](https://wellcom.nl/prijzen-spraakgestuurd-rapporteren), [Wellcom Intended Use](https://portaal.wellcom-health.nl/overeenkomsten/Intended%20Use%20Statement.pdf), [G2 Speech security](https://www.g2speech.com/security), [Ask Aletta FAQ](https://askaletta.com/nl/faq/).

Toetsing en regels: [Digizo.nu spraakgestuurd rapporteren HAZ](https://digizo.nu/proces/spraakgestuurd-rapporteren-haz/), [Digizo.nu info voor fabrikanten](https://digizo.nu/info-voor-fabrikanten/), [LHV-eindrapport spraakgestuurd rapporteren](https://www.lhv.nl/wp-content/uploads/2025/12/2.4-Bijlage-Eindrapport-Spraakgestuurd-rapporteren.pdf), [LHV AI in de huisartsenpraktijk](https://www.lhv.nl/thema/patientengegevens-en-ict/ai-in-de-huisartsenpraktijk/), [Kamervragen ChipSoft, 24 april 2026](https://www.rijksoverheid.nl/documenten/kamerstukken/2026/04/24/antwoordenopkamervragenvandeledenbushoffenkathmannbeidengroenlinkspvdaoverdehackbijsoftwarevoorpatientendossiers), [Cyberbeveiligingsregeling zorg](https://zoek.officielebekendmakingen.nl/stcrt-2026-28763.html), [IGJ over NEN 7510](https://www.igj.nl/vraag-en-antwoord/vragen-over-nen-7510), [NEN informatiebeveiliging in de zorg](https://www.nen.nl/zorg-welzijn/ict-in-de-zorg/informatiebeveiliging-in-de-zorg), [Iusmentis over AI-scribe en MDR](https://blog.iusmentis.com/2026/07/14/een-ai-scribe-is-geen-scriba-maar-een-medisch-adviseur-en-daarom-klasse-iia-mdr/), [Computable, kabinet over CLOUD Act](https://www.computable.nl/2026/10/07/kabinet-erkent-cloud-act-kan-botsen-met-avg-en-toegang-geven-tot-nederlandse-zorgdata/), [BoZ-model verwerkersovereenkomst](https://nhr.nl/wp-content/uploads/2018/10/BOZ-verwerkersovk-NHR-bijlage.pdf).

Hosting en AI: [Cyso Cloud prijzen](https://cyso.cloud/pricing), [Cyso certificeringen](https://cyso.com/en/certifications/), [TransIP NEN 7510 (DNV)](https://www.vdx.nl/wp-content/uploads/2025/08/NEN_7510-ENG-10000336135-MSC-RvA-NLD-15-20250725.pdf), [Rootnet tarieven](https://www.rootnet.nl/tarieven/), [Intermax private cloud](https://www.intermax.nl/oplossingen/cloudoplossingen/private-nederlandse-cloud/), [Microsoft over NEN 7510](https://learn.microsoft.com/en-us/compliance/regulatory/offering-nen-7510-netherlands), [Mistral subverwerkers](https://trust.mistral.ai/subprocessors), [Mistral prijzen](https://mistral.ai/pricing/api/), [Nebul compliance](https://nebul.com/enterprise-security-compliance/), [Fundaments Private AI](https://www.fundaments.nl/diensten/private-ai), [Railway DPA](https://railway.com/legal/dpa), [Scaleway HDS](https://www.scaleway.com/en/security-and-compliance/hds/).

Certificering: [Normwijzer kosten en tijdlijn](https://normwijzer.nl/nen-7510/kosten-en-tijdlijn), [Brand Compliance NEN 7510:2024](https://brandcompliance.com/nieuws/nen-7510-1-2024-onder-accreditatie/), [NEN 7510-partners](https://www.nen.nl/zorg-welzijn/ict-in-de-zorg/informatiebeveiliging-in-de-zorg/nen-7510-partners), [Ateron NEN 7510](https://www.ateron.nl/iso-managementsystemen-en-certificeringen/nen-7510/).

# Fasering: eerst intern gebruik, daarna verspreiden (5 oktober 2026)

VitaScribe wordt in twee fasen ingevoerd. **Fase 1** is gebruik in de eigen
praktijk. **Fase 2** is verspreiding naar andere praktijken, eventueel
commercieel. Voor eigen gebruik gelden duidelijk minder en lichtere
verplichtingen dan voor verspreiden. Die winst zit vooral in de regels voor
medische hulpmiddelen en in de aansprakelijkheid. De AVG geldt in beide fasen
volledig.

Dit is een technische en organisatorische uitwerking, geen juridisch advies.
Laat de punten die in fase 2 aan de orde komen toetsen door een jurist die
gespecialiseerd is in zorg en ICT.

## De schakelaar op de server

Op de server staat de omgevingsvariabele `VITASCRIBE_FASE`.

- **`intern`** (standaard). De openbare aanmeldpagina (`/aanmelden`) is
  dicht. Alleen praktijken en gebruikers die de beheerder zelf in het register
  zet, kunnen VitaScribe gebruiken.
- **`extern`**. De aanmeldpagina is open voor andere praktijken. Zet deze
  waarde pas als alles uit fase 2 geregeld is.

`/api/v1/providers` meldt de huidige fase.

## Fase 1: intern, in de eigen praktijk

### Wat juridisch lichter is

- **Medische hulpmiddelen (MDR).** Bij eigen gebruik wordt niets "in de handel
  gebracht". De EU-modus is alleen verslaglegging en daarmee geen medisch
  hulpmiddel. De Claude-modus met klinisch meedenken (vraagsuggesties,
  NHG-toets) is dat waarschijnlijk wel (MDR regel 11). Voor eigen gebruik
  binnen een zorginstelling kent de MDR een uitzondering (art. 5 lid 5), maar
  daar horen voorwaarden bij: een kwaliteitssysteem, documentatie, een
  openbare verklaring, en de onderbouwing dat er geen gelijkwaardig product met
  CE-markering bestaat. **Advies: houd klinisch meedenken in fase 1 uit**
  (`CLINICAL_DECISION_SUPPORT=false`), of werk alleen in de EU-modus. Dan speelt
  de MDR niet.
- **Productaansprakelijkheid.** Wie software niet aan anderen levert, valt
  niet onder de productaansprakelijkheid. De nieuwe Europese richtlijn
  (2024/2853), die software expliciet meeneemt, geldt voor producten die vanaf
  9 december 2026 in de handel komen. Die wordt dus pas relevant in fase 2.
- **Winkel en voorwaarden.** Er is geen openbare vermelding in de winkel nodig.
  Ook algemene voorwaarden, een SLA en support voor derden zijn niet nodig.

### Wat ook intern volledig geldt

- **AVG.**
  - De praktijk is verwerkingsverantwoordelijke.
  - Zijn de praktijk en ProVitaCare twee verschillende partijen, dan is
    ProVitaCare verwerker. Dan is een verwerkersovereenkomst tussen de
    praktijk en ProVitaCare nodig.
  - Railway en Mistral zijn subverwerkers.
  - Werkt de arts als waarnemer, dan is de praktijkhouder de
    verantwoordelijke. In dat geval zijn de toestemming van de praktijkhouder
    en een verwerkersovereenkomst met hem of haar nodig.
- **DPIA.** Die is nodig, ook bij intern gebruik. Gezondheidsgegevens plus AI
  in de spreekkamer maken dat zo.
- **Patiënten.**
  - Vermeld VitaScribe in de privacyverklaring van de praktijk.
  - Per consult geeft de patiënt toestemming voor de opname (KNMG). De
    extensie vraagt daar al om.
- **WGBO.** De arts blijft verantwoordelijk voor het dossier en leest en
  corrigeert elk verslag. De markeringen en de regel "niet in de opname" zijn
  hulpmiddelen; ze maken die verantwoordelijkheid niet kleiner.
- **AI-verordening.** Wie het systeem zelf bouwt en gebruikt, is zowel
  aanbieder als gebruiker. Een hulpmiddel voor verslaglegging is geen AI met
  een hoog risico. Wel geldt de plicht tot AI-geletterdheid (art. 4): iedereen
  die het gebruikt, weet dat het model kan verzinnen.
- **NEN 7510 en 7513.** Geef elke gebruiker een persoonlijke sleutel, zodat het
  auditlog per persoon herleidbaar is. Doe dit ook als er maar één gebruiker is.
- **Verzekering.** Vraag de beroepsaansprakelijkheidsverzekeraar schriftelijk of
  het gebruik van een AI-hulpmiddel voor verslaglegging gedekt is.

### Checklist fase 1

- [x] Verwerkersovereenkomst Railway, getekend door beide partijen
- [ ] Schriftelijke bevestiging van Railway dat gezondheidsgegevens eronder
      vallen
- [x] Railway actief in het EU-US Data Privacy Framework
- [ ] SOC 2-rapport van Railway
- [ ] Mistral: verwerkersovereenkomst, ZDR, verwerking in de EU, geen training
- [ ] Verwerkersovereenkomst tussen praktijk en ProVitaCare (als dat twee
      verschillende partijen zijn)
- [ ] DPIA, met docs/AUDIT-EU-MODUS.md als technische bijlage
- [ ] Persoonlijke sleutels per gebruiker; de gedeelde sleutel ingetrokken
- [ ] Privacyverklaring van de praktijk bijgewerkt
- [ ] Antwoord van de verzekeraar
- [ ] Klinisch meedenken uit, of alleen de EU-modus
- [ ] Extensie intern verspreiden: uitgepakt laden, of een eigen CRX via de
      server. Niet openbaar in de winkel.

## Fase 2: verspreiden naar andere praktijken

Komt erbij, bovenop fase 1:

- **Per praktijk een verwerkersovereenkomst**, met ProVitaCare als verwerker,
  een beveiligingsbijlage en een lijst van subverwerkers.
- **Aantoonbare informatiebeveiliging.** Praktijken zullen vragen om
  NEN 7510-conformiteit van ProVitaCare, en liefst een certificaat (NEN 7510
  of ISO 27001).
- **Beoogd gebruik vastleggen** als "hulpmiddel bij verslaglegging", overal: in
  de winkel, de handleiding en de voorwaarden. Klinisch meedenken alleen met een
  CE-markering (klasse IIa, via een aangemelde instantie). Anders blijft het uit.
- **Aansprakelijkheid.**
  - Algemene voorwaarden met een aansprakelijkheidsbeperking (tussen bedrijven
    toegestaan).
  - Een product- en cyberverzekering.
  - Rekening houden met de nieuwe richtlijn productaansprakelijkheid.
- **Organisatie.** Support, een incident- en datalekprocedure richting meerdere
  verwerkingsverantwoordelijken, en releasebeheer.
- **Hosting.** Railway kan, binnen het Data Privacy Framework. Een Europese
  host maakt het verhaal tegenover praktijken eenvoudiger. Met een eigen
  domeinnaam is een verhuizing klein werk.
- Daarna: `VITASCRIBE_FASE=extern` en openbaar maken in de winkel.

## Dossier

De stukken voor beide fasen (DPIA, verwerkersovereenkomst, register, beveiliging, patiëntinformatie, werkinstructie en meer) staan in [dossier/](dossier/README.md).

# Dossier VitaScribe: intern en extern

Stand 5 oktober 2026, server- en extensieversie 2.15.6.

Dit dossier bevat de papieren die nodig zijn om VitaScribe verantwoord te
gebruiken. Fase 1 is gebruik in de eigen praktijk (`VITASCRIBE_FASE=intern`).
Fase 2 is verspreiding naar andere praktijken (`VITASCRIBE_FASE=extern`). De
achtergrond staat in [FASERING.md](../FASERING.md), de technische toets in
[AUDIT-EU-MODUS.md](../AUDIT-EU-MODUS.md).

De stukken zijn ingevuld met wat uit de code, de configuratie en de contracten
vaststaat. Wat alleen de praktijk weet, staat tussen rechte haken, zoals
`[PRAKTIJKNAAM]`. Het zijn concepten. Laat ze, en zeker de stukken voor fase 2,
toetsen door een jurist voor zorg en ICT voordat ze getekend of gepubliceerd
worden.

## Welke stukken bij welke fase

| Nr | Stuk | Intern | Extern |
|---|---|---|---|
| 01 | [Beoogd gebruik en MDR-afbakening](01-beoogd-gebruik.md) | ja | ja, ook publiceren |
| 02 | [Verwerkingsregister (AVG art. 30)](02-verwerkingsregister.md) | ja | ja, ook als verwerker |
| 03 | [DPIA](03-dpia.md) | ja | per klantpraktijk, met dit stuk als basis |
| 04 | [Verwerkersovereenkomst](04-verwerkersovereenkomst.md) | nee (één rechtspersoon) | ja, met elke praktijk |
| 05 | [Subverwerkers](05-subverwerkers.md) | ja | ja, ook publiceren |
| 06 | [Beveiligingsbijlage (NEN 7510, 7513)](06-beveiliging.md) | ja | ja |
| 07 | [Datalekprocedure](07-datalekprocedure.md) | ja | ja, met de verwerkersroute |
| 08 | [Patiëntinformatie](08-patientinformatie.md) | ja | voorbeeldtekst voor klantpraktijken |
| 09 | [Werkinstructie en AI-geletterdheid](09-werkinstructie.md) | ja | ja, ook als training |
| 10 | [Brief aan de verzekeraar](10-brief-verzekeraar.md) | ja | ja, plus product- en cyberverzekering |
| 11 | [Algemene voorwaarden (concept)](11-algemene-voorwaarden.md) | nee | ja |
| 12 | [Dienstverlening en support](12-dienstverlening.md) | nee | ja |
| 13 | [Release- en wijzigingsbeheer](13-releasebeheer.md) | aanbevolen | ja |
| 14 | [Werkplan: volledig binnen de Europese regels](14-werkplan-eu.md) | ja | ja |

## Wie is wie

- **Verwerkingsverantwoordelijke:** `[NAAM HOLDING]`, handelend onder de
  naam Huisartsenpraktijk Roosendael in Roermond, vertegenwoordigd door
  A. Bennaghmouch, huisarts en praktijkhouder.
- **ProVitaCare:** de technische tak van dezelfde rechtspersoon. Omdat het één
  rechtspersoon is, is ProVitaCare in fase 1 geen verwerker van de praktijk.
  Daarom vervalt de verwerkersovereenkomst (stuk 04) intern.
- **Verwerkers:** Railway Corp. (hosting) en Mistral AI SAS (spraak en tekst),
  rechtstreeks voor de praktijk. Zie stuk 05.

Kijk in het Handelsregister of "Roosendael" en "ProVitaCare" echt
handelsnamen van één rechtspersoon zijn. Zijn het aparte BV's onder de
holding, dan zijn het twee partijen, en is stuk 04 ook in fase 1 nodig. Zet de
overeenkomsten met Railway en Mistral op naam van de rechtspersoon die de
praktijk voert.

### Advies voor fase 2: het risico scheiden

Verkoopt dezelfde rechtspersoon die de praktijk voert, straks software aan
andere praktijken, dan staat ook de huisartsenpraktijk bloot aan de
aansprakelijkheid voor dat product. Dat zijn claims van klantpraktijken en
productaansprakelijkheid onder de nieuwe richtlijn. Gebruikelijk is dan:

- breng ProVitaCare vóór fase 2 onder in een eigen BV onder de holding;
- sluit daarna een verwerkersovereenkomst tussen de praktijk en die BV
  (stuk 04).

Bespreek dat met je accountant of jurist.

## Checklist fase 1: intern

- [x] Verwerkersovereenkomst Railway, getekend door beide partijen
- [x] Railway actief in het EU-US Data Privacy Framework
- [ ] Schriftelijke bevestiging van Railway dat gezondheidsgegevens eronder vallen
- [ ] SOC 2-rapport van Railway opgevraagd en bewaard
- [x] Mistral: ZDR geactiveerd en geen training bevestigd (6 oktober 2026); online-DPA geldt (stuk 05)
- [ ] Mistral: subverwerkerslijst en DPA-versie vastgelegd; kloonstem (`/v1/audio/voices`, buiten ZDR) geregeld
- [x] Rollen vastgesteld: praktijkhouder, één rechtspersoon (stuk 04 vervalt intern)
- [ ] Handelsregister gecontroleerd; overeenkomsten op naam van de juiste rechtspersoon
- [ ] Stuk 01 ondertekend; op de server `CLINICAL_DECISION_SUPPORT` en `ECONSULT_NHG_IN_EU` uit, of de keuze vastgelegd
- [ ] Stuk 02 in het verwerkingsregister van de praktijk
- [ ] Stuk 03 (DPIA) ingevuld, besproken en ondertekend
- [ ] Persoonlijke sleutels per gebruiker (`API_USERS`); de gedeelde sleutel ingetrokken
- [x] Standaardmodus EU in server en extensie (2.21.1, 7 oktober 2026)
- [ ] Slot op de modus: `TOEGESTANE_MODI=eu` in Railway, of "Alleen EU-modus" bij de praktijk in Beheer
- [x] Testgereedschap in productie uit: sinds 2.21.1 alleen aanwezig met `TESTGEREEDSCHAP=true` (niet zetten in Railway)
- [ ] Stuk 08 verwerkt in de privacyverklaring en in de wachtkamer
- [ ] Stuk 09 gelezen en afgetekend door elke gebruiker
- [ ] Stuk 10 verstuurd en het antwoord bewaard
- [ ] Extensie intern geïnstalleerd, niet openbaar in de winkel

## Checklist fase 2: extern, bovenop fase 1

- [ ] ProVitaCare in een eigen BV; verwerkersovereenkomst tussen de praktijk en die BV
- [ ] Juridische toets van stukken 04, 11 en 12
- [ ] Stuk 01 gepubliceerd in de winkeltekst, de handleiding en de voorwaarden
- [ ] Klinisch meedenken uit, of een CE-markering als medisch hulpmiddel (klasse IIa)
- [ ] NEN 7510-conformiteit van ProVitaCare aantoonbaar; liefst een certificaat
- [ ] Product- en cyberverzekering
- [ ] Supportkanaal en releasebeheer ingericht (stukken 12 en 13)
- [ ] Subverwerkerslijst openbaar, met een wijzigingsprocedure
- [ ] Eigen domeinnaam voor de server
- [ ] Per klantpraktijk: getekende verwerkersovereenkomst, ingevulde DPIA, sleutels per gebruiker
- [ ] `VITASCRIBE_FASE=extern` en de winkelvermelding openbaar

## Bijlagen die niet in de repository staan

- De getekende verwerkersovereenkomst met Railway (envelop
  15F6A42D-5BA0-8848-82F5-EDC780AD0A6F). Bewaar die bij de
  praktijkadministratie, niet hier: er staan persoonsgegevens in.
- Het SOC 2-rapport van Railway. De bevestiging van Mistral (ZDR, geen
  training, 6 oktober 2026) staat als afschrift in
  `docs/wetgeving/bewijs/mistral-zdr-2026-10-06.md`; de originele mails en de
  schermafdruk van de console horen bij de praktijkadministratie.
- Het stappenplan voor alle producten van de praktijk:
  `docs/wetgeving/STAPPENPLAN.md`.
- De ondertekende versies van de stukken uit dit dossier.

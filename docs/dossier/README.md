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
| 04 | [Verwerkersovereenkomst](04-verwerkersovereenkomst.md) | alleen als praktijk en ProVitaCare twee partijen zijn | ja, met elke praktijk |
| 05 | [Subverwerkers](05-subverwerkers.md) | ja | ja, ook publiceren |
| 06 | [Beveiligingsbijlage (NEN 7510, 7513)](06-beveiliging.md) | ja | ja |
| 07 | [Datalekprocedure](07-datalekprocedure.md) | ja | ja, met de verwerkersroute |
| 08 | [Patiëntinformatie](08-patientinformatie.md) | ja | voorbeeldtekst voor klantpraktijken |
| 09 | [Werkinstructie en AI-geletterdheid](09-werkinstructie.md) | ja | ja, ook als training |
| 10 | [Brief aan de verzekeraar](10-brief-verzekeraar.md) | ja | ja, plus product- en cyberverzekering |
| 11 | [Algemene voorwaarden (concept)](11-algemene-voorwaarden.md) | nee | ja |
| 12 | [Dienstverlening en support](12-dienstverlening.md) | nee | ja |
| 13 | [Release- en wijzigingsbeheer](13-releasebeheer.md) | aanbevolen | ja |

## Wie is wie

Dit bepaalt welke stukken nodig zijn. Vul het eerst in.

- **Verwerkingsverantwoordelijke:** de huisartsenpraktijk `[PRAKTIJKNAAM]`,
  vertegenwoordigd door de praktijkhouder `[NAAM PRAKTIJKHOUDER]`.
- **Verwerker:** ProVitaCare `[RECHTSVORM, KVK-NUMMER]`, beheerder van de
  VitaScribe-server.
- **Subverwerkers:** Railway Corp. (hosting) en Mistral AI SAS (spraak en
  tekst). Zie stuk 05.

Zijn de praktijk en ProVitaCare één en dezelfde rechtspersoon, bijvoorbeeld
allebei de eenmanszaak van dezelfde arts, dan is er geen verwerker tussen
die twee. Dan vervalt stuk 04 in fase 1 en sluit de praktijk de
overeenkomsten met Railway en Mistral rechtstreeks. Werkt de arts als
waarnemer, dan is de praktijkhouder de verantwoordelijke en tekent die.

## Checklist fase 1: intern

- [x] Verwerkersovereenkomst Railway, getekend door beide partijen
- [x] Railway actief in het EU-US Data Privacy Framework
- [ ] Schriftelijke bevestiging van Railway dat gezondheidsgegevens eronder vallen
- [ ] SOC 2-rapport van Railway opgevraagd en bewaard
- [ ] Mistral: verwerkersovereenkomst, ZDR, verwerking in de EU, geen training
- [ ] Rollen vastgesteld (zie hierboven); zo nodig stuk 04 getekend
- [ ] Stuk 01 ondertekend; op de server `CLINICAL_DECISION_SUPPORT` uit
- [ ] Stuk 02 in het verwerkingsregister van de praktijk
- [ ] Stuk 03 (DPIA) ingevuld, besproken en ondertekend
- [ ] Persoonlijke sleutels per gebruiker (`API_USERS`); de gedeelde sleutel ingetrokken
- [ ] Testgereedschap in productie uit, of alleen gebruikt met gespeelde consulten
- [ ] Stuk 08 verwerkt in de privacyverklaring en in de wachtkamer
- [ ] Stuk 09 gelezen en afgetekend door elke gebruiker
- [ ] Stuk 10 verstuurd en het antwoord bewaard
- [ ] Extensie intern geïnstalleerd, niet openbaar in de winkel

## Checklist fase 2: extern, bovenop fase 1

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
- Het SOC 2-rapport van Railway en de overeenkomst met Mistral, zodra binnen.
- De ondertekende versies van de stukken uit dit dossier.

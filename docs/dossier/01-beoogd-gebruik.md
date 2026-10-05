# 01 Beoogd gebruik en afbakening als medisch hulpmiddel

Of software een medisch hulpmiddel is, hangt af van het doel dat de maker
eraan geeft (MDR art. 2 lid 1 en lid 12). Dit stuk legt dat doel vast. Het
geldt pas als het overal hetzelfde staat: in de handleiding, de privacytekst,
de winkeltekst en, in fase 2, de voorwaarden.

## Beoogd gebruik

VitaScribe is een hulpmiddel bij de verslaglegging door huisartsen. Het zet
het gesprek in de spreekkamer, of een dictaat van de arts, om in een
**concept** van een SOEP-verslag, een brief of een samenvatting. De arts leest,
corrigeert en keurt elk concept goed voordat het in het dossier komt.

VitaScribe stelt geen diagnose, geeft geen behandeladvies, berekent geen
risico en geeft geen waarschuwingen over de toestand van de patiënt. Wat het
verslag als diagnose of beleid noemt, komt uit wat de arts in het gesprek zelf
zei.

Hulpmiddelen die bij de verslaglegging horen en daarom binnen dit doel vallen:

- markeringen op zinnen die de controleronde niet in het gesprek terugvindt;
- de vaste regel "niet in de opname" als een opname midden in het consult
  ophoudt;
- de weigering om een verslag te maken bij te weinig herkende spraak;
- de geluidscontrole tijdens de opname;
- de controle op medicijnnamen (spelling en bestaan, geen dosering of
  interactie);
- de melding welke onderdelen van de SOEP ontbreken.

**Gebruikers:** huisartsen, en onder hun verantwoordelijkheid
waarnemers en praktijkondersteuners. **Omgeving:** de huisartsenpraktijk, met
het HIS Bricks in Microsoft Edge of Google Chrome.

## Wat buiten het beoogd gebruik valt

Klinisch meedenken: vraagsuggesties tijdens het consult, de toets aan de
NHG-Standaard en voorgestelde Thuisarts-onderwerpen. Die functies helpen bij
een beslissing over één patiënt en maken de software daarmee waarschijnlijk tot
een medisch hulpmiddel van klasse IIa (MDR bijlage VIII, regel 11).

Zo is dat afgeschermd:

- op de server staat `CLINICAL_DECISION_SUPPORT` uit;
- in de EU-modus is klinisch meedenken altijd uit, ongeacht die instelling;
- in de extensie staat elke functie apart uit tot de arts hem aanzet, en dat
  kan alleen als de server het toestaat.

## Fase 1: eigen gebruik

Zolang alleen de eigen praktijk VitaScribe gebruikt, brengt niemand iets "in
de handel" of "in gebruik" bij een ander. Met de afbakening hierboven is
VitaScribe dan geen medisch hulpmiddel, en speelt de MDR niet.

Wil de praktijk klinisch meedenken toch intern gebruiken, dan kan dat alleen
via de uitzondering voor eigen gebruik binnen een zorginstelling (MDR art. 5
lid 5). Daarvoor moet de praktijk onder meer:

- een passend kwaliteitssysteem hebben;
- onderbouwen dat geen gelijkwaardig hulpmiddel met CE-markering beschikbaar
  is;
- een openbare verklaring opstellen en de technische documentatie bijhouden.

Dat is een eigen project. Advies: in fase 1 niet doen.

## Fase 2: verspreiden

Bij levering aan andere praktijken brengt ProVitaCare software in de handel.
Het beoogd gebruik hierboven wordt dan een publieke belofte. Publiceer het
letterlijk in de winkeltekst, de handleiding en de algemene voorwaarden.
Klinisch meedenken gaat alleen mee na een CE-markering via een aangemelde
instantie. Tot die tijd blijft de schakelaar op de server uit, en noemt geen
enkele tekst die functies.

## Vastgesteld

| | |
|---|---|
| Praktijk | `[PRAKTIJKNAAM]` |
| Naam en functie | `[NAAM]`, `[praktijkhouder / huisarts]` |
| Datum | `[DATUM]` |
| Handtekening | |

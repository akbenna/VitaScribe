# 03 DPIA: VitaScribe in Huisartsenpraktijk Roosendael

Gegevensbeschermingseffectbeoordeling volgens AVG art. 35. De opbouw volgt
het Model DPIA Rijksdienst en de vier eisen van art. 35 lid 7:

1. een beschrijving van de verwerking;
2. de noodzaak en de evenredigheid;
3. de risico's;
4. de maatregelen.

De technische onderdelen zijn ingevuld vanuit de code (versie 2.15.6) en de
audit van 5 oktober 2026. De praktijk vult de afweging aan en stelt het
stuk vast.

## 0 Waarom een DPIA

Een individuele huisarts verwerkt patiëntgegevens doorgaans niet "op grote
schaal" (overweging 91), en daarmee is een DPIA niet automatisch verplicht.
Hier gelden wel twee criteria uit de richtlijnen van de Europese
toezichthouders (WP248):

- bijzondere persoonsgegevens, namelijk gezondheidsgegevens;
- een nieuwe technologie, namelijk AI die in de spreekkamer meeluistert.

Bij twee criteria is een DPIA het uitgangspunt. Ook voor de verantwoording naar
patiënten, de verzekeraar en later andere praktijken is hij nodig.

## 1 Beschrijving van de verwerking

### Wat er gebeurt

De arts vraagt de patiënt aan het begin van het consult om toestemming voor de
opname en bevestigt dat in de extensie. Zonder die bevestiging weigert de
server de opname (`REQUIRE_RECORDING_CONSENT`). Daarna gebeurt het volgende:

1. **Opname.** Het geluid gaat in stukjes naar de VitaScribe-server. In de
   EU-modus houdt de server het alleen in het werkgeheugen.
2. **Geluidscontrole.** Na 30 seconden, 2 minuten en 5 minuten laat de server
   het geluid tot dan toe herkennen. De arts krijgt alleen het aantal woorden
   te zien. Zo valt een stille microfoon direct op.
3. **Verslag.** Na "stop" maakt Voxtral (Mistral) er tekst van. Mistral Large
   maakt het SOEP-concept. Een tweede ronde van Mistral Large markeert zinnen
   die niet in het gesprek terug te vinden zijn. Een vaste toets, zonder AI,
   markeert typische verzinsels.
4. **Wissen.** De server wist het geluid en de tekst en stuurt het concept
   naar de browser.
5. **Overnemen.** De arts leest het concept, verbetert het en zet het in Bricks.

Brieven, dossiervragen en post gaan anders. De arts kiest welke delen van het
dossier meegaan. De browser haalt er naam, geboortedatum, BSN, adres en
contactgegevens uit, en de server filtert nog eens. Daarna gaat de tekst naar
het taalmodel.

### Gegevens, betrokkenen, partijen

Zie stuk 02 (register) en stuk 05 (subverwerkers).

### Gegevensstroom in de EU-modus

| Gegeven | Waar | Bewaard |
|---|---|---|
| Geluid | Browser → server (Railway, NL) → Voxtral (Mistral, FR) | Server: nee. Mistral: volgens de overeenkomst, met ZDR: nee |
| Tekst en verslag | Server → Mistral Large → server → browser | Server: nee. Browser: werkgeheugen tot "Nieuw consult" |
| Auditlog | Server, database bij Railway | 5 jaar, zonder inhoud |
| Definitief verslag | Bricks, door de arts | WGBO: 20 jaar |

De Claude-modus (Deepgram en Anthropic, VS) gebruikt de praktijk in fase 1
niet voor echte patiënten. Die modus valt buiten deze DPIA. Wie hem later wil
gebruiken, vult deze DPIA eerst aan.

## 2 Noodzaak en evenredigheid

**Doel en belang.** Huisartsen besteden een groot deel van hun tijd aan
verslaglegging. Een volledig concept bespaart schrijftijd, geeft meer
aandacht voor de patiënt tijdens het consult en levert vaak een vollediger
dossier op. Het doel is legitiem en volgt uit de dossierplicht.

**Proportionaliteit.** De inbreuk is beperkt:

- er wordt alleen opgenomen met de toestemming van de patiënt;
- niets wordt bewaard buiten het HIS;
- er gaat geen dossier mee bij het consultverslag.

**Subsidiariteit.** Zelf typen of dicteren kan altijd en blijft mogelijk.
Een lokaal model in de praktijk, zonder externe partij, is onderzocht.
Op dit moment haalt dat de kwaliteit van een groot model niet, en het vraagt
een eigen GPU-server.

**Rechten van betrokkenen.**

- *Bezwaar.* De patiënt kan de opname weigeren. Dat heeft geen gevolg voor de
  zorg; de arts schrijft dan zelf.
- *Inzage en correctie.* Die lopen via het dossier in het HIS. VitaScribe zelf
  bewaart niets dat inzage behoeft, behalve het auditlog.
- *Informatie.* De patiënt wordt geïnformeerd via de privacyverklaring, de
  wachtkamer en de vraag in de spreekkamer (stuk 08).

## 3 Risico's

Kans en gevolg zijn gescoord als laag, midden of hoog, *na* de maatregelen
in hoofdstuk 4.

| Nr | Risico | Kans | Gevolg | Rest |
|---|---|---|---|---|
| R1 | Het verslag bevat iets wat niet gezegd is (verzinsel), en dat komt ongezien in het dossier | midden | hoog | midden |
| R2 | Een deel van het consult ontbreekt (microfoon, afgebroken opname), en het verslag lijkt toch compleet | laag | midden | laag |
| R3 | Opname zonder dat de patiënt dat weet of wil | laag | hoog | laag |
| R4 | Toegang door Amerikaanse autoriteiten tot verkeer via Railway (CLOUD Act) | laag | hoog | laag tot midden |
| R5 | Mistral bewaart verzoeken (misbruikcontrole) of gebruikt ze voor training | laag | hoog | laag, na ZDR |
| R6 | Onbevoegd gebruik van een sleutel; handelingen niet herleidbaar tot een persoon | laag | midden | laag, na persoonlijke sleutels |
| R7 | Een echt consult belandt via testgereedschap in een log | laag | hoog | laag, na uitzetten |
| R8 | Een naam of een andere identificator uit het gesprek gaat mee naar Mistral | hoog | laag | laag |
| R9 | Een verslag blijft op een gedeelde computer staan voor de volgende gebruiker | laag | midden | laag |
| R10 | Te veel vertrouwen op de software (automation bias) | midden | midden | midden |

## 4 Maatregelen

| Risico | Maatregelen |
|---|---|
| R1 | Het verslag is altijd een concept, en de arts keurt het goed (WGBO). De controleronde markeert zinnen die niet in het gesprek staan, in geel; er wordt niets weggehaald of toegevoegd. Een vaste toets markeert typische verzinsels, zoals krachtscores en testnamen die niet genoemd zijn. Het taalmodel draait met lage temperatuur en de opdracht alleen te noemen wat gezegd is. Werkinstructie en AI-geletterdheid (stuk 09). |
| R2 | Geluidscontrole na 30 seconden, 2 minuten en 5 minuten, met een rode melding bij stilte. Bij te weinig spraak (minder dan 12 woorden) wordt geen verslag gemaakt. Ontbreekt een deel, dan zegt de rubriek "niet in de opname". |
| R3 | De server weigert een opname zonder bevestigde toestemming. Patiëntinformatie (stuk 08). |
| R4 | De server bewaart geen audio en geen tekst. Er is een verwerkersovereenkomst met Railway, en Railway is actief in het DPF. Railway heeft SOC 2 Type II. De server draait in Nederland. Restrisico: Railway valt onder Amerikaans recht. Wil de praktijk dat wegnemen, dan is een Europese host mogelijk. Technisch is dat een kleine verhuizing. |
| R5 | Een verwerkersovereenkomst met Mistral: EU, geen training, ZDR. Zolang die er niet is, worden alleen gespeelde consulten gebruikt. |
| R6 | Een sleutel per gebruiker (`API_USERS`). De gedeelde sleutel wordt ingetrokken. Beheer met een tweede factor (`ADMIN_TOTP`) voor elke beheerder; beheer zonder tweede factor uitzetten. Het auditlog is onveranderbaar en zonder inhoud. |
| R7 | Testgereedschap staat in productie uit, of wordt aantoonbaar alleen met gespeelde consulten gebruikt. |
| R8 | Er gaat alleen iets naar een EU-verwerker, er wordt niets bewaard, en de patiënt heeft toestemming gegeven. Bij brieven en dossiervragen wordt de tekst in de browser gefilterd. Dit restrisico wordt aanvaard. |
| R9 | Het verslag staat alleen in `chrome.storage.session`, dus in het werkgeheugen. De knop "Consult afsluiten" wist het verslag en de opname. Elke gebruiker heeft een eigen Windows-account `[controleren]`. |
| R10 | Werkinstructie (stuk 09): elk verslag lezen, en de gele markeringen eerst. Periodiek steekproeven in de eigen verslagen. |

## 5 Conclusie en besluit

`[In te vullen door de praktijk, bijvoorbeeld:]` Na de maatregelen is het
restrisico aanvaardbaar, op voorwaarde dat:

- de overeenkomst met Mistral (inclusief ZDR) getekend is;
- er persoonlijke sleutels zijn;
- het testgereedschap in productie uit staat.

Tot die tijd gebruikt de praktijk alleen gespeelde consulten. Een
voorafgaande raadpleging van de Autoriteit Persoonsgegevens (art. 36) is niet
nodig, omdat geen hoog restrisico overblijft.

**Herbeoordeling:** jaarlijks, en bij elke wezenlijke wijziging, zoals een
andere aanbieder, de Claude-modus voor echte patiënten, of fase 2.

| | |
|---|---|
| Vastgesteld door | A. Bennaghmouch, huisarts en praktijkhouder |
| Datum | `[DATUM]` |
| Volgende herziening | `[DATUM + 1 JAAR]` |

## Fase 2: DPIA bij klantpraktijken

Elke praktijk die VitaScribe afneemt, is zelf verantwoordelijk en heeft een
eigen DPIA nodig. ProVitaCare levert dit stuk mee, met hoofdstuk 1 en 4
ingevuld. De praktijk vult hoofdstuk 2, 3 en 5 aan voor de eigen situatie.

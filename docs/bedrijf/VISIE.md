# Visie: VitaScribe en Bricks Companion

Oktober 2026. Een visie, geen plan: hij beschrijft waar de twee producten
samen naartoe kunnen en waarom. Hij bouwt op de blauwdruk (`docs/bedrijf/BLAUWDRUK.md` in de VitaScribe-repo),
het dossier van fase 1 en 2 van Bricks Companion, de strategienotitie over
het RHO-partnerschap en de benchmark van 8 oktober. Wat niet vaststaat, staat
er als schatting of als vraag. Hetzelfde stuk staat in beide repo's.

## De kern

VitaScribe en Bricks Companion zijn de twee helften van één consult in
Bricks. VitaScribe **luistert en schrijft**: het zet het gesprek om in een
verslag, en het werk na het consult in brieven, antwoorden en samenvattingen.
Bricks Companion **leest en rekent**: het haalt de gegevens uit het dossier en
legt ze langs de NHG-standaarden. Het eerste doet dat met een taalmodel, het
tweede bewust zonder.

Die scheiding is meer dan een ontwerpkeuze. De regels trekken precies dezelfde
lijn. Een hulpmiddel voor verslaglegging zonder beslisondersteuning kan buiten
de MDR blijven. Beslisondersteuning met berekeningen is een medisch hulpmiddel,
naar verwachting klasse IIa. En AI in een medisch hulpmiddel van klasse IIa
maakt het onder de AI-verordening hoog-risico. Door de twee helften gescheiden
te houden draagt elk product alleen zijn eigen last: VitaScribe die van de AVG
en NEN 7510, Bricks Companion daarbovenop die van de MDR, en geen van beide
die van hoog-risico-AI.

Het doel is niet nog een scribe. Daar is de markt al verdeeld. Het doel is de
werkplek waarop een huisarts en een POH in Bricks het consult én de
chronische zorg doen, verkocht aan wie die chronische zorg organiseert en
betaalt: de zorggroep of de RHO.

## Waar we staan

**Wat er ligt.** Beide producten werken in de eigen praktijk. VitaScribe
heeft een EU-modus met Mistral en zero data retention, een slot op de modus,
een server die klaar is voor een Europese host, en een dossier met DPIA,
register en werkplan. Bricks Companion draait volledig lokaal in de browser,
zonder server en zonder AI, met 460 automatische tests, SCORE2 geverifieerd
tegen het artikel, vijf rondes fictieve patiënten, twee externe
casusbeoordelingen en een dossier voor eigen gebruik onder de MDR (art. 5 lid
5). Met Tetra is er al contact: toegang tot de testomgeving van Bricks
Switchboard voor De Slimme Praktijk.

**De markt.** Spraakgestuurd verslag is in de huisartsenzorg geen nieuwigheid
meer. Juvoly wordt volgens eigen opgave door een derde van de praktijken
gebruikt, koppelt al met Bricks, is in januari 2026 overgenomen door het
Zweedse Tandem Health (dat 100 miljoen dollar ophaalde) en vraagt per praktijk
€0,65 per ingeschreven patiënt per jaar, onbeperkt. Autoscriber en Wellcom zitten
in dezelfde prijsklasse. De IZA-partijen gaven spraakgestuurd rapporteren in
december 2025 de status "Kansrijk voor opschaling", met Juvoly en Autoscriber
als de getoetste tools.

**De regels.** Een certificaat voor NEN 7510 is in de praktijk een
toegangskaart: de minister bevestigde in april dat zorgaanbieders het van
softwareleveranciers eisen, en de Cyberbeveiligingswet geldt sinds augustus.
Over de MDR is de markt verdeeld: Autoscriber en Wellcom noemen hun scribe geen
medisch hulpmiddel, Tandem liet de zijne als klasse IIa certificeren.

## Waar we niet gaan winnen

Op de kale scribe. Opnemen, transcriberen en een SOEP maken doet Juvoly al bij
een derde van de praktijken, met een koppeling aan Bricks, het geld van Tandem
en een prijs die nauwelijks lager kan. Wie daar op prijs of op aantal
gebruikers concurreert, verliest het van een partij die honderd keer groter is.
De scribe in VitaScribe is daarom geen hoofdproduct maar de voorwaarde: hij
moet goed zijn, omdat de rest erop bouwt, en hij moet niet het argument zijn.

## Waar we wel kunnen winnen

**1. De chronische zorg in de spreekkamer.** Geen van de vijf onderzochte
aanbieders legt het consult geverifieerd langs de NHG-standaarden voor CVRM,
diabetes, nierschade en COPD/astma. Bricks Companion doet dat, met de
herindeling naar NHG CVRM 2024, de streefwaarden, de stappenplannen en de
gaten in de registratie, op het moment dat de patiënt in de kamer zit. Voor een
praktijk is dat handige beslisondersteuning. Voor een zorggroep of RHO is het
iets anders: uniforme richtlijnimplementatie en betere ketenzorgindicatoren in
de hele regio, gefinancierd uit middelen voor organisatie en infrastructuur
die daarvoor bedoeld zijn. Daar zit de koper.

**2. Het werk na het consult.** Brieven, specialistenbrieven samenvatten,
dossiervragen, e-consulten, post: VitaScribe doet het, en de kostprijsberekening
laat zien dat het bijna niets kost om te leveren (alle extra functies samen
minder dan €1,50 per arts per maand in de EU-modus). Hier zit de tijdwinst die
een arts merkt, en de marge.

**3. De praktijk met een diverse populatie.** De tolk, patiëntinformatie in het
Nederlands, Turks en Arabisch, Thuisarts op de juiste plek: dit komt voort uit
een praktijk in een wijk als de Donderberg en niet uit een productplan. In de
benchmark vonden we het bij geen van de scribes terug. Voor praktijken in
vergelijkbare wijken is het een reden om te kiezen, niet een extraatje.

**4. Europees en aantoonbaar.** De markt kiest bijna overal Azure. Het kabinet
erkende op 7 oktober dat de CLOUD Act kan botsen met de AVG. VitaScribe kan
eerlijk zeggen: Europese aanbieders, een Nederlandse host, en elk getal in
Bricks Companion deterministisch berekend en getest. Eerlijk, want ook bij
Mistral zitten Amerikaanse moederbedrijven in de keten; het verhaal is
"Europese aanbieders en aantoonbare berekeningen", niet "geen enkele
Amerikaanse partij".

En onder alles: gemaakt door een huisarts, getest op een eigen praktijk, met
een dossier dat elke stap vastlegt. Dat is geen marketing maar de reden dat de
benchmark-partijen hun Intended Use, hun trust centre en hun certificaten
moesten opbouwen. Hier ligt het grootste deel al.

## Hoe de twee samenkomen

Op het scherm zijn het twee zijpanelen in Bricks bij dezelfde patiënt. De
logische volgende stap is dat ze elkaar aanvullen: een bloeddruk die in het
gesprek wordt genoemd, een rookstatus, een nieuwe klacht, die VitaScribe hoort
en die in Bricks Companion terechtkomt.

Precies daar zit de grens die bewaakt moet worden. Zodra uitvoer van een
taalmodel ongezien in een berekening van een medisch hulpmiddel gaat, wordt
het taalmodel deel van dat hulpmiddel, en dan geldt de zware kant van de MDR én
van de AI-verordening voor allebei. Bricks Companion heeft al het juiste
mechanisme: de verplichte controlestap, waarin de arts elke waarde met datum
ziet, corrigeert en bevestigt. Als VitaScribe een waarde aanreikt, dan alleen
als voorstel in die controlestap, gemarkeerd als "gehoord in het gesprek", en
pas na bevestiging door de arts in de berekening. Of dat volstaat om het
taalmodel buiten het hulpmiddel te houden, is een vraag voor de MDR-adviseur,
niet voor dit stuk. Tot dat antwoord er is: geen koppeling.

## Het fundament, één keer gebouwd

Twee producten betekent niet twee keer alles.

- **Eén bedrijf.** Een eigen BV voor ProVitaCare onder de holding (besluit 1),
  met de contracten, de certificaten en later de CE-markering op die naam. De
  praktijk wordt dan klant, met een verwerkersovereenkomst. Dat scheidt ook het
  risico: claims over het product raken de praktijk niet.
- **Eén informatiebeveiligingssysteem.** NEN 7510:2024 en ISO 27001 voor de
  organisatie, met beide producten in de scope. Voor Bricks Companion is dat
  minder zwaar (geen server), maar een inkoper vraagt het van de leverancier,
  niet van het product.
- **Later één kwaliteitssysteem.** Bricks Companion heeft voor CE-markering
  ISO 13485 en IEC 62304 nodig. Als VitaScribe ooit klinische functies als
  hulpmiddel wil verkopen (meedenken, rode vlaggen), of als de toezichthouder
  de scribe zelf zwaarder gaat indelen, past dat in hetzelfde systeem. Het
  tweede product rijdt dan mee op het werk voor het eerste.
- **Eén relatie met Tetra.** Beide producten lezen nu het scherm van Bricks.
  Dat is kwetsbaar: een nieuwe versie van Bricks kan de extractie breken, en
  Tetra kan het in zijn voorwaarden afwijzen. Juvoly heeft al een koppeling met
  Bricks. Er ligt een opening: de toegang tot Switchboard. Het doel op termijn
  is een gesanctioneerde koppeling voor het lezen van het dossier en het
  terugzetten van een verslag, zodat beide producten niet meer van de opbouw
  van het scherm afhangen.

## Drie horizonten

**Horizon 1, nu tot het voorjaar van 2027: de eigen praktijk als bewijs.**
- Beide producten in eigen gebruik, Bricks Companion onder art. 5 lid 5,
  VitaScribe in de EU-modus op een Nederlandse host.
- Meten wat ertoe doet: tijd per consult en per brief, correcties per verslag,
  incidenten, indicatorcompleetheid in de chronische zorg.
- Het Intended Use-document voor VitaScribe, met de pakketgrens langs de MDR.
- Besluit 1 (de BV) en de start van het traject voor NEN 7510 en ISO 27001.
- Het MDR-adviesgesprek voor Bricks Companion (poort 2), met daarin ook de
  vraag over de scribe en over de brug tussen beide.
- Wat níet: nieuwe functies die de MDR-grens raken, verkoop, een tweede HIS.

**Horizon 2, 2027: de eerste zorggroep.**
- VitaScribe gaat, met het certificaat en binnen zijn beoogd gebruik, naar de
  eerste praktijken buiten de eigen praktijk, via één zorggroep of RHO.
- Bricks Companion nog niet: zonder CE-markering niet op de markt, ook niet
  gratis. Wel kan de zorggroep meedenken over de modules en het CE-traject
  meefinancieren als launching customer, met prioriteit en prijs als
  tegenprestatie en geen zeggenschap over de code (strategienotitie RHO).
- Tetra benaderen met resultaten, gericht op een werkafspraak en een
  koppeling.
- De belangenverstrengeling als kaderarts CVRM vooraf melden en de beoordeling
  buiten de eigen rol laten lopen.

**Horizon 3, vanaf 2028: het geheel.**
- CE-markering voor Bricks Companion onder één kwaliteitssysteem.
- Regiolicenties: VitaScribe en Bricks Companion samen aan zorggroepen en
  RHO's, met de vier ketens (CVRM, diabetes, COPD/astma, ouderenzorg).
- Digizo.nu-toetsing zodra de schaal er is (12 maanden, 3 organisaties, 120
  gebruikers).
- Een besluit over VitaScribe's klinische functies als hulpmiddel, als de markt
  erom vraagt.

## Het verdienmodel

De koper is de zorggroep of de RHO, niet de losse huisarts. Die koopt per
regio, betaalt uit middelen voor ketenzorg en infrastructuur, en heeft een
eigen belang bij de indicatoren.

- **VitaScribe** per praktijk, per ingeschreven patiënt per jaar, het model dat
  de markt kent. Het anker is Juvoly (€0,65, alleen scribe). Een rekenvoorbeeld
  uit de blauwdruk: €0,95 per patiënt per jaar laat na de AI-kosten ruim
  voldoende over om de vaste kosten te dragen vanaf ongeveer 16 praktijken in
  het eerste jaar en 6 tot 8 daarna.
- **Bricks Companion** per huisarts-FTE per jaar (het bestaande licentiemodel),
  na CE-markering, en bij voorkeur als regiolicentie.
- **Samen** als één regioaanbod, met een prijs die lager ligt dan de som.

De bedragen zijn rekenvoorbeelden. Ze worden pas echt na de eerste offertes
voor certificering en het MDR-traject.

## De risico's, eerlijk

- **Eén persoon.** De techniek is niet de flessenhals; tijd is dat:
  certificering, support, verkoop en een praktijk tegelijk. Kies daarom per
  horizon één ding dat af moet, en houd de rest stil.
- **Afhankelijk van Bricks.** Beide producten werken alleen op Bricks en lezen
  het scherm. Zonder afspraak met Tetra is dat het grootste bedrijfsrisico. Een
  tweede HIS pas bij een concrete vraag.
- **De MDR-vraag voor de scribe.** Als Nederland de Zweedse lijn volgt (een
  scribe is minstens klasse IIa), moet ook VitaScribe door een MDR-traject.
  Het fundament hierboven vangt dat op, maar het verschuift de tijdlijn.
- **Het MDR-traject voor Bricks Companion kost tijd en geld.** Een notified
  body, ISO 13485 en een klinische evaluatie; reken op een tot twee jaar en
  een bedrag dat pas met offertes vaststaat. Alternatief uit de routekaart:
  samenwerken met een partij die al een kwaliteitssysteem en CE-markering
  heeft.
- **Belangenverstrengeling.** De rol als kaderarts bij de beoogde RHO vraagt
  openheid vooraf en een beoordeling door anderen.
- **Consolidatie.** Tandem kocht Juvoly. Dat is een dreiging, en ook een
  mogelijkheid: een kleine Nederlandse partij met geverifieerde ketenzorg en
  een werkende Bricks-integratie is voor een HIS-leverancier of een scribe-partij
  het soort ding dat ze zelf niet snel bouwen. Geen plan, wel een optie om open
  te houden.

## Besluiten voor jou

1. **Het einddoel.** Een product voor de eigen praktijk en een paar collega's,
   of een bedrijf dat regio's bedient? Alles hierboven gaat uit van het tweede;
   bij het eerste valt het meeste weg en blijft fase 1 het eindpunt.
2. **Eén BV voor beide producten,** met de praktijk als klant (besluit 1).
3. **De volgorde:** eerst VitaScribe naar de markt (zonder MDR, met NEN 7510),
   Bricks Companion als lange lijn met CE-markering. Of omgekeerd, als de RHO
   het CE-traject wil meefinancieren.
4. **De CE-route voor Bricks Companion:** zelf, of met een partner die al een
   kwaliteitssysteem heeft.
5. **Tetra:** wanneer en met welke vraag. Het voorstel: na een half jaar
   resultaten uit de eigen praktijk, met een werkafspraak als eerste vraag en
   een koppeling als doel.

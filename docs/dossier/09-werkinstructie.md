# 09 Werkinstructie en AI-geletterdheid

Voor iedereen die VitaScribe in de praktijk gebruikt. Dit stuk vervult ook de
plicht tot AI-geletterdheid uit de AI-verordening (art. 4, van kracht sinds
2 februari 2025): wie met AI werkt, weet wat het kan, wat het niet kan, en
waar het misgaat.

## Wat je moet weten over het model

Een taalmodel schrijft wat waarschijnlijk klinkt, niet wat waar is. Meestal
is dat hetzelfde. Soms niet. In onze proeven ging het vooral mis bij:

- **Onderzoek dat niet gedaan is.** Een krachtscore "5/5", een negatieve
  Lasègue of "pulmonaal geen afwijkingen", terwijl de arts dat niet zei.
- **Verwisselingen.** Links en rechts, een dosering, de duur van een klacht.
- **Een afgebroken opname.** Het model "maakt het af" met een plausibel
  beleid. VitaScribe zet daar nu "niet in de opname", maar blijf alert.
- **Verkeerd gehoord.** Medicijnnamen en eigennamen.

Het verslag is altijd een concept. Wat in het dossier komt, is jouw tekst en
jouw verantwoordelijkheid (WGBO). Dat verandert niet door de software.

## Zo werk je

1. **Modus.** Voor echte patiënten alleen de **EU-modus**. De Claude-modus en
   het testgereedschap ("Naar testset sturen", de spraaktest) gebruik je
   alleen met gespeelde consulten.
2. **Toestemming.** Vraag het de patiënt (stuk 08) en vink het pas dan aan.
3. **Let op de pil.** Na 30 seconden moet er "✓ gehoord" staan. Staat er
   "geen gesprek gehoord: microfoon?", stop dan en controleer de microfoon.
   Wacht niet tot het einde.
4. **Lees elk verslag helemaal.** Begin bij de **gele markeringen**: die zinnen
   vond de controle niet terug in het gesprek. Klopt het niet, haal het weg.
   Klopt het wel, dan mag het blijven.
   Daarna de **gestippeld onderstreepte woorden**: die zijn nergens in het
   gesprek gezegd, bijvoorbeeld een dosering, een zijde of een bevinding.
   Klik op een zin om te zien waar hij in het gesprek staat. De regel onder
   het verslag telt hoeveel zinnen duidelijk teruggevonden zijn. Een zin
   zonder bron is niet per se fout: een conclusie of samenvatting staat vaak
   niet letterlijk in het gesprek. Jij beslist.
   Onder het verslag staan de **afspraken uit dit consult**: wat in de P
   staat, met een knop die het werk klaarzet (de verwijsbrief met
   specialisme en reden, Thuisarts, of kopiëren voor de agenda). VitaScribe
   stelt zelf geen afspraak voor; staat iets er niet in, dan zat het niet in
   de P.
5. **"Niet in de opname"** betekent dat dat deel van het consult ontbreekt.
   Vul het zelf aan.
6. **Geen verslag bij weinig spraak.** Dan was er te weinig te horen. Schrijf
   zelf, en controleer de microfoon voor het volgende consult.
7. **Afsluiten.** Klik na elke patiënt op **"Consult afsluiten"**. Dan zijn het
   verslag en de opname weg, en staat er niets klaar voor de volgende.
8. **Twijfel of fout.** Meld een opvallende fout bij de beheerder, zonder
   patiëntgegevens, alleen wat er misging. Een mogelijk datalek meld je
   direct (stuk 07).

## De tolk

- Spreek in korte zinnen, één vraag per beurt. Lees de **terugvertaling**: zo
  hoort de patiënt het. Klopt het niet, tik op "Eenvoudiger" of zeg het anders.
- Staat er ⚠, vraag het dan na: het kan een verkeerd verstaan woord zijn.
- Haal een verkeerd verstane beurt weg met ✕; die gaat dan niet mee in het
  verslag.
- Bij slecht nieuws, een ingrijpende keuze of als je twijfelt of het
  overkomt: een professionele tolk. Marokkaans-Arabisch wordt minder goed
  verstaan dan standaard-Arabisch; Berbers kan de tolk niet.
- In de EU-modus wordt Turks, Pools en Oekraïens niet verstaan: je kunt dan
  wel spreken en laten voorlezen, maar het antwoord van de patiënt niet laten
  vertalen.

## E-consult

- Schrijf je beleid zelf, kort. Het concept zet het in gewone taal; het
  verzint zelf geen advies. Staat er *[beleid aanvullen]*, vul dat in.
- Controleer de feiten met **?** in Bricks, en lees het antwoord helemaal
  voor je het verstuurt.
- **NHG meedenken** vink je alleen aan als je dat voor dit e-consult bewust
  wilt. Het is een voorstel; jouw beleid gaat voor. Zegt het dat de vraag niet
  schriftelijk kan, bel de patiënt of plan een afspraak.
- Pas je het antwoord aan, dan stelt VitaScribe een stijlregel voor (aanhef,
  toon, afsluiting). Onthoud alleen regels over vorm, nooit over inhoud.

## Telefoon of iPad

- Koppel met de QR-code in het zijpaneel (de knop met de telefoon, of "Tolk
  via telefoon"). Laat niemand anders die code scannen.
- Je telefoon heeft een code of Face ID en vergrendelt vanzelf.
- Foto's van een patiënt maak je via VitaScribe, niet met de gewone camera:
  dan komen ze niet in je fotorol of iCloud.
- Klik na de patiënt op "Consult afsluiten": de koppeling en de foto's zijn
  dan weg. Sluit na het spreekuur het tabblad op de telefoon.

## Visites

1. **Koppelen, eenmalig.** Zijpaneel, kaart *Visites*: *telefoon koppelen*
   en de QR-code scannen. Zet de pagina op het beginscherm van de telefoon.
2. **Bij de patiënt.** Typ een korte aanduiding, nooit naam of BSN (bijv.
   "mw. J., wondcontrole"). Vraag toestemming en vink die aan. *Start visite*
   en laat het scherm aan. Is de patiënt klaar, tik dan op *Nadicteren* en
   dicteer onderzoek en beleid; dat stuk geldt als het woord van de arts.
   Daarna *Stop*. Voeg eventueel foto's toe (wond, huid, medicijnlijst; ze
   komen niet in je fotorol) en tik op *Versturen*.
   Geen bereik? De visite wacht versleuteld op de telefoon en gaat vanzelf
   zodra er weer bereik is. Wat na 48 uur nog wacht, wordt gewist.
3. **In de praktijk.** Open de patiënt in Bricks, klik in het zijpaneel bij
   de visite op *Open*, lees het verslag na en voeg het in. Foto's van de
   visite staan in de fotolijst bovenaan; zet ze met *In Bricks* in het
   dossier. *Consult
   afsluiten* haalt de visite daarna van de server; anders gebeurt dat na
   48 uur vanzelf.
4. **Telefoon kwijt?** Hij kan geen verslag lezen. Ontkoppel toch meteen:
   *telefoon koppelen › Ontkoppel alle telefoons*.

## Meedenken over wat in beeld is

Open in Bricks het lab, een uitslag of een brief, klik in de balk onderaan
op **Denk mee over wat in beeld is**. VitaScribe beoordeelt dat scherm zoals
in het tabblad Post: waarden met richting, verloop als eerdere waarden in
beeld staan, een samenvatting voor het journaal en uitleg voor de patiënt.
Typ eerst een vraag om te richten (bijv. "is het Hb gedaald sinds de vorige
keer?"). Duiding en beleidsvoorstel alleen als klinische ondersteuning aan
staat; anders krijg je de feiten. Open alleen het onderdeel dat telt: wat
in beeld staat, gaat (gefilterd op naam en BSN) mee.

## Foto's in het dossier

Een foto van de telefoon (wond, huid, medicijnlijst) verschijnt in het
zijpaneel. Open in Bricks bij de patiënt het venster om een document of foto
toe te voegen en klik in het paneel op **In Bricks**: de foto staat dan in het
uploadveld. Geef een omschrijving en sla op in Bricks. Vind VitaScribe geen
uploadveld, dan staat de foto op het klembord.

## Wat VitaScribe van je leert

VitaScribe stelt na invoegen regels voor uit wat je aanpaste. Keur alleen een
**algemene** regel goed, nooit een met een naam, datum of gegeven van een
patiënt. Kijk af en toe onder "Wat VitaScribe leerde" of je minder hoeft aan
te passen, en zet een regel uit die niet klopt.

## Wat VitaScribe niet doet

VitaScribe stelt geen diagnose, geeft geen behandeladvies en waarschuwt niet
voor alarmsymptomen. Klinisch meedenken staat uit, behalve NHG meedenken bij
een e-consult als de praktijk dat toestaat en jij het per e-consult aanvinkt. Mis je een rode vlag in
het verslag, dan ligt dat aan het gesprek of aan het model, niet aan een
bewuste keuze van het systeem.

## Steekproef

Lees `[eens per maand]` drie eigen verslagen opnieuw na, naast wat je je van
het consult herinnert. Noteer fouten die door je eerste controle glipten. Zo
merk je of je te veel gaat vertrouwen op het concept (automation bias).

## Aftekenlijst

| Naam | Functie | Gelezen op | Paraaf |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

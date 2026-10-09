# Thuisarts.nl en informatie delen vanuit VitaScribe

Plan opgesteld 25-09-2026 in een ProVita Care-sessie; fase 1 gebouwd op
25-09-2026 op de tak `claude/thuisarts-en-delen`.

## Stand van zaken

Fase 1 en de eerste twee routes van fase 2 staan er. Eén ding is met opzet
leeg gebleven, en dat is geen slordigheid maar de kern van de zaak.

**Wat werkt.** De koppeling ICPC → Thuisarts, de chip onder de SOEP-regel, de
regel in de patiëntuitleg (met een zin in de taal van de vertaling die zegt dat
de website Nederlands is), de afdruk met een QR-code die in de browser wordt
gemaakt, de wekelijkse linkbewaking vanaf de server, het gebruikslog-eindpunt,
en van fase 2 de routes "meegeven en afdrukken" en "kopiëren voor het
HIS-bericht". De mailroute is gebouwd en staat standaard uit.

**Wat leeg is: de adressen in de koppeltabel.** Alle 43 codes uit de
voorbeeldbank staan erin, met hun titel, maar zonder URL. Thuisarts.nl en
referentiemodel.nhg.org waren vanuit de bouwomgeving niet bereikbaar, en een
adres op thuisarts.nl valt niet uit een ICPC-code af te leiden. Een link uit het
hoofd invullen zou hier de ene onvergeeflijke fout zijn: hij opent, en de
patiënt leest met hetzelfde vertrouwen over de verkeerde aandoening. De module
toont daarom alleen regels die én een adres én een controledatum hebben. Zolang
de tabel leeg is, staat er bij elke code "Geen Thuisarts-pagina bij deze code"
met een zoekveld - zichtbaar onaf, niet stil verkeerd.

Het invullen is daarmee een afgebakende klus van één zitting: `python3
scripts/thuisarts_tabel.py` zegt welke codes nog wachten, en wie een adres
invult zet zijn initialen in `door` en de datum in `gecontroleerd_op`. Vanaf dat
moment bewaakt `scripts/check_thuisarts_links.py` ze wekelijks.

**Eén aanname uit het plan klopte niet.** Het plan stelde dat de arts de
ICPC-code kan aanpassen. Dat kon niet: de code stond als tekst op het scherm.
Omdat de hele koppeling op die code steunt, is de code nu een aanpasbaar veld;
de chip volgt terwijl je typt, en invoegen in Bricks gebruikt dezelfde waarde.
Zonder die stap zou de chip een door een model voorgestelde code volgen, en dat
is precies wat dit plan wil vermijden.

**De 33 fouten in de bestaande testronde** (`tests/test_models.py`,
`tests/test_pipeline.py`) komen van passlib en bcrypt in de testomgeving en
staan er ook zonder deze wijziging.

## Waarom dit eerst een plan was

De vraag kwam binnen in een sessie die op `provita-care` werkt. Daar zijn alleen
de advertentie van de dienst en de schermbeelden te vinden, niet het product.
Twee repo's in één sessie doet de meeste schade stil: een commit op de verkeerde
branch, een pull request die naar de verkeerde basis wijst, of een regel uit de
ene `CLAUDE.md` die in de andere repo wordt gevolgd.

Er is ook een inhoudelijke reden. Twee keuzes horen bij de praktijk en niet bij
de programmeur: of er gemaild mag worden, en met welke beveiligde mail. Die
staan onderaan als open vragen.

## Wat er al was

Elk onderdeel bouwt voort op code die er stond:

- `chrome-extension/sidepanel/patient-ui.js` maakt uit E en P een uitleg op B1,
  met een vertaling als dat gevraagd wordt, en kan die kopiëren en afdrukken.
- `services/cloud_api/patient_info.py` levert die tekst via het EU-taalmodel
  (`data_policy.phi_llm_provider()`), met een gebruiksregel in `audit.log_event`.
- `renderSoep()` in `sidepanel.js` zet de ICPC-code van de SOEP-regel in
  `lastSoep.icpc_code`.
- `services/learning/seed_data/soep_seed_examples.json` bevat 43 ICPC-codes,
  afgestemd op de NIVEL-top.
- `data_policy.py` zet `CLINICAL_DECISION_SUPPORT` standaard uit (MDR). Deze
  wijziging laat die vlag ongemoeid en heeft hem ook niet nodig.

## Het uitgangspunt

**De arts kiest de informatie. De extensie zoekt haar alleen op.**

Een Thuisarts-pagina hoort bij een diagnose. Laat je een taalmodel uit het
dictaat afleiden welke pagina past, dan stelt het model in feite een diagnose
voor. Dat is klinische beslisondersteuning, en precies wat `data_policy`
uitsluit. De koppeling loopt daarom via de ICPC-code die de arts zelf vastlegt,
met een vaste tabel en zonder model ertussen. Is er geen code, dan is er ook
geen voorstel, alleen een zoekveld.

Een tweede gevolg: voor het opzoeken is geen server nodig. De tabel staat in de
extensie, en er gaan geen patiëntgegevens de browser uit om een link te vinden.

## Fase 1: Thuisarts bij de SOEP-regel

### Koppeltabel

`chrome-extension/lib/thuisarts-icpc.json`. Per regel:

```json
{ "icpc": "R78", "titel": "Acute bronchitis", "url": "https://www.thuisarts.nl/...",
  "gecontroleerd_op": "2026-10-01", "door": "AB" }
```

Een ICPC-code mag naar meer dan één pagina wijzen (bij R78 bijvoorbeeld de
aandoening zelf en "hoesten"). Dan kiest de arts. Subrubrieken (`R78.01`) vallen
terug op de hoofdrubriek. Een regel zonder adres of zonder controledatum telt
niet mee.

**Bron van de tabel: nog bij het NHG na te vragen.** Het NHG beheert
Thuisarts.nl en publiceert de ICPC-tabellen voor het HIS, waaronder tabel 65 met
patiëntvriendelijke titels. Of er een officiële koppeling ICPC → Thuisarts
bestaat, en onder welke licentie, was vanuit de bouwomgeving niet te
controleren: beide adressen waren geblokkeerd. Bestaat die koppeling, gebruik
haar dan en vervang de tabel; bestaat ze niet, dan blijft het handwerk.

**Kijk ook wat Bricks zelf al biedt.** Veel HIS'en tonen al een Thuisarts-link
bij een episode. Heeft Bricks dat, dan zit de waarde van VitaScribe niet in de
link, maar in het combineren: de link in de uitleg voor de patiënt, in de
afdruk en in de vertaling.

### Opzoeken

`chrome-extension/lib/thuisarts.js`, met `pagesForIcpc(code, tabel)`: geen DOM,
geen `chrome.*`, geen fetch. Daardoor te controleren met `node --test`, en dat
is ook de reden dat het los staat van de schermcode. De proeven staan in
`tests/js/thuisarts.test.js`:

```
node --test tests/js/thuisarts.test.js
```

### In het zijpaneel

Onder de SOEP-regels staat per pagina een chip `Thuisarts: Acute bronchitis ↗`;
klikken opent de pagina, zodat de arts leest wat de patiënt gaat lezen. Naast
elke chip staat een eigen knop "Voeg toe aan uitleg", die onder de B1-tekst de
regel `Meer lezen: <url>` zet. Heeft een code twee pagina's, dan kiest de arts
welke.

Tonen is niet kiezen. Pas die klik maakt een pagina "gekozen", en ze blijft dat
zolang de link in de tekst staat. Maakt de arts de uitleg opnieuw, of haalt hij
de regel weg, dan verdwijnt ook de QR van de afdruk. Er gaat dus nooit een link
naar de patiënt die de arts niet zelf heeft toegevoegd.

Corrigeert de arts de ICPC-code, dan wisselt de titel ernaast mee naar die van
de nieuwe code (uit de tabel), of blijft leeg. De titel van de oude code laten
staan zou "R78 · Spanningshoofdpijn" opleveren.

Twee randgevallen staan in de tekst op het scherm:

- **Thuisarts is Nederlandstalig.** Staat er ook een vertaling, dan krijgt die
  niet dezelfde regel maar een zin in die taal die zegt dat de website
  Nederlands is. Een proef bewaakt dat elke taal uit het keuzemenu zo'n zin
  heeft, zodat een nieuwe taal niet stil op het Nederlands terugvalt.
- **Past de code niet op een pagina**, dan staat er "Geen Thuisarts-pagina bij
  deze code", met een zoekveld. Het zoekadres van thuisarts.nl is nog niet met
  het oog gecontroleerd; het staat op één plek in `thuisarts.js`.

### Afdrukken met QR-code

Heeft de arts een pagina toegevoegd, dan krijgt de afdruk de link als tekst én
als QR-code. De code wordt in de browser
gemaakt, met `chrome-extension/lib/qrcode/` (qrcode-generator 2.0.4, MIT,
meegeleverd zoals pdf.js). Geen externe dienst: een QR-dienst op internet ziet
anders welke aandoening er op papier gaat.

### Bewaking van de links

`scripts/check_thuisarts_links.py` loopt de tabel na en meldt 404's en
doorverwijzingen; hij volgt een doorverwijzing niet, want of de nieuwe pagina
nog over dezelfde aandoening gaat is geen machineoordeel. Draait wekelijks via
`deploy/cron/vitascribe-thuisarts.cron`, vanaf de server en niet vanuit de
browser van de arts.

Het script schrijft niets in de tabel. `gecontroleerd_op` betekent "met het oog
gezien door `door`", en een 200 van de server is dat niet: een pagina kan
bereikbaar blijven terwijl de inhoud verschuift. Een machine die die datum
ververst, laat een verouderde regel eruitzien als een verse controle.

### Gebruikslog

`POST /api/v1/usage` neemt alleen `action` en `kind` aan, weigert elk ander veld
in plaats van het weg te laten, staat alleen bekende handelingen toe en eist dat
`kind` de vorm van een ICPC-hoofdrubriek heeft. Geen URL, geen tekst.

## Fase 2: informatie delen met de patiënt

**1. Meegeven en afdrukken.** Bestond al; fase 1 voegde de link en de QR-code toe.

**2. Kopiëren voor het HIS-bericht of portaal.** "Kopieer voor bericht" zet de
uitleg plus link op het klembord. Het bericht blijft in het dossier en loopt
over een kanaal dat al beveiligd is. De meeste waarde, het kleinste risico.

**3. Mailen.** Gebouwd, standaard uit, aan te zetten onder Instellingen →
Informatie delen met de patiënt:

- VitaScribe verstuurt zelf nooit mail; de server zou anders verwerker worden
  van een nieuwe gegevensstroom, met een eigen DPIA-paragraaf.
- De knop opent de mailclient van de praktijk via `mailto:`, met onderwerp en
  tekst ingevuld en **zonder ontvanger**. Het adres uit Bricks halen zou een
  nieuwe schraaproute openen, en een verkeerd ingevuld adres is een datalek.
- De tekst bevat geen naam, geboortedatum of BSN.
- Is de uitleg langer dan wat een mailclient uit een `mailto` overneemt, dan
  gaat hij naar het klembord in plaats van half in de mail.

Buiten dit plan: sms, WhatsApp en eigen portalen. Ze roepen dezelfde vragen op
als mail, met minder controle.

## Klaar-criteria

Fase 1 is klaar als:

1. bij de 43 seed-codes een Thuisarts-link verschijnt, of de melding dat er geen
   pagina is - **nu de tweede helft; de eerste helft wacht op de ingevulde tabel**;
2. de link in de B1-uitleg en op de afdruk staat, met een QR-code die in de
   browser is gemaakt - **gedaan**;
3. er geen patiëntgegevens de browser uitgaan voor het opzoeken - **gedaan**;
4. de linkcontrole wekelijks draait en afwijkingen meldt - **gedaan**.

Fase 2 is klaar als route 2 werkt (**gedaan**) en route 3 alleen verschijnt als
de praktijk hem aanzet, zonder ontvanger en zonder identificerende gegevens
(**gedaan**).

## Wat er nog moet gebeuren

1. Navragen bij het NHG: bestaat de koppeling ICPC → Thuisarts, en onder welke
   licentie.
2. Nagaan wat Bricks zelf al toont bij een episode.
3. De 43 adressen invullen en met het oog controleren.
4. Het zoekadres van thuisarts.nl nalopen.
5. De cron installeren op de praktijkserver.

## Open vragen voor de praktijk

1. Mag er gemaild worden, en zo ja via welke beveiligde mail?
2. Heeft Bricks een berichtenfunctie of portaal waar route 2 in past?
3. Wie controleert de koppeltabel, en hoe vaak?

# Testset gespeelde consulten

Transcripten van gespeelde consulten (acteurs, geen patiënten) om SOEP-verslagen
van verschillende taalmodellen te vergelijken en wijzigingen aan de prompts te
toetsen. Beschrijving en valkuilen per consult staan in `index.json`.

- Nooit een echte patiënt in deze map.
- Elk consult heeft een bron. De AmsterdamUMC-video's zijn openbaar op YouTube;
  de transcripten zijn alleen voor interne kwaliteitstoetsing.
- Nieuwe consulten: op `/beheer/spraaktest` met "Bewaar als testset" downloaden
  en het bestand hier toevoegen (tekst + regel in `index.json`).

## Zonder kopiëren en plakken

- **Hele testset** zet bij elk consult de volledige verslagen in het serverlog
  (`soeptest.rapport`, met run-id, rol, model, valkuilen en verdacht). De
  ontwikkelaar leest ze daar terug. Dit geldt alleen voor de vaste testset;
  eigen gesprekken uit een sessie gaan nooit met tekst in het log.
- **Herhaal 2× of 3×** draait de hele set meerdere keren, om te zien hoeveel
  een uitkomst per keer verschilt.
- **Naar testset sturen** (spraaktest) zet de gespeelde gesprekken van die
  pagina in stukken in het log (`testset.inzending`). Daarna worden ze met de
  hand, met valkuilen, aan deze map toegevoegd. Alleen gespeelde consulten.

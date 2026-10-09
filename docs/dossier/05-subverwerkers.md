# 05 Subverwerkers

Stand 7 oktober 2026.

In fase 1 zijn de praktijk en ProVitaCare één rechtspersoon. Railway en
Mistral zijn dan rechtstreeks verwerkers van de praktijk, en de
overeenkomsten lopen op naam van die rechtspersoon. In fase 2 zijn ze
subverwerkers van ProVitaCare, en meldt ProVitaCare wijzigingen 30 dagen
vooraf (stuk 04, art. 5).

## In gebruik voor echte patiënten (EU-modus)

| Partij | Rol | Vestiging | Verwerking | Grondslag en afspraken | Status |
|---|---|---|---|---|---|
| Railway Corp. | Hosting van de VitaScribe-server en de database (register en auditlog) | San Francisco, VS | Server in Nederland (regio Europa-West). Bewaart geen audio of tekst; wel het auditlog zonder inhoud. | Verwerkersovereenkomst getekend (envelop 15F6A42D…). Railway is actief in het EU-US Data Privacy Framework. SOC 2 Type II. | **Beantwoord 5 oktober 2026:** de DPA dekt geen gezondheidsgegevens (bijlage A "None", wordt niet aangepast); logs staan in US West; geen toezegging alleen-EU (`docs/wetgeving/bewijs/railway-dpa-2026-10-05.md`). Echte consulten gaan daarom via een server bij een Europese host (stuk 14, stap 4). Railway alleen voor gespeelde consulten. |
| Mistral AI SAS | Spraakherkenning (Voxtral), tekst (Mistral Large) en voorlezen (Voxtral TTS): SOEP, controleronde, tolk, brieven, dossiervragen, post | Parijs, Frankrijk | Alleen via het EU-endpoint `api.eu.mistral.ai`, sinds 9 oktober 2026: Mistral bevestigde die dag dat het wereldwijde `api.mistral.ai`, dat de code tot dan aanriep, geen verwerking binnen de EER garandeert. Mistral geeft geen absolute garantie: sommige subverwerkers kunnen gegevens vanuit derde landen verwerken, met SCC's. Op de subverwerkerslijst staan ook Amerikaanse moederbedrijven (Microsoft, Google, CoreWeave), met verwerking in de EER; volgens Mistral (7 oktober 2026) raken Azure (Noorwegen, Zweden), Google Cloud (Nederland) en CoreWeave (Spanje) de inferentie via het EU-endpoint, en kan Cloudflare (VS) metadata zonder inhoud verwerken onder SCC's (`docs/wetgeving/leveranciers/mistral.md`). De kloonstem bewaart Mistral standaard ongeveer 30 dagen; verwijderen kan met een DELETE-verzoek. | Verwerkersovereenkomst: de online-DPA van Mistral geldt via de voorwaarden en wordt niet apart ondertekend. Zero data retention (ZDR) geactiveerd op 6 oktober 2026 voor de organisatie van de praktijk, voor de endpoints `/v1/chat/completions`, `/v1/audio/transcriptions` en `/v1/audio/speech`. Geen training op API-data, schriftelijk bevestigd. | **Bevestigd 6 oktober 2026** (ticket #37361256, zie `docs/wetgeving/bewijs/mistral-zdr-2026-10-06.md`). Nog te doen: subverwerkerslijst met datum vastleggen, DPA-versie en schermafdruk van de console bewaren. |

ZDR geldt niet voor stateful endpoints. VitaScribe gebruikt er één: het klonen
van een stem voor de tolk (`POST /v1/audio/voices`, `tolk.py`). Mistral bewaart
die stem van een medewerker, en de code heeft geen verwijderpad. Zolang Mistral
de bewaartermijn en de verwijdering niet heeft bevestigd, hoort die functie uit
te staan of apart in register en DPIA te worden opgenomen, met de toestemming
van de collega. De vervolgvraag aan Mistral staat in het bewijsstuk hierboven.

Zolang het slot op de EU-modus niet aanstaat (`TOEGESTANE_MODI=eu`), gebruikt
de praktijk alleen gespeelde consulten. Zie `docs/wetgeving/STAPPENPLAN.md`,
stappen VS2 tot en met VS4.

## Niet in gebruik voor echte patiënten (Claude-modus)

Deze partijen zijn technisch aangesloten. Ze worden alleen gebruikt met
gespeelde consulten en test-dossiers. Voor echte patiënten zijn eerst een
verwerkersovereenkomst, een doorgiftegrondslag en een aanvulling op de DPIA
nodig.

| Partij | Rol | Vestiging |
|---|---|---|
| Anthropic PBC | Tekst (Claude) | VS |
| Microsoft (Azure AI Speech) | Voorlezen door de tolk, alleen als de beheerder het instelt; in de EU-modus alleen met een besluit van de praktijk (`TOLK_AZURE_IN_EU`) | VS, verwerking in een EU-regio |
| Deepgram Inc. | Spraak, live dicteren (EU-eindpunt) | VS |

Een praktijk die een eigen sleutel bij Anthropic, OpenAI of Deepgram instelt,
sluit de overeenkomst met die partij zelf. Die partij is dan geen subverwerker
van ProVitaCare.

## Geen subverwerker

- **Bricks (HIS).** De extensie leest in de browser wat in beeld staat. Er gaan
  geen gegevens van VitaScribe naar Bricks, behalve wat de arts zelf plakt.
- **Thuisarts.nl en ProVita Care.** De links komen uit een vaste tabel in de
  extensie. Er gaat geen patiëntgegeven mee.
- **Microsoft (Edge Add-ons) en Google (Chrome Web Store).** Die verspreiden
  alleen de extensie, en zien geen gegevens.
- **Stemmen van de browser.** De tolk leest alleen voor met stemmen die op de
  computer zelf staan. De online stemmen van Edge en Chrome sturen de tekst
  naar Microsoft of Google en worden daarom nooit gebruikt.

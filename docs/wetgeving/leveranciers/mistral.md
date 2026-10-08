# Mistral AI (La Plateforme / Studio): Voxtral transcriptie en Mistral Large

Status per 7 oktober 2026. Bron: supportticket #37361256, antwoord van Anna (Mistral AI Support) op 6 oktober 2026, 10:50, aan a.bennaghmouch@gmail.com. Aanvraag op naam van Groepspraktijk het Roosendael, organisatie-ID 2f99df70-61c2-4851-8b16-1b22132c9b95.

## Wat Mistral schriftelijk heeft bevestigd

| Vraag uit de aanvraag (2 oktober 2026) | Antwoord | Waarde voor het dossier |
|---|---|---|
| 1. Zero Data Retention activeren | Geactiveerd op 6 oktober 2026 voor de organisatie. Zichtbaar onder Admin console, Privacy. Geldt voor stateless endpoints: `/v1/chat/completions`, `/v1/fim/completions`, `/v1/embeddings`, moderations en classifications, `/v1/ocr`, `/v1/audio/speech`, `/v1/audio/transcriptions`. Mistral bewaart of logt in- en uitvoer dan niet langer dan strikt nodig om de uitvoer te maken. | Voldoende voor transcriptie en chat, mits de code uitsluitend die endpoints gebruikt. |
| ZDR, uitzonderingen | Niet voor stateful API's: agents, batch, files, conversations, libraries. Niet voor Vibe. Niet voor Labs-modellen. | Harde eis aan de code: geen `/v1/files`, geen batch, geen agents of conversations, geen Labs-model. Controle in de repo (zie stappenplan). |
| 2. Verwerkersovereenkomst | Standaard-DPA online, wordt periodiek bijgewerkt, wordt niet offline ondertekend. | De DPA geldt via de voorwaarden. Voor het dossier: datum en versie noteren en een PDF-afdruk bewaren op de dag van vastlegging. Zet een halfjaarlijkse controle op wijzigingen in de agenda. |
| 3. Verwerking binnen EU/EER | Standaard binnen de EER, tenzij het Amerikaanse endpoint expliciet wordt aangeroepen. Mistral kan niet bevestigen dat nooit gegevens buiten de EER worden verwerkt: sommige subverwerkers verwerken bepaalde gegevens vanuit derde landen, met passende waarborgen (SCC's). | Geen volledige EER-garantie. Dit is een restrisico in de DPIA en een reden om de pseudonimisering vóór verzending te houden waar dat kan. De lijst met subverwerkers is niet meegestuurd: zelf ophalen uit het Trust Center en als bijlage opnemen. |
| 4. Geen training op API-data | Bevestigd. In de Admin console staan training op API-aanroepen en Labs-modellen uit. | Afdoende. Schermafdruk van de console-instelling bij het dossier. |

## Subverwerkers (gevonden 8 oktober 2026)

Het Trust Center van Mistral (`trust.mistral.ai/subprocessors`) noemt onder
meer Microsoft (Zweden, Noorwegen), Google (Nederland, België; de VS alleen
voor het Amerikaanse endpoint), CoreWeave (inferentie in de EER) en Mistral
Compute (Frankrijk). Mistral is een Frans bedrijf, maar er zitten dus
Amerikaanse moederbedrijven in de keten. Voor de CLOUD Act is dat hetzelfde
punt als bij Azure en AWS. Te vragen: welke van deze subverwerkers het
ZDR-verkeer via `api.mistral.ai` voor deze organisatie werkelijk raken.
Gebruik daarom voor de EU-modus de woorden "Europese aanbieders", niet "geen
Amerikaanse partijen". Zie `docs/bedrijf/BLAUWDRUK.md`, paragraaf 3, in de
VitaScribe-repo.

## Nog open bij Mistral

1. De subverwerkerslijst met locaties: niet geleverd in het antwoord. Ophalen uit het Trust Center en vastleggen met datum.
2. De exacte DPA-link uit de mail ("available here") openen, versie en datum noteren, PDF bewaren.
3. Bevestigen dat het EU-endpoint (`api.mistral.ai`) is wat de code aanroept en niet het Amerikaanse endpoint.
4. Schermafdruk van de ZDR-instelling in de Admin console (Privacy) bij het dossier.

## Wat dit betekent voor de DPIA

- Art. 28 AVG: verwerker met online-DPA en SCC's voor eventuele doorgifte. Aanvaardbaar, mits vastgelegd.
- Art. 9 AVG: gezondheidsgegevens in audio en transcript. ZDR beperkt de bewaring bij de verwerker tot de verwerkingsduur. Dit maakt de verwerking niet "lokaal"; het blijft een externe verwerking van bijzondere persoonsgegevens, met de toestemming van de patiënt en de WGBO-grondslag van de praktijk als basis.
- Doorgifte: Mistral sluit verwerking buiten de EER niet uit. In het verwerkingsregister opnemen als "mogelijk, met SCC's", niet als "uitsluitend EU".

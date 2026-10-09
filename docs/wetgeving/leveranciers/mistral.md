# Mistral AI (La Plateforme / Studio): Voxtral transcriptie en Mistral Large

Status per 9 oktober 2026. Bron: supportticket #37361256, antwoord van Anna (Mistral AI Support) op 6 oktober 2026, 10:50, aan a.bennaghmouch@gmail.com. Aanvraag op naam van Groepspraktijk het Roosendael, organisatie-ID 2f99df70-61c2-4851-8b16-1b22132c9b95.

## Wat Mistral schriftelijk heeft bevestigd

| Vraag uit de aanvraag (2 oktober 2026) | Antwoord | Waarde voor het dossier |
|---|---|---|
| 1. Zero Data Retention activeren | Geactiveerd op 6 oktober 2026 voor de organisatie. Zichtbaar onder Admin console, Privacy. Geldt voor stateless endpoints: `/v1/chat/completions`, `/v1/fim/completions`, `/v1/embeddings`, moderations en classifications, `/v1/ocr`, `/v1/audio/speech`, `/v1/audio/transcriptions`. Mistral bewaart of logt in- en uitvoer dan niet langer dan strikt nodig om de uitvoer te maken. | Voldoende voor transcriptie en chat, mits de code uitsluitend die endpoints gebruikt. |
| ZDR, uitzonderingen | Niet voor stateful API's: agents, batch, files, conversations, libraries. Niet voor Vibe. Niet voor Labs-modellen. | Harde eis aan de code: geen `/v1/files`, geen batch, geen agents of conversations, geen Labs-model. Controle in de repo (zie stappenplan). |
| 2. Verwerkersovereenkomst | Standaard-DPA online, wordt periodiek bijgewerkt, wordt niet offline ondertekend. | De DPA geldt via de voorwaarden. Voor het dossier: datum en versie noteren en een PDF-afdruk bewaren op de dag van vastlegging. Zet een halfjaarlijkse controle op wijzigingen in de agenda. |
| 3. Verwerking binnen EU/EER | Standaard binnen de EER, tenzij het Amerikaanse endpoint expliciet wordt aangeroepen. Mistral kan niet bevestigen dat nooit gegevens buiten de EER worden verwerkt: sommige subverwerkers verwerken bepaalde gegevens vanuit derde landen, met passende waarborgen (SCC's). | Geen volledige EER-garantie. Dit is een restrisico in de DPIA en een reden om de pseudonimisering vóór verzending te houden waar dat kan. De lijst met subverwerkers is niet meegestuurd: zelf ophalen uit het Trust Center en als bijlage opnemen. |
| 4. Geen training op API-data | Bevestigd. In de Admin console staan training op API-aanroepen en Labs-modellen uit. | Afdoende. Schermafdruk van de console-instelling bij het dossier. |

## Subverwerkers en kloonstem (antwoord van Mistral, 7 oktober 2026)

Op de vervolgvragen van 7 oktober antwoordde Anna (Mistral AI Support) dezelfde dag, ticket #37361256:

- **Inferentie via het EU-endpoint (`api.eu.mistral.ai`)** voor `/v1/audio/transcriptions` en `/v1/chat/completions` loopt via Azure (Noorwegen, Zweden), Google Cloud (Nederland) en CoreWeave (Spanje). Alle drie hebben een Amerikaans moederbedrijf; de verwerking zelf is in de EER.
- **Cloudflare (VS)** kan metadata zonder inhoud verwerken (request-ID's, tijdstempels) voor de routering, onder SCC's (module 4).
- **Doorgifte voor onderhoud.** De DPA staat toe dat subverwerkers buiten de EER "marginally" op afstand bij gegevens kunnen voor onderhoud of beheer.
- **Kloonstem.** `/v1/audio/voices` valt buiten ZDR en volgt de standaardtermijn, "typically 30 days" voor misbruikmonitoring. Verwijderen kan met `DELETE /v1/audio/voices/{voice_id}` of in de console.
- **DPA-versie.** De DPA zit in de Commercial Terms of Service; de versies en data staan onder de knop "versions" bij de DPA op `legal.mistral.ai`.

Wat dat betekent:

1. **Het endpoint in de code.** De subverwerkers zijn alleen voor `api.eu.mistral.ai` opgegeven. Op 9 oktober bevestigde Mistral dat alleen dat adres verwerking in de EER garandeert; zie hieronder.
2. **Woorden.** De EU-modus gebruikt Europese aanbieders, maar niet zonder Amerikaanse partijen in de keten. Register en DPIA noemen Azure, Google, CoreWeave en Cloudflare bij naam, met de doorgiftegrond.
3. **Kloonstem.** Blijft uit, tot de code de stem na gebruik zelf verwijdert met het DELETE-verzoek. Ook dan ligt de stem tot dat moment bij Mistral, buiten ZDR, en hoort hij met toestemming van de collega in het register.

## Het endpoint (antwoord van Mistral, 9 oktober 2026)

Op de vraag van 8 oktober antwoordde Anna (Mistral AI Support) op 9 oktober, ticket #37361256:

- `api.mistral.ai` is het **wereldwijde** endpoint en garandeert **geen** verwerking binnen de EER. Verzoeken kunnen naar infrastructuur buiten de EER gaan, ook naar subverwerkers in de VS.
- `api.eu.mistral.ai` stuurt de inferentie uitdrukkelijk naar infrastructuur in de EER (Azure in Noorwegen en Zweden, Google Cloud in Nederland, CoreWeave in Spanje).
- Wie verwerking alleen in de EER nodig heeft, zoals een zorgaanbieder, moet `api.eu.mistral.ai` uitdrukkelijk gebruiken.

Dit spreekt het antwoord van 6 oktober tegen ("standaard binnen de EER, tenzij het Amerikaanse endpoint expliciet wordt aangeroepen", tabel bovenaan). Het antwoord van 9 oktober is specifieker en gaat voor.

**Gevolg.** Tot 9 oktober 2026 riep de code `api.mistral.ai` aan, in VitaScribe en in ConsultSpiegel. Verzoeken in de EU-modus hadden in die periode dus geen EER-garantie. Dat hoort zo in de DPIA en het register. Sinds 9 oktober 2026 gebruiken beide uitsluitend `api.eu.mistral.ai`; een proef in elke repo valt om als het wereldwijde adres terugkomt.

Vraag 4 (subverwerkers bij voorlezen) en vraag 5 (toegang van buiten de EER tot de inhoud) heeft Anna doorgezet naar het juridische team van Mistral. Antwoord volgt.

## Welke endpoints de code aanroept (bijgewerkt 9 oktober 2026)

VitaScribe roept bij Mistral vier endpoints aan, alle vier sinds 9 oktober 2026 op `api.eu.mistral.ai` (`services/cloud_api/mistral_adres.py`). ConsultSpiegel gebruikt de eerste twee, ook op het EU-endpoint (`backend/app/config.py`, een ander adres uit de omgeving wordt niet gebruikt):

| Endpoint | Waarvoor | ZDR |
|---|---|---|
| `/v1/audio/transcriptions` | Voxtral, spraak naar tekst | ja |
| `/v1/chat/completions` | Mistral Large, SOEP, brieven, controleronde | ja |
| `/v1/audio/speech` | voorlezen door de tolk | ja |
| `/v1/audio/voices` | kloonstem | nee (stateful, ongeveer 30 dagen) |

Geen `/v1/files`, batch, agents of conversations. Mistral bevestigde het EU-endpoint uitdrukkelijk voor transcriptie en chat. Of voorlezen en de kloonstem op het EU-endpoint werken, is niet getest; de kloonstem staat uit. Een eerdere versie van dit stuk noemde `api.mistral.ai` het EU-endpoint; dat was fout.

## Nog open bij Mistral

1. De subverwerkerslijst met locaties: Mistral verwijst naar het Trust Center en noemde op 7 oktober alleen de subverwerkers van het EU-endpoint. De volledige lijst ophalen en vastleggen met datum.
2. De DPA: versie en datum noteren via de knop "versions" op `legal.mistral.ai`, PDF bewaren.
3. ~~Het endpoint.~~ Beantwoord op 9 oktober 2026: alleen `api.eu.mistral.ai` garandeert de EER. De code is dezelfde dag omgezet.
4. Voorlezen: gelden dezelfde subverwerkers ook voor `/v1/audio/speech`? Gevraagd op 8 oktober 2026; op 9 oktober doorgezet naar het juridische team van Mistral.
5. Doorgifte voor onderhoud: kan toegang op afstand van buiten de EER ook de inhoud raken (audio, transcript, prompt, uitvoer), ook met ZDR aan? Zo ja, welke subverwerkers en met welk doorgiftemechanisme (SCC's of het EU-VS-gegevensprivacykader)? Gevraagd op 8 oktober 2026; op 9 oktober doorgezet naar het juridische team van Mistral.
6. Schermafdruk van de ZDR-instelling in de Admin console (Privacy) bij het dossier.

## Wat dit betekent voor de DPIA

- Art. 28 AVG: verwerker met online-DPA en SCC's voor eventuele doorgifte. Aanvaardbaar, mits vastgelegd.
- Art. 9 AVG: gezondheidsgegevens in audio en transcript. ZDR beperkt de bewaring bij de verwerker tot de verwerkingsduur. Dit maakt de verwerking niet "lokaal"; het blijft een externe verwerking van bijzondere persoonsgegevens, met de toestemming van de patiënt en de WGBO-grondslag van de praktijk als basis.
- Doorgifte: Mistral sluit verwerking buiten de EER niet uit. In het verwerkingsregister opnemen als "mogelijk, met SCC's", niet als "uitsluitend EU".

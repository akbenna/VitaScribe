# Bewijsstuk: Mistral AI, Zero Data Retention en verwerkersafspraken

Supportticket #37361256, "Zero Data Retention request – healthcare organisation (GDPR)". Correspondentie tussen a.bennaghmouch@gmail.com en support@mistral.ai (Intercom, EU). Organisatie in de Mistral-console: Groepspraktijk het Roosendael, ID 2f99df70-61c2-4851-8b16-1b22132c9b95. Dit bestand is een afschrift; de originele mails staan in de mailbox en horen als PDF in het praktijkdossier.

## 1. Aanvraag, 2 oktober 2026, 23:03

Gevraagd, voor transcriptie van consultopnamen met Voxtral (bijzondere persoonsgegevens, art. 9 AVG, met toestemming van de patiënt):

1. Zero Data Retention activeren, ook voor misbruikcontrole.
2. Bevestiging dat de standaard-DPA geldt, met de actuele versie.
3. Bevestiging van verwerking binnen de EU/EER, met de lijst van subverwerkers.
4. Bevestiging dat API-data niet voor training wordt gebruikt.

Op 5 oktober 2026 herhaald met de toevoeging dat het om Voxtral-transcriptie én chat completions (mistral-large-latest) gaat.

## 2. Antwoord van Anna, Mistral AI Support, 6 oktober 2026, 10:50

Letterlijke kern:

> I am pleased to confirm that your request has been approved for Studio. I have just activated this ZDR option for your organization 2f99df70-61c2-4851-8b16-1b22132c9b95. You should see this option enabled in the Privacy section of your Admin console.
>
> For stateless APIs (such as chat completion, FIM, embeddings, classifiers, and OCR) with Zero Data Retention (ZDR) enabled, Mistral does not store or log the input and output longer than is strictly necessary to generate the output.
>
> ZDR applies to the following stateless API endpoints: /v1/chat/completions, /v1/fim/completions, /v1/embeddings, /v1/moderations, /v1/chat/moderations, /v1/classifications, /v1/chat/classifications, /v1/ocr, /v1/audio/speech, /v1/audio/transcriptions.
>
> Please note: ZDR is not available for Vibe. ZDR does not apply to stateful APIs, which include agents, batch, files, conversations, and libraries. ZDR is not available for Labs models.
>
> I also confirm that your API inputs and outputs are not used for training.
>
> Our DPA is available here and is regularly updated to reflect the evolution of our personal data processing, services and security measures, as well as to comply with applicable regulations. For these reasons, we are unable to sign our DPA offline.
>
> By default, unless you specifically call our US API endpoint, our Products are hosted within the European Economic Area (EEA). However, at this stage we cannot confirm that no data will ever be processed or transferred outside the Economic European Area (EEA) in all circumstances, as some of our sub-processors may process certain data from third countries. [...] In all cases where personal data is transferred outside the EEA, we ensure that the transfer is subject to appropriate safeguards in accordance with the GDPR - such as the European Commission's Standard Contractual Clauses (SCCs).

## 3. Wat hiermee is afgedekt en wat niet

| Punt | Afgedekt | Opmerking |
|---|---|---|
| ZDR voor `/v1/audio/transcriptions` en `/v1/chat/completions` | Ja, sinds 6 oktober 2026 | Dat zijn de endpoints die VitaScribe en ConsultSpiegel gebruiken. |
| ZDR voor `/v1/audio/speech` (tolk voorlezen) | Ja | VitaScribe-tolk. |
| ZDR voor `/v1/audio/voices` (stem klonen, VitaScribe-tolk) | **Nee** | Stateful: Mistral bewaart de stem. Niet in de lijst. Zie stappenplan, VitaScribe stap 4. |
| Geen training | Ja | Schriftelijk. |
| DPA | Geldt online, niet ondertekend | Versie en datum vastleggen, PDF bewaren. |
| Verwerking in de EER | Standaard ja, geen absolute garantie | Subverwerkers kunnen vanuit derde landen verwerken, met SCC's. Subverwerkerslijst niet meegestuurd. |

## 4. Nog te vragen aan Mistral (ticket staat op "Waiting on you")

Conceptantwoord, in het Engels, voor de hand:

> Thank you, Anna. For our records, two follow-up questions:
> 1. Could you send or link the current sub-processor list with locations, and confirm which sub-processors (if any) are involved in processing requests to /v1/audio/transcriptions and /v1/chat/completions from the EU endpoint?
> 2. We use /v1/audio/voices (voice cloning) for a translation feature with a staff member's consent. Please confirm the retention period for stored voices, and how we can delete a voice (API or console).
> Kind regards, A. Bennaghmouch

## 5. Nog zelf te doen

1. Schermafdruk van Admin console, Privacy, met de ZDR-instelling en de uitgeschakelde training; datum erbij.
2. De DPA-link uit de mail openen; versie en datum noteren; PDF in het praktijkdossier.
3. Subverwerkerslijst uit het Trust Center van Mistral met datum vastleggen.
4. Halfjaarlijkse controle op wijzigingen van DPA en subverwerkers (Mistral meldt alleen toevoegingen en vervangingen).

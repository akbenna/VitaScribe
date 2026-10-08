# Overige partijen in de keten van VitaScribe

Stand 8 oktober 2026.

| Partij | Waar | Wat | Status |
|---|---|---|---|
| AWS (Amazon Bedrock, eu-central-1) | Code klaar, niet actief | Claude-modellen in Frankfurt; fail-closed op EU-regio | Nog geen account op praktijknaam, geen DPA. Het AWS GDPR DPA hoort bij de voorwaarden. Pas opnemen als de route aangaat. |
| Gladia (Frankrijk) | Code klaar, niet actief | Spraak achteraf in de EU-modus, na het consult of per tolkbeurt; de opdracht wordt bij de dienst gewist zodra de tekst binnen is | Geen sleutel, geen DPA. Alleen getest met nagebootste antwoorden. Keuze tussen Gladia en Speechmatics staat open (werkplan stap 6). |
| Speechmatics (VK, EU-endpoint) | Code klaar, niet actief | Als Gladia | Als Gladia. Het VK valt onder een adequaatheidsbesluit; of dat volstaat voor de EU-modus is een open vraag uit de overdracht. |
| Microsoft (Azure AI Speech, westeurope) | Tolk, alleen met sleutel | Voorlezen van vertaalde tekst | Amerikaans bedrijf, EU-regio. In de EU-modus alleen met `TOLK_AZURE_IN_EU`. Staat in stuk 05, niet in de DPIA-dataflow. |
| Google (Gemini) | Alleen via `PHI_LLM_PROVIDER=gemini` | Tekst | Niet bedoeld voor gebruik; de waarde wordt niet gevalideerd. In de code weigeren (VS5). |
| Groq, OpenAI Whisper | Alleen via `ALLOWED_STT_PROVIDERS` | Audio | Uit de toegestane waarden halen (VS5). |
| YouTube (nocookie) | Beheerpagina | Browser laadt video; IP naar Google | Alleen beheerder. |
| Hugging Face | Lokale stack | Alleen modeldownload (Whisper, pyannote) | Geen gebruikersdata. |
| Microsoft Edge Add-ons, Chrome Web Store | Extensie | Alleen verspreiding | Geen verwerker. |

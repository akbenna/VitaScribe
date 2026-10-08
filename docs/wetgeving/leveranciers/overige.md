# Overige partijen in de keten

Stand 7 oktober 2026.

| Partij | Waar | Wat | Status |
|---|---|---|---|
| AWS (Amazon Bedrock, eu-central-1) | VitaScribe, code klaar, niet actief | Claude-modellen in Frankfurt; fail-closed op EU-regio | Nog geen account op praktijknaam, geen DPA. Het AWS GDPR DPA hoort bij de voorwaarden. Pas opnemen als de route aangaat. |
| Microsoft (Azure AI Speech, westeurope) | VitaScribe tolk, alleen met sleutel | Voorlezen van vertaalde tekst | Amerikaans bedrijf, EU-regio. In de EU-modus alleen met `TOLK_AZURE_IN_EU`. Staat in stuk 05 van VitaScribe, niet in de DPIA-dataflow. |
| Google (Gemini) | VitaScribe, alleen via `PHI_LLM_PROVIDER=gemini` | Tekst | Niet bedoeld voor gebruik; de waarde wordt niet gevalideerd. Aanbeveling: in de code weigeren. |
| Groq, OpenAI Whisper | VitaScribe, alleen via `ALLOWED_STT_PROVIDERS` | Audio | Zelfde als hierboven: uit de toegestane waarden halen. |
| Google Fonts | BennaHealth `/health` | IP-adres en user agent van elke bezoeker | Niet in de privacyverklaring. Lettertype lokaal zetten (Amiri is al lokaal, Newsreader niet). |
| YouTube (nocookie) | ConsultSpiegel afspeellijst, VitaScribe beheerpagina | Browser laadt video; IP naar Google | Alleen opleider of beheerder. In ConsultSpiegel worden gespeelde consulten van derden verwerkt: auteursrecht en YouTube-voorwaarden vastleggen. |
| Hugging Face | ConsultSpiegel, VitaScribe lokale stack | Alleen modeldownload (Whisper, pyannote) | Geen gebruikersdata. |
| Anthropic via Claude-taak | BennaHealth weekbericht | Weekcijfers (gewicht, inname) via een connector | Staat in geen document. Opnemen of stopzetten. |
| Microsoft Edge Add-ons, Chrome Web Store | Bricks Companion, VitaScribe-extensie | Alleen verspreiding | Geen verwerker. |
| Google of Microsoft browsersync | Bricks Companion `chrome.storage.sync` | Licentiesleutel met praktijknaam en -nummers | Geen patiëntgegevens; wel in de privacyverklaring noemen. |

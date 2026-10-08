# Deepgram Inc. (spraakherkenning in de Claude-modus van VitaScribe en ConsultSpiegel)

Stand 7 oktober 2026. De site van Deepgram was vanuit deze omgeving niet bereikbaar; de feiten over het EU-endpoint komen uit zoekresultaten (aankondiging januari 2026, developer-docs) en moeten bij het vastleggen worden nagelezen.

## Wat de code doet

- Beide producten roepen `api.eu.deepgram.com` aan (batch `/v1/listen` en live `wss://.../v1/listen`) met `mip_opt_out=true`. De audio gaat ongepseudonimiseerd.
- De host staat in een omgevingsvariabele (`DEEPGRAM_URL`, `DICTATION_DEEPGRAM_URL`) en is dus overschrijfbaar; er is geen harde garantie op het EU-endpoint.
- In VitaScribe is Deepgram de standaard spraakdienst in de Claude-modus; in ConsultSpiegel alleen in de Claude-modus (simulatie) en nooit bij echte consulten (`ECHT_ALLEEN_EU`).

## Wat bekend is over Deepgram

- EU-endpoint algemeen beschikbaar sinds januari 2026: verwerking binnen de EU, land kan wisselen. Console, facturering en bedrijf blijven Amerikaans.
- `mip_opt_out=true` sluit gebruik voor modelverbetering uit (tegen een hogere prijs).
- Deepgram biedt een DPA met SCC's; of Deepgram DPF-gecertificeerd is, is niet geverifieerd.
- Bewaartermijn van audio en transcript bij Deepgram na een verzoek: niet uit de repo's af te leiden, niet geverifieerd.

## Besluit dat voorligt

Deepgram is in beide producten een Amerikaanse verwerker van ongepseudonimiseerde consultaudio. Voor echte patiënten is dat alleen verdedigbaar met een DPA, een doorgiftegrondslag en een TIA. Het eenvoudigste alternatief is Deepgram uit de keten te halen voor echte patiënten (VitaScribe-werkplan stap 6, ConsultSpiegel doet dit al via `ECHT_ALLEEN_EU`) en Deepgram alleen te houden voor simulatie en dicteren zonder patiëntgegevens.

## Nog te doen

1. Besluit: Deepgram alleen voor simulatie en dictaat, of DPA plus TIA voor echte patiënten.
2. Bij behoud: DPA aangaan (console of per mail), DPF-status en bewaartermijn schriftelijk laten bevestigen, de EU-host in de code vastzetten in plaats van in een omgevingsvariabele.

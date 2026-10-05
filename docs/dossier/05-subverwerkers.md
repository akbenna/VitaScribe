# 05 Subverwerkers

Stand 5 oktober 2026. Wijzigingen meldt de verwerker 30 dagen vooraf (stuk
04, art. 5).

## In gebruik voor echte patiënten (EU-modus)

| Partij | Rol | Vestiging | Verwerking | Grondslag en afspraken | Status |
|---|---|---|---|---|---|
| Railway Corp. | Hosting van de VitaScribe-server en de database (register en auditlog) | San Francisco, VS | Server in Nederland (regio Europa-West). Bewaart geen audio of tekst; wel het auditlog zonder inhoud. | Verwerkersovereenkomst getekend (envelop 15F6A42D…). Railway is actief in het EU-US Data Privacy Framework. SOC 2 Type II. | Bevestiging over gezondheidsgegevens gevraagd; SOC 2-rapport op te vragen |
| Mistral AI SAS | Spraakherkenning (Voxtral) en tekst (Mistral Large): SOEP, controleronde, brieven, dossiervragen, post | Parijs, Frankrijk | EU | Verwerkersovereenkomst, verwerking in de EU, geen training, zero data retention (ZDR) | **Open**: aangevraagd, nog niet bevestigd |

Zolang Mistral open staat, gebruikt de praktijk alleen gespeelde consulten.

## Niet in gebruik voor echte patiënten (Claude-modus)

Deze partijen zijn technisch aangesloten. Ze worden alleen gebruikt met
gespeelde consulten en test-dossiers. Voor echte patiënten zijn eerst een
verwerkersovereenkomst, een doorgiftegrondslag en een aanvulling op de DPIA
nodig.

| Partij | Rol | Vestiging |
|---|---|---|
| Anthropic PBC | Tekst (Claude) | VS |
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

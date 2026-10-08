# Anthropic (Claude API)

Bron: platform.claude.com, "API and data retention", gelezen op 7 oktober 2026.

- Standaard worden prompts en antwoorden niet bewaard, behalve voor "Covered Models" (Fable 5.x en Mythos 5.x), die 30 dagen bewaring vereisen. Welk model de code gebruikt bepaalt dus de bewaring.
- Zero Data Retention bestaat, maar alleen per organisatie via het salesteam, niet via een instelling.
- HIPAA-gereedheid met BAA is zelf te activeren in de console; dat is een Amerikaans kader en vervangt geen AVG-verwerkersovereenkomst. Anthropic heeft een DPA met SCC's; verwerking vindt primair in de VS plaats. EU-verwerking alleen via Amazon Bedrock (eu-central-1) of een enterprisecontract.
- Geen training op API-data zonder uitdrukkelijke toestemming.
- Batch-API en code execution vallen nooit onder ZDR (bewaring 29 tot 30 dagen).

Gevolg voor de repo's: Claude is alleen verdedigbaar voor gepseudonimiseerde tekst zonder bijzondere persoonsgegevens, of voor simulatiegegevens. Voor echte consulten met gezondheidsgegevens hoort de EU-route (Mistral met ZDR) of lokaal (Ollama/Whisper) de standaard te zijn. Dat is al zo bepaald in ConsultSpiegel (ECHT_ALLEEN_EU) en in de EU-modus van VitaScribe.

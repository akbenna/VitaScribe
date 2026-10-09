"""The one address VitaScribe uses for Mistral.

Mistral answered on 8 October 2026 (ticket #37361256) that the global endpoint
api.mistral.ai does not guarantee processing inside the EEA: requests may be
routed to infrastructure elsewhere, including the US. Only api.eu.mistral.ai
routes inference to EEA infrastructure (Azure Norway/Sweden, Google Cloud
Netherlands, CoreWeave Spain). For health data that is the only acceptable
address, so it is not a setting: there is nothing to choose.
"""

MISTRAL_API = "https://api.eu.mistral.ai"

"""Mistral alleen via het EU-endpoint.

Mistral schreef op 8 oktober 2026 (ticket #37361256) dat api.mistral.ai geen
verwerking binnen de EER garandeert; alleen api.eu.mistral.ai doet dat. Deze
proef valt om zodra het wereldwijde adres ergens in de servercode terugkomt,
ook als het via een nieuw bestand binnensluipt.
"""

import re
from pathlib import Path

from services.cloud_api import llm_service, main, stt_service, tolk
from services.cloud_api.mistral_adres import MISTRAL_API

SERVER = Path(__file__).resolve().parent.parent / "services"
WERELDWIJD = re.compile(r"https?://api\.mistral\.ai")


def test_het_adres_is_het_eu_endpoint():
    assert MISTRAL_API == "https://api.eu.mistral.ai"


def test_spraak_en_voorlezen_gaan_naar_de_eu():
    assert stt_service.VOXTRAL_URL.startswith("https://api.eu.mistral.ai/")
    assert tolk.TTS_URL.startswith("https://api.eu.mistral.ai/")
    assert tolk.STEMMEN_URL.startswith("https://api.eu.mistral.ai/")
    assert llm_service.MISTRAL_API == main.MISTRAL_API == MISTRAL_API


def test_nergens_in_de_server_het_wereldwijde_adres():
    treffers = []
    for pad in SERVER.rglob("*.py"):
        for nr, regel in enumerate(pad.read_text(encoding="utf-8").splitlines(), 1):
            if WERELDWIJD.search(regel):
                treffers.append(f"{pad.relative_to(SERVER)}:{nr}")
    assert treffers == [], f"api.mistral.ai gevonden: {treffers}"

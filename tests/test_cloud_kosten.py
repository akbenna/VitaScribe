"""AI-gebruik en geschatte kosten: tellen, per consult in het verslag, overzicht."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import kosten, main


@pytest.fixture(autouse=True)
def _schoon(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    kosten._geheugen.clear()
    kosten._eigen_cache = {}
    yield
    kosten._geheugen.clear()


def test_per_consult_alleen_wat_erbinnen_gebeurt():
    kosten.tel("anthropic", "claude-haiku-5-5", "tekst", in_tokens=999)   # outside a consult
    with kosten.meten() as teller:
        kosten.tel("anthropic", "claude-haiku-5-5", "tekst", in_tokens=1_000_000, uit_tokens=1_000_000)
        kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=10_000, uit_tokens=1_000)
        kosten.tel("deepgram_live", "", "consult", seconden=600)
    s = kosten.samenvatting(teller)
    # Haiku 5.5: 0.10 + 0.50; Sonnet 5: 0.02 + 0.01; Deepgram live: 10 min x 0.0077.
    assert s["totaal"] == {"USD": round(0.60 + 0.03 + 0.077, 4)}
    assert s["aanroepen"] == 3 and s["onbekend"] == []


def test_dienst_zonder_prijs_geen_gok():
    with kosten.meten() as teller:
        kosten.tel("mistral", "mistral-large-latest", "tekst", in_tokens=5000, uit_tokens=300)
        kosten.tel("anthropic", "claude-haiku-4-5-20251001", "tekst", in_tokens=1_000_000)
    s = kosten.samenvatting(teller)
    assert s["totaal"] == {"USD": 1.0} and s["onbekend"] == ["mistral mistral-large-latest"]
    # With the administrator's price it counts, in that currency.
    tabel = kosten.prijzen({"mistral:mistral-large-latest": {"in": 2.0, "uit": 6.0, "valuta": "EUR"}})
    assert kosten.samenvatting(teller, tabel)["totaal"] == {"USD": 1.0, "EUR": round(0.01 + 0.0018, 4)}


def test_tellen_breekt_nooit_het_werk():
    kosten.tel("anthropic", None, None, in_tokens="geen getal", seconden=None)
    assert sum(r.aanroepen for r in kosten._geheugen.values()) == 1


def test_overzicht_per_dienst_en_per_maand():
    kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=1_000_000, uit_tokens=100_000)
    kosten.tel("gladia", "", "consult", seconden=120)
    o = asyncio.run(kosten.overzicht(30))
    assert o["opslag"] == "geheugen" and o["totaal"] == {"USD": 3.0}
    assert o["per_maand"] == {"USD": 63.0}   # one day of use, x 21 working days
    gladia = [r for r in o["regels"] if r["dienst"] == "gladia"][0]
    assert gladia["kosten"] is None and gladia["minuten"] == 2.0 and "gladia" in o["onbekend"]


def test_consult_verslag_bevat_de_kosten(monkeypatch):
    monkeypatch.setenv("API_KEYS", "sleutel-k")
    from services.cloud_api.config import get_config
    get_config.cache_clear()

    class Verslag:
        def to_dict(self):
            return {"soep": {"s": "keelpijn"}}

    async def verwerk(**_):
        kosten.tel("deepgram", "", "consult", seconden=300)
        kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=7000, uit_tokens=1200)
        return Verslag()
    monkeypatch.setattr(main, "process_consultation", verwerk)
    r = TestClient(main.app).post("/api/v1/consult/process", headers={"X-API-Key": "sleutel-k"},
                                  data={"consent": "true", "stt_provider": "voxtral"},
                                  files={"audio": ("c.webm", b"x" * 100, "audio/webm")})
    assert r.status_code == 200, r.text
    k = r.json()["kosten"]
    assert k["aanroepen"] == 2 and k["totaal"]["USD"] == round(5 * 0.0048 + 0.014 + 0.012, 4)
    get_config.cache_clear()

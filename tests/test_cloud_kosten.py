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
        kosten.tel("mistral", "codestral-latest", "tekst", in_tokens=5000, uit_tokens=300)
        kosten.tel("anthropic", "claude-haiku-4-5-20251001", "tekst", in_tokens=1_000_000)
    s = kosten.samenvatting(teller)
    assert s["totaal"] == {"USD": 1.0} and s["onbekend"] == ["mistral codestral-latest"]
    # With the administrator's price it counts, in that currency.
    tabel = kosten.prijzen({"mistral:codestral-latest": {"in": 2.0, "uit": 6.0, "valuta": "EUR"}})
    assert kosten.samenvatting(teller, tabel)["totaal"] == {"USD": 1.0, "EUR": round(0.01 + 0.0018, 4)}


def test_tellen_breekt_nooit_het_werk():
    kosten.tel("anthropic", None, None, in_tokens="geen getal", seconden=None)
    assert sum(r.aanroepen for r in kosten._geheugen.values()) == 1


def test_overzicht_per_dienst_en_per_maand():
    kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=1_000_000, uit_tokens=100_000)
    kosten.tel("gladia", "", "consult", seconden=120)
    kosten.tel("nieuwe_dienst", "", "consult", seconden=60)
    o = asyncio.run(kosten.overzicht(30))
    # Sonnet 5: 2.00 + 1.00; Gladia at its list price: 2 min x 0.0102.
    assert o["opslag"] == "geheugen" and o["totaal"] == {"USD": round(3.0 + 0.0204, 2)}
    assert o["per_maand"] == {"USD": round((3.0 + 0.0204) * 21, 2)}   # one day of use, x 21 working days
    onbekend = [r for r in o["regels"] if r["dienst"] == "nieuwe_dienst"][0]
    assert onbekend["kosten"] is None and onbekend["minuten"] == 1.0 and o["onbekend"] == ["nieuwe_dienst"]


def test_elke_dienst_van_vitascribe_heeft_een_lijstprijs():
    tabel = kosten.prijzen()
    for dienst, model in [("anthropic", "claude-sonnet-5"), ("anthropic", "claude-haiku-5-5"),
                          ("mistral", "mistral-large-latest"), ("mistral", "mistral-small-latest"),
                          ("deepgram", ""), ("deepgram_live", ""), ("voxtral", ""), ("gladia", ""),
                          ("speechmatics", ""), ("azure_tts", ""), ("mistral_tts", "")]:
        p = tabel[kosten.prijssleutel(dienst, model)]
        assert p.get("bron") and p.get("valuta") == "USD", (dienst, model)


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
    assert k["aanroepen"] == 2 and k["totaal"]["USD"] == round(5 * 0.0043 + 0.014 + 0.012, 4)
    get_config.cache_clear()


def test_verdeling_per_onderdeel_binnen_een_consult():
    with kosten.meten() as teller, kosten.als("verslaglegging"):
        kosten.tel("deepgram_live", "", seconden=240)                                  # speech, by its service
        with kosten.als("meedenken"):
            kosten.tel("anthropic", "claude-haiku-5-5", in_tokens=15_000, uit_tokens=3_000)
        kosten.tel("anthropic", "claude-sonnet-5", in_tokens=9_000, uit_tokens=1_300)  # the report
        with kosten.als("nazorg en afspraken"):
            kosten.tel("anthropic", "claude-haiku-5-5", in_tokens=1_700, uit_tokens=800)
    d = kosten.samenvatting(teller)["per_onderdeel"]
    assert list(d) == ["verslaglegging", "spraakherkenning", "meedenken", "nazorg en afspraken"]   # largest first
    assert d["spraakherkenning"] == {"USD": round(4 * 0.0077, 4)}
    assert d["meedenken"] == {"USD": round(0.0015 + 0.0015, 4)}


def test_onderdeel_volgt_het_verzoek(monkeypatch):
    assert kosten.onderdeel_voor_pad("/api/v1/dossier/vraag") == "dossiervraag"
    assert kosten.onderdeel_voor_pad("/api/v1/letters/generate") == "brieven"
    assert kosten.onderdeel_voor_pad("/api/v1/tolk/beurt") == "tolk"
    assert kosten.onderdeel_voor_pad("/iets/anders") == "overig"
    assert kosten.onderdeel_van("azure_tts") == "voorlezen" and kosten.onderdeel_van("voxtral") == "spraakherkenning"
    # Through the app: a dossier question is counted as "dossiervraag".
    monkeypatch.setenv("API_KEYS", "sleutel-k")
    from services.cloud_api import llm_service
    from services.cloud_api.config import get_config
    get_config.cache_clear()

    async def complete(*a, **k):
        kosten.tel("anthropic", "claude-sonnet-5", in_tokens=100, uit_tokens=10)
        return '{"antwoord": "x", "gevonden": false, "zekerheid": "niet_gevonden", "bronnen": [], "let_op": ""}'
    monkeypatch.setattr(llm_service, "complete", complete)
    r = TestClient(main.app).post("/api/v1/dossier/vraag", headers={"X-API-Key": "sleutel-k"},
                                  json={"vraag": "Laatste HbA1c?", "dossier": "Journaal 01-01-2026 HbA1c 53"})
    assert r.status_code == 200, r.text
    assert [k[3] for k in kosten._geheugen] == ["dossiervraag"]
    o = asyncio.run(kosten.overzicht(7))
    assert o["per_onderdeel"][0]["onderdeel"] == "dossiervraag" and o["per_onderdeel"][0]["aandeel"] == 100.0
    get_config.cache_clear()


def test_een_uur_cache_schrijven_kost_twee_keer_de_invoerprijs():
    with kosten.meten() as teller:
        kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=1_000_000, cache_w=1_000_000,
                   cache_w1h=1_000_000, cache_r=1_000_000)
    # Sonnet 5: invoer 2.00, 5 min schrijven 2.50, 1 uur schrijven 4.00, lezen 0.20.
    assert kosten.samenvatting(teller)["totaal"] == {"USD": round(2.00 + 2.50 + 4.00 + 0.20, 4)}
    for sleutel, p in kosten.STANDAARD_PRIJZEN.items():
        if sleutel.startswith("anthropic:"):
            assert p["cache_w1h"] == pytest.approx(2 * p["in"]), sleutel
            assert p["cache_w"] == pytest.approx(1.25 * p["in"]), sleutel
            assert "1-uurscache" in p["bron"] and "2026-10-10" in p["bron"]


def test_overzicht_toont_een_uur_cache_apart():
    kosten.tel("anthropic", "claude-sonnet-5", "tekst", in_tokens=10, cache_w=5, cache_w1h=3000, cache_r=7)
    uit = asyncio.run(kosten.overzicht(1))
    regel = next(r for r in uit["regels"] if r["model"] == "claude-sonnet-5")
    assert (regel["cache_w"], regel["cache_w1h"], regel["cache_r"]) == (5, 3000, 7)
    rij = next(r for r in asyncio.run(kosten.gebruik(1)) if r["model"] == "claude-sonnet-5")
    assert rij["cache_w1h"] == 3000

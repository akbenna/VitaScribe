"""Brieven (informatiebrief / verwijsbrief) via de VitaScribe-server."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import letters, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


H = {"X-API-Key": "geheim"}
DOSSIER = "PATIËNT: J.J.\n== JOURNAAL ==\nLage rugpijn sinds 3 mnd, fysiotherapie gestart."


def fake_stream(pieces, seen=None):
    async def _stream(provider, system, user, max_tokens, quality=False, api_key=None):
        if seen is not None:
            seen.append({"provider": provider, "system": system, "user": user,
                         "quality": quality, "max_tokens": max_tokens, "api_key": api_key})
        for p in pieces:
            yield p
    return _stream


def test_privacy_safety_net_removes_direct_identifiers():
    t = "BSN 123456789, mail jan@voorbeeld.nl, tel 06-12345678 en 0475 123456, NL91ABNA0417164300"
    out = letters.privacy_safety_net(t)
    for secret in ("123456789", "jan@voorbeeld.nl", "12345678", "123456", "NL91ABNA"):
        assert secret not in out
    # medische getallen blijven staan
    assert letters.privacy_safety_net("RR 140/90, Hb 8.4, 500 mg 3dd") == "RR 140/90, Hb 8.4, 500 mg 3dd"
    # datums in het journaal blijven heel (niet als telefoonnummer gezien)
    for datum in ("Datum uitslag: 22-06-202622-06-2026 HA", "20-10-2025 HA-Cons", "12-06-2026"):
        assert letters.privacy_safety_net(datum) == datum


def test_informatiebrief_requires_consent(api):
    resp = api.post("/api/v1/letters/generate", headers=H,
                    json={"kind": "informatiebrief", "aanvrager": "uwv", "dossier": DOSSIER})
    assert resp.status_code == 400
    assert "toestemming" in resp.json()["detail"]


def test_informatiebrief_streams_and_follows_knmg(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte ", "collega,"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "informatiebrief", "aanvrager": "uwv", "toestemming": True,
            "dossier": DOSSIER + " BSN 123456789", "vraag": "1. Welke diagnose?",
            "initialen": "J.J.",
        })
    assert resp.status_code == 200
    assert resp.text == "Geachte collega,"
    call = seen[0]
    assert call["quality"] is True
    assert "GEEN oordeel" in call["system"] and "UWV" in call["system"]
    assert "123456789" not in call["user"] and "1. Welke diagnose?" in call["user"]


def test_verwijzing_uses_quality_model_and_needs_reason(api):
    resp = api.post("/api/v1/letters/generate", headers=H,
                    json={"kind": "verwijzing", "dossier": DOSSIER, "specialisme": "orthopeed"})
    assert resp.status_code == 400
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte collega,"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "specialisme": "orthopedisch chirurg",
            "urgentie": "regulier", "reden": "Graag beoordeling persisterende rugpijn",
        })
    assert resp.status_code == 200
    # The doctor wants to send it nearly as is: the strong model, the whole dossier read.
    assert seen[0]["quality"] is True and seen[0]["max_tokens"] == 2000
    assert "orthopedisch chirurg" in seen[0]["user"]
    assert "Lees het HELE dossier" in seen[0]["system"] and "geen sterretjes" in seen[0]["system"]


def test_provider_error_before_stream_gives_502(api):
    async def failing(provider, system, user, max_tokens, quality=False, api_key=None):
        raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd.")
        yield ""  # pragma: no cover
    with patch.object(letters.llm_service, "stream_llm", failing):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "reden": "x"})
    assert resp.status_code == 502


def test_extract_reads_image_and_filters(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Journaal\nBSN 123456789 hoofdpijn"], seen)):
        resp = api.post("/api/v1/letters/extract", headers=H,
                        json={"kind": "dossier", "media_type": "image/png", "data": "iVBORw0KGgoAAAANS"})
    assert resp.status_code == 200
    assert "123456789" not in resp.json()["text"] and "hoofdpijn" in resp.json()["text"]
    # screenshots can identify the patient: the patient-data model, in its image format
    assert seen[0]["provider"] == "anthropic"
    assert seen[0]["user"][0]["type"] == "image"


def test_letters_require_api_key(api):
    resp = api.post("/api/v1/letters/generate", json={"kind": "verwijzing", "dossier": DOSSIER, "reden": "x"})
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize("aanvrager,moet", [
    ("ind", ["BMA", "exacte sterkte, dosering en frequentie", "medische noodsituatie"]),
    ("duo", ["DUO", "studievertraging", "Geen oordeel over de invloed op de studie"]),
    ("bedrijfsarts", ["bedrijfsarts", "belastbaarheid"]),
    ("letselschade", ["letselschade", "ongevalsgevolgen"]),
    ("ciz", ["Wet langdurige zorg"]),
    ("cbr", ["rijgeschiktheid"]),
])
def test_aanvragers_krijgen_eigen_instructie(api, aanvrager, moet):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["x"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "informatiebrief", "aanvrager": aanvrager, "toestemming": True, "dossier": DOSSIER})
    assert resp.status_code == 200
    assert all(m in seen[0]["system"] for m in moet), seen[0]["system"][-500:]
    # De KNMG-basis (feiten, geen oordeel) blijft er altijd bij.
    assert "GEEN oordeel" in seen[0]["system"]


def test_onbekende_aanvrager_geweigerd(api):
    resp = api.post("/api/v1/letters/generate", headers=H, json={
        "kind": "informatiebrief", "aanvrager": "belastingdienst", "toestemming": True, "dossier": DOSSIER})
    assert resp.status_code == 422


def test_verklaring_op_verzoek_van_de_patient(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Aan wie het aangaat,"], seen)):
        geweigerd = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verklaring", "doel": "wmo_scootmobiel", "dossier": DOSSIER})
        assert geweigerd.status_code == 400
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verklaring", "doel": "wmo_scootmobiel", "toestemming": True, "dossier": DOSSIER,
            "vraag": "Kan door rugpijn niet meer naar de winkel lopen. BSN 123456789"})
    assert resp.status_code == 200
    call = seen[0]
    assert "KNMG" in call["system"] and "geen \\\noordeel, advies of aanbeveling" not in call["system"]
    assert "geen" in call["system"] and "aanbeveling" in call["system"]
    assert "scootmobiel" in call["user"] and "loopafstand" in call["user"]
    assert "winkel lopen" in call["user"] and "123456789" not in call["user"]


def test_alle_aanvragers_hebben_lezer_en_groet():
    for naam, tekst in letters._AANVRAGER.items():
        assert "Met collegiale groet" in tekst or "Met vriendelijke groet" in tekst, naam


def test_lange_initialen_worden_ingekort_niet_geweigerd(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte collega,"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "specialisme": "vaatchirurg", "reden": "Zwelling",
            "initialen": "M.J.W.T.B.J.K.L.",
        })
    assert resp.status_code == 200, resp.text
    assert "patiënt M.J.W.T.B.J." in seen[0]["user"] and "K.L." not in seen[0]["user"]


# ── Vraagstelling uit de brief van de aanvrager ──

def _complete(antwoord, seen=None):
    async def complete(system, user, provider=None, json_mode=False, max_tokens=None, cache_system=False,
                       quality=False, json_schema=None, model=None):
        if seen is not None:
            seen.append({"system": system, "user": user, "provider": provider, "schema": json_schema})
        return antwoord if isinstance(antwoord, str) else __import__("json").dumps(antwoord)
    return complete


BRIEF_UWV = ("UWV Sociaal Medische Zaken\nPostbus 12345\n\nGeachte collega,\nBetreft: mevrouw J. de Vries, BSN 123456789\n"
             "Ten behoeve van de beoordeling arbeidsongeschiktheid verzoeken wij u:\n"
             "1. Welke diagnose is gesteld?\n2. Welke behandeling is ingezet en met welk resultaat?\n"
             "Een machtiging van betrokkene is bijgevoegd.\nMet vriendelijke groet, dr. P. Jansen, verzekeringsarts")


def test_vraagstelling_haalt_de_vragen_eruit(api):
    seen = []
    antwoord = {"aanvrager": "uwv", "instantie": "UWV, verzekeringsarts", "doel": "beoordeling arbeidsongeschiktheid",
                "vragen": ["1. Welke diagnose is gesteld?", "2. Welke behandeling is ingezet en met welk resultaat?"],
                "onderwerp": "", "periode": "", "toestemming": True, "let_op": ""}
    with patch.object(letters.llm_service, "complete", _complete(antwoord, seen)):
        r = api.post("/api/v1/letters/vraagstelling", headers=H, json={"tekst": BRIEF_UWV})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["aanvrager"] == "uwv" and len(d["vragen"]) == 2 and d["toestemming"] is True
    # The BSN never reaches the model; the requester list comes from the server.
    assert "123456789" not in seen[0]["user"] and '"duo"' in seen[0]["system"]


def test_vraagstelling_onbekende_aanvrager_wordt_overig(api):
    antwoord = {"aanvrager": "notaris", "instantie": "", "doel": "", "vragen": ["Wat is er aan de hand?"],
                "onderwerp": "", "periode": "", "toestemming": "ja", "let_op": ""}
    with patch.object(letters.llm_service, "complete", _complete(antwoord)):
        d = api.post("/api/v1/letters/vraagstelling", headers=H, json={"tekst": BRIEF_UWV}).json()
    assert d["aanvrager"] == "overig" and d["toestemming"] is False


def test_vraagstelling_fout_geeft_502(api):
    with patch.object(letters.llm_service, "complete", _complete("geen json")):
        assert api.post("/api/v1/letters/vraagstelling", headers=H, json={"tekst": BRIEF_UWV}).status_code == 502


# ── Bijsturen ──

def test_bijsturen_herschrijft_met_de_opdracht_en_het_dossier(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte collega,\nKorter."], seen)):
        r = api.post("/api/v1/letters/bijsturen", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "specialisme": "vaatchirurg", "reden": "Zwelling",
            "brief": "Geachte collega,\nEen lange brief over de zwelling.\nMet collegiale groet,",
            "opdracht": "Korter, en noem de furosemide",
        })
    assert r.status_code == 200, r.text
    assert "Korter." in r.text
    call = seen[0]
    assert "BIJSTUREN" in call["system"] and "verzin niets" in call["system"]
    assert "DE BRIEF ZOALS HIJ NU IS" in call["user"] and "OPDRACHT VAN DE HUISARTS: Korter, en noem de furosemide" in call["user"]
    assert "DOSSIER" in call["user"]   # new facts only from the dossier


def test_bijsturen_informatiebrief_vraagt_nog_steeds_toestemming(api):
    r = api.post("/api/v1/letters/bijsturen", headers=H, json={
        "kind": "informatiebrief", "dossier": DOSSIER, "aanvrager": "uwv", "brief": "Geachte collega, tekst.",
        "opdracht": "formeler"})
    assert r.status_code == 400



def test_correspondentie_niet_raden_maar_verwijzen_en_bijlagen(api):
    for kind, extra in (("informatiebrief", {"aanvrager": "uwv", "toestemming": True}),
                        ("verwijzing", {"reden": "x"}), ("verklaring", {"toestemming": True})):
        system = letters.build_letter_prompts(letters.GenerateRequest(kind=kind, dossier=DOSSIER, **extra))[0]
        assert "verwijs ik naar de bijgevoegde" in system and "Bijlagen:" in system and "verzin die inhoud" in system, kind

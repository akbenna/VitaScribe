"""Praktijkregister: licenties, praktijkbinding, beheer, aanmelden en eigen sleutels.

Draait tegen een echte PostgreSQL:
- TEST_DATABASE_URL als die staat (CI), anders
- een tijdelijk cluster met initdb/pg_ctl als die op het systeem staan, anders
- overgeslagen.
"""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
import socket
import subprocess
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import audit, beheer, kluis, licentie, main, praktijk_sleutels, register
from services.cloud_api.config import get_config


def _pg_bin(naam: str):
    gevonden = shutil.which(naam)
    if gevonden:
        return gevonden
    for pad in sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{naam}"), reverse=True):
        return pad
    return None


def _vrije_poort() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


@pytest.fixture(scope="module")
def database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        yield url
        return
    initdb, pg_ctl = _pg_bin("initdb"), _pg_bin("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("Geen PostgreSQL beschikbaar (zet TEST_DATABASE_URL of installeer postgresql).")
    map_ = tempfile.mkdtemp(prefix="vs-pg-")
    data = os.path.join(map_, "data")
    gebruiker = {}
    if os.geteuid() == 0:
        # initdb weigert als root te draaien; gebruik 'nobody' met een eigen map.
        import pwd
        nobody = pwd.getpwnam("nobody")
        os.chown(map_, nobody.pw_uid, nobody.pw_gid)
        gebruiker = {"user": nobody.pw_uid, "group": nobody.pw_gid}
    subprocess.run([initdb, "-D", data, "-U", "vs", "--auth=trust", "-E", "UTF8"], check=True,
                   capture_output=True, **gebruiker)
    poort = _vrije_poort()
    subprocess.run([pg_ctl, "-D", data, "-o", f"-p {poort} -k {map_} -c listen_addresses=127.0.0.1",
                    "-l", os.path.join(map_, "log"), "-w", "start"], check=True, capture_output=True, **gebruiker)
    try:
        subprocess.run([_pg_bin("createdb") or "createdb", "-h", "127.0.0.1", "-p", str(poort), "-U", "vs", "vitascribe"],
                       check=True, capture_output=True)
        yield f"postgresql://vs@127.0.0.1:{poort}/vitascribe"
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "immediate", "stop"], capture_output=True, **gebruiker)
        shutil.rmtree(map_, ignore_errors=True)


BEHEER = {"X-Beheer-Sleutel": "beheer-test"}


@pytest.fixture
def api(database_url, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ADMIN_KEY", "beheer-test")
    monkeypatch.setenv("SLEUTELKLUIS", Fernet.generate_key().decode())
    monkeypatch.setenv("API_USERS", "dr.eigen:omgevingssleutel")
    monkeypatch.setenv("VITASCRIBE_FASE", "extern")   # sign-up is open only in the extern phase
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-server")
    get_config.cache_clear()
    licentie.wis_cache()
    licentie._gezien.clear()
    from services.cloud_api import aanmelden, beheer
    aanmelden._per_adres.clear()
    aanmelden._totaal.clear()
    beheer._mislukt.clear()
    beheer._sessies.clear()
    monkeypatch.delenv("ADMIN_USERS", raising=False)
    monkeypatch.delenv("ADMIN_TOTP", raising=False)
    with TestClient(main.app) as client:
        client.portal.call(register.execute,
                           "TRUNCATE vs_praktijk_sleutels, vs_gebruikers, vs_praktijken, vs_instellingen, vs_beheerlog RESTART IDENTITY CASCADE")
        yield client
        client.portal.call(register.sluit)
    get_config.cache_clear()


def _praktijk(api, **velden):
    body = {"naam": "Praktijk De Linde", "plaats": "Venlo", "praktijknummers": ["2876"]}
    body.update(velden)
    r = api.post("/api/v1/beheer/praktijken", headers=BEHEER, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _gebruiker(api, pid, rol="gebruiker"):
    r = api.post(f"/api/v1/beheer/praktijken/{pid}/gebruikers", headers=BEHEER, json={"naam": "dr. Jansen", "rol": rol})
    assert r.status_code == 200, r.text
    return r.json()


def _activeer(api, pid, **extra):
    body = {"status": "actief", "licentietype": "pilot"}
    body.update(extra)
    r = api.patch(f"/api/v1/beheer/praktijken/{pid}", headers=BEHEER, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── Licenties ──

def test_new_practice_is_not_usable_until_activated(api):
    p = _praktijk(api)
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    r = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel})
    assert r.status_code == 403 and "niet actief" in r.json()["detail"]


def test_pilot_activation_defaults_to_twelve_months(api):
    p = _praktijk(api)
    uit = _activeer(api, p["id"])
    tot = date.fromisoformat(uit["geldig_tot"])
    assert 360 <= (tot - licentie.vandaag()).days <= 370


def test_active_licence_works_and_reports_status(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    r = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel, "X-Bricks-Praktijk": "2876"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["praktijk"] == "Praktijk De Linde" and body["bron"] == "register" and body["licentietype"] == "pilot"


def test_key_is_stored_only_as_hash(api):
    p = _praktijk(api)
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    rij = api.portal.call(register.fetchrow, "SELECT * FROM vs_gebruikers")
    assert rij["sleutel_hash"] == licentie.sleutel_hash(sleutel) and rij["sleutel_hint"] == sleutel[-4:]
    assert all(sleutel not in str(v) for v in dict(rij).values())


def test_practice_binding_blocks_other_practice_but_fails_open(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    anders = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel, "X-Bricks-Praktijk": "4410"})
    assert anders.status_code == 403 and "2876" in anders.json()["detail"] and "4410" in anders.json()["detail"]
    zonder = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel})
    assert zonder.status_code == 200
    rommel = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel, "X-Bricks-Praktijk": "abc,12"})
    assert rommel.status_code == 200   # geen herkenbaar nummer = doorlaten


def test_expired_and_withdrawn_licences_are_refused(api):
    p = _praktijk(api)
    _activeer(api, p["id"], geldig_tot=(licentie.vandaag() - timedelta(days=1)).isoformat())
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    r = api.get("/api/v1/licentie", headers={"X-API-Key": sleutel})
    assert r.status_code == 403 and "verlopen" in r.json()["detail"]
    api.post(f"/api/v1/beheer/praktijken/{p['id']}/verlengen", headers=BEHEER)
    assert api.get("/api/v1/licentie", headers={"X-API-Key": sleutel}).status_code == 200
    api.patch(f"/api/v1/beheer/praktijken/{p['id']}", headers=BEHEER, json={"status": "uitgehaald"})
    assert api.get("/api/v1/licentie", headers={"X-API-Key": sleutel}).status_code == 403


def test_disabled_user_and_rotated_key(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    g = _gebruiker(api, p["id"])
    oud = g["sleutel"]
    nieuw = api.post(f"/api/v1/beheer/gebruikers/{g['gebruiker']['id']}/nieuwe-sleutel", headers=BEHEER).json()["sleutel"]
    assert api.get("/api/v1/licentie", headers={"X-API-Key": oud}).status_code == 403
    assert api.get("/api/v1/licentie", headers={"X-API-Key": nieuw}).status_code == 200
    api.patch(f"/api/v1/beheer/gebruikers/{g['gebruiker']['id']}", headers=BEHEER, json={"actief": False})
    r = api.get("/api/v1/licentie", headers={"X-API-Key": nieuw})
    assert r.status_code == 403 and "uitgezet" in r.json()["detail"]


def test_environment_keys_keep_working_and_dev_mode_is_off(api, monkeypatch):
    assert api.get("/api/v1/licentie", headers={"X-API-Key": "omgevingssleutel"}).json()["bron"] == "omgeving"
    monkeypatch.delenv("API_USERS")
    get_config.cache_clear()
    # Register aan en geen sleutels in de omgeving: zonder sleutel mag er niets.
    assert api.get("/api/v1/licentie").status_code == 401
    assert api.get("/api/v1/licentie", headers={"X-API-Key": "willekeurig"}).status_code == 403


def test_last_seen_is_recorded(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    g = _gebruiker(api, p["id"])
    api.get("/api/v1/licentie", headers={"X-API-Key": g["sleutel"], "X-Bricks-Praktijk": "2876"})
    rij = api.portal.call(register.fetchrow, "SELECT laatst_gezien, laatst_praktijknummer FROM vs_gebruikers")
    assert rij["laatst_gezien"] is not None and rij["laatst_praktijknummer"] == "2876"


# ── Beheer ──

def test_admin_requires_key(api):
    assert api.get("/api/v1/beheer/praktijken").status_code == 403
    assert api.get("/api/v1/beheer/praktijken", headers={"X-Beheer-Sleutel": "fout"}).status_code == 403
    for _ in range(10):
        api.get("/api/v1/beheer/praktijken", headers={"X-Beheer-Sleutel": "fout"})
    assert api.get("/api/v1/beheer/praktijken", headers=BEHEER).status_code == 429


def test_admin_rejects_bad_practice_numbers(api):
    r = api.post("/api/v1/beheer/praktijken", headers=BEHEER, json={"naam": "X", "praktijknummers": ["28a"]})
    assert r.status_code == 400


def test_export_contains_no_secrets(api):
    p = _praktijk(api)
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    tekst = api.get("/api/v1/beheer/export", headers=BEHEER).text
    assert "Praktijk De Linde" in tekst and sleutel not in tekst and "sleutel_hash" not in tekst


def test_admin_pages_are_served_with_strict_headers(api):
    r = api.get("/beheer")
    assert r.status_code == 200 and r.headers["x-frame-options"] == "DENY" and "no-store" in r.headers["cache-control"]
    assert api.get("/beheer/beheer.js").status_code == 200
    assert api.get("/aanmelden").status_code == 200


# ── Aanmelden ──

AANMELDING = {"praktijknaam": "Huisartsen Maasbree", "plaats": "Maasbree", "praktijknummer": "3101",
              "contact_naam": "M. de Vries", "email": "praktijk@example.nl", "fte": 2.5, "werkplekken": 4,
              "akkoord": True}


def test_signup_creates_candidate(api):
    r = api.post("/api/v1/aanmelden", json=AANMELDING)
    assert r.status_code == 200, r.text
    lijst = api.get("/api/v1/beheer/praktijken", headers=BEHEER).json()["praktijken"]
    assert lijst[0]["status"] == "aangemeld" and lijst[0]["licentietype"] == "kandidaat"
    assert lijst[0]["praktijknummers"] == ["3101"] and lijst[0]["fte"] == 2.5


def test_signup_validation_honeypot_and_limit(api):
    assert api.post("/api/v1/aanmelden", json={**AANMELDING, "akkoord": False}).status_code == 400
    assert api.post("/api/v1/aanmelden", json={**AANMELDING, "praktijknummer": "12"}).status_code == 400
    assert api.post("/api/v1/aanmelden", json={**AANMELDING, "email": "geen-adres"}).status_code == 400
    assert api.post("/api/v1/aanmelden", json={**AANMELDING, "website": "http://spam"}).status_code == 200
    assert api.get("/api/v1/beheer/praktijken", headers=BEHEER).json()["praktijken"] == []
    for _ in range(5):
        api.post("/api/v1/aanmelden", json=AANMELDING)
    assert api.post("/api/v1/aanmelden", json=AANMELDING).status_code == 429


# ── Eigen sleutels ──

async def _goedgekeurd(aanbieder, sleutel):
    return None


def test_only_practice_admin_sets_own_keys_and_they_are_encrypted(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    gewoon = _gebruiker(api, p["id"])["sleutel"]
    beheerder = _gebruiker(api, p["id"], rol="praktijkbeheerder")["sleutel"]
    eigen = "sk-ant-" + "a" * 40
    with patch.object(praktijk_sleutels, "CONTROLE", _goedgekeurd):
        r = api.put("/api/v1/praktijk/sleutels/brieven", headers={"X-API-Key": gewoon},
                    json={"aanbieder": "anthropic", "sleutel": eigen})
        assert r.status_code == 403
        r = api.put("/api/v1/praktijk/sleutels/brieven", headers={"X-API-Key": beheerder},
                    json={"aanbieder": "anthropic", "sleutel": eigen})
        assert r.status_code == 200, r.text
        assert r.json()["brieven"]["hint"] == "aaaa"
        # Mistral is voor identificeerbare gegevens en neemt geen praktijksleutel aan.
        assert api.put("/api/v1/praktijk/sleutels/brieven", headers={"X-API-Key": beheerder},
                       json={"aanbieder": "mistral", "sleutel": eigen}).status_code == 400
    rij = api.portal.call(register.fetchrow, "SELECT versleuteld FROM vs_praktijk_sleutels")
    assert eigen not in rij["versleuteld"] and kluis.ontsleutel(rij["versleuteld"]) == eigen
    status = api.get("/api/v1/licentie", headers={"X-API-Key": gewoon}).json()
    assert status["eigen_sleutels"]["brieven"]["aanbieder"] == "anthropic" and eigen not in str(status)


def test_rejected_key_is_not_saved(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    beheerder = _gebruiker(api, p["id"], rol="praktijkbeheerder")["sleutel"]

    async def afgewezen(aanbieder, sleutel):
        return "De aanbieder kent deze sleutel niet of heeft hem ingetrokken."

    with patch.object(praktijk_sleutels, "CONTROLE", afgewezen):
        r = api.put("/api/v1/praktijk/sleutels/spraak", headers={"X-API-Key": beheerder},
                    json={"aanbieder": "deepgram", "sleutel": "d" * 40})
    assert r.status_code == 400
    assert api.portal.call(register.fetch, "SELECT * FROM vs_praktijk_sleutels") == []


def test_letters_use_practice_key_and_dictation_data_never_does(api):
    from services.cloud_api import letters

    p = _praktijk(api)
    _activeer(api, p["id"])
    beheerder = _gebruiker(api, p["id"], rol="praktijkbeheerder")["sleutel"]
    with patch.object(praktijk_sleutels, "CONTROLE", _goedgekeurd):
        api.put("/api/v1/praktijk/sleutels/brieven", headers={"X-API-Key": beheerder},
                json={"aanbieder": "openai", "sleutel": "sk-proj-" + "b" * 40})
    gezien = []

    async def nep(provider, system, user, max_tokens, quality=False, api_key=None):
        gezien.append((provider, api_key))
        yield "Geachte collega,"

    with patch.object(letters.llm_service, "stream_llm", nep):
        r = api.post("/api/v1/letters/generate", headers={"X-API-Key": beheerder},
                     json={"kind": "verwijzing", "dossier": "Journaal: hoofdpijn", "reden": "beoordeling"})
    assert r.status_code == 200, r.text
    assert gezien == [("openai", "sk-proj-" + "b" * 40)]

    # Schermafdrukken kunnen personalia tonen: die gaan naar het patiëntmodel, nooit op de praktijksleutel.
    with patch.object(letters.llm_service, "stream_llm", nep):
        api.post("/api/v1/letters/extract", headers={"X-API-Key": beheerder},
                 json={"kind": "dossier", "media_type": "image/png", "data": "aGFsbG8gd2VyZWxk"})
    assert gezien[-1] == ("anthropic", None)


def test_required_own_keys_block_server_keys(api):
    p = _praktijk(api)
    _activeer(api, p["id"], eigen_sleutels_verplicht=True)
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    r = api.post("/api/v1/letters/generate", headers={"X-API-Key": sleutel},
                 json={"kind": "verwijzing", "dossier": "Journaal: hoofdpijn", "reden": "beoordeling"})
    assert r.status_code == 403 and "eigen AI-sleutel" in r.json()["detail"]


def test_deepgram_key_per_practice(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    ident = api.portal.call(licentie.identificeer, _gebruiker(api, p["id"], rol="praktijkbeheerder")["sleutel"], None)
    assert api.portal.call(praktijk_sleutels.kies_spraak, ident) == "dg-server"
    versleuteld = kluis.versleutel("dg-praktijk-" + "c" * 30)
    api.portal.call(register.execute,
                    "INSERT INTO vs_praktijk_sleutels (praktijk_id, dienst, aanbieder, versleuteld, hint) VALUES ($1,'spraak','deepgram',$2,'cccc')",
                    p["id"], versleuteld)
    assert api.portal.call(praktijk_sleutels.kies_spraak, ident) == "dg-praktijk-" + "c" * 30


def test_dictation_refuses_other_practice(api):
    import json as _json

    p = _praktijk(api)
    _activeer(api, p["id"])
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    with api.websocket_connect("/api/v1/dictation/stream") as ws:
        ws.send_text(_json.dumps({"type": "auth", "api_key": sleutel, "praktijk": ["4410"]}))
        antwoord = _json.loads(ws.receive_text())
    assert antwoord["type"] == "error" and "2876" in antwoord["message"]


def test_database_outage_keeps_recent_keys_working(api):
    p = _praktijk(api)
    _activeer(api, p["id"])
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    assert api.get("/api/v1/licentie", headers={"X-API-Key": sleutel}).status_code == 200

    async def weg(h):
        raise OSError("database weg")

    oud = dict(licentie._cache)
    with patch.object(licentie, "_haal", weg):
        for k, (t, v) in oud.items():
            licentie._cache[k] = (t - 60, v)          # voorbij de gewone cache, binnen de noodcache
        assert api.get("/api/v1/licentie", headers={"X-API-Key": sleutel}).status_code == 200
        r = api.get("/api/v1/licentie", headers={"X-API-Key": "vs_onbekend"})
        assert r.status_code == 503


def test_paid_licence_gets_an_end_date(api):
    p = _praktijk(api)
    uit = _activeer(api, p["id"], licentietype="betaald")
    assert uit["geldig_tot"] is not None
    intern = _activeer(api, _praktijk(api, naam="Het Roosendael")["id"], licentietype="intern")
    assert intern["geldig_tot"] is None


def test_vault_rotation(monkeypatch):
    from cryptography.fernet import Fernet

    oud, nieuw = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("SLEUTELKLUIS", oud)
    blob = kluis.versleutel("geheim-123")
    monkeypatch.setenv("SLEUTELKLUIS", f"{nieuw},{oud}")
    assert kluis.ontsleutel(blob) == "geheim-123"
    monkeypatch.setenv("SLEUTELKLUIS", nieuw)
    assert kluis.ontsleutel(blob) is None


def test_binding_helpers():
    assert licentie.praktijknummers_uit_kop("2876, 12, abc, 2876, 4410") == ["2876", "4410"]
    assert licentie.binding_fout([], ["4410"]) is None
    assert licentie.binding_fout(["2876"], []) is None
    assert licentie.binding_fout(["2876"], ["4410", "2876"]) is None
    assert "2876" in licentie.binding_fout(["2876"], ["4410"])


# ── Auditlog (NEN 7513) in het register ──

def _log_in_register(api, gebruiker, handeling, **detail):
    async def schrijf():
        audit.log_event(gebruiker, handeling, **detail)
        await audit.flush()
    api.portal.call(schrijf)


def test_audit_events_are_stored_without_content(api):
    _log_in_register(api, "dr.audit-a", "letters.generate", kind="verwijzing", tekst="Jan de Vries")
    rij = api.portal.call(register.fetchrow,
                          "SELECT gebruiker, handeling, details FROM vs_auditlog WHERE gebruiker = 'dr.audit-a'")
    assert rij["handeling"] == "letters.generate"
    assert "Vries" not in str(rij["details"]) and "verwijzing" in str(rij["details"])
    r = api.get("/api/v1/beheer/auditlog", headers=BEHEER, params={"gebruiker": "dr.audit-a"})
    assert r.status_code == 200 and r.json()["log"][0]["handeling"] == "letters.generate"


def test_audit_log_is_append_only(api):
    import asyncpg

    _log_in_register(api, "dr.audit-b", "dictation.stream")
    for opdracht in ("UPDATE vs_auditlog SET gebruiker = 'iemand anders' WHERE gebruiker = 'dr.audit-b'",
                     "DELETE FROM vs_auditlog WHERE gebruiker = 'dr.audit-b'",
                     "TRUNCATE vs_auditlog"):
        with pytest.raises(asyncpg.RaiseError):
            api.portal.call(register.execute, opdracht)
    assert api.portal.call(register.fetchrow, "SELECT count(*) AS n FROM vs_auditlog WHERE gebruiker = 'dr.audit-b'")["n"] == 1


def test_audit_retention_is_at_least_a_year(monkeypatch):
    monkeypatch.setenv("AUDIT_BEWAARDAGEN", "30")
    assert audit.retention_days() == 365
    monkeypatch.setenv("AUDIT_BEWAARDAGEN", "3650")
    assert audit.retention_days() == 3650
    monkeypatch.delenv("AUDIT_BEWAARDAGEN")
    assert audit.retention_days() == 1825


# ── Beheerders met tweestapsverificatie ──

GEHEIM = "JBSWY3DPEHPK3PXP"


def test_totp_matches_rfc_6238():
    # RFC 6238, bijlage B: SHA1-geheim "12345678901234567890", T = 59 s -> 94287082 (8 cijfers).
    import base64 as b64
    geheim = b64.b32encode(b"12345678901234567890").decode()
    assert beheer.totp_code(geheim, 59) == "287082"
    assert beheer.totp_klopt(geheim, "287082", 59)
    assert beheer.totp_klopt(geheim, beheer.totp_code(geheim, 59 + 30), 59)   # klok iets voor
    assert not beheer.totp_klopt(geheim, "000000", 59)
    assert not beheer.totp_klopt(geheim, "abc", 59)


def test_admin_with_totp_needs_code_and_gets_a_session(api, monkeypatch):
    monkeypatch.setenv("ADMIN_USERS", "anna:anna-sleutel")
    monkeypatch.setenv("ADMIN_TOTP", f"anna:{GEHEIM}")
    # Rechtstreeks met de sleutel mag niet meer als er een code hoort te komen.
    assert api.get("/api/v1/beheer/praktijken", headers={"X-Beheer-Sleutel": "anna-sleutel"}).status_code == 401
    fout = api.post("/api/v1/beheer/inloggen", json={"sleutel": "anna-sleutel", "code": "000000"})
    assert fout.status_code == 403
    import time
    goed = api.post("/api/v1/beheer/inloggen",
                    json={"sleutel": "anna-sleutel", "code": beheer.totp_code(GEHEIM, time.time())})
    assert goed.status_code == 200 and goed.json()["naam"] == "anna" and goed.json()["tweestaps"]
    sessie = {"X-Beheer-Sessie": goed.json()["sessie"]}
    assert api.get("/api/v1/beheer/praktijken", headers=sessie).status_code == 200
    api.post("/api/v1/beheer/praktijken", headers=sessie, json={"naam": "Praktijk Anna", "plaats": "Venlo"})
    log = api.get("/api/v1/beheer/log", headers=sessie).json()["log"]
    assert log[0]["door"] == "anna"
    api.post("/api/v1/beheer/uitloggen", headers=sessie)
    assert api.get("/api/v1/beheer/praktijken", headers=sessie).status_code == 401


def test_expired_session_is_refused(api, monkeypatch):
    monkeypatch.setenv("BEHEER_SESSIE_UREN", "0.25")
    goed = api.post("/api/v1/beheer/inloggen", json={"sleutel": "beheer-test"})
    sessie = goed.json()["sessie"]
    naam, tot = beheer._sessies[sessie]
    beheer._sessies[sessie] = (naam, tot - 3600)
    assert api.get("/api/v1/beheer/praktijken", headers={"X-Beheer-Sessie": sessie}).status_code == 401


# ── Brieven in de EU ──

def test_practice_can_keep_letters_in_the_eu(api):
    from services.cloud_api import praktijk_sleutels

    p = _praktijk(api)
    _activeer(api, p["id"], brieven_in_eu=True)
    sleutel = _gebruiker(api, p["id"])["sleutel"]
    ident = api.portal.call(licentie.identificeer, sleutel, "2876")
    assert ident.brieven_in_eu
    assert api.portal.call(praktijk_sleutels.kies_brieven, ident) == ("mistral", None)

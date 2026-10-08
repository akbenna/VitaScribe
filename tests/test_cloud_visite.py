"""Visite: telefoon stuurt in, alleen de browser van de praktijk kan het verslag openen."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from services.cloud_api import main, pipeline, visite
from services.cloud_api.config import get_config

API = {"X-API-Key": "geheim"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("VISITE", "true")
    monkeypatch.setenv("TEMP_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(visite, "_geheugen", visite._Geheugen())
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _sleutelpaar():
    prive = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    spki = prive.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return prive, base64.b64encode(spki).decode()


def _open(envelop, kid, prive):
    """What the side panel does with WebCrypto: unwrap the AES key, decrypt."""
    oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    sleutel = prive.decrypt(base64.b64decode(envelop["sleutels"][kid]), oaep)
    data = AESGCM(sleutel).decrypt(base64.b64decode(envelop["iv"]), base64.b64decode(envelop["data"]), None)
    return json.loads(data)


class _Uitslag:
    def to_dict(self):
        return {"soep": {"s": "Wond onderbeen li, sinds 2 weken.", "o": "", "e": "", "p": "Wondcontrole POH"},
                "transcript": "Spreker 1: hoe gaat het met de wond?"}


def _koppel(api, monkeypatch, gezien=None):
    prive, spki = _sleutelpaar()
    assert api.post("/api/v1/visite/ontvanger", json={"kid": "pc-praktijk-1", "spki": spki}, headers=API).status_code == 200
    d = api.post("/api/v1/visite/koppel", json={"naam": "Dr. A"}, headers=API).json()
    assert d["pad"].startswith("/v#")
    token = d["pad"][3:]

    async def nep(audio_path, taal=None, **kw):
        if gezien is not None:
            gezien.update(bestaat=audio_path.exists(), taal=taal, modus=visite.data_policy.modus())
        return _Uitslag()
    monkeypatch.setattr(pipeline, "process_consultation", nep)
    return prive, token


def test_visit_end_to_end_only_the_browser_can_read(monkeypatch, tmp_path):
    api = TestClient(main.app)
    gezien = {}
    prive, token = _koppel(api, monkeypatch, gezien)
    tel = {"X-VitaScribe-Visite": token}
    assert api.post("/api/v1/visite/hallo", headers=tel).json() == {"modus": "eu", "naam": "Dr. A"}   # paired without a chosen mode: eu (the default since the eu-default change)

    r = api.post("/api/v1/visite/opname", headers=tel,
                 files={"audio": ("visite.webm", b"\x1aE\xdf\xa3" + b"0" * 4000, "audio/webm")},
                 data={"toestemming": "true", "aanduiding": "mw. J., wond"})
    assert r.status_code == 200 and r.json()["status"] == "verwerken"
    assert gezien["bestaat"] is True
    assert list(tmp_path.iterdir()) == []                      # the recording is gone

    lijst = api.get("/api/v1/visite/postbus", headers=API).json()["visites"]
    assert len(lijst) == 1 and lijst[0]["status"] == "klaar"
    # nothing readable on the server: the label is encrypted too
    opslag = json.dumps(visite._geheugen.post)
    assert "mw. J." not in opslag and "Wond onderbeen" not in opslag
    assert _open(lijst[0]["kop"], "pc-praktijk-1", prive)["aanduiding"] == "mw. J., wond"

    env = api.get(f"/api/v1/visite/postbus/{lijst[0]['id']}", headers=API).json()["envelop"]
    assert _open(env, "pc-praktijk-1", prive)["soep"]["s"].startswith("Wond onderbeen")
    assert api.delete(f"/api/v1/visite/postbus/{lijst[0]['id']}", headers=API).json() == {"ok": True}
    assert api.get("/api/v1/visite/postbus", headers=API).json()["visites"] == []


def test_phone_key_is_write_only(monkeypatch):
    api = TestClient(main.app)
    _, token = _koppel(api, monkeypatch)
    tel = {"X-VitaScribe-Visite": token}
    assert api.get("/api/v1/visite/postbus", headers=tel).status_code in (401, 403)
    assert api.post("/api/v1/visite/koppel", json={}, headers=tel).status_code in (401, 403)
    assert api.post("/api/v1/visite/hallo", headers={"X-VitaScribe-Visite": "verzonnen"}).status_code == 401
    # unpairing in the panel: the phone can no longer send
    assert api.delete("/api/v1/visite/koppel", headers=API).json()["ontkoppeld"] == 1
    assert api.post("/api/v1/visite/hallo", headers=tel).status_code == 401


def test_consent_size_and_flag(monkeypatch):
    api = TestClient(main.app)
    _, token = _koppel(api, monkeypatch)
    tel = {"X-VitaScribe-Visite": token}
    audio = {"audio": ("v.webm", b"0" * 4000, "audio/webm")}
    r = api.post("/api/v1/visite/opname", headers=tel, files=audio, data={"toestemming": "false"})
    assert r.status_code == 400 and "Toestemming" in r.json()["detail"]
    r = api.post("/api/v1/visite/opname", headers=tel, files={"audio": ("v.webm", b"0" * 10, "audio/webm")},
                 data={"toestemming": "true"})
    assert r.status_code == 400
    monkeypatch.setenv("VISITE", "false")
    assert api.post("/api/v1/visite/hallo", headers=tel).status_code == 404
    assert api.get("/api/v1/visite/postbus", headers=API).status_code == 404


def test_report_failure_and_expiry(monkeypatch):
    api = TestClient(main.app)
    _, token = _koppel(api, monkeypatch)

    async def kapot(audio_path, taal=None, **kw):
        raise RuntimeError("stt down")
    monkeypatch.setattr(pipeline, "process_consultation", kapot)
    api.post("/api/v1/visite/opname", headers={"X-VitaScribe-Visite": token},
             files={"audio": ("v.webm", b"0" * 4000, "audio/webm")}, data={"toestemming": "true"})
    [v] = api.get("/api/v1/visite/postbus", headers=API).json()["visites"]
    assert v["status"] == "fout" and "Dicteer" in v["fout"]
    assert api.get(f"/api/v1/visite/postbus/{v['id']}", headers=API).status_code == 409
    # after 48 hours it is gone
    for r in visite._geheugen.post.values():
        r["verloopt"] = 0
    assert api.get("/api/v1/visite/postbus", headers=API).json()["visites"] == []
    assert visite._geheugen.post == {}


def test_eu_mode_of_the_pairing_is_kept(monkeypatch):
    api = TestClient(main.app)
    gezien = {}
    prive, spki = _sleutelpaar()
    eu = dict(API, **{"X-VitaScribe-Modus": "eu"})
    api.post("/api/v1/visite/ontvanger", json={"kid": "pc-praktijk-1", "spki": spki}, headers=eu)
    token = api.post("/api/v1/visite/koppel", json={}, headers=eu).json()["pad"][3:]

    async def nep(audio_path, taal=None, **kw):
        gezien["modus"] = visite.data_policy.modus()
        return _Uitslag()
    monkeypatch.setattr(pipeline, "process_consultation", nep)
    api.post("/api/v1/visite/opname", headers={"X-VitaScribe-Visite": token},
             files={"audio": ("v.webm", b"0" * 4000, "audio/webm")}, data={"toestemming": "true"})
    assert gezien["modus"] == "eu"
    monkeypatch.setenv("TOEGESTANE_MODI", "claude")
    r = api.post("/api/v1/visite/opname", headers={"X-VitaScribe-Visite": token},
                 files={"audio": ("v.webm", b"0" * 4000, "audio/webm")}, data={"toestemming": "true"})
    assert r.status_code == 403


def test_bad_public_key_and_no_receiver(monkeypatch):
    api = TestClient(main.app)
    r = api.post("/api/v1/visite/ontvanger", json={"kid": "pc-praktijk-1", "spki": "A" * 300}, headers=API)
    assert r.status_code == 400
    assert api.post("/api/v1/visite/koppel", json={}, headers=API).status_code == 409


def test_phone_page_is_served_without_the_key():
    api = TestClient(main.app)
    r = api.get("/v")
    assert r.status_code == 200 and "VitaScribe visite" in r.text and r.headers["cache-control"] == "no-store"
    assert "X-VitaScribe-Visite" in api.get("/v/visite.js").text


def test_python_envelope_opens_with_webcrypto_in_the_browser_code():
    """The server's envelope, opened by chrome-extension/lib/visite.js (WebCrypto in Node)."""
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("node niet aanwezig")
    root = Path(__file__).resolve().parents[1]
    script = """
const { webcrypto } = require('node:crypto'); globalThis.crypto = globalThis.crypto || webcrypto;
const V = require(process.argv[1]);
(async () => {
  const p = await V.nieuwSleutelpaar();
  process.stdout.write(JSON.stringify({ kid: p.kid, spki: p.spki }) + '\\n');
  const env = await new Promise((r) => { let d = ''; process.stdin.on('data', (c) => { d += c; }); process.stdin.on('end', () => r(d)); });
  process.stdout.write((await V.open(JSON.parse(env), p)).soep.s);
})();
"""
    proc = subprocess.Popen([node, "-e", script, str(root / "chrome-extension" / "lib" / "visite.js")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    ontvanger = json.loads(proc.stdout.readline())
    envelop = visite.versleutel({"soep": {"s": "Ulcus cruris li, 2 wk"}}, [ontvanger])
    uit, _ = proc.communicate(json.dumps(envelop), timeout=30)
    assert uit == "Ulcus cruris li, 2 wk"


# ── Deel 2: later versturen, nadicteren, foto's ──

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_photos_after_dictation_and_late_sending(monkeypatch):
    api = TestClient(main.app)
    gezien = {}
    prive, spki = _sleutelpaar()
    api.post("/api/v1/visite/ontvanger", json={"kid": "pc-praktijk-1", "spki": spki}, headers=API)
    token = api.post("/api/v1/visite/koppel", json={}, headers=API).json()["pad"][3:]

    async def nep(audio_path, taal=None, nadictaat_vanaf=None, **kw):
        gezien["nadictaat"] = nadictaat_vanaf
        return _Uitslag()
    monkeypatch.setattr(pipeline, "process_consultation", nep)
    import time as _t
    toen = _t.time() - 3 * 3600                      # recorded three hours ago, no signal at the visit
    r = api.post("/api/v1/visite/opname", headers={"X-VitaScribe-Visite": token},
                 files=[("audio", ("v.webm", b"0" * 4000, "audio/webm")),
                        ("fotos", ("wond.png", PNG, "image/png")), ("fotos", ("lijst.jpg", b"\xff\xd8\xff" + b"1" * 500, "image/jpeg"))],
                 data={"toestemming": "true", "aanduiding": "mw. J.", "nadictaat_vanaf": "312.5", "opgenomen": str(toen)})
    assert r.status_code == 200, r.text
    assert gezien["nadictaat"] == 312.5
    [v] = api.get("/api/v1/visite/postbus", headers=API).json()["visites"]
    assert abs(v["gemaakt"] - toen) < 2 and abs(v["verloopt"] - (toen + visite.BEWAAR)) < 2
    assert _open(v["kop"], "pc-praktijk-1", prive)["fotos"] == 2
    env = api.get(f"/api/v1/visite/postbus/{v['id']}", headers=API).json()["envelop"]
    fotos = _open(env, "pc-praktijk-1", prive)["fotos"]
    assert [f["media_type"] for f in fotos] == ["image/png", "image/jpeg"]
    assert base64.b64decode(fotos[0]["data"]) == PNG
    assert "wond" not in json.dumps(visite._geheugen.post)          # photos only inside the envelope


def test_photo_limits(monkeypatch):
    api = TestClient(main.app)
    _, token = _koppel(api, monkeypatch)
    tel = {"X-VitaScribe-Visite": token}
    audio = ("audio", ("v.webm", b"0" * 4000, "audio/webm"))
    te_veel = [audio] + [("fotos", (f"f{i}.png", PNG, "image/png")) for i in range(visite.MAX_FOTOS + 1)]
    assert api.post("/api/v1/visite/opname", headers=tel, files=te_veel, data={"toestemming": "true"}).status_code == 400
    raar = [audio, ("fotos", ("x.exe", b"MZ" * 100, "application/octet-stream"))]
    assert api.post("/api/v1/visite/opname", headers=tel, files=raar, data={"toestemming": "true"}).status_code == 400
    # a time far in the past or in the future is kept within the 48 hours
    import time as _t
    r = api.post("/api/v1/visite/opname", headers=tel, files=[audio],
                 data={"toestemming": "true", "opgenomen": str(_t.time() + 99999)})
    assert r.status_code == 200
    [v] = api.get("/api/v1/visite/postbus", headers=API).json()["visites"]
    assert v["gemaakt"] <= _t.time() + 1


# ── Visiteronde: klaarzetten in de praktijk, versleuteld voor de telefoon ──

def test_round_encrypted_for_the_phone_and_plek_back_in_the_header(monkeypatch):
    api = TestClient(main.app)
    prive_pc, token = _koppel(api, monkeypatch)
    tel = {"X-VitaScribe-Visite": token}
    prive_tel, spki_tel = _sleutelpaar()
    assert api.post("/api/v1/visite/toestel-sleutel", headers=tel, json={"kid": "telefoon-123", "spki": spki_tel}).status_code == 200
    assert api.post("/api/v1/visite/toestel-sleutel", headers=tel, json={"kid": "telefoon-123", "spki": "A" * 300}).status_code == 400
    [t] = api.get("/api/v1/visite/toestellen", headers=API).json()["toestellen"]
    assert t["kid"] == "telefoon-123"
    # the panel encrypts the round for the phone (here: the same envelope format, made in Python)
    ronde = {"plekken": [{"plek": "plek-aaa111", "aanduiding": "1 · mw. J. · wond"},
                         {"plek": "plek-bbb222", "aanduiding": "2 · dhr. K. · COPD"}]}
    env = visite.versleutel(ronde, [t])
    assert api.post("/api/v1/visite/ronde", headers=API, json={"envelop": env}).json() == {"ok": True}
    assert "mw. J." not in json.dumps(visite._geheugen.rondes)           # unreadable on the server
    terug = api.get("/api/v1/visite/ronde", headers=tel).json()["envelop"]
    assert _open(terug, "telefoon-123", prive_tel)["plekken"][1]["aanduiding"] == "2 · dhr. K. · COPD"
    # the phone sends the place along; the panel finds it in the encrypted header
    api.post("/api/v1/visite/opname", headers=tel, files={"audio": ("v.webm", b"0" * 4000, "audio/webm")},
             data={"toestemming": "true", "aanduiding": "1 · mw. J. · wond", "plek": "plek-aaa111"})
    [v] = api.get("/api/v1/visite/postbus", headers=API).json()["visites"]
    assert _open(v["kop"], "pc-praktijk-1", prive_pc)["plek"] == "plek-aaa111"
    # rights: the phone cannot set a round, the panel cannot read the phone's round endpoint without a phone key
    assert api.post("/api/v1/visite/ronde", headers=tel, json={"envelop": env}).status_code in (401, 403)
    assert api.get("/api/v1/visite/ronde", headers=API).status_code == 401
    assert api.post("/api/v1/visite/ronde", headers=API, json={"envelop": {"v": 2}}).status_code == 400
    # removing the round, and a day later it is gone by itself
    assert api.delete("/api/v1/visite/ronde", headers=API).json() == {"ok": True}
    assert api.get("/api/v1/visite/ronde", headers=tel).json() == {"envelop": None}
    api.post("/api/v1/visite/ronde", headers=API, json={"envelop": env})
    for r in visite._geheugen.rondes.values():
        r["verloopt"] = 0
    assert api.get("/api/v1/visite/ronde", headers=tel).json() == {"envelop": None}
    bad = api.post("/api/v1/visite/opname", headers=tel, files={"audio": ("v.webm", b"0" * 4000, "audio/webm")},
                   data={"toestemming": "true", "plek": "x y"})
    assert bad.status_code == 422

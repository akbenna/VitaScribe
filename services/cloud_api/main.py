"""
VitaScribe Cloud API - Main Application

Lightweight FastAPI service for the Chrome extension.
Processes consultation audio -> SOEP + decisief regel.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
import structlog
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .auth import huidige_identiteit, verify_api_key
from .config import get_config
from .dictation import relay_dictation
from .consult_live import volg_consult
from .letters import router as letters_router
from .dossiervraag import router as dossiervraag_router
from .meedenken import router as meedenken_router
from .post import router as post_router
from .patient_info import router as patient_router
from .usage import router as usage_router
from .praktijk_sleutels import kies_spraak, router as licentie_router
from .beheer import router as beheer_router
from .aanmelden import router as aanmelden_router
from . import register
from . import audit, data_policy, llm_service
from .medical_vocabulary import (
    add_custom_correction,
    correct_transcript_full,
    get_hotwords,
    load_custom_vocabulary,
    save_custom_vocabulary,
)
from .pipeline import _parse_json_response, process_consultation, soep_met_problemen
from .prompts import (
    DICTAAT_OPSCHONEN_SYSTEM_PROMPT,
    DICTAAT_OPSCHONEN_USER_TEMPLATE,
    DICTAAT_SOEP_SYSTEM_PROMPT,
    DICTAAT_SOEP_USER_TEMPLATE,
    SOEP_JSON_SCHEMA,
    DICTAAT_SOEP_JSON_SCHEMA,
)

logger = structlog.get_logger()


@asynccontextmanager
async def _levensloop(_app):
    # Het register (als DATABASE_URL staat) meteen verbinden, zodat een
    # verkeerde database bij het opstarten opvalt en niet bij de eerste arts.
    if register.actief():
        try:
            await register.pool()
        except Exception as exc:
            logger.error("register.verbinden_mislukt", error=str(exc))
    yield
    await audit.flush()
    await register.sluit()


app = FastAPI(
    title="VitaScribe Cloud API",
    description="Consult audio → SOEP + decisief regel voor Bricks Huisarts",
    version="1.0.0",
    lifespan=_levensloop,
)

# ── CORS ──

config = get_config()

# Chrome-extension:// origins are NOT matched by allow_origins=["*"].
# Use allow_origin_regex to match everything including chrome-extension://.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Permissions-Policy header ──
# Allow microphone access for pages served from this API (e.g. /debug).
# This tells browsers that microphone usage is explicitly permitted.

@app.middleware("http")
async def add_permissions_policy(request: Request, call_next):
    response = await call_next(request)
    response.headers["Permissions-Policy"] = "microphone=*"
    return response


# ── Ensure temp directory exists ──

os.makedirs(config.temp_dir, exist_ok=True)

# ── Load custom vocabulary if available ──

_custom_vocab_path = Path(config.temp_dir) / "custom_vocabulary.json"
if _custom_vocab_path.exists():
    load_custom_vocabulary(_custom_vocab_path)


# ── Health check (no auth required) ──

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "vitascribe-cloud-api",
        "version": "1.0.0",
        "stt_provider": config.stt.default_provider,
        "llm_provider": config.llm.default_provider,
        "data_policy": data_policy.summary(),
        "register": register.actief(),
    }


@app.get("/extension/update.xml")
async def extension_update_manifest():
    """Update manifest for Edge/Chrome ExtensionInstallForcelist (self-hosted).
    Serves EXTENSION_DIST_DIR/update.xml written by scripts/pack_extension.sh."""
    dist = os.getenv("EXTENSION_DIST_DIR", "")
    path = os.path.join(dist, "update.xml") if dist else ""
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Geen extensiepakket gepubliceerd.")
    with open(path, encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/xml")


# The package was called smartvoice.crx before the rename to VitaScribe. Every
# workstation that was installed earlier holds an update.xml whose codebase
# points at the old path, and it keeps asking there until a new update.xml has
# been packed and published. Both paths therefore serve the same package, and
# either file name on disk is accepted, so the rename never strands a practice
# on an old version. The old path can go once every update.xml in use is new.
_CRX_NAMES = ("vitascribe.crx", "smartvoice.crx")


@app.get("/extension/vitascribe.crx")
@app.get("/extension/smartvoice.crx")
async def extension_package():
    dist = os.getenv("EXTENSION_DIST_DIR", "")
    path = next((os.path.join(dist, n) for n in _CRX_NAMES
                 if dist and os.path.isfile(os.path.join(dist, n))), "")
    if not path:
        raise HTTPException(status_code=404, detail="Geen extensiepakket gepubliceerd.")
    with open(path, "rb") as f:
        return Response(content=f.read(), media_type="application/x-chrome-extension")


def _bedrock_status(cfg) -> str:
    """Route A (Claude in Bedrock, EU) ready to use? Checks the settings only:
    the Bedrock endpoint has no model list to call for free."""
    if not (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")):
        return "geen sleutel"
    probleem = llm_service.bedrock_eu_problem(
        cfg.llm.bedrock_region, cfg.llm.bedrock_model, cfg.llm.bedrock_soep_model)
    return f"niet EU: {probleem}" if probleem else "ok"


@app.get("/health/deep")
async def health_deep(token: str = ""):
    """Checks the services dictation and letters depend on, without sending
    any patient data or using model tokens: opens (and closes) a Deepgram EU
    connection and lists the models of the language-model providers.
    For an uptime monitor; set HEALTH_TOKEN and call /health/deep?token=..."""
    expected = os.getenv("HEALTH_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Ongeldig token.")
    from .dictation import build_deepgram_url, _default_connect
    cfg = get_config()
    checks = {}

    async def check_deepgram():
        if not cfg.stt.deepgram_api_key:
            return "geen sleutel"
        ws = await _default_connect(build_deepgram_url(cfg), cfg.stt.deepgram_api_key)
        try:
            await ws.send('{"type": "CloseStream"}')
        finally:
            await ws.close()
        return "ok"

    async def check_http(url, headers):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
        return "ok" if r.status_code == 200 else f"fout {r.status_code}"

    async def run(name, coro):
        try:
            checks[name] = await coro
        except Exception as exc:  # report, never raise
            checks[name] = f"fout: {str(exc)[:80]}"

    await run("deepgram_eu", check_deepgram())
    if cfg.llm.mistral_api_key:
        await run("mistral", check_http("https://api.mistral.ai/v1/models",
                                        {"Authorization": f"Bearer {cfg.llm.mistral_api_key}"}))
    else:
        checks["mistral"] = "geen sleutel"
    if cfg.llm.anthropic_api_key:
        await run("anthropic", check_http("https://api.anthropic.com/v1/models",
                                          {"x-api-key": cfg.llm.anthropic_api_key,
                                           "anthropic-version": "2023-06-01"}))
    else:
        checks["anthropic"] = "geen sleutel"
    checks["bedrock"] = _bedrock_status(cfg)

    async def check_register():
        await register.fetchrow("SELECT 1")
        return "ok"

    if register.actief():
        await run("register", check_register())

    needed = ["deepgram_eu", data_policy.phi_llm_provider(), data_policy.letters_llm_provider()]
    if register.actief():
        needed.append("register")
    ok = all(checks.get(n) == "ok" for n in needed)
    return JSONResponse(status_code=200 if ok else 503,
                        content={"status": "ok" if ok else "storing", "checks": checks})


# ── Main processing endpoint ──

@app.post("/api/v1/consult/process")
async def process_consult(
    audio: UploadFile = File(..., description="Audio bestand (webm, mp3, wav, m4a)"),
    stt_provider: str = Form(default=None, description="STT provider override"),
    llm_provider: str = Form(default=None, description="LLM provider override"),
    consent: bool = Form(default=False, description="Patiënt gaf toestemming voor opname"),
    nadictaat_vanaf: Optional[float] = Form(default=None, description="Seconde waarop het nadictaat van de arts begint"),
    taal: Optional[str] = Form(default=None, description="Taal van het gesprek (nl, multi, en, tr, pl, uk)"),
    ident=Depends(huidige_identiteit),
):
    """Process a consultation audio recording through the full pipeline."""
    start_time = time.time()
    user = ident.label
    # KNMG (2026): recording a consultation requires the patient's consent.
    if os.getenv("REQUIRE_RECORDING_CONSENT", "true").lower() == "true" and not consent:
        audit.log_event(user, "consult.refused", status="geen_toestemming")
        raise HTTPException(
            status_code=400,
            detail="Toestemming van de patiënt voor de opname is niet bevestigd. Werk de extensie bij.",
        )
    audit.log_event(user, "consult.process", consent=True)

    # Validate file size
    max_size = config.max_audio_size_mb * 1024 * 1024
    content = await audio.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"Bestand te groot. Maximum is {config.max_audio_size_mb}MB.",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Leeg audiobestand.")

    # Determine file extension
    ext = "webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lstrip(".") or ext
    elif audio.content_type:
        content_type_map = {
            "audio/webm": "webm",
            "audio/mp3": "mp3",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
            "audio/mp4": "m4a",
            "audio/ogg": "ogg",
        }
        ext = content_type_map.get(audio.content_type, ext)

    # Save to temp file
    with tempfile.NamedTemporaryFile(
        dir=config.temp_dir, suffix=f".{ext}", delete=False,
    ) as tmp:
        tmp.write(content)
        audio_path = Path(tmp.name)

    try:
        logger.info(
            "consult.process.start",
            file_size=len(content),
            file_size_kb=round(len(content) / 1024, 1),
            file_ext=ext,
            content_type=audio.content_type,
            filename=audio.filename,
        )

        result = await process_consultation(
            audio_path=audio_path,
            stt_provider=stt_provider,
            llm_provider=llm_provider,
            deepgram_key=await kies_spraak(ident),
            nadictaat_vanaf=nadictaat_vanaf,
            taal=taal,
        )

        processing_time = time.time() - start_time
        logger.info(
            "consult.process.complete",
            processing_time_s=round(processing_time, 2),
        )

        response = result.to_dict()
        response["processing_time_secs"] = round(processing_time, 2)
        return response

    finally:
        # Always clean up temp file (privacy: no audio retention)
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.websocket("/api/v1/consult/stream")
async def consult_stream(ws: WebSocket):
    """Live consult: het gesprek wordt gevolgd, na stop komt het verslag."""
    await volg_consult(ws)


# ── Live dictation (side panel) ──

# Output-budgetten: een dictaat is kort, dus ruim genoeg maar begrensd.
DICTAAT_OPSCHONEN_MAX_TOKENS = 1200
DICTAAT_SOEP_MAX_TOKENS = 1600   # room for several SOEP parts
DICTAAT_MAX_CHARS = 20000


app.include_router(letters_router)
app.include_router(dossiervraag_router)
app.include_router(meedenken_router)
app.include_router(post_router)
app.include_router(patient_router)
app.include_router(usage_router)
app.include_router(licentie_router)
app.include_router(beheer_router)
app.include_router(aanmelden_router)


@app.get("/vitascribe-logo.svg", include_in_schema=False)
async def _logo():
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "static" / "logo.svg", media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.websocket("/api/v1/dictation/stream")
async def dictation_stream(ws: WebSocket):
    """Live dictation: audio in, transcript text out while speaking."""
    await relay_dictation(ws)


class DictationProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=DICTAAT_MAX_CHARS)
    mode: Literal["clean", "soep"]
    llm_provider: Optional[str] = None


@app.post("/api/v1/dictation/process")
async def process_dictation(
    body: DictationProcessRequest,
    user: str = Depends(verify_api_key),
):
    """Dictaat licht opschonen (clean) of omzetten naar een SOEP-regel (soep)."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Leeg dictaat.")
    audit.log_event(user, "dictation.process", mode=body.mode, chars=len(text),
                    provider=data_policy.phi_llm_provider())

    start_time = time.time()
    try:
        if body.mode == "clean":
            cleaned = await llm_service.complete(
                system_prompt=DICTAAT_OPSCHONEN_SYSTEM_PROMPT,
                user_prompt=DICTAAT_OPSCHONEN_USER_TEMPLATE.format(dictaat=text),
                provider=data_policy.phi_llm_provider(body.llm_provider),
                max_tokens=DICTAAT_OPSCHONEN_MAX_TOKENS,
            )
            result = {"mode": "clean", "text": cleaned.strip()}
        else:
            raw = await llm_service.complete(
                system_prompt=DICTAAT_SOEP_SYSTEM_PROMPT,
                user_prompt=DICTAAT_SOEP_USER_TEMPLATE.format(dictaat=text),
                provider=data_policy.phi_llm_provider(body.llm_provider),
                json_mode=True,
                max_tokens=DICTAAT_SOEP_MAX_TOKENS,
                quality=True,
                json_schema=DICTAAT_SOEP_JSON_SCHEMA,
            )
            data = _parse_json_response(raw)
            soep = soep_met_problemen(data)
            points = data.get("aandachtspunten")
            soep["aandachtspunten"] = [
                str(x).strip() for x in points if str(x or "").strip()
            ][:4] if isinstance(points, list) else []
            result = {"mode": "soep", "soep": soep}
    except (ValueError, httpx.HTTPError) as exc:
        # Missing provider key, provider error or unparseable model output.
        logger.error("dictation.process_error", mode=body.mode, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Verwerking mislukt: {exc}")

    result["processing_time_secs"] = round(time.time() - start_time, 2)
    return result


# ── Provider info endpoint ──

@app.get("/api/v1/providers")
async def list_providers(_api_key: str = Depends(verify_api_key)):
    """List available STT and LLM providers."""
    cfg = get_config()
    return {
        "stt": {
            "default": cfg.stt.default_provider,
            "available": {
                "groq": bool(cfg.stt.groq_api_key),
                "deepgram": bool(cfg.stt.deepgram_api_key),
                "openai": bool(cfg.stt.openai_api_key),
            },
        },
        "llm": {
            "default": cfg.llm.default_provider,
            "available": {
                "mistral": bool(cfg.llm.mistral_api_key),
                "anthropic": bool(cfg.llm.anthropic_api_key),
                "bedrock": _bedrock_status(cfg) == "ok",
                "gemini": bool(cfg.llm.gemini_api_key),
            },
        },
    }


# ── Vocabulary management endpoints ──


@app.get("/api/v1/vocabulary/hotwords")
async def get_vocabulary_hotwords(_api_key: str = Depends(verify_api_key)):
    """Geeft de hotwords-string voor VibeVoice-ASR (toekomstig)."""
    return {"hotwords": get_hotwords()}


@app.post("/api/v1/vocabulary/correction")
async def add_vocabulary_correction(
    wrong: str = Form(..., description="Verkeerde transcriptie"),
    correct: str = Form(..., description="Correcte spelling"),
    _api_key: str = Depends(verify_api_key),
):
    """
    Voeg een correctie toe aan de custom woordenlijst.
    Onderdeel van de feedbackloop: arts corrigeert -> systeem leert.
    """
    add_custom_correction(wrong, correct)

    # Persist naar disk
    custom_path = Path(get_config().temp_dir) / "custom_vocabulary.json"
    save_custom_vocabulary(custom_path)

    return {
        "status": "ok",
        "wrong": wrong,
        "correct": correct,
        "message": f"Correctie toegevoegd: '{wrong}' → '{correct}'",
    }


@app.post("/api/v1/vocabulary/test")
async def test_vocabulary_correction(
    text: str = Form(..., description="Tekst om te corrigeren"),
    _api_key: str = Depends(verify_api_key),
):
    """Test de woordenlijstcorrectie op een stuk tekst."""
    corrected, stats = correct_transcript_full(text)
    return {
        "original": text,
        "corrected": corrected,
        "total_corrections": stats.total_corrections,
        "corrections": [
            {"from": wrong, "to": correct}
            for wrong, correct in stats.corrections_applied
        ],
    }


# ── Debug test page ──

@app.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """Serve the debug test page."""
    debug_html = Path(__file__).parent / "debug_test.html"
    if debug_html.exists():
        return debug_html.read_text(encoding="utf-8")
    return "<h1>debug_test.html niet gevonden</h1>"


# ── Entry point ──

def main():
    cfg = get_config()
    uvicorn.run(
        "services.cloud_api.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
    )


if __name__ == "__main__":
    main()

"""
AI-Consultassistent - API Gateway
==================================
FastAPI applicatie die alle services orkestreert.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import asyncio

import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

# Lokale imports - sys.path nodig voor dev; in Docker werkt PYTHONPATH=/app
import sys
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.config.settings import config
from shared.database import get_db, init_db, close_db, async_session
from shared.models.consult import Consult, ConsultStatus
from shared.models.transcript import Transcript
from shared.models.soep_concept import SoepConcept as SoepConceptModel
from shared.models.detection_result import DetectionResult as DetectionResultModel
from shared.models.correction import Correction, SoepField
from shared.models.patient_instruction import PatientInstruction

from services.api.auth import (
    LoginRequest, TokenResponse, CurrentUser,
    get_current_user, require_role,
    verify_password, create_access_token,
)
from shared.models.user import User
from services.audit.service import AuditService, AuditEvent

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(config.log_level)
    ),
)
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI-Consultassistent API", env=config.env)
    await init_db()
    logger.info("Database connectie OK")
    # Redis (optional)
    try:
        from shared.redis_client import redis_client
        await redis_client.connect()
        logger.info("Redis connectie OK")
    except Exception as e:
        logger.warning("Redis niet beschikbaar - fallback naar DB polling", error=str(e))

    # Pipeline initialiseren: Whisper + PyAnnote modellen laden (kan ~30s duren)
    try:
        from services.pipeline.orchestrator import pipeline
        await pipeline.initialize()
        logger.info("Pipeline modellen geladen (Whisper + diarisatie)")
    except Exception as e:
        logger.warning(
            "Pipeline modellen niet geladen bij startup - worden geladen bij eerste consult",
            error=str(e),
        )

    # Ollama connectie testen
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{config.ollama.host}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                logger.info("Ollama connectie OK", beschikbare_modellen=models)
                if config.ollama.model not in " ".join(models):
                    logger.warning(
                        "Geconfigureerd model niet gevonden in Ollama",
                        verwacht=config.ollama.model,
                        beschikbaar=models,
                    )
    except Exception as e:
        logger.warning("Ollama niet bereikbaar bij startup", host=config.ollama.host, error=str(e))

    yield
    logger.info("Shutting down AI-Consultassistent API")
    try:
        from shared.redis_client import redis_client
        await redis_client.disconnect()
    except Exception:
        pass
    await close_db()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI-Consultassistent",
    description="Privacy-first AI-systeem voor consultdocumentatie in de huisartsenpraktijk",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audio opslag pad - fallback naar lokale directory als /data niet beschikbaar is
AUDIO_DIR = Path(config.audio.storage_path)
try:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    AUDIO_DIR = Path("./data/audio")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class ConsultStartRequest(BaseModel):
    patient_hash: str = Field(..., description="SHA-256 hash van BSN")


class ConsultStartResponse(BaseModel):
    session_id: str
    status: str = "recording"


class SOEPConcept(BaseModel):
    S: str = ""
    O: str = ""
    E: str = ""
    P: str = ""
    icpc_code: str | None = None
    icpc_titel: str | None = None
    confidence: float | None = None


class RedFlag(BaseModel):
    id: str
    ernst: str
    categorie: str
    beschrijving: str
    nhg_referentie: str | None = None


class MissingInfo(BaseModel):
    id: str
    veld: str
    beschrijving: str
    prioriteit: str


class DetectionResultSchema(BaseModel):
    rode_vlaggen: list[RedFlag] = []
    ontbrekende_info: list[MissingInfo] = []


class ApproveRequest(BaseModel):
    soep_final: SOEPConcept
    corrections: list[dict] = []


class ExportRequest(BaseModel):
    target: str = "clipboard"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    services: dict = {}


# ---------------------------------------------------------------------------
# Background pipeline task
# ---------------------------------------------------------------------------
async def enqueue_pipeline_job(consult_id: uuid.UUID, audio_path: str):
    """Plaats een verwerkingsjob in de Redis Stream voor de worker pool."""
    try:
        from shared.redis_client import redis_client
        await redis_client.client.xadd("jobs:pipeline", {
            "consult_id": str(consult_id),
            "audio_path": audio_path,
            "retry_count": "0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Pipeline job in queue geplaatst",
                    consult_id=str(consult_id))
    except Exception as e:
        # Fallback: draai pipeline direct als Redis niet beschikbaar is
        logger.warning("Redis queue niet beschikbaar - fallback naar directe verwerking",
                       consult_id=str(consult_id), error=str(e))
        from shared.database import async_session
        from services.pipeline.orchestrator import pipeline

        async with async_session() as db:
            try:
                await pipeline.process_consult(db, consult_id, audio_path)
            except Exception as pipe_err:
                logger.error("Directe pipeline verwerking mislukt",
                            consult_id=str(consult_id), error=str(pipe_err))


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login met gebruikersnaam en wachtwoord."""
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Ongeldige inloggegevens")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is gedeactiveerd")

    token, expires = create_access_token(str(user.id), user.role.value)

    return TokenResponse(
        access_token=token,
        expires_in=config.security.session_timeout_minutes * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
        },
    )


@app.get("/api/auth/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Haal huidige gebruiker op."""
    return current_user


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Systeemstatus check."""
    db_status = "ok"
    try:
        await init_db()
    except Exception:
        db_status = "error"

    redis_status = "unchecked"
    try:
        from shared.redis_client import redis_client
        await redis_client.client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "unavailable"

    # Ollama check
    ollama_status = "unchecked"
    ollama_model = None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{config.ollama.host}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                ollama_status = "ok"
                ollama_model = config.ollama.model
                if config.ollama.model not in " ".join(models):
                    ollama_status = "model_missing"
            else:
                ollama_status = "error"
    except Exception:
        ollama_status = "unavailable"

    # Whisper check
    whisper_status = "not_loaded"
    try:
        from services.pipeline.orchestrator import pipeline
        if pipeline.transcription_service._initialized:
            whisper_status = "ready"
    except Exception:
        whisper_status = "error"

    overall = "ok"
    if db_status != "ok":
        overall = "degraded"
    if ollama_status not in ("ok", "unchecked"):
        overall = "degraded"

    return HealthResponse(
        status=overall,
        version="0.1.0",
        services={
            "database": db_status,
            "redis": redis_status,
            "whisper": whisper_status,
            "ollama": ollama_status,
            "ollama_model": ollama_model or config.ollama.model,
        },
    )


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    from shared.metrics import metrics
    from fastapi.responses import Response
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


# ---------------------------------------------------------------------------
# Consult Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/consult/start", response_model=ConsultStartResponse)
async def start_consult(
    request: ConsultStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Start een nieuw consult."""
    consult = Consult(
        patient_hash=request.patient_hash,
        practitioner_id=uuid.UUID(current_user.id),
        status=ConsultStatus.recording,
        started_at=datetime.now(timezone.utc),
    )
    db.add(consult)
    await db.flush()

    logger.info("Consult gestart", session_id=str(consult.id), user=current_user.username)

    return ConsultStartResponse(session_id=str(consult.id))


@app.post("/api/consult/{session_id}/stop")
async def stop_consult(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stop opname en start verwerkingspipeline."""
    consult = await db.get(Consult, uuid.UUID(session_id))
    if not consult:
        raise HTTPException(404, "Consult niet gevonden")

    consult.ended_at = datetime.now(timezone.utc)
    consult.status = ConsultStatus.transcribing

    return {"session_id": session_id, "status": "transcribing"}


@app.post("/api/consult/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_hash: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Upload een audiobestand voor verwerking. Job gaat naar de worker queue."""
    # Validatie
    if not file.filename or not file.filename.endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm")):
        raise HTTPException(400, "Ongeldig audioformaat. Gebruik WAV, MP3, M4A, OGG, FLAC of WebM.")

    # Maak consult aan
    consult_id = uuid.uuid4()
    audio_filename = f"{consult_id}{Path(file.filename).suffix}"
    audio_path = AUDIO_DIR / audio_filename

    # Sla audio op
    async with aiofiles.open(audio_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # Maak consult record
    consult = Consult(
        id=consult_id,
        patient_hash=patient_hash or "anonymous",
        practitioner_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # placeholder voor MVP
        status=ConsultStatus.transcribing,
        started_at=datetime.now(timezone.utc),
        audio_path=str(audio_path),
    )
    db.add(consult)
    await db.commit()

    # Plaats job in Redis queue → worker pool verwerkt async
    background_tasks.add_task(enqueue_pipeline_job, consult_id, str(audio_path))

    logger.info("Audio geupload, pipeline gestart",
                session_id=str(consult_id), filename=file.filename)

    return {
        "session_id": str(consult_id),
        "status": "processing",
        "message": "Audio ontvangen, verwerking gestart.",
    }


@app.get("/api/consult/{session_id}/status")
async def get_consult_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Poll de verwerkingsstatus van een consult."""
    consult = await db.get(Consult, uuid.UUID(session_id))
    if not consult:
        raise HTTPException(404, "Consult niet gevonden")

    # Check welke stappen al klaar zijn
    has_transcript = consult.transcript is not None
    has_extraction = consult.extraction is not None
    has_soep = consult.soep_concept is not None
    has_detection = consult.detection_result is not None

    return {
        "session_id": session_id,
        "status": consult.status.value,
        "steps": {
            "transcription": "completed" if has_transcript else "pending",
            "extraction": "completed" if has_extraction else "pending",
            "soep_generation": "completed" if has_soep else "pending",
            "detection": "completed" if has_detection else "pending",
        },
    }


@app.get("/api/consult/{session_id}/transcript")
async def get_transcript(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Haal het transcript op voor een consult."""
    result = await db.execute(
        select(Transcript).where(Transcript.consult_id == uuid.UUID(session_id))
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(404, "Transcript niet gevonden")

    return {
        "session_id": session_id,
        "segments": transcript.segments,
        "raw_text": transcript.raw_text,
        "model_version": transcript.model_version,
        "confidence_avg": transcript.confidence_avg,
        "duration_secs": transcript.duration_secs,
    }


@app.get("/api/consult/{session_id}/soep", response_model=SOEPConcept)
async def get_soep(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Haal het SOEP-concept op voor review."""
    result = await db.execute(
        select(SoepConceptModel).where(SoepConceptModel.consult_id == uuid.UUID(session_id))
    )
    soep = result.scalar_one_or_none()

    if not soep:
        raise HTTPException(404, "SOEP-concept niet gevonden")

    return SOEPConcept(
        S=soep.s_text,
        O=soep.o_text,
        E=soep.e_text,
        P=soep.p_text,
        icpc_code=soep.icpc_code,
        icpc_titel=soep.icpc_titel,
        confidence=soep.confidence,
    )


@app.get("/api/consult/{session_id}/detection", response_model=DetectionResultSchema)
async def get_detection(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Haal rode vlaggen en ontbrekende info op."""
    result = await db.execute(
        select(DetectionResultModel).where(
            DetectionResultModel.consult_id == uuid.UUID(session_id)
        )
    )
    detection = result.scalar_one_or_none()

    if not detection:
        return DetectionResultSchema()

    return DetectionResultSchema(
        rode_vlaggen=[RedFlag(**f) for f in (detection.red_flags or [])],
        ontbrekende_info=[MissingInfo(**i) for i in (detection.missing_info or [])],
    )


@app.post("/api/consult/{session_id}/approve")
async def approve_soep(
    session_id: str,
    request: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Keur SOEP-concept goed na review."""
    result = await db.execute(
        select(SoepConceptModel).where(SoepConceptModel.consult_id == uuid.UUID(session_id))
    )
    soep = result.scalar_one_or_none()
    if not soep:
        raise HTTPException(404, "SOEP-concept niet gevonden")

    # Update SOEP met eventuele wijzigingen
    soep.s_text = request.soep_final.S
    soep.o_text = request.soep_final.O
    soep.e_text = request.soep_final.E
    soep.p_text = request.soep_final.P
    soep.is_approved = True
    soep.approved_by = uuid.UUID(current_user.id)
    soep.approved_at = datetime.now(timezone.utc)

    # Sla correcties op
    for corr in request.corrections:
        correction = Correction(
            soep_id=soep.id,
            field=SoepField(corr.get("field", "S")),
            original_text=corr.get("original", ""),
            corrected_text=corr.get("corrected", ""),
            corrected_by=uuid.UUID(current_user.id),
        )
        db.add(correction)

    # Update consult status
    consult = await db.get(Consult, uuid.UUID(session_id))
    if consult:
        consult.status = ConsultStatus.approved

    logger.info("SOEP goedgekeurd", session_id=session_id,
                user=current_user.username,
                corrections_count=len(request.corrections))

    return {
        "session_id": session_id,
        "status": "approved",
        "export_ready": True,
    }



@app.get("/api/export/targets")
async def get_export_targets():
    """Beschikbare HIS export opties."""
    from services.his_export.service import his_export_service
    return {"targets": his_export_service.get_available_targets()}


@app.post("/api/consult/{session_id}/export")
async def export_to_his(
    session_id: str,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Exporteer goedgekeurd SOEP naar HIS."""
    from services.his_export.service import his_export_service, SOEPExportData

    result = await db.execute(
        select(SoepConceptModel).where(SoepConceptModel.consult_id == uuid.UUID(session_id))
    )
    soep = result.scalar_one_or_none()
    if not soep:
        raise HTTPException(404, "SOEP-concept niet gevonden")

    if not soep.is_approved:
        raise HTTPException(400, "SOEP moet eerst goedgekeurd worden")

    consult = await db.get(Consult, uuid.UUID(session_id))

    export_data = SOEPExportData(
        consult_id=session_id,
        patient_hash=consult.patient_hash if consult else "",
        practitioner_name=current_user.display_name,
        practitioner_id=current_user.id,
        timestamp=consult.started_at if consult else datetime.now(timezone.utc),
        s_text=soep.s_text,
        o_text=soep.o_text,
        e_text=soep.e_text,
        p_text=soep.p_text,
        icpc_code=soep.icpc_code,
        icpc_titel=soep.icpc_titel,
    )

    export_result = await his_export_service.export_soep(export_data, target=request.target)

    if consult and export_result.success:
        consult.status = ConsultStatus.exported

    logger.info("Export naar HIS", session_id=session_id, target=request.target,
                 success=export_result.success)

    return {
        "session_id": session_id,
        "status": "exported" if export_result.success else "export_failed",
        "target": request.target,
        "export_text": export_result.export_text,
        "export_id": export_result.export_id,
        "message": export_result.message,
        "available_targets": his_export_service.get_available_targets(),
    }

@app.get("/api/consults")
async def list_consults(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lijst van recente consulten."""
    query = select(Consult).order_by(Consult.created_at.desc())

    if status:
        query = query.where(Consult.status == ConsultStatus(status))

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    consults = result.scalars().all()

    # Tel totaal
    count_query = select(func.count(Consult.id))
    if status:
        count_query = count_query.where(Consult.status == ConsultStatus(status))
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "consults": [
            {
                "id": str(c.id),
                "status": c.status.value,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "patient_hash": c.patient_hash[:8] + "...",
            }
            for c in consults
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# WebSocket - Real-time pipeline status
# ---------------------------------------------------------------------------

@app.websocket("/ws/consult/{session_id}")
async def websocket_status(websocket: WebSocket, session_id: str):
    """
    WebSocket voor real-time pipeline status updates.
    Probeert eerst Redis Pub/Sub, valt terug op database polling.
    Client ontvangt JSON messages: {"status": "transcribing", "step": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket verbonden", session_id=session_id)

    try:
        # Try Redis Pub/Sub first
        redis_available = False
        try:
            from shared.redis_client import redis_client
            pubsub = redis_client.client.pubsub()
            await pubsub.subscribe("pipeline:status")
            redis_available = True
            logger.info("Redis Pub/Sub geabonneerd", session_id=session_id)

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                if message and message["type"] == "message":
                    import json
                    data = json.loads(message["data"])
                    if data.get("consult_id") == session_id:
                        await websocket.send_json(data)
                        if data.get("status") in ("reviewing", "approved", "exported", "failed"):
                            break
                else:
                    # Send heartbeat/current status from DB
                    async with async_session() as db:
                        consult = await db.get(Consult, uuid.UUID(session_id))
                        if consult:
                            status = consult.status.value
                            await websocket.send_json({
                                "session_id": session_id,
                                "status": status,
                            })
                            if status in ("reviewing", "approved", "exported", "failed"):
                                break

            await pubsub.unsubscribe("pipeline:status")

        except Exception as redis_err:
            redis_available = False
            logger.warning("Redis Pub/Sub niet beschikbaar, val terug op DB polling", error=str(redis_err))

        # Fallback: database polling (alleen als Redis niet beschikbaar was)
        if not redis_available:
            while True:
                async with async_session() as db:
                    consult = await db.get(Consult, uuid.UUID(session_id))
                    if not consult:
                        await websocket.send_json({"error": "Consult niet gevonden"})
                        break

                    status = consult.status.value
                    await websocket.send_json({
                        "session_id": session_id,
                        "status": status,
                    })

                    if status in ("reviewing", "approved", "exported", "failed"):
                        break

                await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info("WebSocket verbroken", session_id=session_id)
    except Exception as e:
        logger.error("WebSocket fout", session_id=session_id, error=str(e))

# CLAUDE.md - AI-Consultassistent

## Projectoverzicht

Privacy-first AI-systeem dat consultaudio in een Nederlandse huisartsenpraktijk omzet naar gestructureerde SOEP-dossiervoering. Volledig lokaal draaiend op een GPU-server in de praktijk.

## Technische Stack

- **Backend:** Python 3.12, FastAPI, asyncpg, SQLAlchemy (async)
- **Frontend:** Next.js 14, React 18, Tailwind CSS, TypeScript
- **Database:** PostgreSQL 16 + pgcrypto extensie
- **Message Queue:** Redis Streams
- **STT:** Faster-Whisper (Whisper Large v3 Turbo), PyAnnote Audio 3.x
- **LLM:** Ollama met Llama 3.3 8B Instruct (lokaal)
- **Containerisatie:** Docker Compose met NVIDIA GPU support

## Projectstructuur

```
services/              -> Python backend services
  api/main.py          -> FastAPI gateway (alle endpoints)
  transcription/       -> Whisper STT + PyAnnote diarisatie
  extraction/          -> LLM medische extractie + SOEP generatie
  audit/               -> NEN 7513 conforme audit logging
frontend/review-app/   -> Next.js review interface
shared/
  schemas/             -> JSON schema's (medical_extraction, soep_concept, detection_result)
  prompts/templates.py -> Alle LLM prompt templates
  config/settings.py   -> Centrale configuratie (dataclasses, env vars)
database/migrations/   -> PostgreSQL schema (001_init.sql)
```

## Kernconcepten

### SOEP-structuur
Nederlandse huisartsen documenteren in SOEP-formaat:
- **S** (Subjectief): Klachtpresentatie vanuit patientperspectief
- **O** (Objectief): Bevindingen bij onderzoek (ALLEEN wat verricht is)
- **E** (Evaluatie): Werkdiagnose + differentiaaldiagnosen + ICPC-code
- **P** (Plan): Medicatie, verwijzingen, onderzoek, controle

### Pipeline Flow
```
Audio -> Whisper STT -> PyAnnote diarisatie -> Gelabeld transcript
    -> LLM extractie (JSON) -> SOEP generatie -> Rode vlaggen detectie
    -> Review UI -> Arts goedkeuring -> HIS export
```

### Privacy/Compliance Regels
- Alle verwerking lokaal (geen cloud tenzij explicit enabled + gepseudonimiseerd)
- Audio wordt verwijderd na goedkeuring transcript
- Audit logs zijn immutable (triggers in PostgreSQL)
- Patient identificatie via SHA-256 hash van BSN
- Encryptie: AES-256 at-rest, TLS 1.3 in-transit
- Conform NEN 7510:2024, NEN 7513 logging

## Ontwikkelrichtlijnen

### Python Code
- Async/await overal (FastAPI is async)
- Type hints verplicht
- structlog voor logging (niet standaard logging)
- Pydantic v2 voor data validatie
- JSON schema's in shared/schemas/ zijn de bron van waarheid

### LLM Prompts
- Prompt templates staan in shared/prompts/templates.py
- Temperatuur altijd laag (0.1) voor medische output
- JSON format mode afdwingen via Ollama format parameter
- NOOIT het LLM laten fabriceren: alleen rapporteren wat in transcript staat

### Database
- UUID primary keys overal
- JSONB voor flexibele medische data
- Audit logs: GEEN update/delete (triggers blokkeren dit)
- Migraties in database/migrations/ (genummerd)

### Frontend
- TypeScript strict mode
- Tailwind CSS voor styling
- shadcn/ui componenten waar mogelijk
- API calls via typed fetch wrapper

## Commando's

```bash
# Backend development
cd services && pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend development
cd frontend/review-app && npm install && npm run dev

# Database
docker compose up postgres -d
psql -h localhost -U ca_app -d consultassistent -f database/migrations/001_init.sql

# Ollama model pull
ollama pull llama3.1:8b

# Volledig systeem
docker compose up -d
```

## Testen

```bash
# Python (cloud-API, pipeline, beleid)
pip install -r tests/requirements-cloud.txt
pytest -q

# JavaScript in de extensie (koppeltabel Thuisarts, QR)
node --test tests/js/thuisarts.test.js tests/js/dossiervraag.test.js tests/js/post.test.js tests/js/tolk.test.js tests/js/econsult.test.js
```

De extensie heeft geen bouwstap en geen npm-afhankelijkheden: de proeven draaien
op de ingebouwde testloper van Node. Logica die het waard is om te toetsen staat
daarom in `chrome-extension/lib/`, zonder DOM en zonder `chrome.*`. De proeven
zelf staan in `tests/js/`, buiten de extensiemap, omdat `pack_extension.sh` die
map in zijn geheel tot CRX maakt.

## Configuratie

Alle configuratie via environment variabelen (zie .env.example).
Centrale config class: shared/config/settings.py (AppConfig singleton).

## Taal

- Code: Engels (variabelen, functies, comments)
- Medische content: Nederlands
- Prompts: Nederlands
- UI labels: Nederlands
- Documentatie: Nederlands

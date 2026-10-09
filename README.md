# AI-Consultassistent

**Privacy-first AI-systeem voor Nederlandse huisartsenpraktijken.**
Zet consultaudio om in gestructureerde SOEP-dossiervoering - volledig lokaal.

## Architectuur

```
[Microfoon] -> [Audio Capture] -> [Whisper STT + Diarisatie] -> [Transcript Store]
                                                                      |
[HIS] <- [Export] <- [Review UI] <- [Detectie] <- [SOEP Generator] <- [LLM Extractie]
```

## Stack

| Component | Technologie |
|-----------|------------|
| Speech-to-Text | Whisper Large v3 Turbo (Faster-Whisper) |
| Diarisatie | PyAnnote Audio 3.x |
| LLM | Llama 3.3 8B Instruct via Ollama |
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 14 + React + Tailwind CSS |
| Database | PostgreSQL 16 + pgcrypto |
| Message Queue | Redis Streams |
| Containerisatie | Docker Compose |

## Vereisten

### Hardware (minimaal)
- NVIDIA GPU met >=12 GB VRAM (RTX 4070 of hoger)
- 32 GB RAM
- 500 GB NVMe SSD
- Ubuntu 24.04 LTS

### Software
- Docker + Docker Compose
- NVIDIA Container Toolkit
- Ollama (voor LLM)

## Snelstart

```bash
# 1. Clone repo
git clone <repo-url>
cd ai-consultassistent

# 2. Kopieer environment
cp .env.example .env
# -> Pas configuratie aan

# 3. Installeer Ollama en pull model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b

# 4. Start alle services
docker compose up -d

# 5. Open review-interface
open http://localhost:3000
```

## Projectstructuur

```
ai-consultassistent/
├── services/
│   ├── api/                 # FastAPI gateway (alle endpoints)
│   ├── transcription/       # Whisper STT + diarisatie
│   ├── extraction/          # LLM medische extractie + SOEP generatie
│   ├── audit/               # NEN 7513 conforme audit logging
│   ├── Dockerfile           # Backend Docker image
│   └── requirements.txt     # Python dependencies
├── frontend/
│   └── review-app/          # Next.js review-interface
│       ├── src/
│       │   ├── app/         # Next.js app router
│       │   ├── components/  # React componenten
│       │   └── lib/         # API client + utilities
│       ├── Dockerfile       # Frontend Docker image
│       └── package.json
├── shared/
│   ├── schemas/             # JSON-schema's
│   ├── prompts/             # LLM-prompttemplates
│   └── config/              # Gedeelde configuratie
├── database/
│   └── migrations/          # PostgreSQL-migraties
├── scripts/                 # Setup en validatie
├── docs/                    # DPIA, privacy, beheer
├── docker-compose.yml
└── .env.example
```

## Browserextensie (Chrome/Edge)

De extensie in `chrome-extension/` bundelt twee functies in één zijpaneel:

- **Dicteren & SOEP**: live dicteren in het aangeklikte Bricks-veld, en een dictaat laten redigeren tot een SOEP-regel met aandachtspunten.
- **Brieven**: informatiebrieven aan derden en verwijsbrieven. Deze functie was eerder de losse extensie BriefAssistent. Het dossier komt uit Bricks, een schermafdruk of een PDF. De privacyfilter draait in de browser en daarna nog een keer op de server. Er staat geen AI-sleutel in de browser. De server-endpoints staan in `services/cloud_api/letters.py`.

Laden: `edge://extensions` → Ontwikkelaarsmodus → "Uitgepakte extensie laden" → map `chrome-extension`. In Instellingen vul je de server-URL en de API-sleutel in. Voor brieven moet op de server `ANTHROPIC_API_KEY` gezet zijn.

## MVP Fasen

- **Fase 1 (6 weken):** Handmatige upload -> transcriptie -> SOEP-concept
- **Fase 2 (3 maanden):** Real-time capture, review UI, rode vlaggen, audit
- **Fase 3 (6 maanden):** HIS-integratie, feedbackloop, productie-hardening

## Compliance

- Volledig lokale verwerking (geen cloud vereist)
- AVG-conform met DPIA-template
- NEN 7510:2024 / NEN 7513 logging
- Encryptie at-rest (AES-256) en in-transit (TLS 1.3)
- Audit trail op alle patientdata-toegang

## Licentie

Proprietary, ProVita Care (Roermond)

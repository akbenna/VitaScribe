# VitaScribe - Lokale pipeline installeren (on-premise)

Dit is het installatie-runbook voor de **privacy-first lokale pipeline**: Whisper
(spraak→tekst) + PyAnnote (sprekerscheiding) + Ollama (lokaal LLM voor SOEP) +
PostgreSQL, allemaal op een machine in de praktijk. Geen patiëntdata naar de
cloud (conform NEN 7510 / AVG).

Bedoeld voor de persoon die de server inricht (eigen IT / externe hulp). Er zijn
twee fases:

- **Fase A - Voorlopig (nu, zonder GPU):** draaien op CPU om te testen en te
  demonstreren. Trager, kleiner Whisper-model, maar het volledige proces werkt.
- **Fase B - Definitief (zodra de NVIDIA-GPU er is):** omschakelen naar GPU voor
  productiekwaliteit en -snelheid.

De applicatiecode is identiek; alleen de configuratie (`.env`) en het Docker
Compose-profiel verschillen.

---

## 0. Wat je nodig hebt

| | Fase A (voorlopig, CPU) | Fase B (definitief, GPU) |
|---|---|---|
| Machine | bestaande PC/server/Mac | server met **NVIDIA-GPU** (≥12 GB VRAM aanbevolen) |
| OS | Linux/macOS/Windows+WSL2 | Linux (Ubuntu 22.04 aanbevolen) |
| Software | Docker + Docker Compose, Git | + NVIDIA-driver + NVIDIA Container Toolkit |
| Whisper-model | `small` of `medium` | `large-v3-turbo` |
| Snelheid | minuten per consult | (bijna) realtime |

Verder nodig: een **HuggingFace-token** (gratis) voor de PyAnnote-diarisatie -
maak een account op huggingface.co, accepteer de voorwaarden van
`pyannote/speaker-diarization-3.1`, en genereer een token.

---

## 1. Code ophalen

```bash
git clone https://github.com/akbenna/VitaScribe.git
cd VitaScribe
```

## 2. Geheimen genereren

```bash
openssl rand -hex 32   # voor APP_SECRET_KEY
openssl rand -hex 32   # voor DB_ENCRYPTION_KEY
```

---

## Fase A - Voorlopig draaien op CPU (nu)

Doel: testen zonder GPU. Gebruik een klein/sneller Whisper-model.

1. **Configuratie.** Maak een `.env` op basis van het GPU-sjabloon, met deze
   afwijkingen voor CPU:

   ```bash
   cp .env.gpu.example .env
   ```

   Pas in `.env` aan:
   ```
   WHISPER_DEVICE=cpu
   WHISPER_MODEL=small          # of 'medium' als de machine krachtig is
   WHISPER_COMPUTE_TYPE=int8
   WHISPER_USE_FORCED_ALIGNMENT=false
   DIARIZATION_ENABLED=false    # PyAnnote op CPU is traag; tijdelijk uit kan
   ```
   Vul de `<...>`-geheimen en wachtwoorden in.

2. **Stack starten (CPU-profiel).** Dit start PostgreSQL, Redis, Ollama (CPU),
   de Whisper/extractie-API en de frontend:

   ```bash
   docker compose --profile cpu up -d
   ```

3. **Taalmodel ophalen** (eenmalig, ~5 GB):

   ```bash
   docker compose exec ollama-cpu ollama pull llama3.1:8b
   ```

4. **Database klaarzetten** (migraties). Migratie `001_init.sql` draait
   **automatisch** bij de eerste start van PostgreSQL. Migratie `002`
   (tabellen voor de zelflerende laag) moet je éénmalig apart toepassen:

   ```bash
   cat database/migrations/002_feedback_vocabulary.sql | \
     docker compose exec -T postgres psql -U ca_app -d consultassistent
   ```
   De eerste gebruikers worden aangemaakt via `SEED_ON_START=true`.

5. **Koude start laden** (onze gecureerde SOEP-voorbeelden):

   ```bash
   docker compose exec api-cpu python tools/seed_fewshot_bank.py
   ```

6. **Controleren:**
   ```bash
   curl http://localhost:8001/health      # API (CPU-profiel draait op poort 8001)
   ```
   En open de frontend in de browser (zie stap "Frontend" hieronder).

> Op CPU duurt een consult van enkele minuten audio al gauw enkele minuten
> verwerking. Dat is normaal en verdwijnt met de GPU.

---

## Fase B - Definitief op GPU (zodra de NVIDIA-machine er is)

1. **GPU-drivers + toolkit** (Ubuntu):
   ```bash
   nvidia-smi                       # moet de GPU tonen
   # NVIDIA Container Toolkit installeren (volg de officiële NVIDIA-handleiding)
   ```

2. **Configuratie.** Gebruik `.env.gpu.example` ongewijzigd (al op `cuda`,
   `large-v3-turbo`, diarisatie aan). Vul de geheimen + `HF_TOKEN` in:
   ```bash
   cp .env.gpu.example .env
   # bewerk .env: secrets, wachtwoorden, HF_TOKEN
   ```

3. **Stack starten (GPU-profiel):**
   ```bash
   docker compose --profile gpu up -d
   docker compose exec ollama ollama pull llama3.1:8b
   docker compose exec api python tools/seed_fewshot_bank.py
   ```

4. **Controleren:**
   ```bash
   curl http://localhost:8000/health      # API (GPU-profiel draait op poort 8000)
   ```

5. (Optioneel, later) Forced alignment aanzetten voor nóg preciezere
   timestamps: `WHISPER_USE_FORCED_ALIGNMENT=true` in `.env` + container met
   `whisperx` (zie `docs/FASE3_FINETUNING.md`).

---

## Frontend (review-interface)

De lokale pipeline wordt bediend via de **web-frontend** (Next.js review-app),
niet via de Chrome-extensie (die hoort bij de aparte cloud-API).

De frontend draait al mee als Docker Compose-service `frontend` op
**http://localhost:3000** (start automatisch met `docker compose up`). Zorg dat
de frontend naar de juiste API-poort wijst: `8000` bij het GPU-profiel, `8001`
bij het CPU-profiel (env-variabele `NEXT_PUBLIC_API_URL` in de frontend-service).

Voor losse ontwikkeling kan ook handmatig:
```bash
cd frontend/review-app
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # of :8001 bij CPU
```

> Poorten (host): GPU-API 8000, CPU-API 8001, frontend 3000, PostgreSQL 5433,
> Redis 6380, Ollama 11434.

---

## Eerste test (end-to-end)

1. Log in op de frontend met de geseede arts-gebruiker (zie `ADMIN_PASSWORD` /
   `ARTS_PASSWORD` uit `.env`).
2. Start een consult, neem een korte testopname op (of upload een audiobestand).
3. Controleer: transcript verschijnt → SOEP-concept → rode vlaggen → goedkeuren.
4. De woordenlijst en seed-voorbeelden zorgen dat termen en stijl meteen kloppen.

---

## Privacy / NEN-checklist (vóór echte patiëntdata)

- [ ] Server staat in de praktijk, niet bereikbaar vanaf internet (alleen LAN/VPN).
- [ ] `APP_ENV=production`, sterke `APP_SECRET_KEY` en `DB_ENCRYPTION_KEY` gezet.
- [ ] `CLOUD_FALLBACK_ENABLED=false` (geen cloud).
- [ ] Audio wordt na goedkeuring verwijderd (standaardgedrag) - geverifieerd.
- [ ] Back-up en encryptie van de database geregeld.
- [ ] DPIA bijgewerkt; verwerkersregister klopt (geen externe verwerkers nodig).

---

## Hulp aan externe partij - korte checklist

1. Ubuntu-server met NVIDIA-GPU + drivers + Docker + NVIDIA Container Toolkit.
2. `git clone`, `cp .env.gpu.example .env`, geheimen + `HF_TOKEN` invullen.
3. `docker compose --profile gpu up -d`.
4. `ollama pull llama3.1:8b`, migratie 002 toepassen, `python tools/seed_fewshot_bank.py`.
5. `/health` groen, frontend bereikbaar, end-to-end testconsult geslaagd.
6. Privacy-checklist afvinken.

---

## Veelvoorkomende problemen

- **`/health` reageert niet:** container nog aan het opstarten of model nog aan
  het laden (`docker compose logs -f api`). Whisper-model downloadt bij eerste
  start.
- **Diarisatie laadt niet:** ontbrekend/ongeldig `HF_TOKEN` of voorwaarden van
  het PyAnnote-model niet geaccepteerd. De pipeline draait dan zonder
  sprekerscheiding (waarschuwing in de log).
- **Ollama traag / time-out:** verhoog `OLLAMA_TIMEOUT`, controleer GPU-gebruik
  (`nvidia-smi`), of kies een kleiner model voor concepten.
- **Te traag op CPU:** verwacht; dit is de voorlopige fase. Schakel over naar
  GPU (Fase B).

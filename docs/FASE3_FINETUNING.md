# Fase 3 - Forced-alignment & model-fine-tuning (runbook)

Dit is de zwaarste laag: preciezere timestamps en getrainde modellen. Het draait
**niet** in de standaard VitaScribe-omgeving maar op een aparte GPU-machine, en
het is pas zinvol als je voldoende artsfeedback hebt verzameld. Dit document is
het runbook: vereisten, datadrempels, procedure en - cruciaal - evaluatie en
rollback via de meetlat.

## Overzicht en kernkeuze

| Onderdeel | Data nodig | Audio nodig | Status |
|---|---|---|---|
| WhisperX forced-alignment | nee | ja (live audio van het consult) | ingebouwd, toggle |
| ASR-postcorrectie (SFT) | transcriptcorrecties | **nee** | dataset + script |
| SOEP-stijl (DPO) | SOEP-correcties | nee | dataset + script |
| Akoestische Whisper-FT | (audio, transcript) | **ja, met retentie+consent** | optioneel script |

**Belangrijk:** het privacybeleid verwijdert audio na goedkeuring. Daarom is de
primaire STT-verbetering de **tekstgebaseerde ASR-postcorrectie** (geen audio).
Akoestische Whisper-fine-tuning is alleen mogelijk als je apart, met toestemming
en DPIA, audio-retentie inricht - het script blokkeert zichzelf anders.

## 1. WhisperX forced-alignment (preciezere timestamps)

Verfijnt woord-timestamps via wav2vec2, zodat sprekergrenzen midden in een
segment exacter vallen - dat voedt de woord-niveau diarisatie.

```bash
pip install whisperx
# in .env:
WHISPER_USE_FORCED_ALIGNMENT=true
WHISPER_ALIGNMENT_DEVICE=cuda
```

Bij ontbrekende library of fout valt de pipeline automatisch terug op de
Faster-Whisper woord-timestamps (geen crash). Meet de winst met de WER-/term-
meetlat vóór je het standaard aanzet.

## 2. Trainingsdata exporteren

Beide datasets komen uit `consultation_feedback`:

```bash
python tools/build_training_data.py
# of gericht:
python tools/build_training_data.py --only asr --asr-out /data/training/asr_correction.jsonl
python tools/build_training_data.py --only dpo --dpo-out /data/training/soep_dpo.jsonl
```

De export meldt per dataset `records` en `sufficient`. Richtlijn: **≥200**
kwalitatieve paren voordat trainen zin heeft (instelbaar via `--min-pairs` of
`ASR_MIN_PAIRS` / `DPO_MIN_PAIRS`). Onder die drempel weigeren de
trainingsscripts te draaien.

Kwaliteitsfilters zitten al in de builders: identieke paren, te korte/lange
teksten en volledige herschrijvingen (lage gelijkenis) vallen af; DPO-paren
vereisen dat de arts daadwerkelijk iets wijzigde én dat S en E aanwezig zijn.

## 3. ASR-postcorrectie trainen (SFT, geen audio)

```bash
pip install "transformers>=4.40" datasets accelerate sentencepiece torch
python -m services.learning.training.finetune_asr_correction \
    --data /data/training/asr_correction.jsonl \
    --base-model google/mt5-small \
    --output-dir /models/asr_corrector
```

Het resultaat is een contextuele ASR-corrector, complementair aan de
deterministische woordenlijst (niveau 1): het vangt fouten die van de zinscontext
afhangen. Inzet: als post-ASR-stap vóór de extractie (zie rapport §3.3).

## 4. SOEP-stijl trainen (DPO)

```bash
pip install "trl>=0.9" "transformers>=4.40" peft datasets accelerate torch
python -m services.learning.training.train_soep_dpo \
    --data /data/training/soep_dpo.jsonl \
    --base-model meta-llama/Llama-3.1-8B-Instruct \
    --output-dir /models/soep_dpo_adapter
```

Gebruikt LoRA: de basisgewichten blijven intact, rollback = adapter verwijderen.
Converteer de getrainde adapter naar GGUF om in Ollama te draaien.

## 5. Akoestische Whisper-FT (optioneel, alleen met retentie)

```bash
python -m services.learning.training.finetune_whisper \
    --manifest /data/training/audio_manifest.jsonl \
    --base-model openai/whisper-large-v3 \
    --output-dir /models/whisper_nl_praktijk \
    --i-have-consent-and-retention
```

Zonder de bevestigingsvlag blokkeert het script. Het manifest met (audio, tekst)
kun je alleen vullen als je audio bewaart onder toestemming + DPIA.

## 6. Evalueren en promoveren (verplicht)

Geen enkel model gaat naar productie zonder meting tegen de vaste testset:

```bash
# Transcriptie/ASR-correctie: WER + medische-term-foutmarge
python tools/eval_transcription.py --mode transcription cases.json
# SOEP/DPO: edit-distance gegenereerd vs. goedgekeurd
python tools/eval_transcription.py --mode soep soep_cases.json
```

Promoveer een nieuw model alleen als het de huidige baseline **verbetert** op de
meetlat. Houd modelversies bij, draai een regressietest op de testset, en zorg
voor een one-command rollback (vorige model/adapter terugzetten).

## 7. Governance

- Datasets bevatten klinische tekst: zelfde bewaarregime als consulten, lokaal.
- Fine-tunen creëert een afgeleide van patiëntdata in de gewichten: DPIA
  bijwerken, bewaartermijn vastleggen, en "vergeten" mogelijk maken (hertrainen
  zonder ingetrokken data).
- Akoestische FT vereist expliciete, gedocumenteerde toestemming voor
  audio-retentie - anders niet doen.

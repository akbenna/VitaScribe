# Zelflerende jobs periodiek draaien

De zelflerende laag bestaat uit twee jobs die de woordenlijst en de SOEP-stijl
automatisch met de praktijk laten meegroeien. Beide horen **periodiek** te
draaien op de praktijkserver - niet eenmalig. Dit document beschrijft de
installatie.

## Koude start: kennis vanaf dag 1 (vóór er feedback is)

De lerende jobs hebben artscorrecties nodig; bij de start is er nog niets om uit
te leren. Toch begint het systeem niet blanco. Twee kennisbronnen geven meteen
niveau:

1. **Medische woordenlijst** (`shared/vocabulary.py`): een gecureerde lijst van
   honderden NL medicatie-/diagnosetermen + lokale verwijslocaties. Deze voedt
   vanaf de eerste opname de Whisper-hotwords en de naberekening - geen actie
   nodig, staat standaard aan.

2. **Seed-few-shot-bank** (gecureerde, synthetische SOEP-voorbeelden): laad
   eenmalig vóór go-live een set hoogwaardige voorbeelden voor veelvoorkomende
   huisartspresentaties, zodat de SOEP-generatie meteen de juiste stijl,
   beknoptheid en ICPC-conventies aanhoudt.

   ```bash
   python tools/seed_fewshot_bank.py
   ```

   De voorbeelden bevatten **geen patiëntdata** en sturen alleen de *stijl* (de
   prompt zegt expliciet: stijl overnemen, nooit de inhoud). Ze staan in
   `services/learning/seed_data/soep_seed_examples.json` - **review ze als arts**
   en pas ze aan je eigen voorkeuren aan vóór go-live. Zodra echte goedgekeurde
   SOEP's binnenkomen, vult `tools/build_fewshot_bank.py` de bank met
   praktijkeigen voorbeelden; die komen náást de seed-voorbeelden te staan
   (seed-id's beginnen met `seed_`).

Wat een koude start NIET kan: model-fine-tuning/DPO (Fase 3) en de akoestische
verbeteringen vergen echte, verzamelde feedback en blijven dus voor later - zie
`docs/FASE3_FINETUNING.md`.

## Wat er draait

| Job | Script | Wat het doet |
|---|---|---|
| Vocabulaire (niveau 1) | `tools/learn_vocabulary.py` | Leert (fout → goed)-correcties uit artsfeedback en promoveert ze na een bevestigingsdrempel; exporteert naar `custom_vocabulary.json` (gelezen door de transcriptieservice). |
| Few-shot (niveau 2) | `tools/build_fewshot_bank.py` | Vult de few-shot-bank uit goedgekeurde SOEP's; gebruikt door de extractieservice bij SOEP-generatie. |

Het wrapper-script `scripts/run_learning_jobs.sh` draait beide achter elkaar,
laadt `.env`, kiest de juiste Python (venv heeft voorkeur) en logt naar
`logs/`.

## Voorwaarden

- De jobs draaien op de **praktijkserver** met toegang tot de lokale PostgreSQL
  (zelfde `.env` / `DATABASE_URL` als de API).
- De doelpaden moeten schrijfbaar zijn voor de servicegebruiker:
  - `WHISPER_CUSTOM_VOCAB_PATH` (default `/data/vocabulary/custom_vocabulary.json`)
  - `FEWSHOT_BANK_PATH` (default `/data/fewshot/soep_examples.json`)
- Na een run pikt de transcriptieservice de nieuwe woordenlijst op bij de
  **eerstvolgende (her)start**; de few-shot-bank wordt per SOEP-generatie
  opnieuw ingelezen.

## Optie A - systemd-timer (aanbevolen)

```bash
# 1. Kopieer de units (pas WorkingDirectory/User in de .service aan je install aan)
sudo cp deploy/systemd/vitascribe-learning.service /etc/systemd/system/
sudo cp deploy/systemd/vitascribe-learning.timer   /etc/systemd/system/

# 2. Herlaad systemd en zet de timer aan
sudo systemctl daemon-reload
sudo systemctl enable --now vitascribe-learning.timer

# 3. Controleer
systemctl list-timers vitascribe-learning.timer
sudo systemctl start vitascribe-learning.service   # handmatige testrun
journalctl -u vitascribe-learning.service -n 50    # logs bekijken
```

Standaard draait de timer **elke maandag om 03:00** (`OnCalendar` in de
`.timer`). `Persistent=true` haalt een gemiste run in als de server uit stond.

## Optie B - cron

```bash
# Systeembrede cron (met gebruikersveld):
sudo cp deploy/cron/vitascribe-learning.cron /etc/cron.d/vitascribe-learning
# Pas pad en gebruiker in het bestand aan je installatie aan.
```

## Handmatig draaien / tunen

```bash
# Beide jobs in één keer
scripts/run_learning_jobs.sh

# Los, met afgestelde drempels (voorzichtiger leren):
python tools/learn_vocabulary.py --min-confirmations 5 --min-dominance 0.7
python tools/build_fewshot_bank.py --max-examples 300
```

## Afstelknoppen (in `.env`)

```
# Vocabulaire-job - afweging leersnelheid vs. zuiverheid
VOCAB_LEARN_MIN_CONFIRMATIONS=3   # onafhankelijke consulten voor activatie
VOCAB_LEARN_MIN_DOMINANCE=0.6     # consistentie-eis dominante variant
VOCAB_LEARN_PERSIST_FLOOR=2       # vanaf hier bewaren (zichtbaarheid)

# Few-shot - aantal voorbeelden per SOEP en bankgrootte
FEWSHOT_ENABLED=true
FEWSHOT_K=3
FEWSHOT_MAX_EXAMPLES=500
```

## Aanbevolen ritme

Wekelijks is een goede start. Bij hoge consultvolumes kan dagelijks; bij lage
volumes maandelijks. Volg de **SOEP edit-distance** (zie `shared/evaluation.py`)
als KPI: die hoort over de weken te dalen naarmate de lus leert. Stijgt of
stagneert hij, verhoog dan de drempels (zuiverder leren) of inspecteer de
geleerde termen in `vocabulary_corrections`.

# VitaScribe - Upgradeonderzoek: transcriptie, SOEP-samenvatting en de zelflerende laag

*Onderzoeksrapport en gefaseerd implementatieplan - juni 2026*

---

## 1. Kernconclusie vooraf

VitaScribe staat technisch op een gezonde basis: Faster-Whisper `large-v3-turbo` voor spraak-naar-tekst, PyAnnote 3.1 voor diarisatie, een lokaal Ollama-model (`llama3.1:8b`) voor extractie en SOEP-generatie, en - in de cloud-API-tak - een handgeschreven medische woordenlijst die transcriptfouten naberekent. De architectuur is doordacht, maar de drie onderdelen die de *ervaren* kwaliteit bepalen, draaien op dit moment grotendeels **open loop**: ze leren niet van wat de arts elke dag corrigeert.

De grootste winst zit daarom niet in het inruilen van modellen, maar in het sluiten van de lus. Drie observaties dragen dit rapport:

Ten eerste laat de lokale transcriptieservice meetbare kwaliteit liggen. `services/transcription/service.py` roept Whisper aan **zonder** `initial_prompt` of `hotwords`, terwijl er elders in het project al een medische woordenlijst klaarligt. Onderzoek laat zien dat juist het meegeven van domeintermen aan Whisper de woordfoutmarge (WER) op medische audio met ~19% terugbrengt - een vrijwel gratis verbetering die nu niet wordt benut.

Ten tweede is de "zelflerende laag" vandaag vooral een *belofte*. De databasetabellen `consultation_feedback` en `vocabulary_corrections` bestaan, de woordenlijst draagt de comment "groeit mee via de feedbackloop", maar de daadwerkelijke terugkoppeling - correctie van de arts → automatische verbetering van de volgende transcriptie/SOEP - is niet geïmplementeerd. Dit is precies waar u prioriteit aan geeft, en het is ook waar de literatuur de duurzaamste kwaliteitswinst plaatst.

Ten derde ontbreekt een **meetlat**. Er is geen WER-meting op een vaste testset en geen kwaliteitsscore op de SOEP-output. Zonder meten is elke upgrade een gok; mét meten wordt de zelflerende laag pas stuurbaar.

De rest van dit rapport werkt deze drie lijnen uit, met steeds de afweging tussen kwaliteitswinst, inspanning en privacy-impact, en eindigt met een gefaseerd plan dat begint bij de goedkope, veilige winst en pas daarna naar de structurele ingrepen gaat.

---

## 2. Wat er nu staat - en waar de lekken zitten

### 2.1 Twee transcriptiepaden die uit elkaar zijn gegroeid

Het project kent feitelijk twee STT-implementaties. De **lokale** tak (`services/transcription/`) is de NEN-conforme, volledig lokale pipeline uit `CLAUDE.md`. De **cloud-API** tak (`services/cloud_api/`) is een lichter pad voor de Chrome-extensie, met een eigen `stt_service`, een `medical_vocabulary`-naberekening en een eigen promptset.

Het probleem is dat de kwaliteitsverbeteringen ongelijk verdeeld zijn. De cloud-tak heeft wél een vocabulaire-correctielaag (`correct_transcript_full`) en een hotwords-generator; de lokale tak - juist degene die u in productie op de praktijk-GPU wilt - heeft geen van beide. Wie de lokale pipeline gebruikt, krijgt rauwe Whisper-output zonder medische bias en zonder naberekening. Dit is het eerste lek.

### 2.2 Whisper draait zonder context

Concreet roept de lokale service aan:

```python
self.whisper_model.transcribe(
    str(audio_path),
    language="nl",
    beam_size=5,
    word_timestamps=True,
    vad_filter=True,
)
```

Geen `initial_prompt`, geen `hotwords`, geen `condition_on_previous_text`-overweging. Voor een huisartsenpraktijk in Limburg met medicatienamen, afkortingen en dialectinvloeden is dat de zwaarste plek om context weg te laten. De woordfouten die hierdoor ontstaan (medicatie, eponiemen, ICPC-termen) zijn precies de fouten die de arts daarna handmatig moet herstellen - en die nu nergens terugvloeien.

### 2.3 De diarisatie-heuristiek is fragiel

De toewijzing arts/patiënt gebeurt met de aanname "eerste spreker = arts". Dat klopt vaak niet: niet elk consult opent de arts, en bij een derde stem (kind, mantelzorger, tolk) valt het schema om. De diarisatie draait bovendien op segment-niveau, los van de woord-timestamps, terwijl een geforceerde alignment (wav2vec2, zoals WhisperX dat doet) de sprekergrens veel preciezer op de woordgrens legt. Verkeerde sprekerlabels vertalen zich direct naar een vervuilde S- en O-sectie in de SOEP.

### 2.4 De SOEP-generatie is goed doordacht maar niet afgedwongen

De prompts in `shared/prompts/templates.py` zijn van hoge kwaliteit: strikte anti-hallucinatie-instructies, telegramstijl, ICPC-suggestie, een apart detectiestadium voor rode vlaggen. Maar twee dingen ontbreken. De JSON-output wordt afgedwongen met Ollama's generieke `format: "json"`, niet met een **JSON-schema** - terwijl Ollama sinds v0.5 grammatica-gestuurde decoding op een concreet schema ondersteunt, wat zowel de betrouwbaarheid als de snelheid verhoogt. En er zijn geen **few-shot-voorbeelden** in de prompt; de modeloutput leunt volledig op instructies, niet op voorbeelden van hoe een goede SOEP in déze praktijk eruitziet. Dat laatste is de natuurlijke brug naar de zelflerende laag.

### 2.5 De feedbackloop is bedraad maar niet aangesloten

`consultation_feedback` bewaart origineel + gecorrigeerd transcript en SOEP, mét diff. `vocabulary_corrections` telt hoe vaak een correctie is toegepast en bevestigd. De infrastructuur om van correcties te leren is er dus - maar er is geen proces dat (a) uit de transcriptdiffs nieuwe vocabulaire-/hotword-kandidaten destilleert, (b) uit de SOEP-diffs few-shot-voorbeelden of stijlregels afleidt, en (c) die terugzet in de pipeline. De lus eindigt in de database in plaats van terug te komen bij het model.

---

## 3. Deel A - Transcriptiekwaliteit verhogen

### 3.1 Gratis winst: context teruggeven aan Whisper

De goedkoopste, veiligste en best onderbouwde ingreep is het meegeven van domeincontext. Twee mechanismen, met een belangrijk verschil:

- **`initial_prompt`** biast de decoder richting een stijl en algemene domeinwoordenschat. Whisper consumeert alleen de laatste ~224 tokens, dus de prompt moet compact zijn en de meest waardevolle termen achteraan plaatsen. Voor VitaScribe: een korte zin die de setting zet ("Transcript van een Nederlandstalig huisartsconsult. Termen o.a.: …") gevolgd door de meest voorkomende medicatie- en ICPC-termen.
- **`hotwords`** (ondersteund door Faster-Whisper) is bedoeld voor specifieke, zeldzame termen die het model anders mist. De vuistregel uit de praktijk: gebruik `initial_prompt` voor algemene jargon, en voeg `hotwords` toe voor de echt zeldzame namen.

De winst is reëel: geprompte Whisper haalde in onderzoek een **19% lagere WER** op medische audio met de top-200 medische termen. Cruciaal is dat VitaScribe deze lijst al heeft (`medical_vocabulary.get_hotwords()`), maar die alleen in de cloud-tak en alleen "voor toekomstig gebruik" inzet. Stap één is simpelweg: deze lijst ook in de lokale `transcribe()` injecteren.

Let op één bekend risico: een te lange of te generieke `initial_prompt` kan hallucinatie en herhaling juist vergroten. De prompt moet kort, specifiek en periodiek gevalideerd zijn op de testset (zie §6).

### 3.2 Naberekening ook lokaal toepassen

De dictionaire-naberekening (`correct_transcript_full`) die `metaformien → metformine` en `hoge bloeddruk → hypertensie`-achtige fouten herstelt, hoort in beide paden thuis. Dit is deterministisch, auditeerbaar en privacyneutraal - precies wat je in een medische context wilt: geen black box, maar een te inspecteren correctielijst. Het is dubbel werk dat nu maar half wordt gedaan.

### 3.3 LLM-gebaseerde foutcorrectie (post-ASR), met mate

Een krachtiger maar zwaardere stap is een tweede laag die niet op een woordenlijst maar op *context* corrigeert. Een LLM kan "high tension" → "hypertensie" of "pencil in" → "penicilline" herstellen op basis van de zin eromheen - fouten die een statische lijst nooit vangt. Dit kan met hetzelfde lokale Ollama-model als een aparte "ASR-correctie"-stap vóór de extractie.

De afweging: het verhoogt de latentie en introduceert een hallucinatierisico (het model kan "verbeteren" wat correct was). Daarom alleen toepassen op segmenten met lage Whisper-confidence (de `avg_logprob` is al beschikbaar), met een strikte instructie dat alleen evidente ASR-fouten gecorrigeerd mogen worden en de inhoud onaangetast blijft. Dit is een fase-2-ingreep, ná meting.

### 3.4 Modelkeuze: blijven, alignen, of overstappen

Vier opties, oplopend in impact en inspanning:

| Optie | Kwaliteitswinst | Inspanning | Privacy |
|---|---|---|---|
| `large-v3-turbo` houden + context/hotwords | Substantieel, gratis | Laag | Lokaal |
| Over naar **WhisperX** (wav2vec2-alignment + betere diarisatie) | Hoog op sprekertoewijzing en woord-timestamps | Middel | Lokaal |
| **Volledige `large-v3`** i.p.v. turbo (kwaliteit boven snelheid) | Klein-middel op WER | Laag (config) | Lokaal |
| Fine-tunen op NL (JASMIN-CGN) of NL-medische STT | Hoog, maar datahonger | Hoog | Lokaal |

Twee context-feiten wegen mee. Voor algemeen Nederlands presteerde Google Chirp 3 ~4,6 procentpunt beter dan Whisper-large-v3 (11,2% vs ~15,8% WER), en het Nederlandse Juvoly bouwde een eigen model juist omdat Whisper tekortschiet op medisch Nederlands - een signaal dat de bovengrens van out-of-the-box Whisper voor dit domein bestaat. Tegelijk toont onderzoek dat fine-tunen van Whisper op Nederlandse corpora WER-reducties van 65–81% gaf voor lastige sprekergroepen. De pragmatische route: eerst de gratis context-winst pakken (#1), dan WhisperX overwegen voor de diarisatie (#2), en fine-tunen pas op de agenda zetten zodra de feedbackloop genoeg gelabelde correctieparen heeft opgeleverd om mee te trainen (#4) - waarmee de zelflerende laag en de modelkeuze elkaar gaan versterken.

---

## 4. Deel B - SOEP-samenvatting verhogen

### 4.1 Dwing de structuur af met een JSON-schema

De overstap van `format: "json"` naar een **expliciet JSON-schema** in de Ollama-aanroep is laaghangend fruit. Ollama compileert het schema naar een grammatica en beperkt de tokensampler tot geldige voortzettingen; in metingen leverde dat niet alleen gegarandeerd valide JSON maar ook tot ~6× snellere generatie op. Voor VitaScribe betekent dit: geen kapotte JSON meer die de pipeline laat struikelen, en hardere garanties dat elk SOEP-veld en de ICPC-code aanwezig zijn. De schema's staan al in `shared/schemas/`; ze worden nu alleen ná generatie ter validatie gebruikt, niet vooraf ter sturing.

### 4.2 Hallucinatie blijft de kernrisico - bouw er een vangnet omheen

De literatuur over ambient scribes is eensluidend: AI-notities zijn vollediger en beter geordend dan menselijke, maar minder bondig en hallucinatiegevoeliger - het model "gokt de meest waarschijnlijke reden" en schrijft die als feit op, en juist die fouten zijn voor de controlerende arts moeilijk te spotten. VitaScribe doet hier al goed aan met strikte anti-hallucinatie-instructies en een telegramstijl-eis. Twee versterkingen liggen voor de hand. Een **grounding-controle**: een verificatiestap die elke bewering in de SOEP terugkoppelt naar een fragment in het transcript en het anders markeert (de codebase heeft al een `[?]`-conventie en een detectiestadium - dit is de natuurlijke plek). En een **bondigheidsrem**: een expliciete lengtebegrenzing per veld, omdat juist de breedsprakigheid van scribes de hallucinatie binnensluipt.

Een nuchtere bevinding uit recent vergelijkend onderzoek relativeert de modeljacht: een "naïeve" oplossing op een basismodel (zonder medische fine-tuning) scoorde vergelijkbaar met commerciële koplopers. De meerwaarde van domeinspecifieke training in scribes blijkt beperkt zodra het basismodel sterk genoeg is. Voor VitaScribe betekent dat: investeer eerder in prompts, grounding en few-shot dan in een medisch fine-getuned model.

### 4.3 Modelkeuze voor extractie en SOEP

`llama3.1:8b` is een redelijke ondergrens, maar voor Nederlandse medische redenering zijn er in 2026 sterkere lokale kandidaten. Qwen 2.5 scoort goed op meertaligheid en heeft efficiënte Nederlandse tokenisatie; Gemma 3 biedt een 128k-context en sterke samenvattingskwaliteit; Google's **MedGemma** is expliciet op medische taken afgestemd. De config voorziet al in een `fallback_model`, dus een A/B-opzet is goedkoop in te richten: dezelfde transcripten door twee modellen, scoren op de meetlat van §6, en het beste model promoveren. Belangrijk is dat dit een *gemeten* keuze wordt en geen onderbuikkeuze - de testset maakt dit mogelijk.

### 4.4 Few-shot uit de eigen praktijk

De sterkste SOEP-verbetering is tegelijk de brug naar Deel C: voeg aan de SOEP-prompt enkele **voorbeelden van goedgekeurde, door de arts gecorrigeerde SOEP's** toe (few-shot). Het model leert dan niet de algemene SOEP-regels maar de feitelijke stijl, het abstractieniveau en de afkortingsvoorkeuren van déze praktijk. Die voorbeelden komen rechtstreeks uit `consultation_feedback`. Hiermee wordt de prompt zelf een lerend artefact.

---

## 5. Deel C - De zelflerende laag (prioriteit)

Dit is waar VitaScribe zich onderscheidt van een generieke scribe: een systeem dat elke dag een beetje beter wordt op de taal, de patiëntenpopulatie en de stijl van déze praktijk. De infrastructuur ligt klaar; de lus moet worden gesloten. Ik onderscheid drie niveaus, oplopend in kracht en risico.

### 5.1 Niveau 1 - Vocabulaire die meegroeit (deterministisch, veilig)

Dit is het laaghangende, NEN-vriendelijke fruit en de logische eerste implementatie van "zelflerend".

De mechaniek: elke keer dat de arts in de review-UI een woord in het transcript corrigeert, ligt er een (fout → goed)-paar in `consultation_feedback.transcript_diff`. Een periodieke job (dagelijks/wekelijks) destilleert daaruit kandidaat-correcties, telt frequenties, en promoveert een correctie naar de actieve woordenlijst zodra ze vaak genoeg vóórkomt en door meerdere consulten/artsen is *bevestigd* (de velden `times_applied` en `times_confirmed` zijn daar al voor bedoeld). De gepromoveerde termen voeden twee dingen tegelijk: de deterministische naberekening én de Whisper-`hotwords` van de vólgende consulten. Zo corrigeert het systeem een term eerst achteraf, en gaat het die term daarna al goed verstáán.

Waarom dit het juiste startpunt is: het is volledig transparant en auditeerbaar (een mens kan de lijst lezen), het kan niet "wegglijden" zoals een fine-getuned model, en het past naadloos op de bestaande tabellen. De literatuur bevestigt dat gebruikerscorrecties juist op verse en stelselmatig foute termen de meeste ASR-winst geven - precies medicatie en eigennamen.

Eén ontwerpregel is belangrijk: bouw een **bevestigingsdrempel** in (bijv. ≥3 onafhankelijke bevestigingen) zodat een eenmalige typefout of dialectincident niet meteen de woordenlijst vervuilt. Bij sparse of ruizige feedback degradeert de adaptatiesnelheid - beter traag en zuiver dan snel en vervuild.

### 5.2 Niveau 2 - De prompt die meeleert (few-shot + stijlregels)

Het tweede niveau tilt de SOEP-kwaliteit op zonder ook maar één modelgewicht aan te raken. Uit de SOEP-diffs (`soep_diff`) zijn twee dingen te oogsten: concrete **few-shot-voorbeelden** (transcript → door-arts-goedgekeurde SOEP) en terugkerende **stijlcorrecties** (de arts schrapt stelselmatig een bepaalde frase, of codeert een klacht consequent anders). Een dynamische few-shot-selectie - kies de 2–3 meest gelijkende eerdere consulten bij een nieuw transcript - maakt de prompt context-specifiek. Dit is de methode die in de literatuur "latente voorkeur leren uit gebruikersbewerkingen" heet, en ze werkt juist goed wanneer feedback schaars is, omdat elk voorbeeld zwaar telt.

Het privacyaspect verdient aandacht: few-shot-voorbeelden bevatten patiëntinhoud. Ze moeten gepseudonimiseerd in een aparte, lokale voorbeeldbank staan en met dezelfde rechten worden beschermd als de consulten zelf. Omdat alles lokaal blijft, is dit goed verenigbaar met NEN 7510.

### 5.3 Niveau 3 - Het model dat meeleert (fine-tuning / preference learning)

Het zwaarste en krachtigste niveau, en bewust het laatste. Zodra de feedbackloop een paar honderd gecorrigeerde paren heeft verzameld, wordt fine-tunen haalbaar. Twee sporen:

- **STT-fine-tuning** van Whisper op de eigen (audio, gecorrigeerd transcript)-paren - de literatuur laat hier de grootste WER-reducties zien, en juist op de lastige NL/dialect-gevallen.
- **SOEP-preference-learning**: uit (gegenereerde SOEP, door-arts-gecorrigeerde SOEP)-paren ontstaan voorkeursparen (chosen/rejected) waarmee het LLM via lichte fine-tuning of DPO de praktijkstijl internaliseert. De vakliteratuur noemt 200–500 voorkeursparen als bruikbaar startpunt en adviseert te bootstrappen vanaf SFT-output plus menselijke edits - exact het materiaal dat `consultation_feedback` opslaat.

De afwegingen zijn reëel: fine-tunen vraagt GPU-tijd, MLOps-discipline (versiebeheer van modellen, rollback, regressietests op de testset) en governance (een fout-geleerd model is moeilijker te inspecteren dan een woordenlijst). Doe dit pas als niveau 1 en 2 zijn uitgput én de meetlat van §6 bewijst dat de winst er nog zit. Het is geen voorwaarde voor een goed product; het is de kers.

### 5.4 De architectuur van de lus

Schematisch sluit de lus zo:

```
Arts corrigeert (review-UI)
        │
        ▼
consultation_feedback  ──►  diff-analyse (periodieke job)
        │                          │
        │            ┌─────────────┼──────────────┐
        │            ▼             ▼              ▼
        │      vocab-kandidaten  few-shot-bank  trainingsparen
        │            │             │              │
        │            ▼             ▼              ▼
        │      hotwords +       SOEP-prompt    fine-tune
        │      naberekening     (dynamisch)    (periodiek)
        │            │             │              │
        └────────────┴─────────────┴──────────────┘
                     ▼
            betere volgende consulten
```

Niveau 1 voedt de linkertak (verstaan), niveau 2 de middentak (formuleren), niveau 3 de rechtertak (fundamenteel leren). Ze zijn onafhankelijk te bouwen en stapelen.

---

## 6. De meetlat: je kunt niet verbeteren wat je niet meet

Geen van het bovenstaande is stuurbaar zonder evaluatie. Dit is de stille randvoorwaarde van het hele plan en verdient een eigen, vroege investering.

Voor **transcriptie**: leg een vaste, gepseudonimiseerde testset van ~20–30 representatieve consultfragmenten vast met een handmatig geverifieerd "gouden" transcript. Meet daarop WER, en - minstens zo belangrijk voor dit domein - een aparte **medische-term-foutmarge** (hoe vaak gaat een medicatienaam of ICPC-term mis), want één foute medicatienaam weegt zwaarder dan tien foute lidwoorden. Elke STT-ingreep (hotwords, WhisperX, ander model) wordt tegen deze set afgerekend vóór hij naar productie gaat.

Voor **SOEP**: een rubric-gebaseerde score is hier de standaard geworden (volledigheid, correctheid, bondigheid, hallucinatievrijheid). Dit kan deels geautomatiseerd met een LLM-als-beoordelaar op een vaste set, maar de ankerpunten blijven de artsbeoordelingen. Een eenvoudige proxy die meteen werkt: de **edit-afstand tussen gegenereerde en goedgekeurde SOEP** - hoe minder de arts hoeft te corrigeren, hoe beter het systeem. Die metriek valt gratis uit de feedbackloop en is meteen een KPI voor de zelflerende laag: hij hoort over de maanden te dalen.

Zonder deze meetlat is de zelflerende laag blind; mét deze meetlat wordt elke promotie van een vocabulaireterm, elke promptwijziging en elke fine-tune een gemeten, terugdraaibare beslissing.

---

## 7. Gefaseerd implementatieplan

De volgorde is bewust: eerst meten en gratis winst, dan de lus sluiten, dan pas de zware modelingrepen.

**Fase 0 - Meetlat (fundament).** Leg de gepseudonimiseerde STT-testset en het gouden transcript vast. Implementeer WER + medische-term-foutmarge als script. Activeer de edit-afstand-metriek op de SOEP-feedback. Dit blokkeert niets en maakt al het volgende toetsbaar.

**Fase 1 - Gratis kwaliteitswinst (laag risico, lokaal).** Injecteer `initial_prompt` + `hotwords` in de lokale `transcribe()` vanuit de bestaande woordenlijst. Trek de dictionaire-naberekening door naar het lokale pad. Schakel de Ollama-aanroep over op JSON-schema-gestuurde decoding. Voeg een lengterem en grounding-markering toe aan de SOEP. Meet alles tegen Fase 0; verwacht de grootste prijs-kwaliteitssprong hier.

**Fase 2 - De lus sluiten (de prioriteit).** Bouw de periodieke diff-analyse-job die uit `consultation_feedback` vocabulaire-kandidaten promoveert (met bevestigingsdrempel) en de hotwords/naberekening voedt. Bouw de gepseudonimiseerde few-shot-bank en dynamische voorbeeldselectie in de SOEP-prompt. Verfijn de diarisatie (WhisperX-alignment of een betere arts/patiënt-heuristiek). Volg de edit-afstand-KPI om te bewijzen dat het systeem daadwerkelijk leert.

**Fase 3 - Fundamenteel leren (hoog rendement, hoge zorg).** Met voldoende verzamelde paren: A/B-test sterkere lokale LLM's (Qwen 2.5 / Gemma 3 / MedGemma) op de meetlat; verken Whisper-fine-tuning op de eigen correctieparen; en SOEP-preference-learning (DPO) op de chosen/rejected-paren. Met modelversiebeheer, regressietests en rollback.

---

## 8. Privacy- en complianceafweging

De gekozen volgorde is ook de privacyvriendelijke volgorde. Fase 0–2 blijven volledig binnen de lokale, NEN 7510-conforme grenzen: woordenlijsten en few-shot-banken zijn lokaal, gepseudonimiseerd en - anders dan een modelgewicht - door een mens te inspecteren en te corrigeren. Dat sluit aan bij het uitgangspunt uit `CLAUDE.md` dat verwerking lokaal blijft en audit-logs immutable zijn.

Twee punten verdienen expliciete governance. De few-shot-bank (Fase 2) bevat patiëntinhoud en moet onder hetzelfde rechten- en bewaarregime vallen als de consulten zelf, met pseudonimisering vóór opslag. En fine-tuning (Fase 3) creëert een afgeleide van patiëntdata in de modelgewichten; daarvoor zijn een DPIA-update, helder bewaar-/verwijderbeleid en de mogelijkheid tot "vergeten" (hertrainen zonder ingetrokken data) nodig. Geen van deze stappen vereist de cloud - uw "strikt lokaal"-uitgangspunt blijft over de hele linie haalbaar; een gepseudonimiseerde cloud-fallback (al voorzien in de config) is een optie, geen noodzaak.

---

## 9. Uitgevoerd in deze ronde (Fase 0 + Fase 1)

De volgende, veilige en volledig lokale wijzigingen zijn doorgevoerd:

- **Canonieke woordenlijst** verplaatst naar `shared/vocabulary.py` (de cloud-API-tak houdt bewust zijn eigen kopie omdat die los wordt gedeployd). Toegevoegd: `get_initial_prompt()` (compacte, hoog-signaal context binnen Whisper's tokenvenster) naast de bestaande `get_hotwords()`, plus meenemen van geleerde (custom) termen.
- **Lokale Whisper krijgt context terug** (`services/transcription/service.py`): `initial_prompt` + `hotwords` worden nu meegegeven, en het transcript wordt deterministisch nabewerkt via de woordenlijst. Het aantal correcties wordt geteld en gelogd. Aan/uit via env-vars (`WHISPER_USE_INITIAL_PROMPT`, `WHISPER_USE_HOTWORDS`, `WHISPER_POSTCORRECT`).
- **Structured output afgedwongen** (`services/extraction/service.py`): extractie, SOEP en detectie sturen nu het concrete JSON-schema mee aan Ollama (grammatica-gestuurde decoding) i.p.v. de generieke `"json"`-modus. De SOEP-prompt kreeg een expliciete bondigheidsrem en grounding-instructie.
- **Meetlat** (`shared/evaluation.py` + `tools/eval_transcription.py`): WER, medische-term-foutmarge en SOEP edit-distance, met een CLI en voorbeeld-testset (`tools/eval_samples/`). Pure stdlib, draait zonder GPU.
- **Tests** (`tests/test_vocabulary.py`, `tests/test_evaluation.py`): 16 unit tests, alle groen.

Wat bewust **niet** in deze ronde zit (vergt verzamelde feedbackdata én GPU-tijd): model-fine-tuning/DPO (Fase 3, zwaarste stap). De infrastructuur (`consultation_feedback`, custom-vocab-pad, edit-distance-KPI, gelabelde correctieparen) is hiervoor nu wél voorbereid.

### Fase 2, niveau 1 - de eerste zelflerende lus (geïmplementeerd)

De woordenlijst groeit nu automatisch mee met de praktijk:

- **Diff-miner** (`services/learning/diff_miner.py`): destilleert (fout → goed)-paren uit origineel vs. door de arts gecorrigeerd transcript via woord-alignment. Strikte filters tegen vervuiling: alleen korte vervangingen (geen toevoegingen/schrappingen), voldoende tekengelijkenis (waarschijnlijke verhoring, geen inhoudelijke herschrijving), geen cijfers, geen stopwoorden.
- **Learner** (`services/learning/vocabulary_learner.py`): telt bevestigingen over consulten heen en promoveert een correctie alleen bij een **bevestigingsdrempel** (standaard ≥3 onafhankelijke consulten) én een **dominantie-eis** (de dominante goed-variant ≥60%). Promoties worden idempotent geüpsert in `vocabulary_corrections`; hand-gemaakte (`manual`) correcties worden nooit overschreven.
- **Terugkoppeling**: de actieve correcties worden geëxporteerd naar `custom_vocabulary.json` - exact het bestand dat de transcriptieservice bij het opstarten inleest. Daarmee gaan geleerde termen meteen mee in zowel de **hotwords** (het systeem gaat de term beter verstáán) als de **naberekening** (het corrigeert hem alsnog).
- **Draaien**: `python tools/learn_vocabulary.py` (parameters: `--min-confirmations`, `--min-dominance`). Bedoeld om periodiek te draaien (cron/scheduler), bv. wekelijks.
- **Tests**: `tests/test_diff_miner.py` + `tests/test_vocabulary_learner.py`, inclusief een end-to-end run met in-memory sessie. Totaal nu 28 unit tests, alle groen.

Hiermee is de lus gesloten: artscorrectie → geleerde term → beter verstaan én gecorrigeerd in volgende consulten. De `min_confirmations`/`min_dominance`-knoppen maken de afweging tussen leersnelheid en zuiverheid expliciet en instelbaar.

### Fase 2, niveau 2 - de prompt die meeleert (geïmplementeerd)

De SOEP-generatie leert nu de stijl van de praktijk uit eerder goedgekeurde notities (dynamische few-shot):

- **Few-shot-bank** (`services/learning/fewshot_bank.py`): een lokale, gepseudonimiseerde voorbeeldbank. Retrieval gebeurt met gewogen token-gelijkenis (medische termen tellen dubbel) - dependency-vrij, geen embeddings, passend bij de lokale opzet. Een `scrub_pii`-laag verwijdert defensief namen, BSN's, e-mail en telefoonnummers.
- **Builder** (`services/learning/fewshot_builder.py` + `tools/build_fewshot_bank.py`): vult de bank uit `consultation_feedback.soep_corrected`, met een minimale kwaliteitseis (S én E aanwezig) en een bankplafond.
- **Integratie** (`services/extraction/service.py`): bij SOEP-generatie wordt uit de extractie een query gevormd, worden de top-k gelijkende voorbeelden geselecteerd en vóór de taak geplaatst, met de expliciete instructie "neem de stijl over, nooit de inhoud". Volledig backward-compatible: leeg of uitgeschakeld → ongewijzigd gedrag. Config via `FEWSHOT_ENABLED`, `FEWSHOT_K`, `FEWSHOT_BANK_PATH`.
- **Tests**: `tests/test_fewshot_bank.py` (retrieval, scrub, builder met in-memory sessie, promptformat, IO-roundtrip). Totaal nu 37 unit tests, alle groen.

Beide niveaus samen vormen de zelflerende kern: niveau 1 verbetert het *verstaan* (woordenlijst), niveau 2 verbetert het *formuleren* (stijl), beide gevoed door dezelfde artscorrecties - volledig lokaal en auditeerbaar.

### Periodiek draaien (geïmplementeerd)

Beide zelflerende jobs draaien automatisch op de praktijkserver: `scripts/run_learning_jobs.sh` (wrapper), een systemd-service + timer en een cron-alternatief in `deploy/`, met installatie-instructies in `docs/ZELFLEREND_SCHEDULING.md`. Standaard wekelijks (maandag 03:00), met inhaalslag bij een gemiste run.

### Fase 3 - diarisatie-upgrade (geïmplementeerd)

De fragiele "eerste spreker = arts"-aanname en de segment-niveau sprekertoewijzing (§2.3) zijn vervangen:

- **Woord-niveau alignment** (`services/transcription/diarization_align.py`): elk woord wordt toegewezen aan de spreker met de grootste temporele overlap en daarna hergegroepeerd tot zuivere beurten. Dit lost het kernprobleem op dat één Whisper-segment twee sprekers overspant (arts vraagt, patiënt antwoordt) en zo de S/O-scheiding vervuilt.
- **Rolherkenning** (`services/transcription/role_assignment.py`): arts vs. patiënt wordt bepaald op taalkundige cues - vragen stellen, beleid/advies geven en medische terminologie (arts) versus klachten in de ik-vorm (patiënt). Robuust voor wie het consult opent en voor een derde stem (kind/mantelzorger/tolk). De pipeline gebruikt woord-niveau wanneer woord-timestamps beschikbaar zijn en valt anders terug op segment-niveau - beide nu met de cue-gebaseerde rolbepaling.
- **Tests**: `tests/test_diarization.py`, inclusief een end-to-end merge die een tweesprekersegment correct splitst en de rollen toewijst. Totaal nu 45 unit tests, alle groen.

#### Fase 3 - forced-alignment & fine-tuning (geïmplementeerd, GPU-zijde)

De zwaarste laag is gebouwd en getest, klaar om op een GPU-machine te draaien zodra er genoeg feedback is:

- **WhisperX forced-alignment** (`services/transcription/whisperx_align.py`): optionele wav2vec2-verfijning van woord-timestamps (toggle `WHISPER_USE_FORCED_ALIGNMENT`), met automatische fallback naar Faster-Whisper. Voedt de woord-niveau diarisatie nóg preciezer.
- **Trainingsdata-export** (`services/learning/training/` + `tools/build_training_data.py`): bouwt uit `consultation_feedback` een ASR-postcorrectie-SFT-dataset (transcript→correctie, **geen audio nodig** - past binnen het audioverwijderbeleid) en een SOEP-DPO-voorkeursdataset (goedgekeurd = chosen, origineel = rejected), met kwaliteitsfilters en datadrempels.
- **Trainingsscripts**: `finetune_asr_correction.py` (mT5-SFT), `train_soep_dpo.py` (LoRA/DPO op het SOEP-LLM) en - alleen achter een expliciete consent/retentie-vlag - `finetune_whisper.py` (akoestische FT). Elk weigert te draaien onder de datadrempel.
- **Runbook**: `docs/FASE3_FINETUNING.md` met vereisten, procedure, en de verplichte evaluatie-en-rollback via de meetlat vóór productie.
- **Tests**: `tests/test_whisperx_align.py` + `tests/test_training_datasets.py` (pure mappers en data-builders). Totaal nu 53 unit tests, alle groen.

Bewuste ontwerpkeuze: omdat het privacybeleid audio na goedkeuring verwijdert, is de primaire STT-fine-tuning **tekstgebaseerd** (ASR-postcorrectie op de overvloedige transcriptcorrecties); akoestische Whisper-FT blijft optioneel en alleen mogelijk met aparte, toestemming-gedekte audio-retentie.

---

## 10. Bronnen

- [How to Improve Whisper Accuracy with Initial Prompts - Sotto](https://sotto.to/blog/improve-whisper-accuracy-prompts)
- [Improving Accuracy for OpenAI's Whisper - Incredigeek](https://www.incredigeek.com/home/improving-accuracy-for-openais-whisper/)
- [Lost in Transcription, Found in Distribution Shift: Demystifying Hallucination in Speech Foundation Models (arXiv)](https://arxiv.org/pdf/2502.12414)
- [A Custom-Built Ambient Scribe Reduces Cognitive Load and Documentation Burden for Telehealth Clinicians (arXiv)](https://arxiv.org/pdf/2507.17754)
- [Best open source speech-to-text (STT) model in 2026 - Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Improving the Inclusivity of Dutch Speech Recognition by Fine-tuning Whisper on the JASMIN-CGN Corpus (arXiv)](https://arxiv.org/abs/2502.17284)
- [How Juvoly built its own AI speech recognition to beat OpenAI's Whisper - Techzine](https://www.techzine.eu/blogs/infrastructure/129331/how-juvoly-built-its-own-ai-speech-recognition-to-beat-openais-whisper/)
- [Assessing the quality of AI-generated clinical notes - Frontiers in AI (2025)](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1691499/full)
- [An evaluation framework for ambient digital scribing tools - npj Digital Medicine](https://www.nature.com/articles/s41746-025-01622-1)
- [An LLM-Based Comparison of Ambient AI Scribes for Clinical Documentation (medRxiv)](https://www.medrxiv.org/content/10.1101/2025.06.24.25330085v1)
- [Structured outputs - Ollama Blog](https://ollama.com/blog/structured-outputs)
- [Ollama Structured Outputs in Practice with Pydantic](https://jangwook.net/en/blog/en/ollama-structured-outputs-pydantic-local-llm-guide-2026/)
- [WhisperX - Automatic Speech Recognition with Word-level Timestamps & Diarization (GitHub)](https://github.com/m-bain/whisperX)
- [Choosing between Whisper variants: faster-whisper, insanely-fast-whisper, WhisperX - Modal](https://modal.com/blog/choosing-whisper-variants)
- [The Gift of Feedback: Improving ASR Model Quality by Learning from User Corrections through Federated Learning (arXiv)](https://arxiv.org/pdf/2310.00141)
- [Customizing Speech Recognition Model with Large Language Model Feedback (arXiv)](https://arxiv.org/html/2506.11091v1)
- [Towards Understanding ASR Error Correction for Medical Conversations - ACL](https://aclanthology.org/2020.nlpmc-1.2/)
- [Aligning LLM Agents by Learning Latent Preference from User Edits (arXiv)](https://arxiv.org/pdf/2404.15269)
- [Adapting Open-Source LLMs for Cost-Effective, Expert-Level Clinical Note Generation with On-Policy RL (arXiv)](https://arxiv.org/html/2405.00715v4)
- [Fietje: An open, efficient LLM for Dutch (arXiv)](https://arxiv.org/pdf/2412.15450)
- [LLM Model Selection Guide: Qwen, Mistral, Llama, and Gemma Compared](https://dasroot.net/posts/2026/01/llm-model-selection-guide-qwen-mistral-llama-gemma/)

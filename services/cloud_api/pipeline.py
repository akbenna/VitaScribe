"""
VitaScribe Cloud API - Processing Pipeline

Orchestrates the full flow: Audio → STT → SOEP → Decisief Regel → Detection
Single entry point for the Chrome extension.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from . import data_policy, llm_service, stt_service, talen
from .medical_vocabulary import correct_transcript_full, CorrectionStats
from .prompts import (
    SOEP_CONTROLE_JSON_SCHEMA,
    SOEP_CONTROLE_SYSTEM_PROMPT,
    SOEP_CONTROLE_USER_TEMPLATE,
    NAZORG_SYSTEM_PROMPT,
    NAZORG_USER_TEMPLATE,
    SOEP_JSON_SCHEMA,
    SOEP_SYSTEM_PROMPT,
    SOEP_USER_TEMPLATE,
)

logger = structlog.get_logger()

# Output-token budgetten per call-type. Output is bij Claude 5x duurder dan
# input, dus krap begroten waar het kan voorkomt onnodige kosten en runaway.
# Ruim genoeg voor meerdere SOEP-delen (een consult met 2-4 problemen).
SOEP_MAX_TOKENS = 1600
MAX_PROBLEMEN = 4
SOEP_VELDEN = ("s", "o", "e", "p", "icpc_code", "icpc_titel")
MIN_WOORDEN = 12   # fewer recognised words than this: no report (see verwerk_transcript)
NAZORG_MAX_TOKENS = 1000


@dataclass
class SOEPResult:
    s: str = ""
    o: str = ""
    e: str = ""
    p: str = ""
    icpc_code: str = ""
    icpc_titel: str = ""
    # One part per separate health problem; the fields above are part 1.
    problemen: List[Dict[str, str]] = field(default_factory=list)


def soep_met_problemen(data: dict) -> Dict:
    """Model output -> {s, o, e, p, icpc_code, icpc_titel, problemen}.

    "problemen" always holds at least one part, and the top-level fields are
    the first part, so a client that knows only one SOEP line still inserts
    something sensible. Parts without any content are dropped."""
    def schoon(d: dict) -> Dict[str, str]:
        return {k: str(d.get(k) or "").strip() for k in ("titel",) + SOEP_VELDEN}

    delen = []
    for d in data.get("problemen") or []:
        if isinstance(d, dict):
            deel = schoon(d)
            if any(deel[k] for k in ("s", "o", "e", "p")):
                delen.append(deel)
    delen = delen[:MAX_PROBLEMEN]
    if not delen:
        deel = schoon(data)
        deel["titel"] = deel["icpc_titel"]
        delen = [deel]
    uit = {k: delen[0][k] for k in SOEP_VELDEN}
    uit["problemen"] = delen
    return uit


@dataclass
class DetectionResult:
    rode_vlaggen: List[Dict] = field(default_factory=list)
    ontbrekende_info: List[Dict] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Complete result from a single consultation processing."""

    transcript: str = ""
    transcript_raw: str = ""
    transcript_corrections: int = 0
    soep: SOEPResult = field(default_factory=SOEPResult)
    decisief: str = ""
    detection: DetectionResult = field(default_factory=DetectionResult)
    duration_secs: float = 0.0
    stt_provider: str = ""
    llm_provider: str = ""
    # EU mode: what the control pass found unsupported; shown, never removed.
    markeringen: List[Dict] = field(default_factory=list)
    # Per report sentence the passage of the conversation it rests on (bronnen.py).
    bronnen: List[Dict] = field(default_factory=list)
    # What the doctor agreed in P, so the work after the consult can be set up (afspraken_uit).
    afspraken: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        soep = asdict(self.soep)
        if self.markeringen:
            soep["markeringen"] = self.markeringen
        if self.bronnen:
            soep["bronnen"] = self.bronnen
        if self.afspraken:
            soep["afspraken"] = self.afspraken
        return {
            "transcript": self.transcript,
            "transcript_raw": self.transcript_raw,
            "transcript_corrections": self.transcript_corrections,
            "soep": soep,
            "decisief": self.decisief,
            "detection": asdict(self.detection),
            "duration_secs": self.duration_secs,
            "stt_provider": self.stt_provider,
            "llm_provider": self.llm_provider,
        }


def _nazorg_velden(soep: SOEPResult) -> Dict[str, str]:
    """S/O/E/P for the decisief line; with several problems, all of them,
    numbered, so the line covers the whole consult."""
    delen = soep.problemen if len(soep.problemen) > 1 else []
    if not delen:
        return {"s": soep.s, "o": soep.o, "e": soep.e, "p": soep.p,
                "icpc_code": soep.icpc_code or "-", "icpc_titel": soep.icpc_titel or "-"}
    samen = lambda k: " ".join(f"({i}) {d[k]}" for i, d in enumerate(delen, 1) if d.get(k))
    return {"s": samen("s"), "o": samen("o"), "e": samen("e"), "p": samen("p"),
            "icpc_code": ", ".join(d["icpc_code"] for d in delen if d.get("icpc_code")) or "-",
            "icpc_titel": ", ".join(d["icpc_titel"] for d in delen if d.get("icpc_titel")) or "-"}


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


async def genereer_soep(gesprek: str, llm_provider: Optional[str] = None,
                        taal: Optional[str] = None, model: Optional[str] = None,
                        taalregel: Optional[str] = None, huisstijl: bool = True) -> SOEPResult:
    """One SOEP call on a (corrected) conversation per speaker. Raises on failure.

    taalregel: replaces the language line from talen.py (the interpreter
    brings its own: who spoke which language, and that it was translated)."""
    regel = taalregel if taalregel is not None else talen.prompt_regel(talen.kies(taal))
    if huisstijl:
        # What VitaScribe learned from this doctor (leren.py): style and spelling, never content.
        from . import leren
        regel = await leren.huisstijl_prompt() + regel
    antwoord = await llm_service.complete(
        system_prompt=SOEP_SYSTEM_PROMPT,
        user_prompt=regel + SOEP_USER_TEMPLATE.format(transcript=gesprek),
        provider=llm_provider,
        json_mode=True,
        max_tokens=SOEP_MAX_TOKENS,
        quality=True,
        json_schema=SOEP_JSON_SCHEMA,
        model=model,
    )
    return SOEPResult(**soep_met_problemen(_parse_json_response(antwoord)))


MAX_HULPVRAAG = 240


def markeringen_uit(soep: SOEPResult, controle: dict) -> List[Dict]:
    """The control pass as markings for the doctor. Nothing is removed or
    added: the report stays exactly as written; the doctor decides. A fragment
    that is not in the report is dropped, so a marking always points at text
    the doctor can see."""
    delen = soep.problemen or [{k: getattr(soep, k) for k in SOEP_VELDEN}]
    markeringen: List[Dict] = []
    for item in controle.get("schrappen") or []:
        if not isinstance(item, dict):
            continue
        veld, tekst = str(item.get("veld") or "").lower(), str(item.get("tekst") or "").strip()
        try:
            nr = int(item.get("probleem") or 0)
        except (TypeError, ValueError):
            nr = 0
        if veld not in ("s", "o", "e", "p") or len(tekst) < 2 or not 0 <= nr < len(delen):
            continue
        if tekst.lower() not in str(delen[nr].get(veld) or "").lower():
            continue
        markeringen.append({"probleem": nr, "veld": veld, "tekst": tekst,
                            "reden": str(item.get("reden") or "")[:200]})
    hulpvraag = str(controle.get("hulpvraag") or "").strip()[:MAX_HULPVRAAG]
    if hulpvraag:
        markeringen.append({"probleem": 0, "veld": "s", "tekst": "",
                            "reden": "hulpvraag ontbreekt mogelijk: " + hulpvraag})
    return markeringen


AFSPRAAK_SOORTEN = ("verwijzing", "controle", "onderzoek", "recept", "voorlichting", "brief", "vangnet", "overig")
MAX_AFSPRAKEN = 10


def afspraken_uit(ruw, plan: str) -> List[Dict]:
    """The agreements of the consult, only what the plan (P) says.

    This is documentation, not advice: an agreement the language model adds
    that is not in P (most of its words not found there) is dropped, so
    VitaScribe never proposes something the doctor did not agree."""
    from .bronnen import _gevonden, _woorden
    plan_woorden = _woorden(plan)
    plan_set = set(plan_woorden)
    uit: List[Dict] = []
    for item in ruw if isinstance(ruw, list) else []:
        if not isinstance(item, dict):
            continue
        soort = str(item.get("soort") or "").strip().lower()
        tekst = str(item.get("tekst") or "").strip()[:300]
        woorden = _woorden(tekst)
        if soort not in AFSPRAAK_SOORTEN or not woorden:
            continue
        gevonden = sum(_gevonden(w, plan_woorden, plan_set) > 0 for w in woorden) / len(woorden)
        if gevonden < 0.7:
            logger.info("pipeline.afspraak_niet_in_p", soort=soort)
            continue
        uit.append({"soort": soort, "tekst": tekst,
                    "naar": str(item.get("naar") or "").strip()[:80] if soort == "verwijzing" else "",
                    "wanneer": str(item.get("wanneer") or "").strip()[:40]})
        if len(uit) >= MAX_AFSPRAKEN:
            break
    return uit


async def controleer_soep(gesprek: str, soep: SOEPResult, llm_provider: Optional[str] = None,
                          model: Optional[str] = None) -> List[Dict]:
    """Second pass: the report next to the transcript; the model names the
    fragments the conversation does not support. Returns markings for the
    doctor (see markeringen_uit); the report itself is not changed. Raises on
    failure (the caller then shows the report without markings)."""
    delen = soep.problemen or [{k: getattr(soep, k) for k in SOEP_VELDEN}]
    notitie = json.dumps({"problemen": [{k: d.get(k, "") for k in ("s", "o", "e", "p", "icpc_code", "icpc_titel")}
                                        for d in delen]}, ensure_ascii=False)
    antwoord = await llm_service.complete(
        system_prompt=SOEP_CONTROLE_SYSTEM_PROMPT,
        user_prompt=SOEP_CONTROLE_USER_TEMPLATE.format(transcript=gesprek, soep=notitie),
        provider=llm_provider,
        json_mode=True,
        max_tokens=SOEP_MAX_TOKENS,
        quality=True,
        json_schema=SOEP_CONTROLE_JSON_SCHEMA,
        model=model,
    )
    return markeringen_uit(soep, _parse_json_response(antwoord))


async def process_consultation(
    audio_path: Path,
    stt_provider: str = None,
    llm_provider: str = None,
    deepgram_key: str = None,
    nadictaat_vanaf: Optional[float] = None,
    taal: Optional[str] = None,
) -> PipelineResult:
    """
    Process a consultation audio file through the full pipeline.

    nadictaat_vanaf: seconde van de opname waarop de arts "Nadicteren" koos.

    Steps:
    1. Transcribe audio (STT)
    2. Generate SOEP note (LLM)
    3. Generate decisief regel (LLM)
    4. Detect red flags (LLM)
    """
    # AVG: the browser cannot pick a non-EU service for patient data.
    stt_provider = data_policy.stt_provider(stt_provider)

    # ── Step 1: Transcription ──
    logger.info("pipeline.step", step="transcription")
    gekozen = talen.kies(taal)
    transcript = await stt_service.transcribe(audio_path, provider=stt_provider, deepgram_key=deepgram_key,
                                              language=gekozen.deepgram)
    stt_service.markeer_nadictaat(transcript, nadictaat_vanaf)
    try:
        grootte = f"{audio_path.stat().st_size / 1024:.1f} KB"
    except OSError:
        grootte = "onbekend"
    return await verwerk_transcript(transcript, llm_provider=llm_provider, bestandsgrootte=grootte,
                                    taal=gekozen.code)


async def verwerk_transcript(
    transcript: "stt_service.TranscriptResult",
    llm_provider: str = None,
    bestandsgrootte: str = "",
    taal: Optional[str] = None,
    taalregel: Optional[str] = None,
) -> PipelineResult:
    """Van transcript naar SOEP, decisief en aandachtspunten.

    Een opgenomen consult komt hier via process_consultation; een live
    gevolgd consult (consult_live) brengt zijn transcript zelf mee.
    """
    result = PipelineResult()
    llm_provider = data_policy.phi_llm_provider(llm_provider)
    result.transcript_raw = transcript.raw_text
    result.duration_secs = transcript.duration_secs
    result.stt_provider = transcript.provider

    # ── Step 1b: Medical vocabulary postprocessing ──
    # Per spreker, zodat het taalmodel weet wie wat zegt (zie met_sprekers).
    gesprek = stt_service.met_sprekers(transcript)
    if transcript.raw_text.strip():
        corrected_text, correction_stats = correct_transcript_full(gesprek)
        result.transcript = corrected_text
        result.transcript_corrections = correction_stats.total_corrections

        if correction_stats.total_corrections > 0:
            logger.info(
                "pipeline.vocabulary_corrections",
                total=correction_stats.total_corrections,
                medication=correction_stats.medication_corrections,
                medical_terms=correction_stats.medical_term_corrections,
                icpc=correction_stats.icpc_corrections,
                local=correction_stats.local_corrections,
                corrections=correction_stats.corrections_applied[:10],
            )
    else:
        result.transcript = transcript.raw_text

    if not transcript.raw_text.strip():
        logger.warning(
            "pipeline.empty_transcript",
            duration_secs=transcript.duration_secs,
            provider=transcript.provider,
        )
        result.decisief = (
            f"Geen spraak gedetecteerd. "
            f"Audio duur: {transcript.duration_secs:.1f}s, "
            f"Provider: {transcript.provider}"
            + (f", Bestandsgrootte: {bestandsgrootte}" if bestandsgrootte else "")
        )
        return result

    # Too little speech: a language model asked for a report of a few words
    # invents a whole consult (in a test, 6 characters became a diabetes
    # consult). Then no report at all, and say why.
    woorden = len(transcript.raw_text.split())
    if woorden < MIN_WOORDEN:
        logger.warning("pipeline.te_weinig_spraak", woorden=woorden,
                       duration_secs=transcript.duration_secs, provider=transcript.provider)
        result.decisief = (
            f"Te weinig spraak herkend ({woorden} woord{'en' if woorden != 1 else ''} in "
            f"{transcript.duration_secs / 60:.1f} min opname); er is geen verslag gemaakt. "
            "Controleer of de microfoon het gesprek hoort."
        )
        return result

    # ── Step 2: SOEP Generation ──
    logger.info("pipeline.step", step="soep_generation")
    try:
        result.soep = await genereer_soep(result.transcript, llm_provider, taal, taalregel=taalregel)
        result.llm_provider = llm_provider or "default"
    except Exception as e:
        logger.error("pipeline.soep_error", error=str(e))
        result.soep = SOEPResult(s="Fout bij SOEP generatie.", e=str(e))
    else:
        # ── Step 2b: control pass (EU mode): mark what the conversation does not support ──
        if data_policy.eu_modus():
            try:
                result.markeringen = await controleer_soep(result.transcript, result.soep, llm_provider)
            except Exception as e:  # the report stands without these markings
                logger.warning("pipeline.controle_fout", error=type(e).__name__)
            # The fixed check next to it: free, and it does not depend on the model.
            from .soeptest import vaste_markeringen   # soeptest imports pipeline
            delen = result.soep.problemen or [{k: getattr(result.soep, k) for k in SOEP_VELDEN}]
            gezien = {m["tekst"].lower() for m in result.markeringen if m.get("tekst")}
            for m in vaste_markeringen(delen, result.transcript):
                if not m["tekst"] or m["tekst"].lower() not in gezien:
                    result.markeringen.append(m)
            logger.info("pipeline.controle", markeringen=len(result.markeringen),
                        vast=sum(1 for m in result.markeringen if m.get("bron") == "vast"))

        # ── Step 2c: sources (both modes): per sentence where in the conversation it was said ──
        # No language model: free, nothing extra leaves the server, a source cannot be invented.
        try:
            from .bronnen import bronnen_bij_soep
            delen = result.soep.problemen or [{k: getattr(result.soep, k) for k in SOEP_VELDEN}]
            result.bronnen = bronnen_bij_soep(result.transcript, delen)
            logger.info("pipeline.bronnen", zinnen=len(result.bronnen),
                        met_bron=sum(1 for b in result.bronnen if b["status"] == "bron"),
                        zonder=sum(1 for b in result.bronnen if b["status"] == "geen"))
        except Exception as e:  # the report stands without sources
            logger.warning("pipeline.bronnen_fout", error=type(e).__name__)

    # ── Step 3: Nazorg (decisief regel + rode vlaggen) in EEN call ──
    # Beide taken werken op de SOEP; samenvoegen scheelt een derde LLM-call.
    logger.info("pipeline.step", step="nazorg")
    try:
        nazorg_response = await llm_service.complete(
            system_prompt=NAZORG_SYSTEM_PROMPT,
            user_prompt=NAZORG_USER_TEMPLATE.format(**_nazorg_velden(result.soep)),
            provider=llm_provider,
            json_mode=True,
            max_tokens=NAZORG_MAX_TOKENS,
        )
        nazorg_data = _parse_json_response(nazorg_response)
        result.decisief = str(nazorg_data.get("decisief", "")).strip().strip('"').strip("'")
        result.detection = DetectionResult(
            # MDR: no clinical alarm signals unless explicitly enabled.
            rode_vlaggen=(nazorg_data.get("rode_vlaggen", [])
                          if data_policy.clinical_decision_support() else []),
            ontbrekende_info=nazorg_data.get("ontbrekende_info", []),
        )
        result.afspraken = afspraken_uit(nazorg_data.get("afspraken"), _nazorg_velden(result.soep)["p"])
    except Exception as e:
        logger.error("pipeline.nazorg_error", error=str(e))
        result.decisief = "Fout bij generatie decisief regel."

    return result

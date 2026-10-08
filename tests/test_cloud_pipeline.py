"""
Tests voor de geoptimaliseerde cloud_api Claude-route.

Dekt:
  - JSON-prefill in de Anthropic-call (geldige JSON zonder markdown-fences)
  - Per-call max_tokens doorgifte
  - Samengevoegde nazorg-stap (decisief + detectie in EEN LLM-call)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.cloud_api import llm_service, pipeline


@pytest.fixture(autouse=True)
def _korte_testgesprekken(request, monkeypatch):
    """The fake transcripts here are a few words; the guard against too little
    speech has its own test."""
    if "te_weinig_spraak" not in request.node.name:
        monkeypatch.setattr(pipeline, "MIN_WOORDEN", 1)


# ── Anthropic JSON-prefill ──

@pytest.mark.asyncio
async def test_anthropic_json_prefill_prepends_brace():
    """Bij json_mode stuurt de prefill een '{' mee en plakt die terug."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(
        return_value={
            "content": [{"text": '"s": "klacht"}'}],  # zonder leidende '{'
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }
    )

    client = AsyncMock()
    client.post = AsyncMock(return_value=fake_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    cfg = MagicMock()
    cfg.llm.anthropic_api_key = "test-key"
    cfg.llm.anthropic_model = "claude-haiku-4-5-20251001"
    cfg.llm.temperature = 0.1
    cfg.llm.max_tokens = 2048

    with patch.object(llm_service, "get_config", return_value=cfg), \
         patch.object(llm_service.httpx, "AsyncClient", return_value=client):
        out = await llm_service.complete(
            system_prompt="sys",
            user_prompt="usr",
            provider="anthropic",
            json_mode=True,
            max_tokens=300,
        )

    # Resultaat is geldige JSON dankzij teruggeplakte '{'
    assert json.loads(out) == {"s": "klacht"}

    # max_tokens en assistant-prefill correct meegestuurd
    body = client.post.call_args.kwargs["json"]
    assert body["max_tokens"] == 300
    assert body["messages"][-1] == {"role": "assistant", "content": "{"}
    assert isinstance(body["system"], list)


# ── Samengevoegde nazorg-stap ──

@pytest.mark.asyncio
async def test_pipeline_merges_decisief_and_detection_into_one_call():
    """SOEP = 1 call, nazorg (decisief+detectie) = 1 call: totaal 2 LLM-calls."""
    soep_json = json.dumps({
        "s": "3d keelpijn", "o": "geen LO", "e": "virale faryngitis",
        "p": "expectatief", "icpc_code": "R74.01", "icpc_titel": "Acute infectie bovenste luchtwegen",
    })
    nazorg_json = json.dumps({
        "decisief": "Mw. 3d keelpijn → virale faryngitis (R74.01), expectatief",
        "rode_vlaggen": [],
        "ontbrekende_info": [{"veld": "allergieen", "beschrijving": "x", "prioriteit": "laag"}],
    })

    transcript = MagicMock()
    transcript.raw_text = "Goedemorgen, ik heb al drie dagen keelpijn."
    transcript.duration_secs = 42.0
    transcript.provider = "deepgram"

    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])

    with patch.object(pipeline.stt_service, "transcribe",
                      new=AsyncMock(return_value=transcript)), \
         patch.object(pipeline.llm_service, "complete", new=complete_mock), \
         patch.object(pipeline, "correct_transcript_full",
                      return_value=(transcript.raw_text, MagicMock(total_corrections=0))):
        result = await pipeline.process_consultation(Path("/fake/audio.wav"))

    # Precies 2 LLM-calls (geen aparte decisief + detection meer)
    assert complete_mock.await_count == 2

    # Decisief en detectie komen uit de gecombineerde nazorg-call
    assert result.soep.icpc_code == "R74.01"
    assert "virale faryngitis" in result.decisief
    assert result.detection.rode_vlaggen == []
    assert result.detection.ontbrekende_info[0]["veld"] == "allergieen"

    # Per-call max_tokens correct doorgegeven
    soep_call, nazorg_call = complete_mock.await_args_list
    assert soep_call.kwargs["max_tokens"] == pipeline.SOEP_MAX_TOKENS
    assert nazorg_call.kwargs["max_tokens"] == pipeline.NAZORG_MAX_TOKENS


# ── Sprekers: wie zegt wat ──

from services.cloud_api import stt_service  # noqa: E402
from services.cloud_api.medical_vocabulary import correct_transcript_full  # noqa: E402


def _uiting(spreker, tekst):
    return stt_service.TranscriptSegment(text=tekst, start=0.0, end=1.0, speaker=spreker)


def _gesprek(*uitingen):
    tekst = " ".join(t for _, t in uitingen)
    return stt_service.TranscriptResult(
        raw_text=tekst, segments=[_uiting(s, t) for s, t in uitingen], provider="deepgram")


def test_met_sprekers_zet_elke_beurt_op_een_eigen_regel():
    t = _gesprek(("spreker_0", "Wat kan ik voor u doen?"),
                 ("spreker_1", "Ik heb al drie dagen keelpijn."),
                 ("spreker_1", "En koorts."),
                 ("spreker_0", "Ik kijk even in uw keel."))
    assert stt_service.met_sprekers(t) == (
        "Spreker 1: Wat kan ik voor u doen?\n"
        "Spreker 2: Ik heb al drie dagen keelpijn. En koorts.\n"
        "Spreker 1: Ik kijk even in uw keel.")


def test_met_sprekers_nummert_op_volgorde_van_binnenkomst():
    """Deepgram kan met spreker 3 beginnen; het model ziet gewoon Spreker 1."""
    t = _gesprek(("spreker_3", "Goedemorgen."), ("spreker_0", "Goedemorgen dokter."))
    assert stt_service.met_sprekers(t).startswith("Spreker 1: Goedemorgen.\nSpreker 2:")


def test_met_sprekers_laat_een_enkele_stem_ongemoeid():
    t = _gesprek(("spreker_0", "Pt drie dagen keelpijn."), ("spreker_0", "Geen koorts."))
    assert stt_service.met_sprekers(t) == t.raw_text


def test_met_sprekers_zonder_sprekers_of_segmenten():
    zonder = stt_service.TranscriptResult(
        raw_text="tekst", segments=[stt_service.TranscriptSegment(text="tekst", start=0, end=1)])
    assert stt_service.met_sprekers(zonder) == "tekst"
    assert stt_service.met_sprekers(stt_service.TranscriptResult(raw_text="los")) == "los"


def test_woordcorrectie_laat_de_sprekerlabels_staan():
    tekst = "Spreker 1: Hoe gaat het?\nSpreker 2: Ik gebruik metformine."
    uit, _ = correct_transcript_full(tekst)
    assert uit.splitlines()[0].startswith("Spreker 1:")
    assert uit.splitlines()[1].startswith("Spreker 2:")


@pytest.mark.asyncio
async def test_pipeline_geeft_het_gesprek_per_spreker_aan_het_taalmodel():
    soep_json = json.dumps({"s": "3d keelpijn", "o": "", "e": "", "p": "",
                            "icpc_code": "R74", "icpc_titel": "x"})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    t = _gesprek(("spreker_0", "Wat kan ik voor u doen?"),
                 ("spreker_1", "Ik heb al drie dagen keelpijn."))
    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])

    with patch.object(pipeline.stt_service, "transcribe", new=AsyncMock(return_value=t)), \
         patch.object(pipeline.llm_service, "complete", new=complete_mock):
        result = await pipeline.process_consultation(Path("/fake/audio.wav"))

    prompt = complete_mock.await_args_list[0].kwargs["user_prompt"]
    assert "Spreker 1: Wat kan ik voor u doen?\nSpreker 2: Ik heb al drie dagen keelpijn." in prompt
    assert result.transcript.startswith("Spreker 1:")
    assert result.transcript_raw == t.raw_text


def test_soep_prompt_kent_de_sprekerlabels():
    assert "Spreker 1" in pipeline.SOEP_SYSTEM_PROMPT
    assert "heteroanamnese" in pipeline.SOEP_SYSTEM_PROMPT


# ── Nadictaat: de arts dicteert na het consult ──

def _gesprek_met_tijden(*uitingen):
    segs = [stt_service.TranscriptSegment(text=t, start=b, end=e, speaker=s) for s, t, b, e in uitingen]
    return stt_service.TranscriptResult(raw_text=" ".join(u[1] for u in uitingen), segments=segs)


def test_nadictaat_komt_als_laatste_blok_van_de_arts():
    t = _gesprek_met_tijden(("spreker_0", "Wat is er?", 0, 2), ("spreker_1", "Keelpijn.", 2, 4),
                            ("spreker_0", "Keel rood, geen beslag. Beleid expectatief.", 60, 66))
    stt_service.markeer_nadictaat(t, 55.0)
    assert stt_service.met_sprekers(t) == (
        "Spreker 1: Wat is er?\nSpreker 2: Keelpijn.\n"
        "Nadictaat arts: Keel rood, geen beslag. Beleid expectatief.")


def test_nadictaat_telt_op_het_midden_van_een_uiting():
    t = _gesprek_met_tijden(("spreker_0", "net ervoor", 50, 56), ("spreker_0", "net erna", 54, 62))
    stt_service.markeer_nadictaat(t, 55.0)
    assert [s.speaker for s in t.segments] == ["spreker_0", stt_service.NADICTAAT]


def test_nadictaat_ook_bij_een_enkele_stem_of_zonder_sprekers():
    t = _gesprek_met_tijden(("", "pt keelpijn", 0, 3), ("", "LO keel rood", 30, 33))
    stt_service.markeer_nadictaat(t, 20.0)
    assert stt_service.met_sprekers(t) == "pt keelpijn\nNadictaat arts: LO keel rood"


def test_zonder_nadictaat_verandert_er_niets():
    t = _gesprek_met_tijden(("spreker_0", "a", 0, 1), ("spreker_1", "b", 1, 2))
    voor = stt_service.met_sprekers(t)
    stt_service.markeer_nadictaat(t, None)
    assert stt_service.met_sprekers(t) == voor


def test_soep_prompt_laat_het_nadictaat_leiden():
    assert "Nadictaat arts" in pipeline.SOEP_SYSTEM_PROMPT
    assert "volg dan het nadictaat" in pipeline.SOEP_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_upload_route_markeert_het_nadictaat():
    t = _gesprek_met_tijden(("spreker_0", "Wat is er?", 0, 2), ("spreker_1", "Keelpijn.", 2, 4),
                            ("spreker_0", "Keel rood.", 40, 42))
    soep_json = json.dumps({"s": "", "o": "keel rood", "e": "", "p": "", "icpc_code": "", "icpc_titel": ""})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])
    with patch.object(pipeline.stt_service, "transcribe", new=AsyncMock(return_value=t)), \
         patch.object(pipeline.llm_service, "complete", new=complete_mock):
        await pipeline.process_consultation(Path("/fake/audio.wav"), nadictaat_vanaf=30.0)
    prompt = complete_mock.await_args_list[0].kwargs["user_prompt"]
    assert "Nadictaat arts: Keel rood." in prompt


# ── Meerdere problemen: elk een eigen SOEP-deel, één decisiefregel ──

@pytest.mark.asyncio
async def test_pipeline_keeps_parts_and_decisief_covers_all():
    delen = [
        {"titel": "Keelpijn", "s": "3d keelpijn", "o": "keel rood", "e": "virale faryngitis",
         "p": "paracetamol", "icpc_code": "R74", "icpc_titel": "Acute infectie bovenste luchtwegen"},
        {"titel": "Somberheid", "s": "somber sinds 2 mnd, slaapt slecht", "o": "", "e": "depressieve klachten",
         "p": "POH-GGZ", "icpc_code": "P03", "icpc_titel": "Depressief gevoel"},
    ]
    soep_json = json.dumps({**{k: delen[0][k] for k in pipeline.SOEP_VELDEN}, "problemen": delen})
    nazorg_json = json.dumps({"decisief": "Keelpijn (R74) en somberheid (P03)", "rode_vlaggen": [], "ontbrekende_info": []})
    transcript = MagicMock(raw_text="keelpijn en ook somber", duration_secs=60.0, provider="deepgram")
    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])
    with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
         patch.object(pipeline.stt_service, "met_sprekers", return_value="keelpijn en ook somber"), \
         patch.object(pipeline, "correct_transcript_full", return_value=("keelpijn en ook somber", MagicMock(total_corrections=0))):
        result = await pipeline.verwerk_transcript(transcript)
    out = result.to_dict()["soep"]
    assert [d["titel"] for d in out["problemen"]] == ["Keelpijn", "Somberheid"]
    assert out["icpc_code"] == "R74"
    nazorg_prompt = complete_mock.await_args_list[1].kwargs["user_prompt"]
    assert "(1) virale faryngitis" in nazorg_prompt and "(2) depressieve klachten" in nazorg_prompt
    assert "R74, P03" in nazorg_prompt
    # Sources per sentence, per part, without an extra call to the language model
    assert complete_mock.await_count == 2
    keel = [b for b in out["bronnen"] if b["probleem"] == 0 and b["veld"] == "s"]
    assert keel and keel[0]["bronnen"][0]["tekst"] == "keelpijn en ook somber"
    assert keel[0]["status"] == "deels" and keel[0]["ontbreekt"] == ["3d"]      # "3 days" was never said
    assert any(b["probleem"] == 1 and "ggz" in b["ontbreekt"] for b in out["bronnen"])


# ── Taal van het consult (upload) ──

@pytest.mark.asyncio
async def test_opname_in_andere_taal():
    transcript = MagicMock(raw_text="Dzień dobry, boli mnie gardło.", duration_secs=30.0, provider="deepgram")
    soep_json = json.dumps({"s": "Keelpijn. Consult in het Pools.", "o": "", "e": "", "p": "", "icpc_code": "", "icpc_titel": ""})
    nazorg_json = json.dumps({"decisief": "Keelpijn", "rode_vlaggen": [], "ontbrekende_info": []})
    transcribe = AsyncMock(return_value=transcript)
    complete = AsyncMock(side_effect=[soep_json, nazorg_json])
    with patch.object(pipeline.stt_service, "transcribe", new=transcribe), \
         patch.object(pipeline.stt_service, "met_sprekers", return_value=transcript.raw_text), \
         patch.object(pipeline.llm_service, "complete", new=complete), \
         patch.object(pipeline, "correct_transcript_full", return_value=(transcript.raw_text, MagicMock(total_corrections=0))):
        await pipeline.process_consultation(Path("/fake/audio.webm"), taal="pl")
    assert transcribe.await_args.kwargs["language"] == "pl"
    assert "TAAL VAN HET GESPREK" in complete.await_args_list[0].kwargs["user_prompt"]
    assert "Pools" in complete.await_args_list[0].kwargs["user_prompt"]


# ── EU-modus: controleronde markeert, haalt niets weg ──

@pytest.mark.asyncio
async def test_eu_mode_marks_what_the_conversation_does_not_support():
    from services.cloud_api import data_policy
    soep_json = json.dumps({"s": "enkel li", "o": "drukpijn laterale malleolus", "e": "distorsie", "p": "paracetamol",
                            "icpc_code": "L77", "icpc_titel": "Distorsie enkel"})
    controle_json = json.dumps({"schrappen": [{"veld": "o", "tekst": "laterale malleolus", "reden": "niet gezegd"}]})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    transcript = MagicMock(raw_text="enkel verzwikt", duration_secs=60.0, provider="voxtral")
    for modus, verwacht in (("eu", 3), ("claude", 2)):
        complete_mock = AsyncMock(side_effect=[soep_json, controle_json, nazorg_json] if modus == "eu"
                                  else [soep_json, nazorg_json])
        token = data_policy.zet_modus(modus)
        try:
            with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
                 patch.object(pipeline.stt_service, "met_sprekers", return_value="enkel verzwikt"), \
                 patch.object(pipeline, "correct_transcript_full", return_value=("enkel verzwikt", MagicMock(total_corrections=0))):
                out = (await pipeline.verwerk_transcript(transcript)).to_dict()["soep"]
        finally:
            data_policy.herstel_modus(token)
        assert complete_mock.await_count == verwacht
        assert out["o"] == "drukpijn laterale malleolus"          # nothing removed
        if modus == "eu":
            assert out["markeringen"][0] == {"probleem": 0, "veld": "o", "tekst": "laterale malleolus", "reden": "niet gezegd"}
            # the fixed check adds its own findings, marked as such
            assert {m["tekst"] for m in out["markeringen"][1:]} >= {"malleolus", "laterale"}
            assert all(m["bron"] == "vast" for m in out["markeringen"][1:])
        else:
            assert "markeringen" not in out


@pytest.mark.asyncio
async def test_eu_mode_report_stands_when_the_control_pass_fails():
    from services.cloud_api import data_policy
    soep_json = json.dumps({"s": "enkel", "o": "", "e": "distorsie", "p": "", "icpc_code": "", "icpc_titel": ""})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    transcript = MagicMock(raw_text="enkel", duration_secs=60.0, provider="voxtral")
    complete_mock = AsyncMock(side_effect=[soep_json, RuntimeError("mistral weg"), nazorg_json])
    token = data_policy.zet_modus("eu")
    try:
        with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
             patch.object(pipeline.stt_service, "met_sprekers", return_value="enkel"), \
             patch.object(pipeline, "correct_transcript_full", return_value=("enkel", MagicMock(total_corrections=0))):
            out = (await pipeline.verwerk_transcript(transcript)).to_dict()
    finally:
        data_policy.herstel_modus(token)
    assert out["soep"]["e"] == "distorsie" and "markeringen" not in out["soep"] and out["decisief"] == "x"



# ── Te weinig spraak: geen verslag (anders verzint het model een consult) ──

@pytest.mark.asyncio
async def test_te_weinig_spraak_geeft_geen_verslag():
    complete_mock = AsyncMock()
    transcript = MagicMock(raw_text="Ja. Oké, dank u.", duration_secs=220.0, provider="voxtral")
    with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
         patch.object(pipeline.stt_service, "met_sprekers", return_value="Ja. Oké, dank u."):
        out = (await pipeline.verwerk_transcript(transcript)).to_dict()
    assert complete_mock.await_count == 0
    assert out["soep"]["s"] == "" and out["soep"]["e"] == ""
    assert "Te weinig spraak herkend (4 woorden in 3.7 min opname)" in out["decisief"]



@pytest.mark.asyncio
async def test_eu_mode_fixed_check_marks_a_template_exam():
    """The real failure from a test: the recording stopped before the exam and
    the report filled one in. The fixed check marks it without any model."""
    from services.cloud_api import data_policy
    soep_json = json.dumps({"s": "rugpijn re", "o": "Lasègue neg. Kracht re been 5/5.", "e": "Aspecifieke lage rugpijn",
                            "p": "ibuprofen 3dd 400 mg", "icpc_code": "L03", "icpc_titel": "Lage rugpijn"})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    transcript = MagicMock(raw_text="pijn in mijn rug rechts sinds de verhuizing", duration_secs=240.0, provider="voxtral")
    complete_mock = AsyncMock(side_effect=[soep_json, RuntimeError("controle weg"), nazorg_json])
    token = data_policy.zet_modus("eu")
    try:
        with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
             patch.object(pipeline.stt_service, "met_sprekers", return_value="Spreker 2: pijn in mijn rug rechts sinds de verhuizing"), \
             patch.object(pipeline, "correct_transcript_full",
                          return_value=("Spreker 2: pijn in mijn rug rechts sinds de verhuizing", MagicMock(total_corrections=0))):
            out = (await pipeline.verwerk_transcript(transcript)).to_dict()["soep"]
    finally:
        data_policy.herstel_modus(token)
    teksten = {m["tekst"] for m in out["markeringen"]}
    assert {"Lasègue", "5/5", "400 mg"} <= teksten
    assert out["o"] == "Lasègue neg. Kracht re been 5/5."      # marked, not removed


# ── Afspraken uit dit consult: alleen wat in de P staat ──

def test_afspraken_alleen_wat_in_de_p_staat():
    plan = "Verwijzing fysiotherapie. Controle over 2 weken. Paracetamol 1000 mg zo nodig. Terug bij koorts."
    ruw = [
        {"soort": "verwijzing", "tekst": "Verwijzing fysiotherapie", "naar": "fysiotherapeut", "wanneer": ""},
        {"soort": "controle", "tekst": "Controle over 2 weken", "naar": "x", "wanneer": "2 weken"},
        {"soort": "vangnet", "tekst": "Terug bij koorts", "wanneer": ""},
        {"soort": "onderzoek", "tekst": "Bloedonderzoek CRP en BSE", "wanneer": ""},     # not in P: invented
        {"soort": "raar", "tekst": "Paracetamol"},                                        # unknown kind
        "geen dict",
    ]
    uit = pipeline.afspraken_uit(ruw, plan)
    assert [a["soort"] for a in uit] == ["verwijzing", "controle", "vangnet"]
    assert uit[0]["naar"] == "fysiotherapeut" and uit[1]["naar"] == ""          # "naar" only for a referral
    assert uit[1]["wanneer"] == "2 weken"
    assert pipeline.afspraken_uit(None, plan) == [] and pipeline.afspraken_uit(ruw, "") == []
    many = [{"soort": "overig", "tekst": "Paracetamol"}] * 20
    assert len(pipeline.afspraken_uit(many, plan)) == pipeline.MAX_AFSPRAKEN


@pytest.mark.asyncio
async def test_pipeline_geeft_afspraken_mee_in_dezelfde_aanroep():
    soep_json = json.dumps({"s": "keelpijn", "o": "keel rood", "e": "faryngitis", "p": "Verwijzing KNO-arts. Controle 1 week.",
                            "icpc_code": "R74", "icpc_titel": "x"})
    nazorg_json = json.dumps({"decisief": "Keelpijn", "rode_vlaggen": [], "ontbrekende_info": [],
                              "afspraken": [{"soort": "verwijzing", "tekst": "Verwijzing KNO-arts", "naar": "KNO-arts", "wanneer": ""},
                                            {"soort": "recept", "tekst": "Amoxicilline 3dd500mg", "wanneer": ""}]})
    transcript = MagicMock(raw_text="keelpijn al lang " * 5, duration_secs=60.0, provider="deepgram")
    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])
    with patch.object(pipeline.llm_service, "complete", new=complete_mock), \
         patch.object(pipeline.stt_service, "met_sprekers", return_value="keelpijn al lang " * 5), \
         patch.object(pipeline, "correct_transcript_full", return_value=("keelpijn al lang " * 5, MagicMock(total_corrections=0))):
        out = (await pipeline.verwerk_transcript(transcript)).to_dict()["soep"]
    assert complete_mock.await_count == 2                                 # no extra call
    assert out["afspraken"] == [{"soort": "verwijzing", "tekst": "Verwijzing KNO-arts", "naar": "KNO-arts", "wanneer": ""}]
    assert "AFSPRAKEN" in complete_mock.await_args_list[1].kwargs["system_prompt"]

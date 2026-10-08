"""Bronnen bij de SOEP: per zin de plek in het gesprek, zonder taalmodel."""

from pathlib import Path

from services.cloud_api import bronnen

GESPREK = """Spreker 1: Waar komt u voor?
Spreker 2: Ik heb al drie dagen pijn in mijn keel. En ik hoest veel, vooral 's nachts.
Spreker 1: Koorts gehad?
Spreker 2: Nee, geen koorts.
Spreker 1: Ik kijk even in uw keel. De keel is rood, geen beslag.
Nadictaat arts: Keel rood zonder beslag. Beleid: paracetamol zo nodig."""


def _een(soep, veld, zin_begin):
    return next(b for b in bronnen.bronnen_bij_soep(GESPREK, [soep])
                if b["veld"] == veld and b["zin"].startswith(zin_begin))


SOEP = {"s": "Keelpijn sinds 3 dgn. Hoesten, vooral 's nachts. Geen koorts.",
        "o": "Keel rood, geen beslag. Temp 38,5.",
        "e": "Faryngitis (R74)",
        "p": "Paracetamol zn. Amoxicilline 3dd500mg."}


def test_compound_numbers_and_abbreviations_find_their_source():
    b = _een(SOEP, "s", "Keelpijn")          # keelpijn from "pijn in mijn keel", 3 from "drie", dgn = dagen
    assert b["status"] == "bron" and not b["ontbreekt"]
    assert b["bronnen"][0] == {"spreker": "Spreker 2", "tekst": "Ik heb al drie dagen pijn in mijn keel."}
    assert _een(SOEP, "s", "Hoesten")["status"] == "bron"             # stem: hoest / hoesten
    assert _een(SOEP, "e", "Faryngitis")["status"] == "bron"         # medical term for lay words, ICPC ignored


def test_what_nobody_said_is_named():
    temp = _een(SOEP, "o", "Temp")
    assert temp["status"] != "bron" and "38,5" in temp["ontbreekt"]
    amox = _een(SOEP, "p", "Amoxicilline")
    assert amox["status"] == "geen" and amox["bronnen"] == []
    assert set(amox["ontbreekt"]) == {"amoxicilline", "3dd500mg"}
    pcm = _een(SOEP, "p", "Paracetamol")
    assert pcm["status"] == "bron" and pcm["bronnen"][0]["spreker"] == "Nadictaat arts"


def test_two_moments_of_the_conversation_for_one_sentence():
    b = _een({"s": "Keelpijn en geen koorts."}, "s", "Keelpijn")
    assert b["status"] == "bron" and len(b["bronnen"]) == 2


def test_parts_and_limits():
    uit = bronnen.bronnen_bij_soep(GESPREK, [{"s": "Keelpijn."}, {"p": "Paracetamol zn."}])
    assert [(b["probleem"], b["veld"]) for b in uit] == [(0, "s"), (1, "p")]
    assert bronnen.bronnen_bij_soep("", [SOEP]) == []
    assert bronnen.bronnen_bij_soep(GESPREK, [{"s": "", "o": "..."}]) == []
    lang = bronnen.bronnen_bij_soep(GESPREK, [{"s": "Keel. " * 500}])
    assert len(lang) == bronnen.MAX_ZINNEN


def test_plain_transcript_without_speakers():
    uit = bronnen.bronnen_bij_soep("Ik heb hoofdpijn sinds gisteren.", [{"s": "Hoofdpijn."}])
    assert uit[0]["status"] == "bron" and uit[0]["bronnen"][0]["spreker"] == ""


def test_testset_report_invented_details_surface():
    """An acted consult (no patient): the details the test report adds are named."""
    gesprek = (Path(bronnen.__file__).parent / "testset" / "02-verzwikte-enkel.txt").read_text()
    soep = {"s": "Drie weken geleden li enkel verzwikt bij badminton. Loopt op krukken.",
            "o": "Zwelling laterale malleolus li.", "e": "Distorsie enkel li (L77)",
            "p": "Paracetamol 3dd1g zn."}
    uit = {b["zin"]: b for b in bronnen.bronnen_bij_soep(gesprek, [soep])}
    assert uit["Drie weken geleden li enkel verzwikt bij badminton."]["status"] == "bron"
    assert uit["Distorsie enkel li (L77)"]["status"] == "bron"
    assert "malleolus" in uit["Zwelling laterale malleolus li."]["ontbreekt"]
    assert "3dd1g" in uit["Paracetamol 3dd1g zn."]["ontbreekt"]

"""
VitaScribe Cloud API - Stiltes inkorten voor de spraakherkenning

Spraakherkenning wordt per minuut opname betaald, ook voor de minuten waarin
niemand praat: lichamelijk onderzoek, typen, aankleden. Dit kort elke stilte
van minstens MIN_STILTE seconden in tot BEWAAR seconden aan weerszijden, zodat
een pauze een pauze blijft en een zacht uitgesproken woordeinde niet wegvalt.

- Alleen de EU-modus (batch na het consult); live spraakherkenning rekent per
  verbindingsminuut, daar helpt dit niet.
- Standaard uit. De beheerder zet het aan in Beheer, nadat de spraaktest op
  eigen opnamen liet zien dat het transcript gelijk blijft.
- De opname gaat via pipes door ffmpeg en raakt de schijf niet.
- Lukt het niet (geen ffmpeg, kapotte opname, te weinig stilte), dan gaat de
  oorspronkelijke opname door: dit mag een consult nooit laten mislukken.
- Het nadictaat begint op een tijdstip in de opname; verschuif() rekent dat
  om naar de ingekorte opname.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import structlog

from . import register

logger = structlog.get_logger()

INSTELLING = "stilte_inkorten"
MIN_STILTE = 2.0          # seconds: only pauses at least this long are shortened
BEWAAR = 0.4              # seconds of silence kept on each side of the cut
MIN_WINST = 1.0           # below this many seconds saved, send the original
TIMEOUT = 120.0


def drempel_db() -> float:
    """Below this level counts as silence. -45 dB is far under speech at a
    speakerphone (around -30 to -20 dB), and above a quiet room."""
    try:
        return float(os.getenv("STILTE_DREMPEL_DB", "-45").replace(",", "."))
    except ValueError:
        return -45.0


async def aan() -> bool:
    """The administrator's switch in Beheer; off without a register."""
    if not register.actief():
        return False
    try:
        rij = await register.fetchrow("SELECT waarde FROM vs_instellingen WHERE sleutel = $1", INSTELLING)
    except Exception as e:      # register unreachable: leave the recording as it is
        logger.warning("stilte.instelling_onleesbaar", fout=type(e).__name__)
        return False
    return bool(rij) and rij["waarde"] == "aan"


@dataclass
class Ingekort:
    audio: bytes
    voor: float                                   # seconds before
    na: float                                     # seconds after
    knippen: List[Tuple[float, float]] = field(default_factory=list)   # removed, in original time
    # Ogg, not webm: webm written to a pipe has no duration in its header, and
    # a service that reads the header would bill the old length.
    naam: str = "consult.ogg"

    def verschuif(self, t: Optional[float]) -> Optional[float]:
        """A moment in the original recording, in the shortened one."""
        if t is None:
            return None
        return max(t - sum(min(e, t) - s for s, e in self.knippen if s < t), 0.0)


_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_EIND = re.compile(r"silence_end:\s*([\d.]+)")
_TIJD = re.compile(r"time=(\d+):(\d+):([\d.]+)")


def lees_stiltes(log: str) -> Tuple[List[Tuple[float, float]], float]:
    """Silences and total duration from ffmpeg's silencedetect output."""
    tijden = _TIJD.findall(log)
    duur = 0.0
    if tijden:
        h, m, s = tijden[-1]
        duur = int(h) * 3600 + int(m) * 60 + float(s)
    stiltes: List[Tuple[float, float]] = []
    begin: Optional[float] = None
    for regel in log.splitlines():
        if (m := _START.search(regel)):
            begin = max(float(m.group(1)), 0.0)
        elif (m := _EIND.search(regel)) and begin is not None:
            stiltes.append((begin, float(m.group(1))))
            begin = None
    if begin is not None and duur > begin:      # silent until the end
        stiltes.append((begin, duur))
    return stiltes, duur


def knipplan(stiltes: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """What to cut: the middle of every long silence, keeping BEWAAR each side."""
    return [(round(s + BEWAAR, 3), round(e - BEWAAR, 3)) for s, e in stiltes
            if e - s >= MIN_STILTE and e - s > 2 * BEWAAR]


async def _ffmpeg(args: List[str], audio: bytes) -> Tuple[bytes, str]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-nostdin", "-i", "pipe:0", *args,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        uit, log = await asyncio.wait_for(proc.communicate(audio), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg stopte met code {proc.returncode}")
    return uit, log.decode("utf-8", "replace")


async def kort_in(audio: bytes) -> Optional[Ingekort]:
    """The recording with long silences shortened, or None to send the original."""
    if not audio or not shutil.which("ffmpeg"):
        return None
    try:
        _, log = await _ffmpeg(["-af", f"silencedetect=noise={drempel_db()}dB:d={MIN_STILTE}", "-f", "null", "-"], audio)
        stiltes, duur = lees_stiltes(log)
        knippen = knipplan(stiltes)
        winst = sum(e - s for s, e in knippen)
        if duur <= 0 or winst < MIN_WINST:
            return None
        weg = "+".join(f"between(t,{s},{e})" for s, e in knippen)
        nieuw, _ = await _ffmpeg(["-af", f"aselect='not({weg})',asetpts=N/SR/TB", "-ac", "1",
                                  "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"], audio)
        if len(nieuw) < 1000:
            return None
    except Exception as exc:    # never let this break a consult
        logger.warning("stilte.mislukt", error=type(exc).__name__)
        return None
    uit = Ingekort(audio=nieuw, voor=round(duur, 1), na=round(duur - winst, 1), knippen=knippen)
    logger.info("stilte.ingekort", voor=uit.voor, na=uit.na, knippen=len(knippen))
    return uit

"""
VitaScribe Cloud API - Letters (Brieven)

Informatiebrieven aan derden en verwijsbrieven, geschreven door Claude op
basis van een door de arts gefilterd dossier. Voorheen de losse extensie
BriefAssistent, die de Anthropic-sleutel in de browser bewaarde; nu loopt
alles via deze server: de sleutel blijft hier en er is een tweede
privacyfilter als vangnet.

Endpoints (API-sleutel verplicht):
  POST /api/v1/letters/extract   afbeelding (screenshot) -> platte tekst
  POST /api/v1/letters/generate  dossier + vraag -> brieftekst (gestreamd)
"""

from __future__ import annotations

import re
from typing import AsyncIterator, List, Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import audit, data_policy, llm_service
from .auth import huidige_identiteit, verify_api_key
from .praktijk_sleutels import kies_brieven

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/letters", tags=["brieven"])

MAX_DOSSIER_CHARS = 40000
MAX_TEXT_CHARS = 12000
MAX_IMAGE_BYTES_B64 = 7_000_000   # ~5 MB image
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")

# ── Privacy safety net ──
# The extension already filters and shows the doctor exactly what is sent.
# These patterns catch direct identifiers that should never reach the model
# even if the client filter missed them.
_SAFETY_PATTERNS = [
    (re.compile(r"\bNL\d{2}[A-Z]{4}\d{10}\b"), "[IBAN]"),
    (re.compile(r"(?<!\d)\d{9}(?!\d)"), "[BSN]"),
    (re.compile(r"(?<!\d)\d{4}\.\d{2}\.\d{3}(?!\d)"), "[BSN]"),
    (re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+31|0031|0)[\s-]?6[\s-]?\d(?:[\s-]?\d){7}(?!\d)"), "[TEL]"),
    (re.compile(r"(?<!\d)0\d{2,3}[\s-]?\d{6,7}(?!\d)"), "[TEL]"),
]


def privacy_safety_net(text: str) -> str:
    for pattern, tag in _SAFETY_PATTERNS:
        text = pattern.sub(tag, text)
    return text


# ── Prompts ──

_BASIS_INFORMATIEBRIEF = """\
Je bent een Nederlandse huisarts en schrijft als behandelend arts een \
informatiebrief aan een derde. Je volgt de KNMG-richtlijn Omgaan met \
medische gegevens:
- Verstrek alleen FEITELIJKE medische gegevens: klachten, diagnoses, \
  onderzoeksbevindingen, behandeling, medicatie, verwijzingen en het \
  beloop, met datum of periode waar het dossier die geeft.
- Geef GEEN oordeel of beoordeling: niet over arbeids(on)geschiktheid, \
  belastbaarheid of functionele mogelijkheden, causaal verband, \
  aansprakelijkheid, zelfredzaamheid of indicatie voor voorzieningen. \
  Vraagt de aanvrager daarnaar, schrijf dan kort dat de behandelend arts \
  daarover geen oordeel geeft en dat dit aan een onafhankelijk \
  (verzekerings)arts of adviseur is.
- Beantwoord uitsluitend de gestelde vragen, genummerd zoals de \
  aanvrager ze nummert; verstrek geen gegevens die niet gevraagd zijn \
  (proportionaliteit). Geen vragen gegeven: een beknopte feitelijke \
  samenvatting van wat voor het doel van de aanvrager relevant is.
- Alleen wat in het dossier staat. Staat het antwoord niet in het \
  dossier, schrijf dan "Hierover zijn in het dossier geen gegevens \
  bekend." Verzin niets.
- Noem de patiënt uitsluitend met de opgegeven initialen. \
  Placeholders als [DATUM] of [NAAM] laat je staan.
- Stijl: formele Nederlandse brief, zakelijk en helder, zonder \
  vakjargon waar de lezer geen arts is (leg termen kort uit). Opbouw: \
  aanhef, referentie aan het verzoek, antwoorden per vraag, afsluiting \
  met "Met collegiale groet" (aan een arts) of "Met vriendelijke groet", \
  en als laatste regel [Naam huisarts]. Geen markdown-opmaak.
"""

_AANVRAGER = {
    "advocaat": "De aanvrager is een advocaat. Houd de brief strikt feitelijk; \
geen uitspraken over schuld, oorzaak of letsel-gevolgen.",
    "sma": "De aanvrager is een sociaal-medisch adviseur. Je mag medische \
terminologie gebruiken en afsluiten met \"Met collegiale groet\".",
    "gemeente": "De aanvrager is de gemeente (Wmo/Jeugdwet/participatie). \
Leg medische termen in gewone taal uit.",
    "verzekeraar": "De aanvrager is (de medisch adviseur van) een verzekeraar. \
Alleen gegevens die direct op de vraag betrekking hebben.",
    "uwv": "De aanvrager is (de verzekeringsarts van) UWV. Je mag medische \
terminologie gebruiken en afsluiten met \"Met collegiale groet\".",
    "overig": "De aanvrager is een externe instantie.",
}

VERWIJZING_SYSTEM = """\
Je bent een Nederlandse huisarts en schrijft een verwijsbrief aan een \
medisch specialist, in de opbouw van de NHG/NVZ-verwijsbrief:
Geachte collega,
Reden van verwijzing en vraagstelling (concreet: wat wil je weten of \
laten doen)
Anamnese en beloop (kort)
Bevindingen bij onderzoek en relevante uitslagen (met datum)
Relevante voorgeschiedenis
Huidige medicatie en allergieën/contra-indicaties
Wat al is ingezet en met welk effect
Met collegiale groet,
[Naam huisarts]

Regels:
- Alleen wat in het dossier of de opgegeven verwijsreden staat; verzin \
  geen bevindingen, waarden of beloop. Ontbreekt iets wezenlijks, zet dan \
  [aanvullen] op die plek.
- Selecteer wat relevant is voor dit specialisme; laat de rest weg.
- Bondig, telegramstijl binnen de kopjes is prima, medische terminologie.
- Noem de patiënt uitsluitend met de opgegeven initialen. Geen markdown.
"""

_EXTRACT_PROMPTS = {
    "dossier": """\
Dit is een schermafdruk uit een huisartsinformatiesysteem. Schrijf alle \
zichtbare medische informatie letterlijk over, per sectie (Journaal, \
Medicatie, Voorgeschiedenis, Lab, Metingen, Allergieën, Correspondentie), \
elke sectienaam op een eigen regel. Neem datums, ICPC-codes, middelen en \
doseringen exact over. Laat identificerende gegevens WEG: naam, BSN, \
geboortedatum, adres, telefoon, e-mail, patiëntnummer. Alleen platte tekst.""",
    "vraag": """\
Dit is een schermafdruk van een brief of vragenlijst van een advocaat, \
gemeente, UWV, verzekeraar of adviseur aan de huisarts. Schrijf de tekst \
letterlijk over: de context van het verzoek en alle vragen met hun \
nummering. Vervang de naam, geboortedatum, BSN en het adres van de patiënt \
door [PATIËNT]. Alleen platte tekst.""",
}


# ── Request models ──

class ExtractRequest(BaseModel):
    kind: Literal["dossier", "vraag"]
    media_type: str
    data: str = Field(..., min_length=10, max_length=MAX_IMAGE_BYTES_B64)


class GenerateRequest(BaseModel):
    kind: Literal["informatiebrief", "verwijzing"]
    initialen: str = Field("P.X.", max_length=12)
    dossier: str = Field(..., min_length=10, max_length=MAX_DOSSIER_CHARS)
    # informatiebrief
    aanvrager: Optional[Literal["advocaat", "sma", "gemeente", "verzekeraar", "uwv", "overig"]] = None
    vraag: Optional[str] = Field(None, max_length=MAX_TEXT_CHARS)
    toestemming: bool = False
    # verwijzing
    specialisme: Optional[str] = Field(None, max_length=80)
    urgentie: Optional[Literal["regulier", "semi-spoed", "spoed"]] = None
    reden: Optional[str] = Field(None, max_length=MAX_TEXT_CHARS)
    # beide
    extra: Optional[str] = Field(None, max_length=2000)


def build_letter_prompts(req: GenerateRequest) -> "tuple[str, str, bool, int]":
    """Return (system, user, quality_model, max_tokens) for a letter request."""
    initialen = privacy_safety_net(req.initialen.strip() or "P.X.")
    dossier = privacy_safety_net(req.dossier)
    extra = privacy_safety_net(req.extra or "").strip()
    sep = "-" * 40

    if req.kind == "informatiebrief":
        if not req.toestemming:
            raise HTTPException(
                status_code=400,
                detail="Bevestig dat er een gerichte vraag en toestemming van de patiënt is.",
            )
        system = _BASIS_INFORMATIEBRIEF + "\n" + _AANVRAGER[req.aanvrager or "overig"]
        vraag = privacy_safety_net(req.vraag or "").strip()
        parts = []
        if vraag:
            parts.append(f"VERZOEK VAN DE AANVRAGER:\n{sep}\n{vraag}\n{sep}")
        parts.append(f"DOSSIER (gefilterd, patiënt {initialen}):\n{sep}\n{dossier}\n{sep}")
        parts.append(
            "Schrijf de informatiebrief. Beantwoord elke vraag afzonderlijk."
            if vraag else
            "Er is geen vraag bijgevoegd: geef een beknopte feitelijke samenvatting."
        )
        if extra:
            parts.append(f"AANWIJZING VAN DE HUISARTS: {extra}")
        return system, "\n\n".join(parts), True, 2500

    reden = privacy_safety_net(req.reden or "").strip()
    if not reden:
        raise HTTPException(status_code=400, detail="Vul de verwijsreden of vraagstelling in.")
    spec = (req.specialisme or "medisch specialist").strip()
    user = (
        f"VERWIJZING NAAR: {spec}\nURGENTIE: {req.urgentie or 'regulier'}\n"
        f"VERWIJSREDEN/VRAAGSTELLING: {reden}\n"
        + (f"AANWIJZING VAN DE HUISARTS: {extra}\n" if extra else "")
        + f"\nDOSSIER (gefilterd, patiënt {initialen}):\n{sep}\n{dossier}\n{sep}\n\n"
        f"Schrijf de verwijsbrief aan de {spec}."
    )
    return VERWIJZING_SYSTEM, user, False, 1500


# ── Endpoints ──

@router.post("/extract")
async def extract_from_image(body: ExtractRequest, user: str = Depends(verify_api_key)):
    """Read a screenshot (dossier or request letter) into plain text."""
    if body.media_type not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Alleen PNG, JPEG, WebP of GIF.")
    # A screenshot can show name, BSN and address: EU model only.
    provider = data_policy.phi_llm_provider()
    content = [
        llm_service.image_part(provider, body.media_type, body.data),
        llm_service.text_part(provider, _EXTRACT_PROMPTS[body.kind]),
    ]
    chunks: List[str] = []
    try:
        async for piece in llm_service.stream_llm(
            provider, "Je zet schermafdrukken nauwkeurig om naar platte tekst.", content,
            max_tokens=4000, quality=True,
        ):
            chunks.append(piece)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    text = privacy_safety_net("".join(chunks).strip())
    logger.info("letters.extract", kind=body.kind, chars=len(text), provider=provider)
    audit.log_event(user, "letters.extract", kind=body.kind, provider=provider)
    return {"text": text}


@router.post("/generate")
async def generate_letter(body: GenerateRequest, ident=Depends(huidige_identiteit)):
    """Write the letter; the text streams back as it is written.

    A practice with its own Anthropic or OpenAI key writes letters on that key.
    Letters are the only thing that may go there: they are pseudonymised."""
    user_name = ident.label
    system, user, quality, max_tokens = build_letter_prompts(body)
    provider, eigen_sleutel = await kies_brieven(ident)
    audit.log_event(user_name, "letters.generate", kind=body.kind,
                    aanvrager=body.aanvrager or "", consent=bool(body.toestemming),
                    provider=provider + (":eigen" if eigen_sleutel else ""))
    logger.info("letters.generate", kind=body.kind, dossier_chars=len(body.dossier), provider=provider,
                eigen_sleutel=bool(eigen_sleutel))

    stream = llm_service.stream_llm(
        provider, system, user, max_tokens=max_tokens, quality=quality, api_key=eigen_sleutel,
    )
    # Fail before the 200 is sent when the provider rejects the call outright.
    try:
        first = await stream.__anext__()
    except StopAsyncIteration:
        first = ""
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    async def body_iter() -> AsyncIterator[str]:
        yield first
        try:
            async for piece in stream:
                yield piece
        except ValueError as exc:
            yield f"\n\n[Afgebroken: {exc}]"

    return StreamingResponse(body_iter(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

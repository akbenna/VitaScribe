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

from . import audit, data_policy, leren, llm_service
from .auth import huidige_identiteit, verify_api_key
from .praktijk_sleutels import kies_brieven

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/letters", tags=["brieven"])

MAX_DOSSIER_CHARS = 160_000   # all sections in view; ~40k tokens at most
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
    # Phone numbers, but never inside a date run ("22-06-202622-06-2026").
    (re.compile(r"(?<![\d\-/.,])(?:\+31|0031|0)[ -]?6[ -]?\d(?:[ -]?\d){7}(?![\d\-/])"), "[TEL]"),
    (re.compile(r"(?<![\d\-/.,])0\d{2,3}[ -]?\d{6,7}(?![\d\-/])"), "[TEL]"),
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

# Per requester: who reads the letter, what they need, in which register.
# Always on top of the KNMG basis above (facts only, no judgement).
_COLLEGIAAL = "De lezer is arts: medische terminologie mag, afsluiten met \"Met collegiale groet\". "
_LEEK = "De lezer is geen arts: leg elke medische term kort in gewone taal uit, afsluiten met \"Met vriendelijke groet\". "

_AANVRAGER = {
    "advocaat": _LEEK + "De aanvrager is een advocaat (bijvoorbeeld letselschade, \
arbeidsrecht, familie- of strafrecht). Verstrek alleen wat de schriftelijke \
machtiging van de patiënt en de vraag dekken. Chronologisch per vraag: datum, \
klacht zoals de patiënt die meldde, bevindingen, diagnose, behandeling, \
verwijzing. Geen uitspraken over oorzaak, schuld, geloofwaardigheid of gevolgen, \
en geen kopie of samenvatting van het hele dossier.",
    "letselschade": _COLLEGIAAL + "De aanvrager is de medisch adviseur in een \
letselschadezaak (verzekeraar of belangenbehartiger). Geef een chronologisch \
overzicht van de gevraagde periode: klachten zoals gemeld, bevindingen, \
diagnoses, behandeling en verwijzingen met datum. Vraagt de adviseur naar \
klachten van vóór het ongeval, noem die feitelijk binnen de gevraagde periode. \
Geen uitspraken over oorzaak, ongevalsgevolgen, prognose of eindtoestand.",
    "uwv": _COLLEGIAAL + "De aanvrager is de verzekeringsarts of arbeidsdeskundige \
van UWV. Noem per vraag: diagnose(s) met datum, klachten zoals de patiënt ze \
meldt, behandeling en behandelaars (ook specialist, GGZ, fysiotherapie), \
huidige medicatie en het beloop. Geen oordeel over arbeidsongeschiktheid, \
belastbaarheid of functionele mogelijkheden: dat stelt de verzekeringsarts vast.",
    "bedrijfsarts": _COLLEGIAAL + "De aanvrager is de bedrijfsarts (arbodienst). \
Richt je op de actuele situatie: diagnose, behandeltraject en behandelaars, \
medicatie, en de verwachte duur van de behandeling als die in het dossier \
staat. Geen oordeel over belastbaarheid, werkhervatting of verzuim.",
    "sma": _COLLEGIAAL + "De aanvrager is een sociaal-medisch adviseur (vaak voor \
gemeente of verzekeraar). Feitelijk per vraag: diagnoses, behandeling, \
medicatie en beloop. Geen eigen oordeel over beperkingen of indicaties.",
    "verzekeraar": _COLLEGIAAL + "De aanvrager is de medisch adviseur van een \
verzekeraar (bijvoorbeeld arbeidsongeschiktheids- of levensverzekering). \
Alleen gegevens die rechtstreeks op de gestelde vraag en de gemachtigde \
periode betrekking hebben; niets daarbuiten. Geen oordeel over risico, \
acceptatie of eerdere aanwezigheid van een aandoening.",
    "gemeente": _LEEK + "De aanvrager is de gemeente of het Wmo-, Jeugd- of \
Participatieloket; de lezer is meestal een consulent zonder medische \
achtergrond. Noem de aandoeningen die voor de vraag van belang zijn, sinds \
wanneer, de behandeling en welke beperkingen in het dossier beschreven staan, \
in gewone taal. Geen oordeel over de vraag of een voorziening nodig is: dat \
beoordeelt de gemeente of haar adviseur.",
    "ciz": _LEEK + "De aanvrager is het CIZ (indicatie Wet langdurige zorg). \
Noem diagnoses, beperkingen zoals ze in het dossier beschreven staan (beoordeel \
ze niet zelf), hulpmiddelen, betrokken zorgverleners en de zorg die nu \
geleverd wordt.",
    "ind": _COLLEGIAAL + "De aanvrager is de IND, meestal via het Bureau Medische \
Advisering (BMA), dat de vragen opstelt. Beantwoord elke vraag volledig en \
precies, want de beoordeling hangt af van details: alle diagnoses met datum van \
vaststelling, de huidige behandeling en wie die geeft (huisarts, specialisten, \
GGZ), alle huidige medicatie met exacte sterkte, dosering en frequentie, het \
beloop en de geplande behandeling of controles, zoals ze in het dossier staan. \
Geef geen oordeel over een medische noodsituatie, over de gevolgen van stoppen \
met de behandeling, over reisgeschiktheid of over de beschikbaarheid van zorg \
in het land van herkomst: dat beoordeelt het BMA.",
    "duo": _LEEK + "De aanvrager is DUO (Dienst Uitvoering Onderwijs), \
bijvoorbeeld bij een verzoek om studievertraging door ziekte of een beperking. \
Alleen feiten: welke aandoening, zo beperkt als de vraag toelaat, sinds \
wanneer, en in welke periode klachten of behandeling in het dossier staan. Geen \
oordeel over de invloed op de studie.",
    "cbr": _COLLEGIAAL + "De aanvrager is het CBR of een door het CBR aangewezen \
arts (rijgeschiktheid). Alleen feitelijke gegevens over de aandoening waarnaar \
gevraagd wordt: diagnose, behandeling, medicatie, en of er recent \
ontregeling of aanvallen in het dossier staan. Geen oordeel over \
rijgeschiktheid.",
    "overig": _LEEK + "De aanvrager is een externe instantie. Beantwoord alleen de \
gestelde vragen, feitelijk.",
}

# ── Supporting letter at the patient's own request (housing urgency, Wmo) ──
# KNMG: a treating doctor does not write a judgement or recommendation for his
# own patient ("rolvermenging"). What is allowed: factual information, at the
# patient's request, that the patient hands in himself. The letter supports by
# being complete and to the point, not by advising.
_DOEL = {
    "woningurgentie": "een aanvraag voor urgentie of een medische indicatie voor een woning. Relevant: \
aandoeningen die met de huidige woning te maken hebben (trappen, loopafstand, \
ademhaling, psychische klachten, valrisico) zoals ze in het dossier staan.",
    "wmo_scootmobiel": "een Wmo-aanvraag voor een scootmobiel of ander vervoersmiddel. Relevant: \
aandoeningen die het lopen of het reizen beperken, de loopafstand of \
loopbeperking zoals die in het dossier beschreven staat, hulpmiddelen die al \
gebruikt worden, en de behandeling.",
    "wmo_woning": "een Wmo-aanvraag voor een woningaanpassing (bijvoorbeeld traplift, douche). \
Relevant: aandoeningen die traplopen, staan, bukken of de persoonlijke \
verzorging beperken, zoals in het dossier beschreven, en gebruikte hulpmiddelen.",
    "wmo_hulp": "een Wmo-aanvraag voor huishoudelijke hulp of begeleiding. Relevant: \
aandoeningen en beperkingen in het dagelijks functioneren zoals in het dossier \
beschreven, en de zorg die nu geleverd wordt.",
    "parkeerkaart": "een aanvraag voor een gehandicaptenparkeerkaart. Relevant: aandoeningen \
die het lopen beperken en de loopafstand zoals die in het dossier staat. De \
gemeente laat dit meestal keuren door een onafhankelijk arts.",
    "vervoer": "een aanvraag voor aangepast vervoer (regiotaxi, Valys). Relevant: \
aandoeningen die zelfstandig reizen met het openbaar vervoer beperken, zoals \
in het dossier beschreven.",
    "overig": "een aanvraag bij een instantie, zoals de patiënt die hieronder toelicht.",
}

VERKLARING_SYSTEM = """\
Je bent een Nederlandse huisarts en schrijft, op verzoek van je eigen \
patiënt, een feitelijke brief die de patiënt zelf meestuurt bij een \
aanvraag. Je volgt de KNMG-richtlijn: als behandelend arts geef je geen \
oordeel, advies of aanbeveling over je eigen patiënt (bijvoorbeeld niet "ik \
adviseer urgentie" of "een scootmobiel is noodzakelijk"). Wel geef je \
volledige, feitelijke informatie die voor de aanvraag van belang is; daarmee \
help je de patiënt het meest.
- Aanhef "Aan wie het aangaat," en een eerste zin dat de brief is \
  opgesteld op verzoek van de patiënt, voor het doel hieronder.
- Daarna, in gewone taal en met datum of periode: de aandoeningen die voor \
  dit doel van belang zijn, sinds wanneer, de behandeling en behandelaars, \
  medicatie, gebruikte hulpmiddelen, en de beperkingen zoals ze in het \
  dossier beschreven staan ("patiënt meldt…", "bij onderzoek…").
- Alleen wat in het dossier staat; verzin niets. Laat weg wat voor dit doel \
  niet relevant is (proportionaliteit).
- Sluit af met: "De beoordeling van de aanvraag laat ik aan de (medisch) \
  adviseur van de instantie." en "Met vriendelijke groet," en als laatste \
  regel [Naam huisarts].
- Noem de patiënt uitsluitend met de opgegeven initialen. Geen markdown.
"""

VERWIJZING_SYSTEM = """\
Je bent een Nederlandse huisarts en schrijft een verwijsbrief aan een \
medisch specialist, in de opbouw van de NHG/NVZ-verwijsbrief. De arts wil \
de brief vrijwel zo kunnen versturen: haal alles wat ertoe doet uit het \
dossier.

Opbouw (de koppen als gewone regel, zonder tekens ervoor of erachter):
Geachte collega,
Reden van verwijzing en vraagstelling
Anamnese en beloop
Bevindingen bij onderzoek en relevante uitslagen
Relevante voorgeschiedenis
Huidige medicatie en allergieën/contra-indicaties
Wat al is ingezet en met welk effect
Met collegiale groet,
[Naam huisarts]

Zo vul je het:
- Lees het HELE dossier: elke journaalregel (S, O, E, P, ook korte \
  notities van assistente, POH en thuiszorg), episodes, medicatie (ook \
  gestopte en gewijzigde), labuitslagen, metingen en brieven.
- Reden en vraagstelling: uit de opgegeven verwijsreden, concreet.
- Anamnese en beloop: uit de S-regels en notities over deze klacht en wat \
  ermee samenhangt, in de tijd geordend, met datum ("Sinds 08-2026 zwelling \
  re enkel; 15-09-2026 toegenomen, geen pijn."). Ook gerelateerde klachten \
  die de specialist moet kennen.
- Bevindingen en uitslagen: uit de O-regels, metingen en het lab, met \
  datum. Relevante normale waarden mogen kort ("nierfunctie normaal \
  (kreat 81, 02-09-2026)").
- Voorgeschiedenis: episodes en eerdere aandoeningen die voor dit \
  specialisme van belang zijn, met jaartal.
- Medicatie: wat de patiënt nu gebruikt, met dosering; een middel dat \
  met de klacht te maken kan hebben (gestart, gestopt, gewijzigd) met datum.
- Wat al is ingezet: uit de P-regels, eerdere verwijzingen, \
  medicatiewijzigingen en uitslagen, met het effect als dat er staat.

Regels:
- Alleen wat in het dossier of de verwijsreden staat; verzin geen \
  bevinding, waarde, datum of beloop.
- Staat er voor een kop echt niets in het dossier, schrijf dan één korte \
  regel "[aanvullen: ...]" met hooguit een paar woorden over wat de \
  specialist mist. Geen lijsten van wat er allemaal zou kunnen; liever één \
  gerichte plek dan vijf vage.
- Selecteer wat relevant is voor dit specialisme; laat de rest weg.
- Bondig, telegramstijl binnen de kopjes, medische terminologie.
- Noem de patiënt uitsluitend met de opgegeven initialen.
- Platte tekst: geen markdown, geen sterretjes, geen hekjes, geen \
  opsommingstekens voor de koppen.
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
    kind: Literal["informatiebrief", "verwijzing", "verklaring"]
    initialen: str = Field("P.X.", max_length=12)
    dossier: str = Field(..., min_length=10, max_length=MAX_DOSSIER_CHARS)
    # informatiebrief
    aanvrager: Optional[Literal["advocaat", "letselschade", "uwv", "bedrijfsarts", "sma", "verzekeraar",
                                "gemeente", "ciz", "ind", "duo", "cbr", "overig"]] = None
    vraag: Optional[str] = Field(None, max_length=MAX_TEXT_CHARS)
    toestemming: bool = False
    # verklaring op verzoek van de patiënt
    doel: Optional[Literal["woningurgentie", "wmo_scootmobiel", "wmo_woning", "wmo_hulp",
                           "parkeerkaart", "vervoer", "overig"]] = None
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

    if req.kind == "verklaring":
        if not req.toestemming:
            raise HTTPException(status_code=400, detail="Bevestig dat de patiënt om deze brief vraagt.")
        toelichting = privacy_safety_net(req.vraag or "").strip()
        parts = [f"DOEL: {_DOEL[req.doel or 'overig']}"]
        if toelichting:
            parts.append(f"WAT DE PATIËNT AANVRAAGT EN WAAROM (in zijn of haar woorden):\n{sep}\n{toelichting}\n{sep}")
        parts.append(f"DOSSIER (gefilterd, patiënt {initialen}):\n{sep}\n{dossier}\n{sep}")
        if extra:
            parts.append(f"AANWIJZING VAN DE HUISARTS: {extra}")
        parts.append("Schrijf de brief.")
        return VERKLARING_SYSTEM, "\n\n".join(parts), True, 1800

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
    return VERWIJZING_SYSTEM, user, True, 2000


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
    # How this doctor writes this kind of letter (learned, approved by the doctor).
    system = await leren.brief_prompt(body.kind) + system
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

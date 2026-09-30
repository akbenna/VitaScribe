"""Route A controleren: bereikt de server Claude in Amazon Bedrock (EU)?

Stuurt twee korte verzoeken zonder patiëntgegevens (Haiku en het SOEP-model),
elk een paar tientallen tokens, en meldt model, regio, snelheid en of het
antwoord geldige JSON was. Kosten: een fractie van een cent.

    AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... python scripts/bedrock_check.py

Optioneel: BEDROCK_REGION, BEDROCK_MODEL, BEDROCK_SOEP_MODEL (zie DEPLOY.md).
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cloud_api import llm_service  # noqa: E402
from services.cloud_api.config import get_config  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"icpc": {"type": "string"}, "omschrijving": {"type": "string"}},
    "required": ["icpc", "omschrijving"],
    "additionalProperties": False,
}


async def main() -> int:
    cfg = get_config().llm
    probleem = llm_service.bedrock_eu_problem(cfg.bedrock_region, cfg.bedrock_model, cfg.bedrock_soep_model)
    if probleem:
        print(f"Niet EU: {probleem}. Er is niets verstuurd.")
        return 1
    if not (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")):
        print("Zet AWS_ACCESS_KEY_ID en AWS_SECRET_ACCESS_KEY.")
        return 1
    print(f"Regio {cfg.bedrock_region}")
    ok = True
    for quality, model in ((False, cfg.bedrock_model), (True, cfg.bedrock_soep_model)):
        start = time.time()
        try:
            raw = await llm_service.complete(
                "Je bent een Nederlandse huisarts. Antwoord kort.",
                "Welke ICPC-code hoort bij een ongecompliceerde blaasontsteking?",
                provider="bedrock", json_mode=True, max_tokens=200, quality=quality,
                json_schema=SCHEMA,
            )
            data = json.loads(raw)
            print(f"  {model}: ok in {time.time() - start:.1f} s -> {data}")
        except Exception as exc:  # report every failure, then continue
            ok = False
            print(f"  {model}: FOUT {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

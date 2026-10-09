#!/usr/bin/env python3
"""
VitaScribe - Few-shot koude start (seed)
========================================

Laadt gecureerde, synthetische SOEP-voorbeelden in de few-shot-bank, zodat de
SOEP-generatie vanaf dag 1 op niveau functioneert - nog vóór er echte
artsfeedback is.

Gebruik:
    python tools/seed_fewshot_bank.py
    python tools/seed_fewshot_bank.py --bank /data/fewshot/soep_examples.json

De voorbeelden bevatten GEEN patiëntdata en zijn ter review door de arts.
Praktijkeigen voorbeelden (tools/build_fewshot_bank.py) komen er later naast.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.learning.fewshot_seed import DEFAULT_SEED_PATH, seed_bank  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="VitaScribe few-shot seed (koude start)")
    ap.add_argument("--bank", default=None,
                    help="Pad naar de few-shot-bank (default: FEWSHOT_BANK_PATH of config)")
    ap.add_argument("--seed", default=DEFAULT_SEED_PATH,
                    help="Pad naar het seed-bestand (default: ingebouwde set)")
    args = ap.parse_args(argv)

    bank_path = args.bank
    if not bank_path:
        try:
            from shared.config.settings import config
            bank_path = config.fewshot.bank_path
        except Exception:
            bank_path = "/data/fewshot/soep_examples.json"

    added, total = seed_bank(bank_path, seed_path=args.seed)
    print(f"Seed geladen: {added} voorbeelden toegevoegd/bijgewerkt. "
          f"Bank bevat nu {total} voorbeelden ({bank_path}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

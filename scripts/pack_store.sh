#!/usr/bin/env bash
# Pakt chrome-extension/ in als .zip voor de Edge Add-ons-winkel (Partner Center).
# Gebruik:
#
#   scripts/pack_store.sh [server-host] [uitvoermap]
#   scripts/pack_store.sh smartvoice-production.up.railway.app
#
# WAAROM EEN APART PAKKET
#
# De eigen uitrol (pack_extension.sh) maakt een ondertekende .crx met de
# .pem-sleutel, en het beleid op de werkplekken installeert die. De winkel wil
# iets anders: een gewone .zip, zonder sleutel, en ondertekent zelf. Daardoor
# krijgt de winkelversie een EIGEN extensie-ID. Instellingen (serveradres,
# sleutel) gaan niet mee van de ene versie naar de andere.
#
# Het manifest in de repo is gemaakt voor ontwikkeling en eigen uitrol. Voor de
# keuring halen we er weg wat alleen voor ontwikkeling is, en maken we de
# serverrechten zo smal als ze kunnen:
#
#   - localhost:8002 (de ontwikkelserver en de nagebootste Bricks-pagina)
#     verdwijnt uit host_permissions en uit de content scripts. In de code
#     wordt de eigen server het standaardadres voor een lege instelling.
#   - *.up.railway.app (elke app op Railway) wordt het ene adres van de eigen
#     server. Een keurder vraagt anders terecht waarom de extensie bij elke
#     Railway-app mag.
#
# Het script verandert niets aan chrome-extension/; het werkt op een kopie.
set -euo pipefail

HOST="${1:-smartvoice-production.up.railway.app}"
OUT="${2:-dist/store}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$HOST" == *"/"* || "$HOST" == *"*"* ]]; then
  echo "Geef alleen de hostnaam, zonder https:// en zonder sterretje: bv. smartvoice-production.up.railway.app" >&2
  exit 2
fi

WERK="$(mktemp -d)"
trap 'rm -rf "$WERK"' EXIT
cp -R "$ROOT/chrome-extension" "$WERK/ext"
# Voorbeeldconfiguratie van de server en Finder-rommel horen niet in het pakket.
rm -f "$WERK/ext/.env.example"
find "$WERK/ext" -name '.DS_Store' -delete

python3 - "$WERK/ext/manifest.json" "$HOST" <<'PY'
import json, sys

pad, host = sys.argv[1], sys.argv[2]
m = json.load(open(pad, encoding="utf-8"))

# Een sleutel of eigen updateadres in het manifest laat de winkel het pakket
# weigeren; ze horen bij de eigen uitrol, niet hier.
for veld in ("key", "update_url"):
    if veld in m:
        sys.exit(f"manifest.json bevat '{veld}'; dat hoort niet in een winkelpakket.")

ontwikkeling = lambda p: p.startswith("http://localhost")

rechten = []
for p in m.get("host_permissions", []):
    if ontwikkeling(p):
        continue
    rechten.append(f"https://{host}/*" if p == "https://*.up.railway.app/*" else p)
if f"https://{host}/*" not in rechten:
    rechten.append(f"https://{host}/*")
m["host_permissions"] = rechten

for cs in m.get("content_scripts", []):
    cs["matches"] = [p for p in cs["matches"] if not ontwikkeling(p)]
    if not cs["matches"]:
        sys.exit("Een content script houdt geen adressen over; controleer het manifest.")

over = [p for p in json.dumps(m).split('"') if "localhost" in p or "*.up.railway.app" in p]
if over:
    sys.exit(f"Er staan nog ontwikkeladressen in het manifest: {over}")

json.dump(m, open(pad, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(pad, "a", encoding="utf-8").write("\n")
print(f"versie {m['version']}")
PY

# Het standaardadres: wie niets invult, praat in het winkelpakket met de
# VitaScribe-server en niet met een testserver op de eigen computer (die de
# rechten hierboven toch al niet toelaten).
python3 - "$WERK/ext" "$HOST" <<'PY'
import pathlib, sys

map_, host = pathlib.Path(sys.argv[1]), sys.argv[2]
ontwikkel, server = "http://localhost:8002", f"https://{host}"
hint = "Bijv. https://smartvoice-production.up.railway.app (cloud) of http://localhost:8002 (lokaal)"
for pad in list(map_.rglob("*.js")) + list(map_.rglob("*.html")):
    tekst = pad.read_text(encoding="utf-8")
    nieuw = tekst.replace(hint, f"Standaard: {server}").replace(ontwikkel, server)
    if nieuw != tekst:
        pad.write_text(nieuw, encoding="utf-8")
# A localhost address left in the package (not the word itself: a pattern that
# recognises a local development server, lib/instellingen.js, may name it).
over = [str(p.relative_to(map_)) for p in map_.rglob("*") if p.is_file() and p.suffix in (".js", ".html", ".json")
        and "://localhost" in p.read_text(encoding="utf-8")]
if over:
    sys.exit(f"Er staat nog localhost in het pakket: {over}")
print(f"standaardserver {server}")
PY

VERSION="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" "$WERK/ext/manifest.json")"
mkdir -p "$ROOT/$OUT"
ZIP="$ROOT/$OUT/vitascribe-edge-$VERSION.zip"
rm -f "$ZIP"
# manifest.json moet bovenin de zip staan, niet in een submap.
(cd "$WERK/ext" && zip -qr -X "$ZIP" .)

echo "Klaar: $ZIP"
echo "Server in het manifest: https://$HOST"
echo "Upload dit bestand in Partner Center. Verhoog bij elke volgende upload eerst"
echo "de versie in chrome-extension/manifest.json; de winkel weigert een versie die"
echo "hij al kent."

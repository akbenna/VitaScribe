# 13 Release- en wijzigingsbeheer

In fase 1 aanbevolen, in fase 2 verplicht. Elke wijziging aan een prompt, een
model of de pipeline kan de inhoud van verslagen veranderen. Daarom gaat geen
versie live zonder toets.

## Werkwijze

1. **Wijziging via een pull request** op GitHub, met een beschrijving van wat
   er verandert en waarom.
2. **Automatische proeven**: Python (`pytest`), JavaScript (`node --test`), en
   de browserproeven van de extensie. Alles groen.
3. **Testset met gespeelde consulten** (`services/cloud_api/testset/`). Bij een
   wijziging die het verslag raakt, zoals een prompt, een model of de
   controleronde, draait de testset in beide modi. Vergelijk de score met de
   vorige versie. De versie gaat niet live als de score daalt zonder
   verklaring.
4. **Vastleggen**: het versienummer van de extensie in `manifest.json`, de
   wijziging in de beschrijving van het pull request, de datum van de deploy.
5. **Uitrol**:
   - de server via Railway, na het samenvoegen;
   - de extensie in fase 1 intern, in fase 2 via de winkel;
   - bij een wijziging die niet terugwaarts werkt: de minimumversie
     (`MIN_EXTENSIE_VERSIE`) ophogen.
6. **Terugrollen**: Railway kan een vorige deployment herstellen. Noteer
   wanneer dat gebeurde en waarom.

## Wezenlijke wijzigingen

Een wezenlijke wijziging vraagt meer dan de werkwijze hierboven. Het gaat dan
om:

- een andere aanbieder of een model van een andere aanbieder;
- een nieuwe gegevensstroom;
- de Claude-modus voor echte patiënten;
- klinisch meedenken aan;
- de overgang naar fase 2.

Bij zo'n wijziging:

- werk de DPIA bij (stuk 03);
- werk de subverwerkerslijst bij (stuk 05);
- meld het in fase 2 30 dagen vooraf aan de klantpraktijken;
- toets het opnieuw aan het beoogd gebruik (stuk 01).

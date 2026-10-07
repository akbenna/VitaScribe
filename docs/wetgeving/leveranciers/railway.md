# Railway Corp. (hosting: VitaScribe-server, ConsultSpiegel, ProVita SciencePulse-pipeline)

Stand 7 oktober 2026. Bronnen: `docs/fase2/LEVERANCIERS-EN-VERWERKERS.md` (Bricks Companion, 5 oktober 2026), `docs/dossier/05-subverwerkers.md` (VitaScribe, 5 oktober 2026), `docs/AUDIT-EU-MODUS.md` (VitaScribe). De site van Railway was vanuit deze omgeving niet bereikbaar; wat hieronder over de DPA-tekst staat komt uit de eigen samenvatting in de Bricks-repo en moet tegen de getekende envelop worden nagelezen.

## Wat vastligt

- Verwerkersovereenkomst getekend op 5 oktober 2026 (DocuSign-envelop 15F6A42D-5BA0-8848-82F5-EDC780AD0A6F), op naam van ProVita. Railway is verwerker, de praktijk of ProVita verwerkingsverantwoordelijke.
- Railway is actief in het EU-US Data Privacy Framework; subsidiair SCC's (DPA art. 9.6). SOC 2 Type II.
- Infrastructuur: Google Cloud. Subverwerkers op trust.railway.com, wijzigingen 10 dagen vooraf.
- Regio van de projecten: Europa-West (europe-west4, Nederland) voor VitaScribe en ConsultSpiegel volgens de audit; de regio staat nergens in code of configuratie en moet in het Railway-dashboard per project worden vastgelegd met een schermafdruk.
- Bijlage A van de DPA vermeldt bij bijzondere categorieën "None". De Bricks-repo concludeerde daaruit: geen gezondheidsgegevens via Railway, ook niet gepseudonimiseerd.

## Wat dat betekent

De VitaScribe- en ConsultSpiegel-servers draaien op Railway en verwerken audio en transcripten van consulten in het werkgeheugen. Dat zijn gezondheidsgegevens, ook al wordt niets bewaard. De eigen conclusie in de Bricks-repo (geen gezondheidsgegevens via Railway) en het feitelijke gebruik in VitaScribe en ConsultSpiegel spreken elkaar dus tegen. Dat is het belangrijkste open punt van deze leverancier.

Twee uitwegen, één te kiezen:
1. Railway schriftelijk laten bevestigen dat gezondheidsgegevens (doorstroom, niet opgeslagen) onder de DPA vallen, en bijlage A laten aanpassen. Daarnaast een transfer impact assessment voor de CLOUD Act (Amerikaanse moeder, data in Nederland).
2. Verhuizen naar een Europese host (Hetzner, Scaleway, OVH). VitaScribe noemt dit "technisch een kleine verhuizing" (werkplan EU, stap 1).

## Nog te doen

1. Schermafdruk van de regio per project (VitaScribe, ConsultSpiegel, SciencePulse) in `docs/wetgeving/bewijs/`.
2. Bevestiging over gezondheidsgegevens vragen, of besluit 2 nemen.
3. SOC 2-rapport opvragen en bewaren.
4. Vastleggen op welke rechtspersoon het Railway-account en de DPA staan, en of dat dezelfde is als de verwerkingsverantwoordelijke (zie Besluit 1 in het stappenplan).
5. Back-ups van de Railway-PostgreSQL (ConsultSpiegel-sessies, VitaScribe-register en auditlog): bewaartermijn van back-ups vastleggen; die valt buiten de eigen opruimtaken.

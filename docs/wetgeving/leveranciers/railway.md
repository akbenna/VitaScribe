# Railway Corp. (hosting: VitaScribe-server, ConsultSpiegel, ProVita SciencePulse-pipeline)

Stand 7 oktober 2026. Bronnen: de getekende DPA zelf (nagelezen op 7 oktober 2026), het antwoord van Railway Support van 5 oktober 2026 (beide in `bewijs/railway-dpa-2026-10-05.md`), `docs/dossier/05-subverwerkers.md` en `docs/AUDIT-EU-MODUS.md` (VitaScribe).

## Wat vastligt

- Verwerkersovereenkomst getekend op 5 oktober 2026 (DocuSign-envelop 15F6A42D-5BA0-8848-82F5-EDC780AD0A6F). Exporteur in bijlage B: "A. Bennaghmouch h.o.d.n. ProVitaCare". Railway is verwerker; wie verwerkingsverantwoordelijke is, hangt af van besluit 1.
- Railway is actief in het EU-US Data Privacy Framework; subsidiair SCC's (DPA art. 9.6). SOC 2 Type II.
- Infrastructuur: Google Cloud. Subverwerkers op trust.railway.com, wijzigingen 10 dagen vooraf.
- Regio van de projecten: Europa-West (europe-west4, Nederland) voor VitaScribe en ConsultSpiegel volgens de audit; de regio staat nergens in code of configuratie en moet in het Railway-dashboard per project worden vastgelegd met een schermafdruk.
- Bijlage A van de DPA vermeldt bij bijzondere categorieën "None", en als betrokkenen alleen klanten en hun medewerkers. Art. 3 verbiedt gegevens die niet bij de dienst passen en legt dat risico, met vrijwaring, bij de klant. Art. 9.1 zegt dat de verwerking primair in de VS plaatsvindt.

## Antwoord van Railway (5 oktober 2026)

Railway heeft op de vraag over gezondheidsgegevens geantwoord (afschrift in `bewijs/railway-dpa-2026-10-05.md`):

- De DPA dekt geen bijzondere persoonsgegevens (art. 9 AVG). Bijlage A ("Special Categories of Data: None") wordt voor niemand aangepast.
- EU West staat in Amsterdam: service, volumes, back-ups en PostgreSQL-herstelgegevens staan daar.
- Application-, deploy-, build- en HTTP-logs staan voor elke service in US West.
- Er is op geen enkel plan een contractuele toezegging voor verwerking alleen in de EU.
- Een BAA (HIPAA) bestaat op het Enterprise-plan, maar dat is Amerikaans recht en lost de AVG-vraag niet op.

## Wat dat betekent

Besluit 2 uit het stappenplan is daarmee beantwoord. Gezondheidsgegevens van echte patiënten gaan niet via Railway, ook niet als doorstroom. Voor VitaScribe en ConsultSpiegel is de route een server bij een Europese host (Hetzner, Scaleway of OVHcloud) voor alles met echte patiënten. VitaScribe heeft die mogelijkheid al: werkplan stap 4, `deploy/eu/`, en in de extensie de instelling "Server voor de EU-modus".

Railway blijft bruikbaar voor gespeelde consulten, simulatie en diensten zonder gezondheidsgegevens (ProVita SciencePulse, websites). Omdat de logs in de VS staan, mag geen logregel inhoud bevatten; namen van gebruikers in het auditlog zijn persoonsgegevens van medewerkers en staan dan ook in de VS (in het register opnemen).

## Nog te doen

1. Schermafdruk van de regio per project (VitaScribe, ConsultSpiegel, SciencePulse) in `docs/wetgeving/bewijs/`.
2. ~~Bevestiging over gezondheidsgegevens vragen.~~ Beantwoord op 5 oktober 2026: valt er niet onder. Besluit 2: Europese host voor echte patiënten.
3. SOC 2-rapport opvragen en bewaren.
4. Vastleggen op welke rechtspersoon het Railway-account en de DPA staan, en of dat dezelfde is als de verwerkingsverantwoordelijke (zie Besluit 1 in het stappenplan).
5. Back-ups van de Railway-PostgreSQL (ConsultSpiegel-sessies, VitaScribe-register en auditlog): bewaartermijn van back-ups vastleggen; die valt buiten de eigen opruimtaken.

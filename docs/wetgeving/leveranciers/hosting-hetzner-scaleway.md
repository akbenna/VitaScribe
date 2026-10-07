# Europese host voor echte patiënten: Hetzner of Scaleway

Stand 7 oktober 2026. Besluitstuk bij besluit 2 uit het stappenplan. Prijzen
zijn exclusief btw. De sites van beide hosts waren vanuit de werkomgeving niet
rechtstreeks te openen; de cijfers komen uit zoekresultaten (eigen pagina's van
de hosts waar mogelijk, anders vergelijkingssites, zie de bronnen onderaan).
Controleer prijs en voorraad in de console vóór je bestelt.

## Wat de server moet doen

De vraag is niet welke host beter is, maar welke past bij wat er al staat.

**VitaScribe** (nu). De Europese server is een doorgeefluik: audio en tekst
gaan van de extensie via de server naar Mistral en terug. Er blijft geen
opname of verslag staan, alleen het register en het auditlog zonder inhoud.
`deploy/eu/` is gebouwd voor een gewone virtuele machine: Docker Compose,
PostgreSQL in een container, Caddy voor het certificaat. 2 vCPU en 4 GB is
ruim.

**ConsultSpiegel** (later, als er echte consulten komen). Zwaarder: Whisper
lokaal als terugvaloptie (model medium, int8, op CPU) en pyannote voor de
sprekerherkenning, plus een database met gepseudonimiseerde transcripten. Dat
vraagt eerder 4 vCPU en 8 GB, en hier blijft wel gezondheidsinformatie staan.

**ProVita, BennaHealth en Bricks Companion** hebben geen server bij deze host
nodig.

De les van Railway: de eerste vraag is niet de prijs maar of de
verwerkersovereenkomst gezondheidsgegevens toelaat. Railway zei nee (bijlage A
"None", art. 3 met vrijwaring). Die vraag staat hieronder dus voorop.

## De doorslaggevende vraag: mogen gezondheidsgegevens erop?

**Scaleway: in het gewone aanbod niet.** De DPA van Scaleway (versie juni 2024)
legt de keuze van de dienst bij de klant en zegt dat waar Scaleway een
specifieke dienst aanbiedt, de klant die moet gebruiken, met gezondheidsgegevens
als eerste voorbeeld. Een oudere versie zei het rechtstreeks: de klant verwerkt
geen gezondheidsgegevens via de diensten. Voor gezondheidsgegevens heeft
Scaleway een apart HDS-aanbod (Hébergeur de Données de Santé, de Franse
certificering). Volgens Scaleway zelf:

- loopt dat via een eigen verkooptraject en een apart HDS-contract; zonder dat
  traject is het hosten van gezondheidsgegevens "strictly prohibited";
- is er een Business- of Enterprise-supportabonnement bij nodig (Business:
  minimaal 250 euro per maand of 10 procent van de rekening);
- staat de data dan uitsluitend in Franse datacenters, dus niet in Amsterdam;
- geldt de certificering voor een afgebakende set diensten: instances (CPU en
  GPU), object- en blokopslag, bare metal en VPC. Juist de diensten die op
  Railway lijken (Serverless Containers, beheerde PostgreSQL) staan daar in de
  bronnen niet bij.

Met het gewone Scaleway-account zouden we dus precies in de valkuil van Railway
lopen, maar dan met de DPA die het zelf al zegt.

**Hetzner: ja, als je het zelf vastlegt.** De AVV (verwerkersovereenkomst naar
art. 28 AVG) sluit je in de console af. Vooraf kies je welke soorten
persoonsgegevens en welke betrokkenen het betreft, uit een lijst of als eigen
invoer, en dat komt in bijlage 1 van de overeenkomst. Er is geen bepaling
gevonden die gezondheidsgegevens uitsluit. Wel twee kanttekeningen:

- De oudere voorbeeld-AVV's die te vinden zijn, noemen in bijlage 1 alleen
  stamgegevens, communicatiegegevens, contractgegevens, logs en betaalgegevens.
  Of de console nu een vakje voor gezondheidsgegevens heeft, is niet
  vastgesteld. Zet het er anders als eigen invoer bij: "gezondheidsgegevens
  (art. 9 AVG) van patiënten, in doorvoer en in een database".
- Hetzner zegt zelf dat de klant verantwoordelijk is voor de gegevens op de
  server en voor de versleuteling ervan. Dat past bij een virtuele machine: wij
  beheren de server, Hetzner levert de machine.

Advies: vraag bij het afsluiten via een ticket ook schriftelijk bevestiging
dat gezondheidsgegevens onder de AVV vallen, en bewaar dat antwoord in
`docs/wetgeving/bewijs/`. Dan staat het zwart op wit, anders dan bij Railway
achteraf.

## Vergelijking op alle punten

| | Hetzner | Scaleway (gewoon) | Scaleway HDS |
|---|---|---|---|
| Bedrijf | Hetzner Online GmbH, Gunzenhausen (DE), familiebedrijf, geen Amerikaanse moeder | Scaleway SAS, Parijs, onderdeel van iliad (FR), geen Amerikaanse moeder | idem |
| CLOUD Act | niet van toepassing | niet van toepassing | niet van toepassing |
| Gezondheidsgegevens | toegestaan als je ze in bijlage 1 van de AVV opneemt (schriftelijk laten bevestigen) | niet toegestaan volgens de DPA | daarvoor bedoeld |
| Locatie | Neurenberg of Falkenstein (DE), Helsinki (FI) | Parijs, Amsterdam, Warschau, Milaan | alleen Frankrijk |
| Certificering | ISO/IEC 27001:2022 (Neurenberg, Falkenstein, Helsinki); BSI C5 type 2 alleen door derden genoemd, niet bevestigd | ISO/IEC 27001:2022 | HDS (door BSI Group), ISO 27001; SecNumCloud in aanvraag |
| NEN 7510 | nee | nee | nee |
| Kleinste passende server (VitaScribe, 2 vCPU, 4 GB) | CX23: 5,49 per maand, maar sinds juni 2026 meestal uitverkocht; CPX22: 19,99 per maand, wel te bestellen | DEV1-S (2 vCPU, 2 GB) rond 6,50 plus 2,92 voor een IPv4-adres; DEV1-M voor 4 GB | instance-prijs plus Business-support minimaal 250 per maand; HDS-toeslag niet openbaar, via verkoop |
| Server voor ConsultSpiegel (4 vCPU, 8 GB) | CX33: 8,49 (meestal uitverkocht); CPX32: 35,99 | PLAY2-NANO rond 19,50 plus opslag en IPv4 | als links, plus het supportabonnement |
| Back-ups | automatische back-ups voor ongeveer 20 procent van de serverprijs (7 dagen) | snapshots en back-ups per GB | idem |
| Beheerde PostgreSQL | geen eigen dienst | ja, vanaf rond 11 per maand | niet in de genoemde HDS-afbakening |
| Railway-achtig (container zonder server) | nee | Serverless Containers | niet in de genoemde HDS-afbakening |
| Spraak en taal in de EU als eigen dienst | nee | Generative APIs: Whisper large v3 (0,003 per minuut) en Mistral-modellen, in Europese datacenters | niet in de genoemde HDS-afbakening |
| Beschikbaarheid | sinds 26 juni 2026 beperkt: nieuwe servers voor nieuwe klanten (en een deel van de bestaande) worden geweigerd door krapte aan hardware; volgens de status nog niet opgelost | geen vergelijkbare melding gevonden | via verkoop, doorlooptijd onbekend |
| Prijsontwikkeling 2026 | twee verhogingen (1 april en 15 juni), CPX en CCX tot +176 procent | gerichte verhogingen per 1 juni, bij kleine instances een paar procent | onbekend |
| Support | tickets, ma t/m vr 8 tot 18 uur, voor de cloud 24/7 in uitzonderingen; geen betaalde abonnementen | Basic gratis (8 uur reactietijd), Advanced 50 per maand (2 uur) | Business verplicht (30 minuten, 24/7) |
| Taal | Duits en Engels | Frans en Engels | Frans en Engels |
| Gebruiksgemak | eenvoudige console, weinig keuzes, past één op één op `deploy/eu/` | uitgebreide console in de stijl van AWS, veel diensten | verkooptraject, contract, daarna een VM zoals bij Hetzner |
| Account | soms identiteitscontrole bij aanmelden (paspoort, via iDenfy); betaalmiddel op eigen naam | gewone aanmelding | via verkoop |

## Wat dit betekent voor de constructie

**Gebruiksgemak valt weg als verschil.** Het voordeel van Scaleway, dat het
"meer op Railway lijkt", zit in Serverless Containers en beheerde PostgreSQL.
Die vallen voor gezondheidsgegevens buiten het HDS-aanbod. Voor echte patiënten
draai je bij allebei dus een gewone virtuele machine, en daarvoor is
`deploy/eu/` al geschreven. Bijwerken (`git pull`, opnieuw starten) en de
back-up van het register doe je bij beide zelf.

**De kosten lopen ver uiteen.** Bij Hetzner kost de VitaScribe-server tussen
de 6 en 24 euro per maand, back-up inbegrepen, afhankelijk van of er een CX23
vrij is. Scaleway HDS begint bij 250 euro per maand alleen al voor het
verplichte supportabonnement, plus de server en een HDS-toeslag die alleen de
verkoop noemt. Voor een doorgeefluik met twee artsen is dat buiten verhouding.

**Wat Scaleway HDS wél biedt** is een certificaat dat speciaal voor
gezondheidsgegevens bestaat, en het merkt dat de Franse nationale
gezondheidsdata-hub in april 2026 voor Scaleway koos. Tegenover klantpraktijken
in fase 2 is dat een sterk verhaal. Maar HDS is Frans recht; Nederlandse
praktijken vragen om NEN 7510, en die heeft geen van beide hosts. Voor fase 2 is
het dus geen beslissend voordeel.

**Het echte risico bij Hetzner is beschikbaarheid, niet de wet.** Sinds eind
juni weigert Hetzner nieuwe servers aan een deel van de klanten, nieuwe klanten
voorop, en de goedkope CX-lijn is meestal uitverkocht. Het kan dus zijn dat je
een account maakt en geen server krijgt, of alleen een duurdere CPX22. Dat is
lastig, maar geen blokkade: CPX22 is voor deze toepassing goed genoeg en voor
19,99 per maand nog steeds een fractie van Scaleway HDS.

## Advies

**Kies Hetzner.** Het past bij wat er staat: een virtuele machine met Docker
Compose, met een overeenkomst waarin je de gezondheidsgegevens zelf benoemt in
plaats van ze stilzwijgend uit te sluiten. Het is de goedkoopste route die
juridisch klopt, en het Duitse bedrijf valt buiten de CLOUD Act.

Doe het in deze volgorde:

1. Account op naam van de rechtspersoon die ook verwerkingsverantwoordelijke
   is (besluit 1). Dezelfde fout als bij de Railway-DPA ("h.o.d.n.
   ProVitaCare") hier niet herhalen.
2. AVV in de console vóór de eerste server. In bijlage 1: gezondheidsgegevens
   (art. 9 AVG) van patiënten, en als betrokkenen patiënten en medewerkers.
3. Ticket aan Hetzner met de vraag te bevestigen dat dat onder de AVV valt.
   Het antwoord gaat naar `docs/wetgeving/bewijs/`.
4. Server: CX23 als die vrij is, anders CPX22. Locatie Neurenberg of
   Falkenstein (beide onder het ISO-certificaat). Automatische back-ups aan.
5. Dan `deploy/eu/README.md` volgen.
6. ConsultSpiegel pas als er echte consulten komen, op een eigen server
   (CX33 of CPX32), zodat een fout in het ene product het andere niet raakt.

**Kies Scaleway HDS alleen als** je in fase 2 een gecertificeerde
gezondheidshost als verkoopargument wilt, en bereid bent tot een
verkooptraject, een Franse locatie en minimaal rond de 270 euro per maand. Dat
besluit kan later: de code verhuist met één domeinnaam.

**Het gewone Scaleway-aanbod valt voor echte patiënten af**, om dezelfde reden
als Railway.

## Wat nog te controleren is

- Hetzner: of de console gezondheidsgegevens in bijlage 1 accepteert, en de
  bevestiging per ticket (stap 2 en 3 hierboven).
- Hetzner: of BSI C5 type 2 echt bestaat (alleen door een derde genoemd).
- Hetzner: actuele voorraad en prijs van CX23 en CPX22 op de dag van bestellen.
- Scaleway, alleen als het in beeld komt: de prijs van HDS via verkoop, en het
  certificaat met de afbakening van de diensten.

## Bronnen

- Hetzner prijzen en verhogingen 2026: [Better Stack](https://betterstack.com/community/guides/web-servers/hetzner-cloud-review/), [Northflank](https://northflank.com/blog/hetzner-cloud-server-price-increases), [wz-it](https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/), [Vincent Schmalbach](https://www.vincentschmalbach.com/hetzner-cheap-cloud-unavailable-price-increases/), [costgoat](https://costgoat.com/pricing/hetzner)
- Hetzner beschikbaarheid: [statuspagina Hetzner](https://status.hetzner.com/incident/0a75c7ae-3377-41dc-aabe-601063724d24), [bex.co](https://bex.co/blog/2026/08/19/hetzner-capacity-crunch-owning-hardware-when-provider-says-no-stock)
- Hetzner certificering en AVV: [Hetzner certificaten](https://www.hetzner.com/unternehmen/zertifizierung/), [Hetzner Docs, gegevensbescherming](https://docs.hetzner.com/de/general/general-terms-and-conditions/data-privacy-faq/), [voorbeeld-AVV Hetzner](https://www.hetzner.com/AV/DPA_de.pdf)
- Hetzner support en identiteit: [Hetzner Docs, openingstijden support](https://docs.hetzner.com/general/infrastructure-and-availability/support-team-opening-hours/), [Hetzner Docs, fraudepreventie](https://docs.hetzner.com/general/security-and-identify/fraud-prevention-faq/)
- Scaleway DPA en HDS: [DPA juni 2024](https://www-uploads.scaleway.com/DPA_2024_ENG_b0abb5cc26.pdf), [DPA 2021](https://www-uploads.scaleway.com/Data_Processing_Agreement_03092021_6e2ca4da3c.pdf), [Scaleway HDS](https://www.scaleway.com/en/security-and-compliance/hds/), [Scaleway zorg](https://www.scaleway.com/en/healthcare-and-life-sciences-solutions/), [Scaleway beveiliging en compliance](https://www.scaleway.com/en/security-and-compliance/), [Qovery over HDS](https://www.qovery.com/blog/hds-certified-hosting-providers-compliant-cloud-migration)
- Scaleway en de Franse gezondheidsdata-hub: [Scaleway nieuws](https://www.scaleway.com/en/news/scaleway-selected-to-support-frances-health-data-hub-in-its-transition-to-a-sovereign-cloud/), [Usine Digitale](https://www.usine-digitale.fr/souverainete/souverainete-numerique-adieu-microsoft-scaleway-va-devenir-le-nouvel-hebergeur-de-la-plateforme-des-donnees-de-sante-des-francais.NQ6547FIANFI7ATVDC7DXQ7EFA.html)
- Scaleway prijzen: [prijsupdate Scaleway](https://www.scaleway.com/en/blog/a-transparent-update-on-scaleway-pricing/), [eucloudcost](https://www.eucloudcost.com/providers/scaleway/), [HostStack over PostgreSQL](https://hoststack.dev/blog/scaleway-postgresql-pricing-2026), [Serverless-prijzen](https://www.scaleway.com/en/pricing/serverless/), [Generative APIs](https://www.scaleway.com/en/generative-apis/)
- Scaleway support: [supportabonnementen](https://www.scaleway.com/en/support/), [uitleg abonnementen](https://www.scaleway.com/en/docs/account/support/understanding-support-plans/)

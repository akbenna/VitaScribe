# Bewijsstuk: Railway, verwerkersovereenkomst en gezondheidsgegevens

Afschrift van het antwoord van Railway Support (support@railway.com) aan a.benna@outlook.com, maandag 5 oktober 2026, 23:17, onderwerp "Re: FW: Voltooid: Railway Corporation Data Processing Addendum". Het origineel staat in de mailbox en hoort als PDF bij het praktijkdossier, naast de getekende DPA (envelop 15F6A42D-5BA0-8848-82F5-EDC780AD0A6F).

## Letterlijk

> Thank you for sending the executed DPA.
>
> On your first question: our published Data Processing Addendum is the only data processing agreement we offer, and we do not amend it or its exhibits for any customer, including the "Special Categories of Data: None" line in Exhibit A. That means the DPA contains no terms covering the processing of GDPR Article 9 data, and an amended Exhibit A is not available. Whether your processing can proceed on that basis is a decision for you and your own counsel.
>
> If your processing falls under HIPAA, a BAA is available on our Enterprise plan at a $1,000/month minimum committed for 12 months. It sits alongside the DPA and does not modify it.
>
> On your second question: EU West is located in Amsterdam, Netherlands. A service deployed there runs there, and any volume attached to it is stored there, along with its volume backups and PostgreSQL point-in-time recovery data. Application, deploy, build, and HTTP logs are stored in US West for every service, including EU West services. We have not verified the placement of your specific services in this reply, and we do not offer a contractual commitment to EU-only processing on any plan.
>
> Our subprocessor list is at trust.railway.com/item/subprocessors, and our security materials are at trust.railway.com.

## Wat hiermee vaststaat

| Vraag | Antwoord van Railway | Gevolg |
|---|---|---|
| Vallen gezondheidsgegevens (art. 9 AVG) onder de DPA? | Nee. Bijlage A zegt "Special Categories of Data: None" en wordt voor geen enkele klant aangepast. | Voor gezondheidsgegevens is er geen verwerkersovereenkomst met Railway in de zin van art. 28 lid 3 AVG. Dat geldt ook voor gegevens die alleen doorstromen. |
| Is een BAA een oplossing? | Alleen voor HIPAA, Enterprise-plan, 1.000 dollar per maand, 12 maanden. Wijzigt de DPA niet. | Geen oplossing: HIPAA is Amerikaans recht en dekt de AVG niet. |
| Waar draait EU West? | Amsterdam. Service, volumes, volumeback-ups en PostgreSQL-herstelgegevens staan daar. | De database en het geheugen van de server staan in Nederland. |
| Waar staan de logs? | Application-, deploy-, build- en HTTP-logs staan voor elke service in US West, ook voor EU West-services. | Alles wat de server naar stdout schrijft, en elk HTTP-verzoek (IP-adres, pad), ligt in de VS. |
| Contractuele toezegging alleen-EU? | Nee, op geen enkel plan. | Er is geen garantie dat verwerking in de EU blijft. |

## Conclusie voor de producten

- **VitaScribe en ConsultSpiegel**: echte consulten (gezondheidsgegevens van patiënten) mogen niet via de Railway-server. Dat geldt voor de EU-modus net zo goed als voor de Claude-modus: de server op Railway ziet de audio en de tekst, ook als hij niets bewaart. De route is een server bij een Europese host. Voor VitaScribe is die gebouwd (werkplan stap 4, `deploy/eu/`).
- **Railway blijft bruikbaar** voor wat geen gezondheidsgegevens bevat: gespeelde consulten en simulatie, de SciencePulse-pipeline van ProVita (openbare literatuur), en websites zonder patiëntgegevens.
- **Logs**: zolang Railway in gebruik is, mag geen enkele logregel inhoud bevatten. VitaScribe logt zonder inhoud en het testgereedschap staat standaard uit; het auditlog op stdout bevat wel namen van gebruikers (persoonsgegevens van medewerkers, geen gezondheidsgegevens), en dat staat dus in de VS.

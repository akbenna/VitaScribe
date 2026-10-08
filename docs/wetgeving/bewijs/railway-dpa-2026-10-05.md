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

## Wat de getekende DPA zelf zegt

Nagelezen in de getekende versie (DocuSign-envelop 15F6A42D-5BA0-8848-82F5-EDC780AD0A6F, ingangsdatum 5 oktober 2026). De DPA bevestigt de mail van support en gaat op drie punten verder.

| Bepaling | Tekst (samengevat) | Gevolg |
|---|---|---|
| Bijlage A, Special Categories | "Sensitive Data or Special Categories of Data: None" | Zoals support schreef: geen gezondheidsgegevens. |
| Bijlage A, betrokkenen | "Customers and Customer employees" | Patiënten staan niet in de omschrijving. Ook dat sluit gezondheidsgegevens van patiënten buiten de overeenkomst. |
| Art. 3, plichten van de klant | De klant levert geen persoonsgegevens die "inappropriate for the nature of the Services" zijn, en vrijwaart Railway voor alle claims en schade die daaruit volgen. | Gezondheidsgegevens via Railway laten lopen is niet alleen onbeschermd, het is ook een tekortkoming van de klant, met een vrijwaring. Het risico ligt dan contractueel bij de praktijk. |
| Art. 9.1, doorgifte | Railway verklaart dat zijn "primary processing operations take place in the United States" en dat doorgifte naar de VS nodig is voor de dienst. Grondslag: DPF of de SCC's (art. 9.2). | De klant erkent doorgifte naar de VS. De keuze voor regio EU West verandert dat contractueel niet. |
| Bijlage B, partijen | Data-exporteur: "A. Bennaghmouch h.o.d.n. ProVitaCare", Roermond. | De DPA staat op naam van ProVitaCare, niet op die van de praktijk of de holding. Dat raakt besluit 1 in het stappenplan (welke rechtspersoon). |
| Art. 6, subverwerkers | Algemene toestemming; nieuwe subverwerkers 10 dagen vooraf op trust.railway.com, met bezwaarrecht. | Abonneren op die meldingen (art. 6.2 vraagt dat van de klant). |
| Art. 8, datalek | Melding "without undue delay", zonder termijn in uren. | De VitaScribe-verwerkersovereenkomst belooft de praktijk 24 uur; die belofte rust voor Railway niet op een termijn van Railway. |
| Bijlage C, beveiliging | Versleuteling in rust, TLS onderweg, 2FA voor personeel, dagelijkse back-ups "across multiple sites and regions". | Back-ups over meerdere regio's: support schrijft dat volumeback-ups in EU West blijven. Bij twijfel geldt de schriftelijke DPA; dat punt navragen als Railway voor persoonsgegevens blijft. |
| Art. 5, audit | Eén keer per jaar, op kosten van de klant. | Voor fase 1 genoeg; het SOC 2-rapport is het praktische alternatief. |

## Conclusie voor de producten

- **VitaScribe en ConsultSpiegel**: echte consulten (gezondheidsgegevens van patiënten) mogen niet via de Railway-server. Dat geldt voor de EU-modus net zo goed als voor de Claude-modus: de server op Railway ziet de audio en de tekst, ook als hij niets bewaart. De route is een server bij een Europese host. Voor VitaScribe is die gebouwd (werkplan stap 4, `deploy/eu/`).
- **Railway blijft bruikbaar** voor wat geen gezondheidsgegevens bevat: gespeelde consulten en simulatie, de SciencePulse-pipeline van ProVita (openbare literatuur), en websites zonder patiëntgegevens.
- **Logs**: zolang Railway in gebruik is, mag geen enkele logregel inhoud bevatten. VitaScribe logt zonder inhoud en het testgereedschap staat standaard uit; het auditlog op stdout bevat wel namen van gebruikers (persoonsgegevens van medewerkers, geen gezondheidsgegevens), en dat staat dus in de VS.

# 02 Verwerkingsregister: VitaScribe

Deze regel hoort in het register van verwerkingsactiviteiten van de praktijk
(AVG art. 30 lid 1). In fase 2 houdt ProVitaCare daarnaast een register als
verwerker bij (art. 30 lid 2). Dat staat onderaan.

## Register van de praktijk (verwerkingsverantwoordelijke)

| Onderdeel | Invulling |
|---|---|
| Verantwoordelijke | `[NAAM HOLDING]`, handelend onder de naam Huisartsenpraktijk Roosendael, Roermond. Contact: A. Bennaghmouch, praktijkhouder, `[E-MAIL]` |
| Functionaris gegevensbescherming | `[naam, of: niet aangesteld]`. Een praktijk van deze omvang verwerkt doorgaans niet "op grote schaal" (AVG overweging 91) en hoeft dan geen FG aan te stellen. |
| Naam verwerking | Verslaglegging met AI-ondersteuning (VitaScribe) |
| Doel | Concepten maken van het SOEP-verslag, brieven en samenvattingen, die de arts controleert en zelf in het dossier zet. Doel is een vollediger dossier met minder schrijftijd. |
| Grondslag | AVG art. 6 lid 1 sub b en c: de behandelovereenkomst en de dossierplicht (art. 7:454 BW). Voor gezondheidsgegevens: art. 9 lid 2 sub h, samen met art. 30 lid 3 sub a UAVG. Voor de opname vraagt de arts per consult toestemming. Dat is een eis van de beroepsethiek (KNMG), niet de AVG-grondslag. |
| Betrokkenen | Patiënten; begeleiders die in de spreekkamer meepraten; gebruikers (artsen, waarnemers, POH). |
| Gegevens van patiënten | Geluid van het consult; de tekst van het gesprek; gezondheidsgegevens die daarin worden genoemd; het concept van het verslag. Bij brieven, dossiervragen en post: delen van het dossier die de arts kiest, gefilterd op naam, geboortedatum, BSN, adres en contactgegevens. |
| Gegevens van gebruikers | Naam, gebruikerssleutel, Bricks-praktijknummer, tijdstip van gebruik, het auditlog zonder inhoud. |
| Ontvangers | Railway Corp. (hosting) en Mistral AI SAS (spraak en tekst), als verwerkers van de praktijk. Zie stuk 05. ProVitaCare is de technische tak van dezelfde rechtspersoon en daarom geen ontvanger of verwerker. |
| Doorgifte buiten de EER | Railway Corp. is gevestigd in de VS. De server staat in Nederland, maar het verkeer gaat door die server. Grondslag: het EU-US Data Privacy Framework, waarin Railway actief gecertificeerd is, plus de verwerkersovereenkomst met Railway. In de EU-modus gaat geen gegeven naar een Amerikaanse AI-dienst. |
| Bewaartermijnen | Audio: niet bewaard. De server houdt hem alleen in het werkgeheugen en wist hem na verwerking. Tekst en verslag: niet bewaard op de server. In de browser blijft het verslag in het werkgeheugen tot "Nieuw consult" of tot de browser sluit. Het definitieve verslag staat in het HIS, onder de bewaartermijn van de WGBO (20 jaar). Auditlog: 5 jaar (`AUDIT_BEWAARDAGEN=1825`). |
| Beveiliging | Zie stuk 06: TLS, een sleutel per gebruiker, beheer met een tweede factor, geen opslag van inhoud, een onveranderbaar auditlog, EU-modus en toestemmingscontrole. |
| DPIA | Ja, zie stuk 03. Datum: `[DATUM]`. |

## Register van ProVitaCare als verwerker (fase 2)

| Onderdeel | Invulling |
|---|---|
| Verwerker | ProVitaCare `[KVK]`, `[ADRES]`, contact `[E-MAIL]` |
| Verantwoordelijken | De praktijken met een verwerkersovereenkomst; lijst bijhouden per praktijk met de datum van ondertekening. |
| Categorieën verwerkingen | Spraakherkenning, verslaglegging, brieven, dossiervragen en post, zoals omschreven in stuk 04, bijlage A. |
| Doorgifte buiten de EER | Railway Corp. (VS), op grond van het Data Privacy Framework. |
| Beveiliging | Stuk 06. |

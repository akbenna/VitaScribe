# 06 Beveiligingsbijlage (NEN 7510, NEN 7513)

Technische en organisatorische maatregelen volgens AVG art. 32. Dit is
bijlage B bij de verwerkersovereenkomst. "Ingericht" betekent: zo werkt de
code in versie 2.15.6. "Te doen" betekent: de instelling of afspraak moet nog
gemaakt worden.

## Technisch

| Maatregel | Hoe | Status |
|---|---|---|
| Versleuteling onderweg | HTTPS en WSS (TLS) tussen extensie en server, en tussen server en aanbieders | ingericht |
| Geen opslag van inhoud | Audio alleen in het werkgeheugen van de server, gewist na verwerking. Bij een upload wordt het tijdelijke bestand direct verwijderd. Tekst en verslag worden niet bewaard. | ingericht |
| Opslag in de browser | Consultresultaat alleen in `chrome.storage.session` (werkgeheugen), gewist bij "Consult afsluiten" of bij het sluiten van de browser. Oude gegevens op schijf worden bij de start opgeruimd. | ingericht |
| Toegang per persoon | Een sleutel per gebruiker (`API_USERS` of het register). Een server zonder sleutels weigert alles (fail closed). | ingericht; **te doen:** de gedeelde sleutel intrekken |
| Beheer | Beheerderssleutel met een tweede factor per beheerder (`ADMIN_TOTP`), en een beheersessie met beperkte duur | **te doen:** TOTP instellen voor elke beheerder |
| Eigen sleutels van praktijken | Versleuteld in de database (Fernet, `SLEUTELKLUIS`), met wisselbare kluissleutel | ingericht |
| Toestemming | De server weigert een opname zonder bevestigde toestemming (`REQUIRE_RECORDING_CONSENT`, standaard aan) | ingericht |
| Modus | De EU-modus stuurt niets naar een Amerikaanse AI-dienst, ook niet met een eigen sleutel van de praktijk. Live dicteren is daar geweigerd. | ingericht |
| Klinisch meedenken | Op de server uit (`CLINICAL_DECISION_SUPPORT`); in de EU-modus altijd uit, behalve met `ECONSULT_NHG_IN_EU` (NHG bij e-consult, per e-consult aan te vinken) | **te controleren** in Railway |
| Telefoon of iPad | Koppeling met een geheim in de QR-code (192 bits), als header, vervalt na 2 uur stil en 12 uur altijd; in de modus van de arts; niets opgeslagen op server of telefoon | in gebruik |
| Slot op de modus | `TOEGESTANE_MODI` op de server en "Alleen EU-modus" per praktijk; de server weigert een andere modus (ook WebSocket). Sinds 2.23.1 is de EU-modus de standaard: een aanvraag zonder modus, en een verse installatie van de extensie, werken in de EU-modus | standaard EU ingericht; `TOEGESTANE_MODI=eu` **zetten** in Railway zolang Claude niet is goedgekeurd |
| Fase | `VITASCRIBE_FASE=intern`: openbare aanmelding dicht | ingericht |
| Filter op identificatoren | Brieven, dossiervragen en post: naam, geboortedatum, BSN, adres en contact gefilterd in de browser, en op de server nog eens | ingericht |
| Versiecontrole | De extensie meldt haar versie; de server meldt de minimumversie, en het zijpaneel waarschuwt bij een te oude versie | ingericht |
| Testgereedschap | Spraaktest, SOEP-test en testset-inzendingen sturen naar alle aangesloten diensten en schrijven tekst in het log. Standaard uit: zolang de schakelaar in Beheer (Instellingen) uit staat, geven die routes 404, ook voor een beheerder. De beheerder zet hem zelf aan en uit; elke wijziging staat met naam en tijdstip in het beheerlog | ingericht (standaard uit); na gebruik uitzetten |
| Leveranciers | Railway: SOC 2 Type II, server in NL. Mistral: EU. | zie stuk 05 |

## Logging (NEN 7513)

Het auditlog legt vast wie welke functie wanneer gebruikte, en met welke
uitkomst. Er staat nooit inhoud in: geen audio, geen tekst, geen namen, geen
dossiergegevens. Elke gebeurtenis gaat naar stdout en naar de tabel
`vs_auditlog`. Die database weigert wijzigingen en het leegmaken van de tabel.
Regels jonger dan een jaar zijn niet te verwijderen. Na `AUDIT_BEWAARDAGEN`
(standaard 1825 dagen, vijf jaar) worden ze opgeruimd.

Voorwaarde voor herleidbaarheid tot een persoon: iedere gebruiker heeft een
eigen sleutel. Zolang de gedeelde sleutel actief is, staat in het log
`user=gedeeld`. Dat voldoet niet.

**Controle:** de praktijk kijkt `[elk kwartaal]` het log in op opvallend
gebruik, zoals gebruik buiten werktijd of door een onbekende gebruiker, en
noteert dat.

## Organisatorisch

| Maatregel | Invulling |
|---|---|
| Rollen | Beheerder: A. Bennaghmouch. Gebruikers: zie de aftekenlijst in stuk 09. |
| Sleutelbeheer | Een sleutel per persoon, niet gedeeld. Bij vertrek of verlies direct intrekken. Sleutels niet per mail sturen. |
| Werkplek | Een eigen Windows-account per gebruiker; schermvergrendeling; het consult afsluiten na elke patiënt |
| Training | Stuk 09: werkinstructie en AI-geletterdheid, afgetekend |
| Wijzigingen | Stuk 13: elke versie eerst getest met gespeelde consulten |
| Incidenten | Stuk 07 |
| Leveranciers | Jaarlijks de verwerkersovereenkomsten, de DPF-status en het SOC 2-rapport nakijken |
| Herziening | Deze bijlage jaarlijks, en bij elke wezenlijke wijziging |

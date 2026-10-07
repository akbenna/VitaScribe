# Resend (e-mail: BennaHealth prikkel- en coachmail, mogelijk ProVita)

Stand 7 oktober 2026. Niet geverifieerd tegen de site van Resend.

## Wat de code doet

In BennaHealth bouwt de database een mail met de weegstatus, het laatste gewicht in kilo's met datum en maaltijdsuggesties, en stuurt die via `api.resend.com` als `ProVita Care <info@provita-care.nl>` naar het ene adres in `kal_config.prikkel_email`. Dat adres is van de beheerder, niet van de gebruiker. Zodra er testers zijn, komen hun gewichten in de mailbox van de beheerder.

## Wat dat betekent

- Resend is een verwerker van gezondheidsgegevens (gewicht) en moet in register, DPIA en privacyverklaring staan. Dat staat er nu niet.
- Resend is een Amerikaans bedrijf; standaardregio VS, EU-regio beschikbaar. DPA via de voorwaarden; doorgiftegrondslag na te gaan.
- Inhoudelijk: de mail hoort naar de gebruiker zelf te gaan, of geen gewicht te bevatten. Dat is een codewijziging, geen papier.

## Nog te doen

1. Besluit: gewicht uit de mail, of de mail naar de gebruiker zelf (met een adres dat nu niet bestaat in het accountmodel).
2. Regio op EU zetten, DPA vastleggen.
3. Opnemen in register, DPIA en privacyverklaring van BennaHealth.

# Tweede VitaScribe-server bij een Europese host

Stuk 14, stap 4. Dit is een **alternatief naast Railway, geen vervanging**.
Railway blijft draaien zoals nu. In de extensie kies je per modus de server:

| Modus | Server |
|---|---|
| Claude-modus | Railway, zoals nu |
| EU-modus | deze Europese server, als je hem invult bij *Instellingen › Server voor de EU-modus* |

Laat je dat veld leeg, dan verandert er niets. Zo kun je de nieuwe server
rustig proberen en altijd terug.

Deze server laat alleen de EU-modus toe (`TOEGESTANE_MODI=eu` in `.env`). De
keten voor echte patiënten loopt dan helemaal via Europese bedrijven:
browser, deze host (Duitsland of Frankrijk), Mistral (Frankrijk).

## 1. Host kiezen en server aanmaken

**Hetzner** (Duitsland). Goedkoop en eenvoudig.

1. Maak een account op naam van de rechtspersoon (hetzner.com › Cloud).
2. Teken de verwerkersovereenkomst: Console › account › *Data Processing
   Agreement*. Download hem en bewaar hem bij het dossier.
3. Maak een server: locatie Falkenstein of Nürnberg, image *Ubuntu 24.04*,
   type CX22 (2 vCPU, 4 GB). Dat is ruim voldoende, want de server rekent
   niets zelf.
4. Voeg je SSH-sleutel toe. Zet een firewall met alleen poort 22, 80 en 443
   open.

**Scaleway** (Frankrijk). Werkt meer zoals Railway, iets duurder.

1. Account op naam van de rechtspersoon. De DPA staat in de voorwaarden;
   download hem.
2. Instances › Create: regio Paris of Amsterdam, *Ubuntu 24.04*, type
   DEV1-M of PLAY2-SMALL.
3. Security group: poort 22, 80 en 443.

## 2. Domein

Maak bij je domeinbeheer een A-record, bijvoorbeeld
`vitascribe-eu.provita-care.nl`, naar het IP-adres van de server. Wacht tot
het werkt; `ping vitascribe-eu.provita-care.nl` geeft dan dat adres.

## 3. Installeren (eenmalig, ongeveer een kwartier)

Log in met `ssh root@<ip-adres>` en voer uit:

```sh
apt update && apt install -y docker.io docker-compose-v2 git
git clone https://github.com/akbenna/VitaScribe.git /opt/vitascribe
cd /opt/vitascribe/deploy/eu
cp env.voorbeeld .env
nano .env        # vul de waarden in, zie hieronder
docker compose up -d --build
```

De repository is privé. Gebruik voor `git clone` een *deploy key*. Maak er
op de server een met `ssh-keygen -t ed25519`, zet de publieke sleutel in
GitHub bij de repository › Settings › Deploy keys (alleen lezen), en clone
met `git@github.com:akbenna/VitaScribe.git`.

In `.env` vul je in:

- `VITASCRIBE_DOMEIN`: het domein uit stap 2.
- `POSTGRES_PASSWORD`: een lang willekeurig wachtwoord, bijvoorbeeld de
  uitvoer van `openssl rand -hex 24`.
- `API_USERS`, `ADMIN_KEY`, `ADMIN_TOTP`, `APP_SECRET_KEY`,
  `MISTRAL_API_KEY`, `SLEUTELKLUIS`: dezelfde waarden als op Railway. Kopieer
  ze zelf uit Railway › Variables. Met dezelfde `API_USERS` werkt dezelfde
  sleutel van een arts op beide servers.

Na een minuut: open `https://<domein>/health`. Je hoort JSON te zien met
`"modus"` en `"data_policy"`.

## 4. De extensie

Open in de extensie *Instellingen › API Verbinding › Server voor de
EU-modus*:

1. Vul `https://<domein>` in. Laat de sleutel leeg als het dezelfde is als
   op Railway.
2. Klik *Test EU-server*. Bij "In orde" is het klaar.
3. Zet bovenin het paneel de schakelaar op EU. Alles in de EU-modus gaat nu
   naar de nieuwe server: consult, dicteren, brieven, dossiervraag,
   e-consult, tolk en de telefoon. Schakel je naar Claude, dan gaat alles
   weer naar Railway.

## 5. Bijhouden

**Bijwerken**, na elke nieuwe versie (Railway doet dit vanzelf, deze server
niet):

```sh
cd /opt/vitascribe && git pull && cd deploy/eu && docker compose up -d --build
```

**Back-up van het register.** Daarin staan praktijken, gebruikers, geleerde
regels en het auditlog; geen opnames of verslagen. Zet in `crontab -e`:

```
15 2 * * * /opt/vitascribe/deploy/eu/back-up.sh
```

Kopieer `back-ups/` af en toe naar een tweede plek binnen de EU.

**Logs**, zonder inhoud:

```sh
docker compose logs --tail 100 vitascribe
```

## Wat het register betekent bij twee servers

Elke server heeft een eigen database. Praktijken, gebruikers en geleerde
regels uit Beheer staan dus per server.

In fase 1 is dat geen probleem. De sleutels staan in `API_USERS`, op beide
servers gelijk. Wat VitaScribe in de EU-modus leert, leert het op de
EU-server.

Wil je later één register, dan kan de EU-server de database van de andere
gebruiken, of andersom (`DATABASE_URL`). Kies dan de Europese als de centrale.

## Dossier

Zodra deze server echte patiënten bedient:

- **Stuk 05:** de host als verwerker, met de DPA.
- **Stuk 03 (DPIA):** in de EU-modus loopt het verkeer niet meer via
  Railway (R4).
- **Stuk 06:** TLS via Caddy, firewall en back-ups.

Laat Claude dat bijwerken met de naam van de host die je koos.

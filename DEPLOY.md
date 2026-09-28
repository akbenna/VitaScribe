# VitaScribe — Go-Live Deployment Guide

## Overzicht

- **Frontend**: Vercel (`vitascribe.vercel.app`; tot dat domein is toegevoegd draait hij op `smartvoice-nine.vercel.app`)
- **Backend API**: Railway (CPU-only container)
- **Database**: Railway PostgreSQL plugin
- **Cache**: Railway Redis plugin (optioneel, graceful fallback)
- **STT/LLM**: Cloud API's (Deepgram + Mistral/Claude) of eigen GPU-server

---

## Stap 1 — Railway Project Aanmaken

1. Ga naar [railway.app](https://railway.app) en log in met GitHub
2. Klik **New Project** → **Deploy from GitHub repo**
3. Selecteer je VitaScribe repository
4. Railway detecteert automatisch `railway.toml` en `Dockerfile.railway`

## Stap 2 — Database & Redis Toevoegen

In het Railway dashboard:

1. Klik **+ New** → **Database** → **PostgreSQL**
2. Railway maakt `DATABASE_URL` automatisch aan als env var
3. (Optioneel) Klik **+ New** → **Database** → **Redis**
4. Railway maakt `REDIS_URL` automatisch aan

## Stap 3 — Environment Variables Instellen

Ga naar je service → **Variables** en stel in:

```
# Verplicht
APP_ENV=production
APP_SECRET_KEY=<genereer: openssl rand -hex 32>

# CORS — je Vercel frontend URL. Alleen services/api leest deze variabele. De
# cloud-API die Railway draait (Dockerfile.railway: services.cloud_api) laat elke
# herkomst toe, omdat de extensie vanaf chrome-extension:// aanroept.
# Tijdens de overstap staan beide erin: het nieuwe adres en het huidige live adres.
# Het oude kan eruit zodra de frontend alleen nog op vitascribe.vercel.app draait.
CORS_ALLOWED_ORIGINS=https://vitascribe.vercel.app,https://smartvoice-nine.vercel.app

# Database — Railway vult DATABASE_URL automatisch in
# Je hoeft POSTGRES_* niet handmatig te zetten

# Eerste keer users aanmaken
SEED_ON_START=true
ADMIN_PASSWORD=<kies een sterk wachtwoord>
ARTS_PASSWORD=<kies een sterk wachtwoord>

# STT — Deepgram cloud API (geen GPU nodig)
CLOUD_STT_PROVIDER=deepgram
CLOUD_STT_API_KEY=<je Deepgram API key>

# LLM — Cloud fallback (geen lokale Ollama nodig)
CLOUD_FALLBACK_ENABLED=true
CLOUD_FALLBACK_PROVIDER=mistral
CLOUD_FALLBACK_API_KEY=<je Mistral API key>
CLOUD_FALLBACK_API_URL=https://api.mistral.ai/v1

# Audit
AUDIT_LOG_RETENTION_YEARS=5
```

> Na eerste deploy: zet `SEED_ON_START=false` om te voorkomen dat seed elke keer draait.

## Stap 4 — Deploy

Railway bouwt automatisch bij push naar main. Je kunt ook handmatig triggeren:

1. Push je code: `git push origin main`
2. Railway bouwt de Docker image (duurt ~2-3 minuten)
3. Health check op `/health` bevestigt dat de API draait
4. Je krijgt een Railway URL. Bij de praktijk is dat `smartvoice-production.up.railway.app`. Dat adres houdt de oude
   naam met opzet: het staat in de extensie-instellingen op elke werkplek en in het
   installatiebeleid, en een ander adres betekent op elke pc opnieuw instellen.

## Stap 5 — Frontend Koppelen aan Backend

In het **Vercel** dashboard:

1. Ga naar je VitaScribe frontend project → **Settings** → **Environment Variables**
2. Voeg toe:
   ```
   NEXT_PUBLIC_API_URL=https://smartvoice-production.up.railway.app
   ```
   (vervang met je daadwerkelijke Railway URL)
3. Klik **Redeploy** om de nieuwe env var actief te maken

## Stap 6 — Testen

1. Ga naar `https://vitascribe.vercel.app` (of, tot de overstap, `https://smartvoice-nine.vercel.app`)
2. Log in met `arts1` / het wachtwoord dat je hebt ingesteld
3. Test de health check: `curl https://<railway-url>/health`
4. Wijzig wachtwoorden na eerste login

---

## STT & LLM Strategie (zonder GPU)

Railway biedt geen GPU's. Je hebt twee opties voor de Whisper STT en Ollama LLM:

### Optie A: Cloud API's (aanbevolen voor start)

| Component | Service       | Kosten              |
|-----------|---------------|---------------------|
| STT       | Deepgram Nova | ~$0.0043/min        |
| LLM       | Mistral       | ~$0.002/1K tokens   |

Dit is de snelste manier om live te gaan. Configureer via de env vars hierboven.

### Optie B: Eigen GPU Server

Als je een GPU-machine hebt (lokaal of cloud VM met NVIDIA):

1. Installeer Ollama + Faster-Whisper op die machine
2. Stel `OLLAMA_HOST` en `WHISPER_HOST` in als Railway env vars die naar je GPU server wijzen
3. Zorg voor een VPN of SSH tunnel voor veilige verbinding

### Optie C: Hybride

Start met cloud API's, migreer later naar eigen GPU als het volume toeneemt.

---

## Kosten Inschatting (Railway)

| Component     | Railway Plan | Geschatte kosten/maand |
|---------------|-------------|------------------------|
| API Container | Hobby       | ~$5                    |
| PostgreSQL    | Plugin      | ~$5                    |
| Redis         | Plugin      | ~$3 (optioneel)        |
| **Totaal**    |             | **~$10-13/maand**      |

Plus STT/LLM API kosten afhankelijk van gebruik (~$5-20/maand voor kleine praktijk).

---

## Checklist voor Go-Live

- [ ] Railway project aangemaakt met GitHub repo
- [ ] PostgreSQL plugin toegevoegd
- [ ] Environment variables ingesteld
- [ ] `APP_SECRET_KEY` gegenereerd en ingesteld
- [ ] `CORS_ALLOWED_ORIGINS` wijst naar Vercel URL
- [ ] Eerste deploy geslaagd, `/health` geeft `{"status": "ok"}`
- [ ] Seed users aangemaakt, `SEED_ON_START` daarna op `false`
- [ ] Vercel `NEXT_PUBLIC_API_URL` wijst naar Railway URL
- [ ] Frontend opnieuw gedeployed
- [ ] Inloggen werkt via de frontend
- [ ] Wachtwoorden gewijzigd na eerste login
- [ ] STT API key (Deepgram) geconfigureerd
- [ ] LLM API key (Mistral) geconfigureerd

---

## Live dicteren (zijpaneel)

De Chrome-extensie heeft een dicteerpaneel naast Bricks (knop in de popup of **Alt+Shift+D**).
De tekst verschijnt terwijl je spreekt en gaat naar het Bricks-veld waarin je het laatst klikte.

**Railway-variabelen:**

```
DEEPGRAM_API_KEY=<je Deepgram API key>      # ook gebruikt voor live dicteren
LLM_PROVIDER=anthropic                      # voor "Opschonen" en "Maak SOEP"
# SOEP op Claude Sonnet 5 (standaard), opschonen op Haiku; zie .env.example
ANTHROPIC_API_KEY=<je Anthropic API key>
# Optioneel (standaardwaarden):
DICTATION_DEEPGRAM_URL=wss://api.eu.deepgram.com/v1/listen   # EU-verwerking
DICTATION_DEEPGRAM_MODEL=nova-3
DICTATION_MAX_SECONDS=600
```

Kies bij Railway een EU-regio voor de service, zodat audio de EU niet verlaat en de vertraging laag blijft.

**Eerste gebruik:** bij de eerste start opent een tabblad dat eenmalig om microfoontoestemming vraagt
(Chrome kan dat niet vanuit het zijpaneel zelf). Na een update van de extensie: ververs het Bricks-tabblad.

**Consult opnemen:** klik op het VitaScribe-icoon en op de opnameknop, of druk **Alt+Shift+C**. Starten
bevestigt dat de patiënt toestemming geeft (dat staat bij de knop). Vooraf controleert VitaScribe de
sleutel; klopt die niet, dan start er geen opname. De popup gaat dicht en het zijpaneel blijft dicht.
Tijdens de opname staat **REC** op het icoon en een klein bolletje met de tijd, "Nadicteren" en "Stop" op
de pagina. Het bolletje gaat mee naar elke pagina en elk tabblad en kun je wegslepen; het onthoudt zijn
plek. De opname loopt in de achtergrond van de extensie door, ook als je wegklikt.
Na "Stop" (bolletje, popup, zijpaneel of Alt+Shift+C) toont het bolletje **Verslag klaar**: klik in de
S-regel van het consult en kies **Invoegen** (S, O, E, ICPC en P worden gevuld), of **Bekijk** voor het
zijpaneel met Thuisarts en patiëntinstructie. Mislukt het versturen, dan blijft de opname bewaard tot
**Opnieuw versturen**. Na een browserherstart of een update van de extensie is een lopende opname wel weg.

**Popup, bolletje en zijpaneel zijn één geheel.** Ze tonen hetzelfde consult en hetzelfde verslag.
Pas je het verslag in het zijpaneel aan, dan voegt "Invoegen" in het bolletje of de popup die aangepaste
tekst in. Voeg je in via het zijpaneel, dan verdwijnen bolletje en ✓ ook. Dicteer je in het zijpaneel,
dan staat op de pagina hetzelfde opnameteken met Stop als bij Alt+Shift+D; en wat je met Alt+Shift+D
dicteert, verschijnt ook in het zijpaneel.

**Meerdere problemen in één consult.** Komen twee of meer afzonderlijke problemen aan bod (bijv. keelpijn
én somberheid), dan maakt VitaScribe per probleem een eigen SOEP-deel met eigen ICPC-code. In het zijpaneel
staan ze als tabs ("1 · Keelpijn (R74)", "2 · Somberheid (P03)"); het bolletje en de popup voegen ze één voor
één in ("Invoegen deel 1", dan in een nieuwe SOEP-regel "Invoegen deel 2"). Klachten van één ziektebeeld
blijven één deel. Bij psychische klachten volgt de SOEP een eigen opbouw (klachten, stressoren, functioneren,
slaap, middelen, suïcidegedachten alleen zoals besproken; O = psychisch onderzoek zoals beschreven; E met
P-code; P met POH-GGZ en afspraken).

**Vraagsuggesties tijdens het consult (klinische ondersteuning).** Aan te zetten in Instellingen
("Vraagsuggesties tijdens het consult"); werkt alleen met "Live volgen" en als de server
`CLINICAL_DECISION_SUPPORT=true` heeft. Tijdens de opname zet VitaScribe hooguit eens per halve minuut 2-4
korte vragen onder het opnamebalkje (zijpaneel en popup) die bij de klacht horen en nog niet gesteld zijn;
alarmsymptomen in rood. Aantikken = gevraagd. Niet op de pagina zelf, niet na "Nadicteren". Dit valt onder de
MDR (klinische beslissingsondersteuning): bedoeld voor de eigen praktijk; bij verkoop eerst regelen.

**Dicteren zonder zijpaneel:** klik in het Bricks-veld en druk **Alt+Shift+D** (of klik op het
extensie-icoon en dan "Dicteer in veld"). Een label rechtsonder toont dat VitaScribe luistert; nogmaals
Alt+Shift+D of "Stop" beëindigt het. Lukt invoegen niet, dan staat het dictaat op het klembord.
Met het zijpaneel open bedient dezelfde sneltoets het paneel.

**S/O/E/P per veld:** klik in Bricks in de S-regel en kies "Alles invoegen": S komt in die regel, O, E en P
in de regels daarna (een ICPC-codeveld ertussen krijgt de code). Wijkt de opmaak af, gebruik dan eenmalig
"S/O/E/P-velden koppelen" (popup of zijpaneel) en klik in Bricks achter elkaar in het S-, O-, E- en P-veld. Daarna vult "Alles invoegen" (zijpaneel), "Push naar Bricks"
(popup) en de invoegknop in Bricks elke regel in het eigen veld. Bestaande tekst blijft staan. Opnieuw
koppelen kan altijd, bijvoorbeeld als Bricks van opmaak verandert.

**Snelteksten & correcties:** via de link onderaan het paneel. Een commando ("normaal longen") wordt
vervangen door je standaardtekst; correcties verbeteren woorden die verkeerd verstaan worden en gaan als
hint mee naar Deepgram. Opgeslagen per computer (Chrome, lokaal); overzetten via Exporteren/Importeren.

**Endpoints:**
- `WS /api/v1/dictation/stream`: audio in, tekst terug (eerste bericht: `{"type":"auth","api_key":"..."}`)
- `POST /api/v1/dictation/process`: `{"text": "...", "mode": "clean" | "soep"}`

## Praktijkregister en licenties (cloud-API)

Om VitaScribe aan andere praktijken aan te bieden, zet je op de service van de cloud-API drie variabelen:

```
DATABASE_URL=<koppel de Railway-PostgreSQL>      # zet het register aan
ADMIN_KEY=<openssl rand -hex 32>                   # opent /beheer
SLEUTELKLUIS=<Fernet-sleutel, zie hieronder>       # eigen AI-sleutels van praktijken
```

Maak de kluissleutel met `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Zonder `DATABASE_URL` werkt de server zoals voorheen, met `API_USERS` en `API_KEYS`. Die sleutels blijven ook met het register werken. Hoe het beheer werkt, staat in [docs/LICENTIEBEHEER.md](docs/LICENTIEBEHEER.md).

### Beheerders en tweestapsverificatie

Geef elke beheerder een eigen sleutel en een eigen geheim voor een
authenticator-app. Het beheerlog laat dan zien wie wat deed, en een gestolen
sleutel alleen is niet genoeg.

```bash
ADMIN_USERS=anna:<openssl rand -hex 32>,piet:<openssl rand -hex 32>
ADMIN_TOTP=anna:<geheim>,piet:<geheim>
BEHEER_SESSIE_UREN=8          # optioneel; daarna opnieuw inloggen
```

Maak een geheim met
`python -c "import base64,os; print(base64.b32encode(os.urandom(20)).decode())"`
en zet het in de app met de link
`otpauth://totp/VitaScribe:anna?secret=<geheim>&issuer=VitaScribe` (als QR-code,
of door het geheim over te typen). `ADMIN_KEY` blijft werken als gedeelde
sleutel onder de naam "beheerder", zonder code. Haal hem weg zodra iedereen een
eigen sleutel met code heeft.

### Auditlog (NEN 7513)

Met het register aan schrijft de server elk gebruik ook naar de tabel
`vs_auditlog`. De database weigert daar wijzigen en leegmaken, en een regel
jonger dan een jaar kan niet worden verwijderd. `AUDIT_BEWAARDAGEN` (standaard
1825, vijf jaar; minimaal 365) bepaalt wanneer oude regels opgeruimd worden.
Nalopen kan via `GET /api/v1/beheer/auditlog?dagen=30&gebruiker=<naam>`.

### Een server zonder sleutels

Zonder `API_USERS`, `API_KEYS` en register weigert de server elk verzoek.
Alleen voor lokale ontwikkeling zet je `VITASCRIBE_OPEN=1`. Controleer na elke
uitrol met `curl -H "X-API-Key: fout" https://<server>/api/v1/providers` dat het
antwoord 403 of 503 is en geen 200.

### Brieven in de EU

Een praktijk die geen brieven naar de VS wil, krijgt in `/beheer` het vinkje
"Brieven in de EU". Brieven gaan dan naar Mistral, ook als de praktijk een eigen
sleutel bij Anthropic of OpenAI heeft. Voor alle praktijken tegelijk zet je
`LETTERS_LLM_PROVIDER=mistral`.

### Back-up van het register

- Zet in Railway de back-ups van de PostgreSQL-dienst aan (Backups, dagelijks)
  en noteer hoe lang ze bewaard worden.
- Download maandelijks de export uit `/beheer` (knop Export) en bewaar die
  versleuteld buiten Railway. De export bevat geen sleutels.
- Oefen één keer per jaar een herstel: zet een back-up terug in een nieuwe
  PostgreSQL-dienst, koppel een testserver en controleer dat `/beheer` de
  praktijken toont. Leg de datum vast.

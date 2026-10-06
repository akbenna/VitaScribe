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

**Taal van het gesprek.** In de popup en het zijpaneel staat onder de opnameknop "Taal gesprek":
Nederlands (standaard), Meertalig (Deepgram Nova-3 `multi`: Nederlands, Engels, Frans, Duits, Spaans,
Italiaans, Portugees, Russisch, Hindi en Japans door elkaar), Engels, Turks, Pools of Oekraïens. Turks, Pools
en Oekraïens verstaan alleen die taal: kies ze als (vrijwel) het hele gesprek in die taal gaat. De keuze
geldt voor één consult en springt daarna terug naar Nederlands; Alt+Shift+C start altijd in het Nederlands.
De SOEP is altijd Nederlands, met in S de taal van het consult. Kosten: spraakherkenning in dezelfde orde
(fractie van een cent per minuut); het taalmodel gebruikt voor een anderstalig transcript meer tokens,
hooguit rond een cent extra per consult.

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

**Zijpaneel eerst, minimaliseren kan.** Een klik op het VitaScribe-icoon opent altijd het zijpaneel.
Rechtsboven in het paneel staat "Minimaliseren": het paneel gaat dicht en het hele scherm is vrij; een
volgende klik op het icoon haalt het terug. Een consultopname loopt door, met het bolletje op de pagina.
Wie liever de compacte popup op het icoon heeft, kiest dat in Instellingen onder "Weergave".

**Meedenken onder de SOEP.** Na elke SOEP (dictaat of consult) kijkt de server op de achtergrond mee
(`POST /api/v1/soep/meedenken`, Claude). Altijd: elk geneesmiddel in S en P met de juiste Nederlandse
stofnaam; een verhaspelde naam krijgt een knop "Vervang", die alleen werkt als de genoemde tekst letterlijk
in de SOEP staat. Met "Meedenken bij het beleid" in Instellingen, en `CLINICAL_DECISION_SUPPORT=true` op de
server: of P in lijn is met de NHG-Standaard bij de werkdiagnose in E, hooguit drie voorstellen die met
"+ P" in het plan kunnen, en Thuisarts.nl-onderwerpen als zoeklink. Niets verandert zonder klik; een
aanpassing gaat ook mee naar het bolletje en de popup. Kosten: ongeveer een cent per SOEP.

**Post & lab (vierde tabblad).** Klik in de Bricks-post een labuitslag, kweek of brief aan: zolang het
tabblad open is, leest het paneel het bericht in (vanaf "Afzender"; de regel "Patiënt" met naam,
geboortedatum en adres gaat er niet mee, alleen de leeftijd; de episodelijst gaat mee als context) en
stuurt het naar `POST /api/v1/post/beoordeel`. Terug komt een klinische samenvatting voor "Samenvatting
(zichtbaar in journaal)" en uitleg in eenvoudige woorden voor de patiënt voor "Memo", elk met een knop
die de tekst in het Bricks-veld zet (bestaande tekst blijft staan). Bij lab de relevante waarden; met
"Klinisch meedenken" in Instellingen (en `CLINICAL_DECISION_SUPPORT=true`) ook duiding, een oordeel
(normaal, afwijkend, of "via aanvrager" als het afhangt van kliniek of eerdere waarden) en een
beleidsvoorstel conform NHG; bij een kweek het passende middel met oog op nierfunctie en allergie uit
de episodes. Bij een brief: van, reden, conclusie en wat er van de huisarts verwacht wordt. Een bericht
dat al beoordeeld is, komt uit het geheugen van het paneel. Kosten: ongeveer 1 à 2 cent per bericht.

**Dossiervraag (balk onderaan het zijpaneel, in elk tabblad).** Stel een vraag aan het dossier dat
in Bricks open staat ("laatste kweken en resistentie?", "ooit een echo buik?"), of kies een snelle vraag.
Bij elke vraag leest het paneel de geopende onderdelen opnieuw in; naam, BSN, geboortedatum, adres en
contactgegevens gaan er niet mee, datums wel. Het antwoord noemt alleen wat er staat, met datum en een
letterlijk citaat als bron; de server controleert elk citaat in de tekst (✓) en markeert wat niet
letterlijk terug te vinden is (?). Een vervolgvraag ("en daarvoor?") krijgt de laatste drie vragen mee;
bij een andere patiënt begint het opnieuw. Niets wordt bewaard. Het dossier staat in de gecachte
system-prompt: de eerste vraag kost bij een gemiddeld dossier enkele centen, volgende vragen over
dezelfde patiënt ongeveer een tiende daarvan. Taalmodel: `PHI_LLM_PROVIDER` (standaard Claude).
Beperking: alleen wat in Bricks geopend (en geladen) is, telt mee; het paneel meldt welke onderdelen
het heeft ingelezen.

**Endpoints:**
- `POST /api/v1/dossier/vraag`: `{"dossier": "...", "vraag": "...", "eerder": [{"vraag","antwoord"}]}` →
  `{"antwoord", "gevonden", "bronnen": [{"datum","onderdeel","citaat","geverifieerd"}], "let_op"}`
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
"Brieven in de EU". Brieven gaan dan naar het EU-model van de server (Bedrock
EU als route A aan staat, anders Mistral), ook als de praktijk een eigen
sleutel bij Anthropic of OpenAI heeft. Voor alle praktijken tegelijk zet je
`LETTERS_LLM_PROVIDER=bedrock` (of `mistral`).

### Spraaktest: Voxtral (EU) tegen Deepgram

In `/beheer` staat rechtsboven **Spraaktest**. Neem daar een rollenspel op of
upload een opname: dezelfde audio gaat tegelijk naar Deepgram en naar Mistral
Voxtral Mini Transcribe (Frankrijk), en je ziet beide transcripten met sprekers,
verwerkingstijd, herkende vaktermen en kosten naast elkaar. Er wordt niets
bewaard. Nodig: `MISTRAL_API_KEY` (dezelfde sleutel als het taalmodel) en
`DEEPGRAM_API_KEY`. Gebruik geen echte patiëntopnamen zolang er geen
verwerkersovereenkomst met Mistral is.

Onder de transcripten staat **Maak SOEP van beide**: van elk transcript maakt
de server een SOEP met dezelfde woordenlijst en hetzelfde taalmodel als bij een
echt consult (`PHI_LLM_PROVIDER`). Met **Blind beoordelen** heten de verslagen
"A" en "B" in willekeurige volgorde, tot je op Onthul klikt. Kost twee
SOEP-aanroepen per klik (enkele dollarcenten).

Naast de microfoon kan de spraaktest het geluid van een ander tabblad opnemen
(op Windows ook van de hele pc), eventueel met de microfoon erbij gemengd. Onder
**Afspeellijst van YouTube** plak je een afspeellijst of losse filmpjes: de
pagina speelt ze af in de speler zonder cookies (youtube-nocookie.com), neemt
elk filmpje apart op en zet de vergelijkingen in een tabel. Alleen voor die
speler staat de pagina een frame van YouTube toe; er draait geen script van
YouTube in de beheerpagina.

### Twee modi: Claude en EU

Bovenin het zijpaneel en de popup staat een knop **Claude | EU**. De arts wisselt
met één klik; de keuze gaat met elke aanvraag mee (kopregel
`X-VitaScribe-Modus`, of `modus` bij het aanmelden op een WebSocket).

- **Claude** (standaard): alle functies. Spraak via Deepgram (EU-eindpunt),
  tekst via `PHI_LLM_PROVIDER` (Claude).
- **EU** (formeel): alleen Europese bedrijven. Het consult via Voxtral na
  afloop, alle tekst (SOEP, brieven, dossiervraag, post, meedenken) via
  `EU_LLM_PROVIDER` (standaard Mistral; `bedrock` mag ook). Eigen sleutels van
  de praktijk bij een Amerikaanse aanbieder worden niet gebruikt. Live dicteren
  weigert de server; vraagsuggesties kunnen niet, en klinische ondersteuning
  (`CLINICAL_DECISION_SUPPORT`) staat in deze modus altijd uit: de EU-modus is
  alleen verslaglegging.
  Eén uitzondering, alleen als de praktijk daar bewust voor kiest:
  `ECONSULT_NHG_IN_EU=true` staat in de EU-modus "NHG meedenken" bij een
  e-consult toe. De arts vinkt het dan nog per e-consult aan; het staat nooit
  vanzelf aan. Andere klinische ondersteuning blijft uit.

De arts kiest; de server volgt die keuze altijd en verandert hem nooit. Kan
de EU-modus niet werken (geen `MISTRAL_API_KEY`), dan mislukt de aanvraag met
een melding; de server valt nooit stil terug op Claude. De knop waarschuwt
daar vooraf voor (`eu_probleem` in `/api/v1/providers`). Nodig voor EU:
`MISTRAL_API_KEY` van een betaald account met verwerkersovereenkomst en zero
data retention.

### Testset en SOEP-test (Claude tegen Mistral)

In `services/cloud_api/testset/` staan gespeelde consulten (acteurs, geen
patiënten) met per consult de valkuilen (`index.json`). Op `/beheer/spraaktest`:

- **Bewaar als testset** downloadt alle vergelijkingen van de sessie als JSON;
  nieuwe consulten voeg je toe als `.txt` met een regel in `index.json`.
- **SOEP-test: Claude tegen Mistral** maakt van één gesprek twee verslagen met
  dezelfde SOEP-stap, blind te beoordelen. Onder elk verslag staat wat
  verdacht is: een sterkte, bloeddruk, plaats of zijde die niet in het gesprek
  staat, of "uitgesloten". **Hele testset** doet dat voor alle consulten en
  zet de aantallen in een tabel. Kost per consult één Claude- en één
  Mistral-verslag (enkele dollarcenten).
- **Valkuilen**: per testconsult staan in `index.json` onder `toets` wat er
  niet in mag (`mag_niet`) en wat er in moet (`moet`), als regex met uitleg.
  De tabel telt per model hoeveel valkuilen het verslag ontweek.
- **EU-model** kiest Mistral Large (standaard, `MISTRAL_QUALITY_MODEL`) of
  Medium voor deze test, zonder de serverinstelling te wijzigen.
- De ICPC-titel wordt vergeleken met een kleine richttabel
  (`icpc_controle.py`, door de arts te controleren); codes die daar niet in
  staan worden niet beoordeeld.

### Voxtral als spraakdienst voor consulten

Met `ALLOWED_STT_PROVIDERS=voxtral` gaan alle consulten naar Mistral Voxtral
(EU), ook het live consult: de server houdt het geluid tijdens het consult in
het werkgeheugen (nooit op schijf) en stuurt na "stop" de hele opname in één
keer naar Voxtral. Er gaat dan niets naar Deepgram. Het terugvalpad (de
extensie stuurt haar eigen kopie op) volgt dezelfde keuze. Engelse vulwoorden
die Voxtral soms schrijft ("Yeah", "Okay") worden in Nederlandse consulten
"ja" en "oké".

Wat in deze stand niet verandert of niet kan:

- Dicteren blijft live via Deepgram (EU-eindpunt): daarvoor is tekst tijdens
  het spreken nodig, en Voxtral Realtime is nog niet ingebouwd.
- Vraagsuggesties tijdens het consult werken niet in deze stand; ze hebben
  tekst tijdens het gesprek nodig.
- De extensie toont tijdens het consult alleen "Luistert mee", zonder aantal
  stemmen.

Nodig: `MISTRAL_API_KEY` van een betaald Mistral-account met
verwerkersovereenkomst. `/health/deep` meldt dan ook de controle `mistral`.
Terugzetten: `ALLOWED_STT_PROVIDERS=deepgram`.

### Route A: Claude in Amazon Bedrock (EU)

Hetzelfde model (Haiku 4.5, Sonnet 5 voor SOEP), maar verwerkt door AWS in de
EU in plaats van door Anthropic in de VS. Anthropic heeft op Bedrock geen
toegang tot prompts of antwoorden en is dan geen subverwerker.

1. AWS-account van de praktijk, regio `eu-central-1` (Frankfurt). Vraag in de
   Bedrock-console modeltoegang aan voor Claude Sonnet 5 en Claude Haiku 4.5.
   Laat *model invocation logging* uit.
2. IAM-gebruiker met alleen het recht om het model aan te roepen
   (`bedrock-mantle:CreateInference`, beperkt tot die twee modellen). Maak
   voor die gebruiker een toegangssleutel.
3. Zoek in de Bedrock-console de model-ID's van het **EU-inferentieprofiel**
   op. De server gaat uit van `eu.anthropic.claude-sonnet-5` en
   `eu.anthropic.claude-haiku-4-5`; wijkt de console af, zet dan
   `BEDROCK_SOEP_MODEL` en `BEDROCK_MODEL`.
4. Test lokaal, zonder patiëntgegevens:
   `AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=… python scripts/bedrock_check.py`
5. Zet in Railway: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `BEDROCK_REGION=eu-central-1`, eventueel de model-ID's, en als laatste
   `PHI_LLM_PROVIDER=bedrock` (en `LETTERS_LLM_PROVIDER=bedrock`).
6. Controleer `/health`: `patient_data_llm` is `bedrock` en
   `patient_data_llm_in_eu` is `true`. `/health/deep` meldt `bedrock: ok`.

De server weigert te verzenden als de regio niet met `eu-` begint of een
model-ID met `global.`, `us.` of een andere niet-EU-route begint. Er gaat dan
niets de deur uit; de arts ziet een foutmelding. Terug naar de directe API:
`PHI_LLM_PROVIDER=anthropic`.

Verschillen met de directe API: regionale verwerking kost ongeveer 10% meer,
en Bedrock kent geen *structured outputs*. Het JSON-schema gaat daar als
instructie mee en de server knipt het JSON-object uit het antwoord; dat is
getest, maar controleer na de omschakeling een paar SOEP's, dossiervragen en
Post-beoordelingen.

### Back-up van het register

- Zet in Railway de back-ups van de PostgreSQL-dienst aan (Backups, dagelijks)
  en noteer hoe lang ze bewaard worden.
- Download maandelijks de export uit `/beheer` (knop Export) en bewaar die
  versleuteld buiten Railway. De export bevat geen sleutels.
- Oefen één keer per jaar een herstel: zet een back-up terug in een nieuwe
  PostgreSQL-dienst, koppel een testserver en controleer dat `/beheer` de
  praktijken toont. Leg de datum vast.

### EU-modus: controleronde

Elk consult in de EU-modus gaat na het SOEP-verslag nog een keer naar Mistral
(Large, `MISTRAL_QUALITY_MODEL`), samen met het transcript. Wat het gesprek
niet onderbouwt, komt als `soep.markeringen` terug en staat geel gemarkeerd in
het zijpaneel (vanaf extensie 2.15.0). Er wordt niets weggehaald of
toegevoegd; de arts beslist. Mislukt de controle, dan blijft het verslag
zonder markeringen staan. Kosten: ongeveer een halve cent per consult.

### Tolk (vanaf extensie 2.16.0)

Tabblad Tolk in het zijpaneel: arts en patiënt spreken om beurten, VitaScribe
vertaalt elke beurt en leest hem voor. Endpoints onder `/api/v1/tolk`
(`talen`, `beurt`, `spreek`, `verslag`); de server bewaart niets.

- **Verstaan:** EU-modus Voxtral (`MISTRAL_API_KEY`), Claude-modus Deepgram
  (`DEEPGRAM_API_KEY` of de eigen sleutel van de praktijk). Voxtral kent geen
  Turks, Pools en Oekraïens; in de EU-modus wordt dan alleen de arts verstaan.
  Marokkaans- en Syrisch-Arabisch gaan in de Claude-modus als eigen dialect
  naar Deepgram (`ar-MA`, `ar-SY`).
- **Vertalen:** het taalmodel van de modus (`phi_llm_provider`), snel model.
- **Voorlezen:** bij voorkeur een stem die de taal als moedertaal spreekt.
  Volgorde `TOLK_TTS_VOORKEUR` (standaard `azure,mistral,mistral_overig`), daarna de stem op
  de computer.
  - **Azure AI Speech** (aanbevolen, natuurlijkst): maak in Azure een
    Speech-resource in `westeurope` (Nederland) of een andere EU-regio, en zet
    `TOLK_AZURE_KEY` en `TOLK_AZURE_REGION`. De gratis laag (F0) bevat 500.000
    tekens per maand, genoeg voor honderden tolkgesprekken. Stemmen per land:
    `nl-NL-FennaNeural`/`MaartenNeural`, `tr-TR-EmelNeural`/`AhmetNeural`,
    `ar-MA-MounaNeural`/`JamalNeural`, `ar-SY-AmanyNeural`/`LaithNeural`, enz.;
    andere stem met `TOLK_AZURE_STEM_<CODE>` (bijv. `TOLK_AZURE_STEM_AR_MA`).
    Tempo: `TOLK_TEMPO` (standaard `-8%`). Microsoft is een Amerikaans bedrijf:
    in de EU-modus alleen met `TOLK_AZURE_IN_EU=true`, na een besluit van de
    praktijk en met Microsoft in de lijst van verwerkers (zoals Railway).
  - **Mistral (Voxtral TTS)** met een stem van die taal: een eigen stem die de
    praktijk opnam (zijpaneel › Tolk › Eigen stem voor deze taal: een collega
    die de taal als moedertaal spreekt, 15–20 seconden; Mistral kloont de stem
    en het accent; bewaard in `vs_instellingen` als `tolk_stem:<code>`), of
    een Mistral-stem van die taal. Vaste stem: `TOLK_STEM_<CODE>` (bijv.
    `TOLK_STEM_AR_MA`).
  - **Mistral, andere stem** (`mistral_overig`): de eerste stem van het
    account (of `TOLK_STEM`), met een vreemd accent; nog altijd beter dan de
    stemmen van Windows.
    `TOLK_TTS_MODEL` (standaard `voxtral-mini-tts-latest`).
- **Handsfree:** de extensie stuurt elke beurt als WAV met `spreker=auto`.
  EU-modus: Voxtral herkent de taal zelf (één aanroep). Claude-modus: Deepgram
  verstaat de beurt twee keer tegelijk (als Nederlands en als de taal van de
  patiënt); het taalmodel kiest welke herkenning zinnig is en daarmee wie er
  sprak.
- **Kosten:** per beurt een korte spraakherkenning en een kleine vertaling;
  voorlezen ongeveer 1,6 cent per 1000 tekens. Een tolkgesprek van 15 minuten
  kost enkele tientallen centen.
- **Verslag:** "Maak verslag" stuurt de Nederlandse kant van het gesprek door
  dezelfde pipeline als een opgenomen consult (in de EU-modus met
  controleronde en markeringen).

### Leren per arts (vanaf extensie 2.18.0)

`/api/v1/leren`: na invoegen of kopiëren stuurt de extensie het concept en de
aangepaste versie; het taalmodel van de modus leidt er algemene regels uit af
(huisstijl, verkeerd verstane woorden). Alleen die regels worden bewaard
(`vs_leren`, per arts: `gebruiker:<id>` uit het register, of de naam uit
`API_USERS`), plus getallen per dag (`vs_leermeting`). Een stijl- of tolkregel
gaat mee na goedkeuring; een woord ook vanzelf na drie keer. Gebruik:

- SOEP (consult, dictaat, tolk): "HUISSTIJL VAN DEZE ARTS" en "JUISTE SPELLING"
  in de opdracht. De testset en de spraaktest draaien zonder.
- Spraakherkenning: geleerde woorden eerst in Voxtral `context_bias` en in de
  Deepgram-keyterms (dicteren, live consult).
- Tolk: afspraken per taal in elke vertaling.

Zonder `DATABASE_URL` staat het geleerde in het geheugen en is het weg na een
herstart. Een gedeelde sleutel (`API_KEYS`) leert voor iedereen samen: geef
elke arts een eigen sleutel.

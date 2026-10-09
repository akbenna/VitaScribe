-- VitaScribe - praktijkregister
--
-- Wordt bij het opstarten van de server uitgevoerd en is daarom idempotent:
-- elke opdracht mag vaker draaien zonder iets te veranderen. Een wijziging
-- aan een bestaande tabel komt hieronder als losse ALTER ... IF NOT EXISTS,
-- nooit door een CREATE aan te passen.

CREATE TABLE IF NOT EXISTS vs_praktijken (
    id                       BIGSERIAL PRIMARY KEY,
    naam                     TEXT NOT NULL,
    plaats                   TEXT NOT NULL DEFAULT '',
    -- Het nummer in de Bricks-URL (https://groep06.brickshuisarts.nl/2876/...).
    -- Leeg = niet praktijkgebonden.
    praktijknummers          TEXT[] NOT NULL DEFAULT '{}',
    agb                      TEXT NOT NULL DEFAULT '',
    contact_naam             TEXT NOT NULL DEFAULT '',
    contact_email            TEXT NOT NULL DEFAULT '',
    telefoon                 TEXT NOT NULL DEFAULT '',
    fte                      NUMERIC(5, 2),
    werkplekken              INTEGER,
    licentietype             TEXT NOT NULL DEFAULT 'kandidaat'
        CHECK (licentietype IN ('kandidaat', 'pilot', 'betaald', 'intern')),
    status                   TEXT NOT NULL DEFAULT 'aangemeld'
        CHECK (status IN ('aangemeld', 'actief', 'uitgehaald', 'afgewezen')),
    -- Leeg = onbeperkt geldig; alleen bedoeld voor de eigen praktijk.
    geldig_tot               DATE,
    serienummer              TEXT NOT NULL DEFAULT '',
    -- Aan: geen brieven of spraak op de sleutels van de server, alleen op die
    -- van de praktijk zelf.
    eigen_sleutels_verplicht BOOLEAN NOT NULL DEFAULT FALSE,
    notities                 TEXT NOT NULL DEFAULT '',
    opmerking_aanmelding     TEXT NOT NULL DEFAULT '',
    aangemeld_op             TIMESTAMPTZ NOT NULL DEFAULT now(),
    bijgewerkt_op            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vs_gebruikers (
    id                     BIGSERIAL PRIMARY KEY,
    praktijk_id            BIGINT NOT NULL REFERENCES vs_praktijken(id) ON DELETE CASCADE,
    naam                   TEXT NOT NULL,
    email                  TEXT NOT NULL DEFAULT '',
    rol                    TEXT NOT NULL DEFAULT 'gebruiker'
        CHECK (rol IN ('gebruiker', 'praktijkbeheerder')),
    -- sha256 van de sleutel. De sleutel zelf wordt één keer getoond en nergens bewaard.
    sleutel_hash           TEXT NOT NULL UNIQUE,
    sleutel_hint           TEXT NOT NULL,
    actief                 BOOLEAN NOT NULL DEFAULT TRUE,
    aangemaakt_op          TIMESTAMPTZ NOT NULL DEFAULT now(),
    laatst_gezien          TIMESTAMPTZ,
    laatst_praktijknummer  TEXT
);
CREATE INDEX IF NOT EXISTS vs_gebruikers_praktijk ON vs_gebruikers (praktijk_id);

-- Aan: brieven gaan naar het taalmodel in de EU (Mistral) in plaats van naar
-- de brievenaanbieder van de server of een eigen sleutel in de VS.
ALTER TABLE vs_praktijken ADD COLUMN IF NOT EXISTS brieven_in_eu BOOLEAN NOT NULL DEFAULT FALSE;
-- Deze praktijk gebruikt alleen de EU-modus (stuk 14, stap 3): de Claude-modus wordt geweigerd.
ALTER TABLE vs_praktijken ADD COLUMN IF NOT EXISTS alleen_eu BOOLEAN NOT NULL DEFAULT FALSE;

-- Eigen sleutels van een praktijk bij een AI-dienst, versleuteld (zie kluis.py).
-- 'brieven': Anthropic of OpenAI, alleen voor gepseudonimiseerde brieven.
-- 'spraak':  Deepgram.
CREATE TABLE IF NOT EXISTS vs_praktijk_sleutels (
    praktijk_id     BIGINT NOT NULL REFERENCES vs_praktijken(id) ON DELETE CASCADE,
    dienst          TEXT NOT NULL CHECK (dienst IN ('brieven', 'spraak')),
    aanbieder       TEXT NOT NULL,
    versleuteld     TEXT NOT NULL,
    hint            TEXT NOT NULL,
    ingesteld_door  BIGINT REFERENCES vs_gebruikers(id) ON DELETE SET NULL,
    ingesteld_op    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (praktijk_id, dienst),
    CHECK ((dienst = 'brieven' AND aanbieder IN ('anthropic', 'openai'))
        OR (dienst = 'spraak' AND aanbieder = 'deepgram'))
);

CREATE TABLE IF NOT EXISTS vs_instellingen (
    sleutel TEXT PRIMARY KEY,
    waarde  TEXT NOT NULL
);

-- Wat er in het beheer gebeurde: welke handeling, bij welke praktijk, wanneer.
-- Nooit een sleutel, ook niet versleuteld.
CREATE TABLE IF NOT EXISTS vs_beheerlog (
    id           BIGSERIAL PRIMARY KEY,
    op           TIMESTAMPTZ NOT NULL DEFAULT now(),
    door         TEXT NOT NULL,
    handeling    TEXT NOT NULL,
    praktijk_id  BIGINT,
    details      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS vs_beheerlog_op ON vs_beheerlog (op DESC);

-- Het gebruikslog volgens NEN 7513: wie welke functie wanneer gebruikte, met
-- welke uitkomst, nooit inhoud (zie audit.py). Alleen toevoegen: wijzigen of
-- leegmaken weigert de database, en een regel verdwijnt pas als hij ouder is
-- dan een jaar (audit.py ruimt op na AUDIT_BEWAARDAGEN, minimaal 365).
CREATE TABLE IF NOT EXISTS vs_auditlog (
    id         BIGSERIAL PRIMARY KEY,
    op         TIMESTAMPTZ NOT NULL DEFAULT now(),
    gebruiker  TEXT NOT NULL,
    handeling  TEXT NOT NULL,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS vs_auditlog_op ON vs_auditlog (op);
CREATE INDEX IF NOT EXISTS vs_auditlog_gebruiker ON vs_auditlog (gebruiker, op);

CREATE OR REPLACE FUNCTION vs_auditlog_bewaken() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Het auditlog kan niet worden gewijzigd.';
    ELSIF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'Het auditlog kan niet worden leeggemaakt.';
    ELSIF OLD.op > now() - interval '365 days' THEN
        RAISE EXCEPTION 'Regels in het auditlog blijven minstens een jaar staan.';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS vs_auditlog_rij ON vs_auditlog;
CREATE TRIGGER vs_auditlog_rij BEFORE UPDATE OR DELETE ON vs_auditlog
    FOR EACH ROW EXECUTE FUNCTION vs_auditlog_bewaken();
DROP TRIGGER IF EXISTS vs_auditlog_leeg ON vs_auditlog;
CREATE TRIGGER vs_auditlog_leeg BEFORE TRUNCATE ON vs_auditlog
    FOR EACH STATEMENT EXECUTE FUNCTION vs_auditlog_bewaken();

-- Wat VitaScribe per arts leert (leren.py): stijlregels voor de SOEP, woorden
-- voor de spraakherkenning en afspraken voor de tolk. Nooit patiëntgegevens:
-- alleen algemene regels, die de arts zelf goedkeurt.
CREATE TABLE IF NOT EXISTS vs_leren (
    id          BIGSERIAL PRIMARY KEY,
    eigenaar    TEXT NOT NULL,
    soort       TEXT NOT NULL,              -- soep | woord | tolk | econsult | brief
    taal        TEXT NOT NULL DEFAULT '',   -- bij tolk: de taal van de patiënt; bij brief: de briefsoort
    sleutel     TEXT NOT NULL,              -- genormaliseerd, tegen dubbelen
    regel       TEXT NOT NULL,
    van         TEXT NOT NULL DEFAULT '',
    naar        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'voorstel',   -- voorstel | actief | afgewezen
    aantal      INTEGER NOT NULL DEFAULT 1,
    gemaakt     TIMESTAMPTZ NOT NULL DEFAULT now(),
    bijgewerkt  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (eigenaar, soort, taal, sleutel)
);

-- Alleen getallen per arts per dag: hoeveel er werd aangepast, hoe vaak de tolk
-- iets eenvoudiger moest zeggen. Om te zien of het leren werkt.
CREATE TABLE IF NOT EXISTS vs_leermeting (
    eigenaar     TEXT NOT NULL,
    dag          DATE NOT NULL,
    soort        TEXT NOT NULL,             -- soep | tolk | econsult | brief
    aantal       INTEGER NOT NULL DEFAULT 0,
    gewijzigd    REAL NOT NULL DEFAULT 0,   -- som van de percentages
    markeringen  INTEGER NOT NULL DEFAULT 0,
    eenvoudiger  INTEGER NOT NULL DEFAULT 0,
    weggehaald   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (eigenaar, dag, soort)
);

-- Visites (visite.py). Openbare sleutels van de browsers van een arts; alleen
-- die browsers kunnen een visiteverslag openen.
CREATE TABLE IF NOT EXISTS vs_visite_ontvanger (
    wie     TEXT NOT NULL,
    kid     TEXT NOT NULL,
    spki    TEXT NOT NULL,
    gezien  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (wie, kid)
);

-- Telefoons die een visite mogen insturen (alleen schrijven). Alleen de
-- SHA-256 van de toestelsleutel staat hier.
CREATE TABLE IF NOT EXISTS vs_visite_toestel (
    hash      TEXT PRIMARY KEY,
    wie       TEXT NOT NULL,
    eigenaar  TEXT NOT NULL DEFAULT '',
    modus     TEXT NOT NULL,
    naam      TEXT NOT NULL DEFAULT '',
    gemaakt   TIMESTAMPTZ NOT NULL DEFAULT now(),
    laatst    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- De postbus: per visite een versleutelde envelop (verslag) en kop
-- (aanduiding). De server kan ze niet openen. Uiterlijk na 48 uur gewist.
CREATE TABLE IF NOT EXISTS vs_visite_post (
    id        TEXT PRIMARY KEY,
    wie       TEXT NOT NULL,
    gemaakt   TIMESTAMPTZ NOT NULL DEFAULT now(),
    verloopt  TIMESTAMPTZ NOT NULL,
    status    TEXT NOT NULL,              -- verwerken | klaar | fout
    kop       JSONB,
    envelop   JSONB,
    fout      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS vs_visite_post_wie ON vs_visite_post (wie, verloopt);

-- Visiteronde: de openbare sleutel van de telefoon (een ronde wordt voor hem
-- versleuteld), en per arts één klaargezette ronde, versleuteld, een dag geldig.
ALTER TABLE vs_visite_toestel ADD COLUMN IF NOT EXISTS kid TEXT;
ALTER TABLE vs_visite_toestel ADD COLUMN IF NOT EXISTS spki TEXT;
CREATE TABLE IF NOT EXISTS vs_visite_ronde (
    wie       TEXT PRIMARY KEY,
    envelop   JSONB NOT NULL,
    verloopt  TIMESTAMPTZ NOT NULL
);

-- AI-gebruik per dag, per dienst, model en soort (kosten.py): alleen hoeveelheden,
-- nooit inhoud. Voor het kostenoverzicht in Beheer.
CREATE TABLE IF NOT EXISTS vs_ai_gebruik (
    dag        DATE NOT NULL,
    dienst     TEXT NOT NULL,
    model      TEXT NOT NULL DEFAULT '',
    soort      TEXT NOT NULL DEFAULT '',
    aanroepen  INTEGER NOT NULL DEFAULT 0,
    in_tokens  BIGINT NOT NULL DEFAULT 0,
    uit_tokens BIGINT NOT NULL DEFAULT 0,
    cache_w    BIGINT NOT NULL DEFAULT 0,
    cache_r    BIGINT NOT NULL DEFAULT 0,
    seconden   DOUBLE PRECISION NOT NULL DEFAULT 0,
    tekens     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (dag, dienst, model, soort)
);

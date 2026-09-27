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

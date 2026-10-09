-- =============================================================================
-- AI-Consultassistent - Database Initialisatie
-- =============================================================================
-- PostgreSQL 16 + pgcrypto
-- Conform NEN 7513 logging-eisen
-- =============================================================================

-- Extensies
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- ENUM types
-- =============================================================================
CREATE TYPE consult_status AS ENUM (
    'recording',
    'transcribing',
    'extracting',
    'reviewing',
    'approved',
    'exported',
    'failed'
);

CREATE TYPE soep_field AS ENUM ('S', 'O', 'E', 'P');

CREATE TYPE flag_severity AS ENUM ('laag', 'middel', 'hoog', 'kritiek');

CREATE TYPE user_role AS ENUM ('arts', 'poh', 'beheerder');

-- =============================================================================
-- Gebruikers
-- =============================================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(100) UNIQUE NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    role            user_role NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Consulten
-- =============================================================================
CREATE TABLE consults (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_hash    VARCHAR(64) NOT NULL,  -- SHA-256 van BSN
    practitioner_id UUID NOT NULL REFERENCES users(id),
    status          consult_status NOT NULL DEFAULT 'recording',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    audio_path      VARCHAR(500),          -- Pad naar versleuteld audiobestand
    audio_deleted   BOOLEAN DEFAULT false,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_consults_patient ON consults(patient_hash);
CREATE INDEX idx_consults_practitioner ON consults(practitioner_id);
CREATE INDEX idx_consults_status ON consults(status);
CREATE INDEX idx_consults_date ON consults(started_at);

-- =============================================================================
-- Transcripten
-- =============================================================================
CREATE TABLE transcripts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consult_id      UUID NOT NULL REFERENCES consults(id) ON DELETE CASCADE,
    -- Encrypted velden: versleuteld met pgcrypto in applicatielaag
    raw_text        TEXT NOT NULL,
    segments        JSONB NOT NULL,        -- [{spreker, start, eind, tekst, confidence}]
    model_version   VARCHAR(100) NOT NULL,
    language        VARCHAR(10) DEFAULT 'nl',
    confidence_avg  FLOAT,
    word_count      INTEGER,
    duration_secs   FLOAT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_transcripts_consult ON transcripts(consult_id);

-- =============================================================================
-- Medische Extracties
-- =============================================================================
CREATE TABLE extractions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consult_id      UUID NOT NULL REFERENCES consults(id) ON DELETE CASCADE,
    transcript_id   UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    -- Gestructureerde medische data
    klachten        JSONB DEFAULT '[]',
    anamnese        JSONB DEFAULT '{}',
    lich_onderzoek  JSONB DEFAULT '{}',
    vitale_params   JSONB DEFAULT '{}',
    medicatie       JSONB DEFAULT '[]',
    allergieen      JSONB DEFAULT '[]',
    voorgeschiedenis JSONB DEFAULT '[]',
    model_version   VARCHAR(100) NOT NULL,
    confidence      FLOAT,
    raw_response    JSONB,                 -- Volledige LLM-response voor debugging
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_extractions_consult ON extractions(consult_id);

-- =============================================================================
-- SOEP-Concepten
-- =============================================================================
CREATE TABLE soep_concepts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consult_id      UUID NOT NULL REFERENCES consults(id) ON DELETE CASCADE,
    extraction_id   UUID NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
    -- SOEP-velden
    s_text          TEXT NOT NULL DEFAULT '',
    o_text          TEXT NOT NULL DEFAULT '',
    e_text          TEXT NOT NULL DEFAULT '',
    p_text          TEXT NOT NULL DEFAULT '',
    -- ICPC-suggestie (toekomstig)
    icpc_code       VARCHAR(10),
    icpc_titel      VARCHAR(200),
    -- Review status
    model_version   VARCHAR(100) NOT NULL,
    confidence      FLOAT,
    is_approved     BOOLEAN DEFAULT false,
    approved_by     UUID REFERENCES users(id),
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_soep_consult ON soep_concepts(consult_id);

-- =============================================================================
-- Detectieresultaten (Rode Vlaggen + Missing Info)
-- =============================================================================
CREATE TABLE detection_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consult_id      UUID NOT NULL REFERENCES consults(id) ON DELETE CASCADE,
    red_flags       JSONB DEFAULT '[]',
    -- [{id, ernst, categorie, beschrijving, bron_segment, nhg_referentie}]
    missing_info    JSONB DEFAULT '[]',
    -- [{id, veld, beschrijving, prioriteit}]
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_detection_consult ON detection_results(consult_id);

-- =============================================================================
-- Correcties (Feedbackloop)
-- =============================================================================
CREATE TABLE corrections (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    soep_id         UUID NOT NULL REFERENCES soep_concepts(id) ON DELETE CASCADE,
    field           soep_field NOT NULL,
    original_text   TEXT NOT NULL,
    corrected_text  TEXT NOT NULL,
    corrected_by    UUID NOT NULL REFERENCES users(id),
    corrected_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_corrections_soep ON corrections(soep_id);
CREATE INDEX idx_corrections_field ON corrections(field);

-- =============================================================================
-- Patientinstructies
-- =============================================================================
CREATE TABLE patient_instructions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consult_id      UUID NOT NULL REFERENCES consults(id) ON DELETE CASCADE,
    instruction_text TEXT NOT NULL,
    language        VARCHAR(10) DEFAULT 'nl',
    readability     VARCHAR(10) DEFAULT 'B1',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Audit Logs (NEN 7513 conform)
-- =============================================================================
-- Immutable: geen UPDATE of DELETE toegestaan op deze tabel
CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         UUID REFERENCES users(id),
    user_role       user_role,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     VARCHAR(100),
    ip_address      INET,
    user_agent      VARCHAR(500),
    details         JSONB DEFAULT '{}',
    checksum        VARCHAR(64)            -- SHA-256 van vorige log entry (chain)
);

CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Voorkom mutaties op audit_logs
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs zijn immutable. UPDATE en DELETE zijn niet toegestaan.';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

CREATE TRIGGER audit_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

-- =============================================================================
-- Updated_at trigger
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_consults
    BEFORE UPDATE ON consults FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER set_updated_at_soep
    BEFORE UPDATE ON soep_concepts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER set_updated_at_users
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- Initiele beheerder (wachtwoord wijzigen bij eerste login!)
-- =============================================================================
INSERT INTO users (username, display_name, role, password_hash) VALUES
    ('admin', 'Systeembeheerder', 'beheerder',
     crypt('CHANGE_ME_ON_FIRST_LOGIN', gen_salt('bf', 12)));

-- =============================================================================
-- Placeholder user voor anonieme uploads (MVP)
-- =============================================================================
INSERT INTO users (id, username, display_name, role, password_hash) VALUES
    ('00000000-0000-0000-0000-000000000000', 'system', 'Systeem', 'beheerder',
     crypt('DISABLED', gen_salt('bf', 12)))
ON CONFLICT DO NOTHING;

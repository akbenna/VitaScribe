-- =============================================================================
-- AI-Consultassistent - Feedbackloop & Vocabulaire
-- =============================================================================
-- Migratie 002: tabellen voor de zelflerend-laag
-- - consultation_feedback: artscorrecties op transcripten en SOEP
-- - vocabulary_corrections: geleerde woordenlijstcorrecties
-- =============================================================================

-- =============================================================================
-- FEEDBACK TABEL
-- Slaat de originele en gecorrigeerde versies op per consult
-- =============================================================================

CREATE TABLE IF NOT EXISTS consultation_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consultation_id UUID REFERENCES consultations(id) ON DELETE SET NULL,

    -- Transcript feedback
    transcript_original TEXT,
    transcript_corrected TEXT,
    transcript_diff JSONB,

    -- SOEP feedback
    soep_original JSONB,
    soep_corrected JSONB,
    soep_diff JSONB,

    -- Metadata
    corrected_by UUID REFERENCES users(id),
    correction_type VARCHAR(50) DEFAULT 'manual',
    vocabulary_corrections_applied INTEGER DEFAULT 0,
    processing_time_secs FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_consultation ON consultation_feedback(consultation_id);
CREATE INDEX idx_feedback_created ON consultation_feedback(created_at);

COMMENT ON TABLE consultation_feedback IS
    'Artscorrecties op transcripten en SOEP - trainingsdata voor de zelflerend-laag';


-- =============================================================================
-- VOCABULARY CORRECTIONS TABEL
-- Geleerde correcties uit de feedbackloop
-- =============================================================================

CREATE TABLE IF NOT EXISTS vocabulary_corrections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    wrong_text VARCHAR(255) NOT NULL,
    correct_text VARCHAR(255) NOT NULL,
    category VARCHAR(50) DEFAULT 'custom',

    -- Hoe vaak is deze correctie toegepast?
    times_applied INTEGER DEFAULT 0,
    -- Hoe vaak is deze correctie bevestigd door een arts?
    times_confirmed INTEGER DEFAULT 0,
    -- Is deze correctie actief?
    is_active BOOLEAN DEFAULT TRUE,

    -- Herkomst
    source VARCHAR(50) DEFAULT 'manual',
    added_by UUID REFERENCES users(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(wrong_text, correct_text)
);

CREATE INDEX idx_vocab_active ON vocabulary_corrections(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_vocab_category ON vocabulary_corrections(category);

COMMENT ON TABLE vocabulary_corrections IS
    'Geleerde woordenlijstcorrecties uit artsfeedback - groeit mee met gebruik';


-- =============================================================================
-- TRIGGER: updated_at automatisch bijwerken
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_feedback_updated
    BEFORE UPDATE ON consultation_feedback
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_vocab_updated
    BEFORE UPDATE ON vocabulary_corrections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

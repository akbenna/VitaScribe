-- =============================================================================
-- Seed Data - Testgebruikers + demo consult
-- =============================================================================
-- Draai na 001_init.sql:
--   psql -h localhost -U ca_app -d consultassistent -f scripts/seed_data.sql
-- =============================================================================

-- Testgebruikers (wachtwoord: "test123" voor allemaal)
INSERT INTO users (id, username, display_name, role, password_hash) VALUES
    ('11111111-1111-1111-1111-111111111111',
     'dr.janssen', 'Dr. A. Janssen', 'arts',
     crypt('test123', gen_salt('bf', 12))),
    ('22222222-2222-2222-2222-222222222222',
     'poh.devries', 'M. de Vries (POH)', 'poh',
     crypt('test123', gen_salt('bf', 12)))
ON CONFLICT (username) DO NOTHING;

-- Demo consult (volledig doorlopen pipeline)
INSERT INTO consults (
    id, patient_hash, practitioner_id, status, started_at, ended_at
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd',
    '11111111-1111-1111-1111-111111111111',
    'reviewing',
    NOW() - INTERVAL '30 minutes',
    NOW() - INTERVAL '15 minutes'
) ON CONFLICT DO NOTHING;

-- Demo transcript
INSERT INTO transcripts (
    id, consult_id, raw_text, segments, model_version, language, confidence_avg, word_count, duration_secs
) VALUES (
    '44444444-4444-4444-4444-444444444444',
    '33333333-3333-3333-3333-333333333333',
    'Arts: Goedemorgen, waarmee kan ik u helpen? Patient: Ik heb al drie dagen hoofdpijn, een drukkend gevoel bovenop mijn hoofd. Arts: Heeft u ook koorts of nekpijn? Patient: Nee, geen koorts. Ik heb paracetamol geprobeerd maar dat helpt niet echt. Arts: Gebruikt u verder nog medicijnen? Patient: Nee, niks. Arts: Ik ga even uw bloeddruk meten. Die is 130 over 85, dat is goed. Patient: Oké, fijn. Arts: Ik denk dat het spanningshoofdpijn is. Ik schrijf ibuprofen voor, 400 milligram, drie keer per dag zo nodig. Als het na een week niet over is, kom dan terug.',
    '[
        {"spreker": "arts", "start": 0.0, "eind": 4.2, "tekst": "Goedemorgen, waarmee kan ik u helpen?", "confidence": 0.95},
        {"spreker": "patient", "start": 4.5, "eind": 11.0, "tekst": "Ik heb al drie dagen hoofdpijn, een drukkend gevoel bovenop mijn hoofd.", "confidence": 0.92},
        {"spreker": "arts", "start": 11.5, "eind": 15.0, "tekst": "Heeft u ook koorts of nekpijn?", "confidence": 0.94},
        {"spreker": "patient", "start": 15.3, "eind": 22.0, "tekst": "Nee, geen koorts. Ik heb paracetamol geprobeerd maar dat helpt niet echt.", "confidence": 0.91},
        {"spreker": "arts", "start": 22.5, "eind": 25.0, "tekst": "Gebruikt u verder nog medicijnen?", "confidence": 0.96},
        {"spreker": "patient", "start": 25.2, "eind": 26.5, "tekst": "Nee, niks.", "confidence": 0.93},
        {"spreker": "arts", "start": 27.0, "eind": 33.0, "tekst": "Ik ga even uw bloeddruk meten. Die is 130 over 85, dat is goed.", "confidence": 0.94},
        {"spreker": "patient", "start": 33.2, "eind": 34.5, "tekst": "Oké, fijn.", "confidence": 0.97},
        {"spreker": "arts", "start": 35.0, "eind": 50.0, "tekst": "Ik denk dat het spanningshoofdpijn is. Ik schrijf ibuprofen voor, 400 milligram, drie keer per dag zo nodig. Als het na een week niet over is, kom dan terug.", "confidence": 0.93}
    ]',
    'whisper-large-v3-turbo',
    'nl',
    0.94,
    115,
    50.0
) ON CONFLICT DO NOTHING;

-- Demo extractie
INSERT INTO extractions (
    id, consult_id, transcript_id, klachten, anamnese, lich_onderzoek,
    vitale_params, medicatie, allergieen, voorgeschiedenis,
    model_version, confidence, raw_response
) VALUES (
    '55555555-5555-5555-5555-555555555555',
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',
    '["Hoofdpijn, drukkend karakter, 3 dagen, bovenop het hoofd"]',
    '{"duur": "3 dagen", "karakter": "drukkend", "locatie": "bovenop hoofd", "koorts": false, "nekpijn": false, "paracetamol": "onvoldoende effect"}',
    '{"bloeddruk_gemeten": true}',
    '{"systolisch": 130, "diastolisch": 85}',
    '{"huidig": [], "voorgeschreven": [{"naam": "ibuprofen", "dosering": "400mg", "frequentie": "3dd zo nodig"}]}',
    '[]',
    '[]',
    'llama3.1:8b',
    0.89,
    NULL
) ON CONFLICT DO NOTHING;

-- Demo SOEP concept
INSERT INTO soep_concepts (
    id, consult_id, extraction_id, s_text, o_text, e_text, p_text,
    icpc_code, icpc_titel, model_version, confidence
) VALUES (
    '66666666-6666-6666-6666-666666666666',
    '33333333-3333-3333-3333-333333333333',
    '55555555-5555-5555-5555-555555555555',
    'Patient, presenteert zich met sinds 3 dagen bestaande hoofdpijn. Drukkend karakter, gelokaliseerd bovenop het hoofd. Geen koorts, geen nekpijn. Paracetamol heeft onvoldoende effect.',
    'Bloeddruk 130/85 mmHg.',
    'Spanningshoofdpijn (ICPC: N02). DD: medicatieovergebruik hoofdpijn (geen aanwijzingen), cervicogene hoofdpijn (geen nekklachten).',
    'Medicamenteus: Ibuprofen 400mg 3dd zo nodig. Niet-medicamenteus: advies ontspanning, voldoende slaap, adequate vochtinname. Controle: bij aanhouden klachten >1 week terugkomen.',
    'N02',
    'Spanningshoofdpijn',
    'llama3.1:8b',
    0.87
) ON CONFLICT DO NOTHING;

-- Demo detectie
INSERT INTO detection_results (
    id, consult_id, red_flags, missing_info
) VALUES (
    '77777777-7777-7777-7777-777777777777',
    '33333333-3333-3333-3333-333333333333',
    '[]',
    '[{"id": "mi_1", "veld": "anamnese", "beschrijving": "Visusklachten niet uitgevraagd", "prioriteit": "laag"}, {"id": "mi_2", "veld": "anamnese", "beschrijving": "Stress/werkbelasting niet uitgevraagd", "prioriteit": "middel"}]'
) ON CONFLICT DO NOTHING;

-- Demo patientinstructie
INSERT INTO patient_instructions (
    consult_id, instruction_text, language, readability
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    'Beste patient,

U bent vandaag bij de huisarts geweest voor hoofdpijn.

Wat heeft de arts gevonden?
- Uw bloeddruk is goed (130/85).
- De arts denkt dat u spanningshoofdpijn heeft.

Wat kunt u doen?
- Neem ibuprofen 400 mg, maximaal 3 keer per dag, als u pijn heeft.
- Probeer voldoende te slapen en te ontspannen.
- Drink genoeg water.

Wanneer moet u terugkomen?
- Als de hoofdpijn na 1 week niet over is.
- Als u koorts krijgt of als de pijn erger wordt.

Heeft u vragen? Bel dan de huisartsenpraktijk.',
    'nl',
    'B1'
) ON CONFLICT DO NOTHING;

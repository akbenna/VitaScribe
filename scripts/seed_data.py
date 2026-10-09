"""
Seed script - Maak testgebruikers aan via Python (voor gebruik zonder psql/pgcrypto).

Gebruik:
    python scripts/seed_data.py

Maakt dezelfde testdata als seed_data.sql, maar met bcrypt hashing via Python.
"""

import asyncio
import sys
from pathlib import Path

# Voeg project root toe aan path
sys.path.insert(0, str(Path(__file__).parent.parent))

from passlib.context import CryptContext
from sqlalchemy import text
from shared.database import engine, async_session
from shared.models.base import Base
from shared.models import User, Consult, Transcript, Extraction, SoepConcept, DetectionResult, PatientInstruction
from shared.models.user import UserRole
from shared.models.consult import ConsultStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_PASSWORD = "test123"


async def seed():
    # Maak tabellen aan als ze niet bestaan
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Check of er al users zijn
        result = await db.execute(text("SELECT COUNT(*) FROM users"))
        count = result.scalar()
        if count and count > 0:
            print(f"Database bevat al {count} gebruikers. Overslaan.")
            return

        # Testgebruikers
        users = [
            User(
                id="11111111-1111-1111-1111-111111111111",
                username="dr.janssen",
                display_name="Dr. A. Janssen",
                role=UserRole.arts,
                password_hash=pwd_context.hash(TEST_PASSWORD),
            ),
            User(
                id="22222222-2222-2222-2222-222222222222",
                username="poh.devries",
                display_name="M. de Vries (POH)",
                role=UserRole.poh,
                password_hash=pwd_context.hash(TEST_PASSWORD),
            ),
            User(
                id="00000000-0000-0000-0000-000000000001",
                username="admin",
                display_name="Systeembeheerder",
                role=UserRole.beheerder,
                password_hash=pwd_context.hash(TEST_PASSWORD),
            ),
        ]
        for u in users:
            db.add(u)

        await db.flush()
        print(f"  {len(users)} testgebruikers aangemaakt")
        print(f"  Wachtwoord voor iedereen: {TEST_PASSWORD}")

        # Demo consult
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        consult = Consult(
            id="33333333-3333-3333-3333-333333333333",
            patient_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd",
            practitioner_id="11111111-1111-1111-1111-111111111111",
            status=ConsultStatus.reviewing,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=15),
        )
        db.add(consult)
        await db.flush()

        transcript = Transcript(
            id="44444444-4444-4444-4444-444444444444",
            consult_id=consult.id,
            raw_text="Arts: Goedemorgen, waarmee kan ik u helpen? Patient: Ik heb al drie dagen hoofdpijn...",
            segments=[
                {"spreker": "arts", "start": 0.0, "eind": 4.2, "tekst": "Goedemorgen, waarmee kan ik u helpen?", "confidence": 0.95},
                {"spreker": "patient", "start": 4.5, "eind": 11.0, "tekst": "Ik heb al drie dagen hoofdpijn, een drukkend gevoel bovenop mijn hoofd.", "confidence": 0.92},
                {"spreker": "arts", "start": 11.5, "eind": 15.0, "tekst": "Heeft u ook koorts of nekpijn?", "confidence": 0.94},
                {"spreker": "patient", "start": 15.3, "eind": 22.0, "tekst": "Nee, geen koorts. Ik heb paracetamol geprobeerd maar dat helpt niet echt.", "confidence": 0.91},
            ],
            model_version="whisper-large-v3-turbo",
            language="nl",
            confidence_avg=0.93,
            word_count=115,
            duration_secs=50.0,
        )
        db.add(transcript)
        await db.flush()

        extraction = Extraction(
            id="55555555-5555-5555-5555-555555555555",
            consult_id=consult.id,
            transcript_id=transcript.id,
            klachten=["Hoofdpijn, drukkend karakter, 3 dagen"],
            anamnese={"duur": "3 dagen", "karakter": "drukkend"},
            lich_onderzoek={"bloeddruk_gemeten": True},
            vitale_params={"systolisch": 130, "diastolisch": 85},
            medicatie={"voorgeschreven": [{"naam": "ibuprofen", "dosering": "400mg"}]},
            allergieen=[],
            voorgeschiedenis=[],
            model_version="llama3.1:8b",
            confidence=0.89,
        )
        db.add(extraction)
        await db.flush()

        soep = SoepConcept(
            id="66666666-6666-6666-6666-666666666666",
            consult_id=consult.id,
            extraction_id=extraction.id,
            s_text="Patient presenteert zich met sinds 3 dagen bestaande hoofdpijn. Drukkend karakter, bovenop het hoofd. Geen koorts, geen nekpijn. Paracetamol onvoldoende effect.",
            o_text="Bloeddruk 130/85 mmHg.",
            e_text="Spanningshoofdpijn (ICPC: N02).",
            p_text="Ibuprofen 400mg 3dd zo nodig. Advies: ontspanning, voldoende slaap. Controle bij aanhouden >1 week.",
            icpc_code="N02",
            icpc_titel="Spanningshoofdpijn",
            model_version="llama3.1:8b",
            confidence=0.87,
        )
        db.add(soep)

        detection = DetectionResult(
            id="77777777-7777-7777-7777-777777777777",
            consult_id=consult.id,
            red_flags=[],
            missing_info=[
                {"id": "mi_1", "veld": "anamnese", "beschrijving": "Visusklachten niet uitgevraagd", "prioriteit": "laag"},
                {"id": "mi_2", "veld": "anamnese", "beschrijving": "Stress/werkbelasting niet uitgevraagd", "prioriteit": "middel"},
            ],
        )
        db.add(detection)

        instruction = PatientInstruction(
            consult_id=consult.id,
            instruction_text="Beste patient,\n\nU bent vandaag bij de huisarts geweest voor hoofdpijn.\n\nWat kunt u doen?\n- Neem ibuprofen 400 mg, maximaal 3 keer per dag.\n- Probeer voldoende te slapen.\n\nWanneer terugkomen?\n- Als de hoofdpijn na 1 week niet over is.",
        )
        db.add(instruction)

        await db.commit()
        print("  Demo consult met volledig pipeline resultaat aangemaakt")
        print("\nKlaar! Log in met:")
        print("  Gebruiker: dr.janssen")
        print("  Wachtwoord: test123")


if __name__ == "__main__":
    print("Seed data aanmaken...")
    asyncio.run(seed())

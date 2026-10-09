"""
PatientInstruction model - Patientinstructie in eenvoudig Nederlands.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin
from shared.models.types import UUIDType


class PatientInstruction(Base, UUIDMixin):
    __tablename__ = "patient_instructions"

    consult_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False,
    )
    instruction_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="nl")
    readability: Mapped[str] = mapped_column(String(10), default="B1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaties
    consult = relationship("Consult", back_populates="patient_instruction")

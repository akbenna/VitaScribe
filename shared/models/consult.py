"""
Consult model - Een consult met status-tracking.
"""

from __future__ import annotations

import enum

from sqlalchemy import String, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin, TimestampMixin
from shared.models.types import UUIDType, JSONType


class ConsultStatus(str, enum.Enum):
    recording = "recording"
    transcribing = "transcribing"
    extracting = "extracting"
    reviewing = "reviewing"
    approved = "approved"
    exported = "exported"
    failed = "failed"


class Consult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "consults"

    patient_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    practitioner_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=False
    )
    status: Mapped[ConsultStatus] = mapped_column(
        Enum(ConsultStatus, name="consult_status"),
        nullable=False,
        default=ConsultStatus.recording,
    )
    started_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    consult_metadata: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)

    # Relaties
    practitioner = relationship("User", back_populates="consults")
    transcript = relationship("Transcript", back_populates="consult", uselist=False)
    extraction = relationship("Extraction", back_populates="consult", uselist=False)
    soep_concept = relationship("SoepConcept", back_populates="consult", uselist=False)
    detection_result = relationship("DetectionResult", back_populates="consult", uselist=False)
    patient_instruction = relationship("PatientInstruction", back_populates="consult", uselist=False)

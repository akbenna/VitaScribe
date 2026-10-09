"""
SoepConcept model - SOEP-dossiervoering concept.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin, TimestampMixin
from shared.models.types import UUIDType


class SoepConcept(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "soep_concepts"

    consult_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    extraction_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("extractions.id", ondelete="CASCADE"),
        nullable=False,
    )
    s_text: Mapped[str] = mapped_column(Text, default="")
    o_text: Mapped[str] = mapped_column(Text, default="")
    e_text: Mapped[str] = mapped_column(Text, default="")
    p_text: Mapped[str] = mapped_column(Text, default="")
    icpc_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    icpc_titel: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relaties
    consult = relationship("Consult", back_populates="soep_concept")
    extraction = relationship("Extraction", back_populates="soep_concept")
    approved_by_user = relationship("User", back_populates="approved_soeps")
    corrections = relationship("Correction", back_populates="soep")

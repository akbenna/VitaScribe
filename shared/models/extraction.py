"""
Extraction model - LLM medische extractie uit transcript.
"""

from __future__ import annotations

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin
from shared.models.types import UUIDType, JSONType


class Extraction(Base, UUIDMixin):
    __tablename__ = "extractions"

    consult_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    transcript_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    klachten: Mapped[dict] = mapped_column(JSONType, default=list)
    anamnese: Mapped[dict] = mapped_column(JSONType, default=dict)
    lich_onderzoek: Mapped[dict] = mapped_column(JSONType, default=dict)
    vitale_params: Mapped[dict] = mapped_column(JSONType, default=dict)
    medicatie: Mapped[dict] = mapped_column(JSONType, default=list)
    allergieen: Mapped[dict] = mapped_column(JSONType, default=list)
    voorgeschiedenis: Mapped[dict] = mapped_column(JSONType, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Relaties
    consult = relationship("Consult", back_populates="extraction")
    transcript = relationship("Transcript", back_populates="extraction")
    soep_concept = relationship("SoepConcept", back_populates="extraction", uselist=False)

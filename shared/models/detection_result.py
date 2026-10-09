"""
DetectionResult model - Rode vlaggen + ontbrekende informatie.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin
from shared.models.types import UUIDType, JSONType


class DetectionResult(Base, UUIDMixin):
    __tablename__ = "detection_results"

    consult_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("consults.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    red_flags: Mapped[dict] = mapped_column(JSONType, default=list)
    missing_info: Mapped[dict] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaties
    consult = relationship("Consult", back_populates="detection_result")

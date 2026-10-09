"""
User model - Gebruikers (arts, poh, beheerder).
"""

from __future__ import annotations

import enum

from sqlalchemy import String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, UUIDMixin, TimestampMixin


class UserRole(str, enum.Enum):
    arts = "arts"
    poh = "poh"
    beheerder = "beheerder"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaties
    consults = relationship("Consult", back_populates="practitioner")
    corrections = relationship("Correction", back_populates="corrected_by_user")
    approved_soeps = relationship("SoepConcept", back_populates="approved_by_user")

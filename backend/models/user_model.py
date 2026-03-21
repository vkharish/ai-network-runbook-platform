from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.security import Role
from backend.database.base import AuditBase


class User(AuditBase):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=Role.ENGINEER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="created_by_user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role}>"

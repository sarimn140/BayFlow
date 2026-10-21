"""ORM models of the identity module: `users` (spec 02 §3.1, §3.22)."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, false, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.orm import TimestampMixin, UUIDPrimaryKeyMixin, not_blank


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One login account; customer, staff and owner are all users (roles live in memberships)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("email LIKE '_%@_%'", name="email_shape"),
        not_blank("full_name"),
        # Bonus (brief §8.2): AI Front Desk caller lookup by phone.
        Index("ix_users_phone", "phone", postgresql_where=text("phone IS NOT NULL")),
        # The few platform admins (D94): the last-admin safeguard locks and counts them.
        Index("ix_users_platform_admin", "id", postgresql_where=text("is_platform_admin")),
    )

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A BayFlow operator (D94, spec 19 §1): not a shop role; set only by the bootstrap script, the
    # seed or another platform admin.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

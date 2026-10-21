"""platform admin: users.is_platform_admin, shop suspension, audit_events

Spec 19 (D94-D97), spec 02 §3.22:

- `users.is_platform_admin boolean NOT NULL DEFAULT false` (D94) and the partial index
  `ix_users_platform_admin` on `id` where it is true (the last-admin safeguard locks those rows).
- `shops.suspended_at`, `suspended_reason varchar(500)`, `suspended_by_user_id` (FK `users`,
  `RESTRICT`) with `ck_shops_suspension_complete`: all three null or all three set (D96).
- `audit_events` exactly as spec 19 §3.1 (D95), with its five indexes; `category`, `actor_role`
  and `target_type` are stored enums (D29: VARCHAR(32) + CHECK); `action` is dotted lower snake
  case; `metadata` is a JSON object. The trigger `trg_audit_events_append_only` rejects `UPDATE`
  and `DELETE` with the baseline's `forbid_mutation()` (spec 02 §8; SQLSTATE `P0001`).

Expand-only: existing rows get `is_platform_admin = false` and no suspension. Generated with
autogenerate, then reviewed; the trigger is hand-written.

Revision ID: 339df51b764d
Revises: 23165172278b
Create Date: 2026-10-09 20:47:36.027034+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "339df51b764d"
down_revision: str | Sequence[str] | None = "23165172278b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_index(
        "ix_users_platform_admin",
        "users",
        ["id"],
        unique=False,
        postgresql_where=sa.text("is_platform_admin"),
    )

    op.add_column("shops", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shops", sa.Column("suspended_reason", sa.String(length=500), nullable=True))
    op.add_column("shops", sa.Column("suspended_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_shops_suspended_by_user_id_users"),
        "shops",
        "users",
        ["suspended_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_shops_suspension_complete"),
        "shops",
        "((suspended_at IS NULL) = (suspended_reason IS NULL))"
        " AND ((suspended_at IS NULL) = (suspended_by_user_id IS NULL))",
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("shop_id", sa.Uuid(), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("target_label", sa.String(length=200), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "action ~ '^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$'",
            name=op.f("ck_audit_events_action_format"),
        ),
        sa.CheckConstraint(
            "actor_role IN ('PLATFORM_ADMIN', 'OWNER', 'SERVICE_ADVISOR', 'TECHNICIAN', "
            "'PARTS_PERSON', 'QC_INSPECTOR', 'CUSTOMER', 'SYSTEM', 'ANONYMOUS')",
            name=op.f("ck_audit_events_actor_role"),
        ),
        sa.CheckConstraint(
            "category IN ('AUTH', 'USER', 'SHOP', 'MEMBERSHIP', 'BOOKING', 'ADMIN')",
            name=op.f("ck_audit_events_category"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name=op.f("ck_audit_events_metadata_object")
        ),
        sa.CheckConstraint(
            "target_type IN ('USER', 'SHOP', 'MEMBERSHIP', 'BOOKING')",
            name=op.f("ck_audit_events_target_type"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_audit_events_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_occurred_at_id",
        "audit_events",
        [sa.literal_column("occurred_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_shop_id_occurred_at",
        "audit_events",
        ["shop_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor_user_id_occurred_at",
        "audit_events",
        ["actor_user_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_category_occurred_at",
        "audit_events",
        ["category", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_target_type_target_id",
        "audit_events",
        ["target_type", "target_id"],
        unique=False,
    )

    # Append-only (spec 02 §8, spec 19 §3.1): any UPDATE or DELETE raises SQLSTATE P0001 through
    # the baseline's forbid_mutation(). TRUNCATE does not fire row triggers (test clean-up).
    op.execute(
        "CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events"
        " FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_audit_events_append_only ON audit_events")
    op.drop_index("ix_audit_events_target_type_target_id", table_name="audit_events")
    op.drop_index("ix_audit_events_category_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_shop_id_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_constraint(op.f("ck_shops_suspension_complete"), "shops", type_="check")
    op.drop_constraint(op.f("fk_shops_suspended_by_user_id_users"), "shops", type_="foreignkey")
    op.drop_column("shops", "suspended_by_user_id")
    op.drop_column("shops", "suspended_reason")
    op.drop_column("shops", "suspended_at")

    op.drop_index(
        "ix_users_platform_admin", table_name="users", postgresql_where=sa.text("is_platform_admin")
    )
    op.drop_column("users", "is_platform_admin")

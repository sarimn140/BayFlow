"""text AI: ai_audit_events and ai_drafts

D103, modules/ai.md "Tables":

- `ai_audit_events`: one row per model call (AI-41): feature, prompt version, provider, model,
  actor, subject, the masked prompt, the output, status, tokens and latency. Append-only: the
  trigger `trg_ai_audit_events_append_only` rejects `UPDATE` and `DELETE` with the baseline's
  `forbid_mutation()` (like `audit_events`).
- `ai_drafts`: model output waiting for a person's decision (AI-42); composite FK
  `(shop_id, audit_event_id)` → `ai_audit_events(shop_id, id)` (D20).

Expand-only: two new tables. Generated with autogenerate, then reviewed; the trigger is
hand-written.

Revision ID: 90a856e17478
Revises: 339df51b764d
Create Date: 2026-10-10 05:14:04.466957+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "90a856e17478"
down_revision: str | Sequence[str] | None = "339df51b764d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("feature", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("input_masked", sa.Text(), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_role IN ('CUSTOMER', 'OWNER', 'SERVICE_ADVISOR', 'TECHNICIAN', 'PARTS_PERSON', "
            "'QC_INSPECTOR', 'SYSTEM')",
            name=op.f("ck_ai_audit_events_actor_role"),
        ),
        sa.CheckConstraint(
            "feature IN ('ESTIMATE_EXPLAINER', 'ESTIMATE_CHECKER', 'VOICE_TO_ESTIMATE', "
            "'SYMPTOM_TRIAGE', 'ASK_YOUR_SHOP')",
            name=op.f("ck_ai_audit_events_feature"),
        ),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR output IS NOT NULL",
            name=op.f("ck_ai_audit_events_succeeded_output"),
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'PROVIDER_ERROR', 'INVALID_OUTPUT', 'GUARD_BLOCKED')",
            name=op.f("ck_ai_audit_events_status"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('BOOKING', 'ESTIMATE', 'SHOP')",
            name=op.f("ck_ai_audit_events_subject_type"),
        ),
        sa.CheckConstraint(
            "char_length(input_masked) <= 32000",
            name=op.f("ck_ai_audit_events_input_masked_length"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0 AND (input_tokens IS NULL OR input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0)",
            name=op.f("ck_ai_audit_events_non_negative_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_ai_audit_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_ai_audit_events_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_audit_events")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_ai_audit_events_shop_id_id")),
    )
    op.create_index(
        "ix_ai_audit_events_shop_id_created_at",
        "ai_audit_events",
        ["shop_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "ai_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("feature", sa.String(length=32), nullable=False),
        sa.Column("audit_event_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'PENDING') = (decided_by_user_id IS NULL AND decided_at IS NULL)",
            name=op.f("ck_ai_drafts_decision"),
        ),
        sa.CheckConstraint(
            "(status IN ('ACCEPTED', 'EDITED')) = (final_payload IS NOT NULL)",
            name=op.f("ck_ai_drafts_final_payload"),
        ),
        sa.CheckConstraint(
            "decision_note IS NULL OR btrim(decision_note) <> ''",
            name=op.f("ck_ai_drafts_decision_note_not_blank"),
        ),
        sa.CheckConstraint(
            "feature IN ('ESTIMATE_EXPLAINER', 'ESTIMATE_CHECKER', 'VOICE_TO_ESTIMATE', "
            "'SYMPTOM_TRIAGE', 'ASK_YOUR_SHOP')",
            name=op.f("ck_ai_drafts_feature"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'EDITED', 'REJECTED')",
            name=op.f("ck_ai_drafts_status"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('BOOKING', 'ESTIMATE', 'SHOP')",
            name=op.f("ck_ai_drafts_subject_type"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_ai_drafts_decided_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name=op.f("fk_ai_drafts_requested_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "audit_event_id"],
            ["ai_audit_events.shop_id", "ai_audit_events.id"],
            name=op.f("fk_ai_drafts_shop_id_audit_event_id_ai_audit_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_ai_drafts_shop_id_shops"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_drafts")),
        sa.UniqueConstraint("audit_event_id", name=op.f("uq_ai_drafts_audit_event_id")),
    )
    op.create_index(
        "ix_ai_drafts_shop_id_status_created_at",
        "ai_drafts",
        ["shop_id", "status", "created_at"],
        unique=False,
    )

    op.execute(
        "CREATE TRIGGER trg_ai_audit_events_append_only BEFORE UPDATE OR DELETE ON ai_audit_events"
        " FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_ai_audit_events_append_only ON ai_audit_events")
    op.drop_index("ix_ai_drafts_shop_id_status_created_at", table_name="ai_drafts")
    op.drop_table("ai_drafts")
    op.drop_index("ix_ai_audit_events_shop_id_created_at", table_name="ai_audit_events")
    op.drop_table("ai_audit_events")

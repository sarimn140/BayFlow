"""baseline schema

Every table of spec 02 (core and the spec 05 bonus tables) with its keys, CHECK constraints
(D29 enums as VARCHAR(32) + CHECK, D41 whole rupees), composite tenant foreign keys (D20),
partial and expression indexes, the D79 `seq` identity columns, and the append-only triggers on
`booking_events` and `stock_movements` (spec 02 §8). Generated with autogenerate, then reviewed.

Revision ID: 23165172278b
Revises:
Create Date: 2026-10-09 10:17:24.926040+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "23165172278b"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Karachi'"),
            nullable=False,
        ),
        sa.Column(
            "slot_duration_minutes", sa.Integer(), server_default=sa.text("60"), nullable=False
        ),
        sa.Column("slot_capacity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("is_listed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("btrim(address) <> ''", name=op.f("ck_shops_address_not_blank")),
        sa.CheckConstraint("btrim(city) <> ''", name=op.f("ck_shops_city_not_blank")),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_shops_name_not_blank")),
        sa.CheckConstraint("btrim(phone) <> ''", name=op.f("ck_shops_phone_not_blank")),
        sa.CheckConstraint(
            "logo_url IS NULL OR logo_url LIKE 'https://%'", name=op.f("ck_shops_logo_url_https")
        ),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_shops_slug_format")),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 0 AND 5", name=op.f("ck_shops_rating_range")
        ),
        sa.CheckConstraint("slot_capacity BETWEEN 1 AND 50", name=op.f("ck_shops_slot_capacity")),
        sa.CheckConstraint(
            "slot_duration_minutes BETWEEN 15 AND 240 AND slot_duration_minutes % 15 = 0",
            name=op.f("ck_shops_slot_duration"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shops")),
        sa.UniqueConstraint("slug", name=op.f("uq_shops_slug")),
    )
    op.create_index(
        "ix_shops_listed_city_name",
        "shops",
        ["city", "name"],
        unique=False,
        postgresql_where=sa.text("is_listed"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("btrim(full_name) <> ''", name=op.f("ck_users_full_name_not_blank")),
        sa.CheckConstraint("email LIKE '_%@_%'", name=op.f("ck_users_email_shape")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(
        "ix_users_phone",
        "users",
        ["phone"],
        unique=False,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    op.create_table(
        "parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("on_hand", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reorder_level", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_parts_name_not_blank")),
        sa.CheckConstraint(
            "sku ~ '^[A-Z0-9][A-Z0-9._/-]{0,39}$'", name=op.f("ck_parts_sku_format")
        ),
        sa.CheckConstraint("on_hand >= 0", name=op.f("ck_parts_on_hand_non_negative")),
        sa.CheckConstraint("reorder_level >= 0", name=op.f("ck_parts_reorder_level")),
        sa.CheckConstraint("reserved <= on_hand", name=op.f("ck_parts_reserved_lte_on_hand")),
        sa.CheckConstraint("reserved >= 0", name=op.f("ck_parts_reserved_non_negative")),
        sa.CheckConstraint("unit_cost = trunc(unit_cost)", name=op.f("ck_parts_whole_rupees")),
        sa.CheckConstraint("unit_cost >= 0", name=op.f("ck_parts_unit_cost")),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_parts_shop_id_shops"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parts")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_parts_shop_id_id")),
        sa.UniqueConstraint("shop_id", "sku", name=op.f("uq_parts_shop_id_sku")),
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("base_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_services_name_not_blank")),
        sa.CheckConstraint(
            "base_price IS NULL OR base_price = trunc(base_price)",
            name=op.f("ck_services_whole_rupees"),
        ),
        sa.CheckConstraint(
            "base_price IS NULL OR base_price >= 0", name=op.f("ck_services_base_price")
        ),
        sa.CheckConstraint(
            "estimated_duration_minutes BETWEEN 5 AND 10080", name=op.f("ck_services_duration")
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_services_shop_id_shops"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_services_shop_id_id")),
    )
    op.create_index(
        "uq_services_active_name",
        "services",
        ["shop_id", sa.literal_column("lower(name)")],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "shop_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
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
            "role <> 'OWNER' OR is_active", name=op.f("ck_shop_memberships_owner_active")
        ),
        sa.CheckConstraint(
            "role IN ('OWNER', 'SERVICE_ADVISOR', 'TECHNICIAN', 'PARTS_PERSON', 'QC_INSPECTOR')",
            name=op.f("ck_shop_memberships_role"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_shop_memberships_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_shop_memberships_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_shop_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shop_memberships")),
        sa.UniqueConstraint("shop_id", "user_id", name=op.f("uq_shop_memberships_shop_id_user_id")),
    )
    op.create_index(
        "ix_shop_memberships_shop_role_active",
        "shop_memberships",
        ["shop_id", "role"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_shop_memberships_user_active",
        "shop_memberships",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "uq_shop_memberships_one_owner_per_shop",
        "shop_memberships",
        ["shop_id"],
        unique=True,
        postgresql_where=sa.text("role = 'OWNER'"),
    )
    op.create_table(
        "shop_working_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
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
            "is_closed OR (opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > "
            "opens_at)",
            name=op.f("ck_shop_working_hours_open_times"),
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_shop_working_hours_weekday")),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_shop_working_hours_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shop_working_hours")),
        sa.UniqueConstraint(
            "shop_id", "weekday", name=op.f("uq_shop_working_hours_shop_id_weekday")
        ),
    )
    op.create_table(
        "slot_counters",
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booked_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "booked_count >= 0", name=op.f("ck_slot_counters_booked_count_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_slot_counters_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("shop_id", "slot_start", name=op.f("pk_slot_counters")),
    )
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("registration_number", sa.String(length=20), nullable=False),
        sa.Column("registration_key", sa.String(length=20), nullable=False),
        sa.Column("make", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("color", sa.String(length=30), nullable=True),
        sa.Column("mileage_km", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("btrim(make) <> ''", name=op.f("ck_vehicles_make_not_blank")),
        sa.CheckConstraint("btrim(model) <> ''", name=op.f("ck_vehicles_model_not_blank")),
        sa.CheckConstraint(
            "btrim(registration_number) <> ''",
            name=op.f("ck_vehicles_registration_number_not_blank"),
        ),
        sa.CheckConstraint(
            "registration_key = upper(regexp_replace(registration_number, '[[:space:]-]', '', "
            "'g')) AND registration_key ~ '^[A-Z0-9]{2,20}$'",
            name=op.f("ck_vehicles_registration_key"),
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km BETWEEN 0 AND 2000000",
            name=op.f("ck_vehicles_mileage"),
        ),
        sa.CheckConstraint("year BETWEEN 1900 AND 2100", name=op.f("ck_vehicles_year")),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_vehicles_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
        sa.UniqueConstraint("owner_user_id", "id", name=op.f("uq_vehicles_owner_user_id_id")),
        sa.UniqueConstraint(
            "owner_user_id",
            "registration_key",
            name=op.f("uq_vehicles_owner_user_id_registration_key"),
        ),
    )
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=9), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("mileage_km", sa.Integer(), nullable=True),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("technician_user_id", sa.Uuid(), nullable=True),
        sa.Column("parts_person_user_id", sa.Uuid(), nullable=True),
        sa.Column("qc_inspector_user_id", sa.Uuid(), nullable=True),
        sa.Column("customer_notes", sa.String(length=2000), nullable=True),
        sa.Column("inspection_notes", sa.String(length=4000), nullable=True),
        sa.Column("repair_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "((status = 'CANCELLED') = (cancelled_at IS NOT NULL)) AND ((cancelled_at IS NULL) = "
            "(cancelled_by_user_id IS NULL)) AND (cancel_reason IS NULL OR cancelled_at IS NOT "
            "NULL)",
            name=op.f("ck_bookings_cancellation_fields"),
        ),
        sa.CheckConstraint(
            "(qc_inspector_user_id IS NOT NULL) = (status IN ('QC_IN_PROGRESS', "
            "'READY_FOR_PICKUP', 'COMPLETED'))",
            name=op.f("ck_bookings_qc_picker"),
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED') = (completed_at IS NOT NULL)",
            name=op.f("ck_bookings_completion_fields"),
        ),
        sa.CheckConstraint(
            "parts_person_user_id IS NOT NULL OR status IN ('PENDING', 'CONFIRMED', 'ASSIGNED', "
            "'INSPECTING', 'ESTIMATE_REVIEW', 'AWAITING_CUSTOMER', 'ESTIMATE_APPROVED', "
            "'ESTIMATE_REJECTED', 'CANCELLED')",
            name=op.f("ck_bookings_parts_person_required"),
        ),
        sa.CheckConstraint(
            "reference ~ '^BF-[0-9A-HJKMNP-TV-Z]{6}$'", name=op.f("ck_bookings_reference_format")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'ASSIGNED', 'INSPECTING', 'ESTIMATE_REVIEW', "
            "'AWAITING_CUSTOMER', 'ESTIMATE_APPROVED', 'ESTIMATE_REJECTED', 'PARTS_PENDING', "
            "'PARTS_ORDERED', 'PARTS_READY', 'IN_REPAIR', 'QC_PENDING', 'QC_IN_PROGRESS', "
            "'READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED')",
            name=op.f("ck_bookings_status"),
        ),
        sa.CheckConstraint(
            "technician_user_id IS NOT NULL OR status IN ('PENDING', 'CONFIRMED', 'CANCELLED')",
            name=op.f("ck_bookings_technician_required"),
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km BETWEEN 0 AND 2000000",
            name=op.f("ck_bookings_mileage_km"),
        ),
        sa.CheckConstraint(
            "qc_inspector_user_id IS NULL OR qc_inspector_user_id <> technician_user_id",
            name=op.f("ck_bookings_qc_picker_not_technician"),
        ),
        sa.CheckConstraint("slot_end > slot_start", name=op.f("ck_bookings_slot_order")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_bookings_version_positive")),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"],
            ["users.id"],
            name=op.f("fk_bookings_cancelled_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id", "vehicle_id"],
            ["vehicles.owner_user_id", "vehicles.id"],
            name=op.f("fk_bookings_customer_user_id_vehicle_id_vehicles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id"],
            ["users.id"],
            name=op.f("fk_bookings_customer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "parts_person_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            name=op.f("fk_bookings_shop_id_parts_person_user_id_shop_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "qc_inspector_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            name=op.f("fk_bookings_shop_id_qc_inspector_user_id_shop_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "technician_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            name=op.f("fk_bookings_shop_id_technician_user_id_shop_memberships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_bookings_shop_id_shops"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.UniqueConstraint("reference", name=op.f("uq_bookings_reference")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_bookings_shop_id_id")),
    )
    op.create_index(
        "ix_bookings_customer_user_id_slot_start",
        "bookings",
        ["customer_user_id", "slot_start"],
        unique=False,
    )
    op.create_index(
        "ix_bookings_parts_person_jobs",
        "bookings",
        ["shop_id", "parts_person_user_id", "status"],
        unique=False,
        postgresql_where=sa.text("parts_person_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_bookings_shop_id_slot_start", "bookings", ["shop_id", "slot_start"], unique=False
    )
    op.create_index(
        "ix_bookings_shop_id_status_slot_start",
        "bookings",
        ["shop_id", "status", "slot_start"],
        unique=False,
    )
    op.create_index(
        "ix_bookings_technician_jobs",
        "bookings",
        ["shop_id", "technician_user_id", "status"],
        unique=False,
        postgresql_where=sa.text("technician_user_id IS NOT NULL"),
    )
    op.create_table(
        "booking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(action = 'CREATE') = (from_status IS NULL)",
            name=op.f("ck_booking_events_create_from"),
        ),
        sa.CheckConstraint(
            "action IN ('CREATE', 'CONFIRM', 'DECLINE', 'ASSIGN_TECHNICIAN', 'START_INSPECTION', "
            "'EDIT_ESTIMATE', 'SUBMIT_ESTIMATE', 'SEND_ESTIMATE', 'APPROVE_ESTIMATE', "
            "'REJECT_ESTIMATE', 'REVISE_ESTIMATE', 'RETURN_TO_TECHNICIAN', 'ASSIGN_PARTS_PERSON', "
            "'ORDER_PARTS', 'MARK_PARTS_READY', 'RECEIVE_PARTS', 'ALLOCATE_PARTS', "
            "'START_REPAIR', 'SEND_TO_QC', 'PICK_QC', 'PASS_QC', 'FAIL_QC', 'NOTIFY_READY', "
            "'COMPLETE', 'CANCEL', 'REASSIGN_TECHNICIAN', 'REASSIGN_PARTS_PERSON')",
            name=op.f("ck_booking_events_action"),
        ),
        sa.CheckConstraint(
            "action NOT IN ('EDIT_ESTIMATE', 'START_REPAIR', 'NOTIFY_READY', "
            "'REASSIGN_TECHNICIAN', 'REASSIGN_PARTS_PERSON') OR from_status = to_status",
            name=op.f("ck_booking_events_operation_status"),
        ),
        sa.CheckConstraint(
            "actor_role IN ('CUSTOMER', 'OWNER', 'SERVICE_ADVISOR', 'TECHNICIAN', 'PARTS_PERSON', "
            "'QC_INSPECTOR', 'SYSTEM')",
            name=op.f("ck_booking_events_actor_role"),
        ),
        sa.CheckConstraint(
            "actor_user_id IS NOT NULL OR actor_role = 'SYSTEM'",
            name=op.f("ck_booking_events_actor"),
        ),
        sa.CheckConstraint(
            "from_status IN ('PENDING', 'CONFIRMED', 'ASSIGNED', 'INSPECTING', 'ESTIMATE_REVIEW', "
            "'AWAITING_CUSTOMER', 'ESTIMATE_APPROVED', 'ESTIMATE_REJECTED', 'PARTS_PENDING', "
            "'PARTS_ORDERED', 'PARTS_READY', 'IN_REPAIR', 'QC_PENDING', 'QC_IN_PROGRESS', "
            "'READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED')",
            name=op.f("ck_booking_events_from_status"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name=op.f("ck_booking_events_metadata_object")
        ),
        sa.CheckConstraint(
            "to_status IN ('PENDING', 'CONFIRMED', 'ASSIGNED', 'INSPECTING', 'ESTIMATE_REVIEW', "
            "'AWAITING_CUSTOMER', 'ESTIMATE_APPROVED', 'ESTIMATE_REJECTED', 'PARTS_PENDING', "
            "'PARTS_ORDERED', 'PARTS_READY', 'IN_REPAIR', 'QC_PENDING', 'QC_IN_PROGRESS', "
            "'READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED')",
            name=op.f("ck_booking_events_to_status"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_booking_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_booking_events_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_events")),
        sa.UniqueConstraint("seq", name=op.f("uq_booking_events_seq")),
    )
    op.create_index(
        "ix_booking_events_booking_id_created_at_seq",
        "booking_events",
        ["booking_id", "created_at", "seq"],
        unique=False,
    )
    op.create_table(
        "booking_parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("required_qty", sa.Integer(), nullable=False),
        sa.Column("reserved_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
            "consumed_qty = 0 OR (consumed_qty = required_qty AND reserved_qty = 0)",
            name=op.f("ck_booking_parts_consume_all"),
        ),
        sa.CheckConstraint(
            "required_qty > 0 AND reserved_qty >= 0 AND consumed_qty >= 0 AND reserved_qty + "
            "consumed_qty <= required_qty",
            name=op.f("ck_booking_parts_quantities"),
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_booking_parts_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "part_id"],
            ["parts.shop_id", "parts.id"],
            name=op.f("fk_booking_parts_shop_id_part_id_parts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_parts")),
        sa.UniqueConstraint(
            "booking_id", "part_id", name=op.f("uq_booking_parts_booking_id_part_id")
        ),
    )
    op.create_table(
        "booking_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("name_snapshot", sa.String(length=120), nullable=False),
        sa.Column("base_price_snapshot", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(name_snapshot) <> ''", name=op.f("ck_booking_services_name_snapshot_not_blank")
        ),
        sa.CheckConstraint(
            "base_price_snapshot IS NULL OR base_price_snapshot = trunc(base_price_snapshot)",
            name=op.f("ck_booking_services_whole_rupees"),
        ),
        sa.CheckConstraint(
            "base_price_snapshot IS NULL OR base_price_snapshot >= 0",
            name=op.f("ck_booking_services_price"),
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_booking_services_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "service_id"],
            ["services.shop_id", "services.id"],
            name=op.f("fk_booking_services_shop_id_service_id_services"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_services")),
        sa.UniqueConstraint(
            "booking_id", "service_id", name=op.f("uq_booking_services_booking_id_service_id")
        ),
    )
    op.create_table(
        "call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'RINGING'"), nullable=False
        ),
        sa.Column("missed_reason", sa.String(length=32), nullable=True),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("answered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("ended_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "rung_user_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "declined_user_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("room_name", sa.String(length=128), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ring_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("ai_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_dispatch_id", sa.String(length=64), nullable=True),
        sa.Column("ai_call_token_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("ai_answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("ai_error", sa.String(length=200), nullable=True),
        sa.Column("ai_identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_identity_method", sa.String(length=32), nullable=True),
        sa.Column(
            "ai_identity_attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
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
            "(status = 'MISSED') = (missed_reason IS NOT NULL)",
            name=op.f("ck_call_logs_missed_fields"),
        ),
        sa.CheckConstraint(
            "ai_dispatched_at IS NULL OR (direction = 'CUSTOMER_TO_SHOP' AND status = 'MISSED')",
            name=op.f("ck_call_logs_ai_dispatch"),
        ),
        sa.CheckConstraint(
            "ai_identity_method IN ('NAME', 'PHONE', 'EMAIL', 'BOOKING_REFERENCE')",
            name=op.f("ck_call_logs_ai_identity_method"),
        ),
        sa.CheckConstraint(
            "direction IN ('CUSTOMER_TO_SHOP', 'SHOP_TO_CUSTOMER')",
            name=op.f("ck_call_logs_direction"),
        ),
        sa.CheckConstraint(
            "missed_reason IN ('NO_ANSWER', 'DECLINED', 'CALLER_HUNG_UP')",
            name=op.f("ck_call_logs_missed_reason"),
        ),
        sa.CheckConstraint(
            "status <> 'CONNECTED' OR answered_at IS NOT NULL",
            name=op.f("ck_call_logs_connected_fields"),
        ),
        sa.CheckConstraint(
            "status IN ('RINGING', 'CONNECTED', 'ENDED', 'MISSED')",
            name=op.f("ck_call_logs_status"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('ENDED', 'MISSED') OR ended_at IS NOT NULL",
            name=op.f("ck_call_logs_ended_fields"),
        ),
        sa.CheckConstraint(
            "(duration_seconds IS NULL OR duration_seconds >= 0) AND (ai_duration_seconds IS NULL "
            "OR ai_duration_seconds >= 0)",
            name=op.f("ck_call_logs_durations"),
        ),
        sa.ForeignKeyConstraint(
            ["answered_by_user_id"],
            ["users.id"],
            name=op.f("fk_call_logs_answered_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["caller_user_id"],
            ["users.id"],
            name=op.f("fk_call_logs_caller_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id"],
            ["users.id"],
            name=op.f("fk_call_logs_customer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_user_id"],
            ["users.id"],
            name=op.f("fk_call_logs_ended_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_call_logs_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_logs")),
        sa.UniqueConstraint("room_name", name=op.f("uq_call_logs_room_name")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_call_logs_shop_id_id")),
    )
    op.create_index(
        "ix_call_logs_ai_leg_open",
        "call_logs",
        ["ai_dispatched_at"],
        unique=False,
        postgresql_where=sa.text("ai_dispatched_at IS NOT NULL AND ai_ended_at IS NULL"),
    )
    op.create_index(
        "ix_call_logs_booking_id_started_at",
        "call_logs",
        ["booking_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_call_logs_caller_user_id_started_at",
        "call_logs",
        ["caller_user_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_call_logs_connected_answered_at",
        "call_logs",
        ["answered_at"],
        unique=False,
        postgresql_where=sa.text("status = 'CONNECTED'"),
    )
    op.create_index(
        "ix_call_logs_customer_user_id_started_at",
        "call_logs",
        ["customer_user_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_call_logs_ringing_deadline",
        "call_logs",
        ["ring_deadline"],
        unique=False,
        postgresql_where=sa.text("status = 'RINGING'"),
    )
    op.create_index(
        "ix_call_logs_shop_id_started_at",
        "call_logs",
        ["shop_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_call_logs_one_active_per_booking",
        "call_logs",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('RINGING', 'CONNECTED') OR (ai_dispatched_at IS NOT NULL AND ai_ended_at "
            "IS NULL)"
        ),
    )
    op.create_table(
        "estimates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'DRAFT'"), nullable=False
        ),
        sa.Column(
            "parts_total",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "labour_total",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "grand_total",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("customer_note", sa.String(length=500), nullable=True),
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
            "((sent_at IS NULL) = (sent_by_user_id IS NULL)) AND (status NOT IN ('SENT', "
            "'APPROVED', 'REJECTED') OR sent_at IS NOT NULL)",
            name=op.f("ck_estimates_sent_fields"),
        ),
        sa.CheckConstraint(
            "((status IN ('APPROVED', 'REJECTED')) = (decided_at IS NOT NULL)) AND ((decided_at "
            "IS NULL) = (decided_by_user_id IS NULL)) AND (customer_note IS NULL OR decided_at IS "
            "NOT NULL)",
            name=op.f("ck_estimates_decision_fields"),
        ),
        sa.CheckConstraint(
            "status <> 'SUBMITTED' OR submitted_at IS NOT NULL",
            name=op.f("ck_estimates_submitted_fields"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'SENT', 'APPROVED', 'REJECTED', 'SUPERSEDED')",
            name=op.f("ck_estimates_status"),
        ),
        sa.CheckConstraint(
            "parts_total = trunc(parts_total) AND labour_total = trunc(labour_total) AND "
            "grand_total = trunc(grand_total)",
            name=op.f("ck_estimates_whole_rupees"),
        ),
        sa.CheckConstraint(
            "parts_total >= 0 AND labour_total >= 0 AND grand_total = parts_total + labour_total",
            name=op.f("ck_estimates_totals"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_estimates_version_positive")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_estimates_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_estimates_decided_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sent_by_user_id"],
            ["users.id"],
            name=op.f("fk_estimates_sent_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_estimates_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estimates")),
        sa.UniqueConstraint("booking_id", "version", name=op.f("uq_estimates_booking_id_version")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_estimates_shop_id_id")),
    )
    op.create_index(
        "uq_estimates_one_approved_per_booking",
        "estimates",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'APPROVED'"),
    )
    op.create_index(
        "uq_estimates_one_open_version_per_booking",
        "estimates",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('DRAFT', 'SUBMITTED', 'SENT')"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_role", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(body) <> ''", name=op.f("ck_notifications_body_not_blank")),
        sa.CheckConstraint("btrim(title) <> ''", name=op.f("ck_notifications_title_not_blank")),
        sa.CheckConstraint(
            "link LIKE '/%' AND link NOT LIKE '//%' AND strpos(link, '\\') = 0",
            name=op.f("ck_notifications_link_relative"),
        ),
        sa.CheckConstraint(
            "recipient_role IN ('CUSTOMER', 'OWNER', 'SERVICE_ADVISOR', 'TECHNICIAN', "
            "'PARTS_PERSON', 'QC_INSPECTOR', 'SYSTEM')",
            name=op.f("ck_notifications_recipient_role"),
        ),
        sa.CheckConstraint(
            "type IN ('BOOKING_CREATED', 'BOOKING_CONFIRMED', 'TECHNICIAN_ASSIGNED', "
            "'ESTIMATE_SUBMITTED', 'ESTIMATE_SENT', 'ESTIMATE_APPROVED', 'ESTIMATE_REJECTED', "
            "'ESTIMATE_RETURNED', 'PARTS_NEEDED', 'PARTS_READY', 'QC_REQUESTED', 'QC_FAILED', "
            "'QC_PASSED', 'VEHICLE_READY', 'BOOKING_CANCELLED', 'CALL_MISSED', 'AI_TASK_CREATED')",
            name=op.f("ck_notifications_type"),
        ),
        sa.CheckConstraint(
            "booking_id IS NULL OR shop_id IS NOT NULL",
            name=op.f("ck_notifications_booking_needs_shop"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_notifications_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_notifications_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_recipient_user_id_created_at",
        "notifications",
        ["recipient_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["recipient_user_id"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("po_number", sa.String(length=9), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'ORDERED'"), nullable=False
        ),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_name", sa.String(length=120), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status = 'RECEIVED') = (received_at IS NOT NULL)",
            name=op.f("ck_purchase_orders_received_fields"),
        ),
        sa.CheckConstraint(
            "po_number ~ '^PO-[0-9A-HJKMNP-TV-Z]{6}$'",
            name=op.f("ck_purchase_orders_po_number_format"),
        ),
        sa.CheckConstraint(
            "status IN ('ORDERED', 'PARTIALLY_RECEIVED', 'RECEIVED')",
            name=op.f("ck_purchase_orders_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_purchase_orders_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_purchase_orders_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_purchase_orders_shop_id_shops"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_purchase_orders_shop_id_id")),
        sa.UniqueConstraint(
            "shop_id", "po_number", name=op.f("uq_purchase_orders_shop_id_po_number")
        ),
    )
    op.create_index(
        "ix_purchase_orders_booking",
        "purchase_orders",
        ["shop_id", "booking_id"],
        unique=False,
        postgresql_where=sa.text("booking_id IS NOT NULL"),
    )
    op.create_index(
        "ix_purchase_orders_shop_id_status_created_at",
        "purchase_orders",
        ["shop_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "qc_inspections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("inspector_user_id", sa.Uuid(), nullable=False),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
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
            "checklist IS NULL OR jsonb_typeof(checklist) = 'array'",
            name=op.f("ck_qc_inspections_checklist_array"),
        ),
        sa.CheckConstraint(
            "result <> 'PASS' OR checklist IS NOT NULL",
            name=op.f("ck_qc_inspections_pass_checklist"),
        ),
        sa.CheckConstraint("result IN ('PASS', 'FAIL')", name=op.f("ck_qc_inspections_result")),
        sa.CheckConstraint(
            "(result IS NULL) = (completed_at IS NULL)", name=op.f("ck_qc_inspections_completion")
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_qc_inspections_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "inspector_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            name=op.f("fk_qc_inspections_shop_id_inspector_user_id_shop_memberships"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qc_inspections")),
        sa.UniqueConstraint("shop_id", "id", name=op.f("uq_qc_inspections_shop_id_id")),
    )
    op.create_index(
        "ix_qc_inspections_booking_id_picked_at",
        "qc_inspections",
        ["booking_id", "picked_at"],
        unique=False,
    )
    op.create_index(
        "ix_qc_inspections_shop_id_inspector_user_id_picked_at",
        "qc_inspections",
        ["shop_id", "inspector_user_id", "picked_at"],
        unique=False,
    )
    op.create_index(
        "uq_qc_inspections_one_open_per_booking",
        "qc_inspections",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("result IS NULL"),
    )
    op.create_table(
        "ai_call_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("call_log_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("intent", sa.String(length=120), nullable=False),
        sa.Column("intent_category", sa.String(length=32), nullable=False),
        sa.Column("details", sa.String(length=4000), nullable=False),
        sa.Column("sentiment", sa.String(length=32), nullable=False),
        sa.Column("is_urgent", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "transcript",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_fallback", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(details) <> ''", name=op.f("ck_ai_call_summaries_details_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(intent) <> ''", name=op.f("ck_ai_call_summaries_intent_not_blank")
        ),
        sa.CheckConstraint(
            "intent_category IN ('STATUS_INQUIRY', 'ESTIMATE_INQUIRY', 'APPOINTMENT_INQUIRY', "
            "'RESCHEDULE_REQUEST', 'PICKUP_INQUIRY', 'CALLBACK_REQUEST', 'COMPLAINT', "
            "'SAFETY_CONCERN', 'OTHER')",
            name=op.f("ck_ai_call_summaries_intent_category"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(transcript) = 'array'", name=op.f("ck_ai_call_summaries_transcript_array")
        ),
        sa.CheckConstraint(
            "sentiment IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE')",
            name=op.f("ck_ai_call_summaries_sentiment"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id"],
            ["users.id"],
            name=op.f("fk_ai_call_summaries_customer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_ai_call_summaries_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "call_log_id"],
            ["call_logs.shop_id", "call_logs.id"],
            name=op.f("fk_ai_call_summaries_shop_id_call_log_id_call_logs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_call_summaries")),
        sa.UniqueConstraint("call_log_id", name=op.f("uq_ai_call_summaries_call_log_id")),
    )
    op.create_table(
        "estimate_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("estimate_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("line_type", sa.String(length=32), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(line_type = 'PART') = (part_id IS NOT NULL)", name=op.f("ck_estimate_lines_part_ref")
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''", name=op.f("ck_estimate_lines_description_not_blank")
        ),
        sa.CheckConstraint(
            "line_type <> 'LABOUR' OR quantity BETWEEN 0.01 AND 999.99",
            name=op.f("ck_estimate_lines_labour_quantity"),
        ),
        sa.CheckConstraint(
            "line_type <> 'PART' OR (quantity = trunc(quantity) AND quantity BETWEEN 1 AND 9999)",
            name=op.f("ck_estimate_lines_part_quantity"),
        ),
        sa.CheckConstraint(
            "line_type IN ('PART', 'LABOUR')", name=op.f("ck_estimate_lines_line_type")
        ),
        sa.CheckConstraint(
            "line_total = round(quantity * unit_price)", name=op.f("ck_estimate_lines_line_total")
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 50", name=op.f("ck_estimate_lines_position")),
        sa.CheckConstraint(
            "unit_price = trunc(unit_price) AND line_total = trunc(line_total)",
            name=op.f("ck_estimate_lines_whole_rupees"),
        ),
        sa.CheckConstraint("unit_price >= 0", name=op.f("ck_estimate_lines_unit_price")),
        sa.ForeignKeyConstraint(
            ["shop_id", "estimate_id"],
            ["estimates.shop_id", "estimates.id"],
            name=op.f("fk_estimate_lines_shop_id_estimate_id_estimates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "part_id"],
            ["parts.shop_id", "parts.id"],
            name=op.f("fk_estimate_lines_shop_id_part_id_parts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estimate_lines")),
        sa.UniqueConstraint(
            "estimate_id", "position", name=op.f("uq_estimate_lines_estimate_id_position")
        ),
    )
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("ordered_qty", sa.Integer(), nullable=False),
        sa.Column("received_qty", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=False),
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
            "ordered_qty > 0 AND received_qty >= 0 AND received_qty <= ordered_qty",
            name=op.f("ck_purchase_order_items_quantities"),
        ),
        sa.CheckConstraint(
            "unit_cost = trunc(unit_cost)", name=op.f("ck_purchase_order_items_whole_rupees")
        ),
        sa.CheckConstraint("unit_cost >= 0", name=op.f("ck_purchase_order_items_unit_cost")),
        sa.ForeignKeyConstraint(
            ["shop_id", "part_id"],
            ["parts.shop_id", "parts.id"],
            name=op.f("fk_purchase_order_items_shop_id_part_id_parts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "purchase_order_id"],
            ["purchase_orders.shop_id", "purchase_orders.id"],
            name=op.f("fk_purchase_order_items_shop_id_purchase_order_id_purchase_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_order_items")),
        sa.UniqueConstraint(
            "purchase_order_id",
            "part_id",
            name=op.f("uq_purchase_order_items_purchase_order_id_part_id"),
        ),
    )
    op.create_table(
        "qc_issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("qc_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
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
            "((status = 'RESOLVED') = (resolved_at IS NOT NULL)) AND ((resolved_at IS NULL) = "
            "(resolved_by_user_id IS NULL))",
            name=op.f("ck_qc_issues_resolution_fields"),
        ),
        sa.CheckConstraint(
            "btrim(description) <> ''", name=op.f("ck_qc_issues_description_not_blank")
        ),
        sa.CheckConstraint("btrim(title) <> ''", name=op.f("ck_qc_issues_title_not_blank")),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name=op.f("ck_qc_issues_status")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_qc_issues_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            name=op.f("fk_qc_issues_resolved_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_qc_issues_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "qc_inspection_id"],
            ["qc_inspections.shop_id", "qc_inspections.id"],
            name=op.f("fk_qc_issues_shop_id_qc_inspection_id_qc_inspections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qc_issues")),
    )
    op.create_index(
        "ix_qc_issues_booking_id_status", "qc_issues", ["booking_id", "status"], unique=False
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("on_hand_delta", sa.Integer(), nullable=False),
        sa.Column("reserved_delta", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(movement_type = 'RECEIVE' AND on_hand_delta = quantity AND reserved_delta = 0) OR "
            "(movement_type = 'RESERVE' AND on_hand_delta = 0 AND reserved_delta = quantity) OR "
            "(movement_type = 'RELEASE' AND on_hand_delta = 0 AND reserved_delta = -quantity) OR "
            "(movement_type = 'CONSUME' AND on_hand_delta = -quantity AND reserved_delta = "
            "-quantity) OR (movement_type = 'ADJUST' AND abs(on_hand_delta) = quantity AND "
            "reserved_delta = 0)",
            name=op.f("ck_stock_movements_deltas"),
        ),
        sa.CheckConstraint(
            "(movement_type IN ('RESERVE', 'RELEASE', 'CONSUME') AND booking_id IS NOT NULL) OR "
            "(movement_type = 'RECEIVE' AND booking_id IS NULL AND purchase_order_id IS NOT NULL) "
            "OR (movement_type = 'ADJUST' AND booking_id IS NULL AND purchase_order_id IS NULL "
            "AND note IS NOT NULL)",
            name=op.f("ck_stock_movements_links"),
        ),
        sa.CheckConstraint(
            "movement_type IN ('RECEIVE', 'RESERVE', 'RELEASE', 'CONSUME', 'ADJUST')",
            name=op.f("ck_stock_movements_movement_type"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_stock_movements_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_stock_movements_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_stock_movements_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "part_id"],
            ["parts.shop_id", "parts.id"],
            name=op.f("fk_stock_movements_shop_id_part_id_parts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "purchase_order_id"],
            ["purchase_orders.shop_id", "purchase_orders.id"],
            name=op.f("fk_stock_movements_shop_id_purchase_order_id_purchase_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
        sa.UniqueConstraint("seq", name=op.f("uq_stock_movements_seq")),
    )
    op.create_index(
        "ix_stock_movements_part_id_created_at_seq",
        "stock_movements",
        ["part_id", "created_at", "seq"],
        unique=False,
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("call_log_id", sa.Uuid(), nullable=True),
        sa.Column("customer_user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("is_urgent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("done_note", sa.String(length=500), nullable=True),
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
            "((status = 'DONE') = (done_at IS NOT NULL)) AND ((done_at IS NULL) = "
            "(done_by_user_id IS NULL))",
            name=op.f("ck_tasks_done_fields"),
        ),
        sa.CheckConstraint("btrim(title) <> ''", name=op.f("ck_tasks_title_not_blank")),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name=op.f("ck_tasks_metadata_object")
        ),
        sa.CheckConstraint(
            "kind IN ('CALLBACK', 'RESCHEDULE_REQUEST', 'ESCALATION', 'FOLLOW_UP')",
            name=op.f("ck_tasks_kind"),
        ),
        sa.CheckConstraint("status IN ('OPEN', 'DONE')", name=op.f("ck_tasks_status")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_tasks_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id"],
            ["users.id"],
            name=op.f("fk_tasks_customer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["done_by_user_id"],
            ["users.id"],
            name=op.f("fk_tasks_done_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "booking_id"],
            ["bookings.shop_id", "bookings.id"],
            name=op.f("fk_tasks_shop_id_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "call_log_id"],
            ["call_logs.shop_id", "call_logs.id"],
            name=op.f("fk_tasks_shop_id_call_log_id_call_logs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_tasks_shop_id_shops"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(
        "ix_tasks_shop_id_status_is_urgent_created_at",
        "tasks",
        [
            "shop_id",
            "status",
            sa.literal_column("is_urgent DESC"),
            sa.literal_column("created_at DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "uq_tasks_one_per_call_and_kind",
        "tasks",
        ["call_log_id", "kind"],
        unique=True,
        postgresql_where=sa.text("call_log_id IS NOT NULL"),
    )

    # Append-only ledgers (spec 02 §8): any UPDATE or DELETE raises SQLSTATE P0001.
    # TRUNCATE does not fire row triggers, so test clean-up still works.
    op.execute(
        """
        CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_booking_events_append_only BEFORE UPDATE OR DELETE ON booking_events"
        " FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_stock_movements_append_only BEFORE UPDATE OR DELETE ON stock_movements"
        " FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_stock_movements_append_only ON stock_movements")
    op.execute("DROP TRIGGER trg_booking_events_append_only ON booking_events")
    op.execute("DROP FUNCTION forbid_mutation()")
    op.drop_index(
        "uq_tasks_one_per_call_and_kind",
        table_name="tasks",
        postgresql_where=sa.text("call_log_id IS NOT NULL"),
    )
    op.drop_index("ix_tasks_shop_id_status_is_urgent_created_at", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_stock_movements_part_id_created_at_seq", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_qc_issues_booking_id_status", table_name="qc_issues")
    op.drop_table("qc_issues")
    op.drop_table("purchase_order_items")
    op.drop_table("estimate_lines")
    op.drop_table("ai_call_summaries")
    op.drop_index(
        "uq_qc_inspections_one_open_per_booking",
        table_name="qc_inspections",
        postgresql_where=sa.text("result IS NULL"),
    )
    op.drop_index(
        "ix_qc_inspections_shop_id_inspector_user_id_picked_at", table_name="qc_inspections"
    )
    op.drop_index("ix_qc_inspections_booking_id_picked_at", table_name="qc_inspections")
    op.drop_table("qc_inspections")
    op.drop_index("ix_purchase_orders_shop_id_status_created_at", table_name="purchase_orders")
    op.drop_index(
        "ix_purchase_orders_booking",
        table_name="purchase_orders",
        postgresql_where=sa.text("booking_id IS NOT NULL"),
    )
    op.drop_table("purchase_orders")
    op.drop_index(
        "ix_notifications_unread",
        table_name="notifications",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.drop_index("ix_notifications_recipient_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "uq_estimates_one_open_version_per_booking",
        table_name="estimates",
        postgresql_where=sa.text("status IN ('DRAFT', 'SUBMITTED', 'SENT')"),
    )
    op.drop_index(
        "uq_estimates_one_approved_per_booking",
        table_name="estimates",
        postgresql_where=sa.text("status = 'APPROVED'"),
    )
    op.drop_table("estimates")
    op.drop_index(
        "uq_call_logs_one_active_per_booking",
        table_name="call_logs",
        postgresql_where=sa.text(
            "status IN ('RINGING', 'CONNECTED') OR (ai_dispatched_at IS NOT NULL AND ai_ended_at "
            "IS NULL)"
        ),
    )
    op.drop_index("ix_call_logs_shop_id_started_at", table_name="call_logs")
    op.drop_index(
        "ix_call_logs_ringing_deadline",
        table_name="call_logs",
        postgresql_where=sa.text("status = 'RINGING'"),
    )
    op.drop_index("ix_call_logs_customer_user_id_started_at", table_name="call_logs")
    op.drop_index(
        "ix_call_logs_connected_answered_at",
        table_name="call_logs",
        postgresql_where=sa.text("status = 'CONNECTED'"),
    )
    op.drop_index("ix_call_logs_caller_user_id_started_at", table_name="call_logs")
    op.drop_index("ix_call_logs_booking_id_started_at", table_name="call_logs")
    op.drop_index(
        "ix_call_logs_ai_leg_open",
        table_name="call_logs",
        postgresql_where=sa.text("ai_dispatched_at IS NOT NULL AND ai_ended_at IS NULL"),
    )
    op.drop_table("call_logs")
    op.drop_table("booking_services")
    op.drop_table("booking_parts")
    op.drop_index("ix_booking_events_booking_id_created_at_seq", table_name="booking_events")
    op.drop_table("booking_events")
    op.drop_index(
        "ix_bookings_technician_jobs",
        table_name="bookings",
        postgresql_where=sa.text("technician_user_id IS NOT NULL"),
    )
    op.drop_index("ix_bookings_shop_id_status_slot_start", table_name="bookings")
    op.drop_index("ix_bookings_shop_id_slot_start", table_name="bookings")
    op.drop_index(
        "ix_bookings_parts_person_jobs",
        table_name="bookings",
        postgresql_where=sa.text("parts_person_user_id IS NOT NULL"),
    )
    op.drop_index("ix_bookings_customer_user_id_slot_start", table_name="bookings")
    op.drop_table("bookings")
    op.drop_table("vehicles")
    op.drop_table("slot_counters")
    op.drop_table("shop_working_hours")
    op.drop_index(
        "uq_shop_memberships_one_owner_per_shop",
        table_name="shop_memberships",
        postgresql_where=sa.text("role = 'OWNER'"),
    )
    op.drop_index(
        "ix_shop_memberships_user_active",
        table_name="shop_memberships",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(
        "ix_shop_memberships_shop_role_active",
        table_name="shop_memberships",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("shop_memberships")
    op.drop_index(
        "uq_services_active_name", table_name="services", postgresql_where=sa.text("is_active")
    )
    op.drop_table("services")
    op.drop_table("parts")
    op.drop_index(
        "ix_users_phone", table_name="users", postgresql_where=sa.text("phone IS NOT NULL")
    )
    op.drop_table("users")
    op.drop_index(
        "ix_shops_listed_city_name", table_name="shops", postgresql_where=sa.text("is_listed")
    )
    op.drop_table("shops")

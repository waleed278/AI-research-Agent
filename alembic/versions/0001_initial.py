"""initial schema: api_keys, research_jobs, trace_events, research_results

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False on all three: the types are created explicitly (once,
# with checkfirst) at the top of upgrade() -- without this, SQLAlchemy also
# tries to CREATE TYPE implicitly the first time each enum is used as a
# column type in create_table(), which fails with "type already exists".
job_status = postgresql.ENUM(
    "queued", "running", "completed", "failed", "cancelled", name="job_status", create_type=False
)
job_phase = postgresql.ENUM(
    "planning",
    "researching",
    "critiquing",
    "synthesizing",
    "done",
    name="job_phase",
    create_type=False,
)
trace_event_type = postgresql.ENUM(
    "phase_change",
    "llm_call",
    "tool_call",
    "tool_result",
    "error",
    name="trace_event_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    job_status.create(bind, checkfirst=True)
    job_phase.create(bind, checkfirst=True)
    trace_event_type.create(bind, checkfirst=True)

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "research_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("max_sources", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("phase", job_phase, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["api_key_id"], ["api_keys.id"], name="fk_research_jobs_api_key_id_api_keys"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_jobs"),
    )
    op.create_index("ix_research_jobs_api_key_id", "research_jobs", ["api_key_id"])
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])
    op.create_index("ix_research_jobs_created_at", "research_jobs", ["created_at"])

    op.create_table(
        "trace_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("phase", job_phase, nullable=False),
        sa.Column("event_type", trace_event_type, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["research_jobs.id"], name="fk_trace_events_job_id_research_jobs"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trace_events"),
    )
    op.create_index("ix_trace_events_job_id", "trace_events", ["job_id"])
    op.create_index("ix_trace_events_job_seq", "trace_events", ["job_id", "seq"])

    op.create_table(
        "research_results",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_markdown", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["research_jobs.id"], name="fk_research_results_job_id_research_jobs"
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_research_results"),
    )


def downgrade() -> None:
    op.drop_table("research_results")
    op.drop_table("trace_events")
    op.drop_table("research_jobs")
    op.drop_table("api_keys")
    trace_event_type.drop(op.get_bind(), checkfirst=True)
    job_phase.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)

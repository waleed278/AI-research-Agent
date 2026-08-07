"""platform accounts: users, api_keys.user_id, llm_credentials, uploaded_files,
research_jobs provider/model + user_id (drops api_key_id)

Revision ID: 0002_platform_accounts
Revises: 0001_initial
Create Date: 2026-08-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_platform_accounts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

llm_provider = postgresql.ENUM("openai", "gemini", "anthropic", name="llm_provider", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    llm_provider.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # api_keys becomes user-owned (see app/db/models.py::ApiKey docstring).
    op.add_column("api_keys", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.create_foreign_key(
        "fk_api_keys_user_id_users", "api_keys", "users", ["user_id"], ["id"]
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    op.create_table(
        "llm_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", llm_provider, nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_llm_credentials_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_llm_credentials"),
        sa.UniqueConstraint("user_id", "provider", name="uq_llm_credentials_user_provider"),
    )
    op.create_index("ix_llm_credentials_user_id", "llm_credentials", ["user_id"])

    # research_jobs: add user_id/llm_provider/llm_model, drop api_key_id.
    op.add_column("research_jobs", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("research_jobs", sa.Column("llm_provider", llm_provider, nullable=False))
    op.add_column(
        "research_jobs", sa.Column("llm_model", sa.String(length=100), nullable=False, server_default="")
    )
    op.alter_column("research_jobs", "llm_model", server_default=None)
    op.drop_constraint("fk_research_jobs_api_key_id_api_keys", "research_jobs", type_="foreignkey")
    op.drop_index("ix_research_jobs_api_key_id", table_name="research_jobs")
    op.drop_column("research_jobs", "api_key_id")
    op.create_foreign_key("fk_research_jobs_user_id_users", "research_jobs", "users", ["user_id"], ["id"])
    op.create_index("ix_research_jobs_user_id", "research_jobs", ["user_id"])

    # uploaded_files references research_jobs, so it must come after that table is finalized.
    op.create_table(
        "uploaded_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("extracted_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_uploaded_files_user_id_users"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["research_jobs.id"], name="fk_uploaded_files_job_id_research_jobs"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_uploaded_files"),
    )
    op.create_index("ix_uploaded_files_user_id", "uploaded_files", ["user_id"])
    op.create_index("ix_uploaded_files_job_id", "uploaded_files", ["job_id"])


def downgrade() -> None:
    op.drop_table("uploaded_files")

    op.drop_index("ix_research_jobs_user_id", table_name="research_jobs")
    op.drop_constraint("fk_research_jobs_user_id_users", "research_jobs", type_="foreignkey")
    op.add_column("research_jobs", sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_research_jobs_api_key_id_api_keys", "research_jobs", "api_keys", ["api_key_id"], ["id"]
    )
    op.create_index("ix_research_jobs_api_key_id", "research_jobs", ["api_key_id"])
    op.drop_column("research_jobs", "llm_model")
    op.drop_column("research_jobs", "llm_provider")
    op.drop_column("research_jobs", "user_id")

    op.drop_table("llm_credentials")

    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_constraint("fk_api_keys_user_id_users", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "user_id")

    op.drop_table("users")

    llm_provider.drop(op.get_bind(), checkfirst=True)

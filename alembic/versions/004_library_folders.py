"""add hierarchical folders and paper library state

Revision ID: 004_library_folders
Revises: 003_parse_progress
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_library_folders"
down_revision: Union[str, None] = "003_parse_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["folders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"], unique=False)

    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("folder_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_papers_folder_id_folders", "folders", ["folder_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_papers_folder_id", ["folder_id"], unique=False)
        batch_op.create_index("ix_papers_deleted_at", ["deleted_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_index("ix_papers_deleted_at")
        batch_op.drop_index("ix_papers_folder_id")
        batch_op.drop_constraint("fk_papers_folder_id_folders", type_="foreignkey")
        batch_op.drop_column("last_opened_at")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("folder_id")

    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_table("folders")

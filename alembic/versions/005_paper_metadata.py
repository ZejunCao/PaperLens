"""add paper bibliographic metadata

Revision ID: 005_paper_metadata
Revises: 004_library_folders
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_paper_metadata"
down_revision: Union[str, None] = "004_library_folders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("authors", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("abstract", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("publication", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("doi", sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column("arxiv_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("source_url", sa.String(length=1024), nullable=True))
        batch_op.add_column(sa.Column("keywords", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("metadata_source", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_papers_arxiv_id", ["arxiv_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_index("ix_papers_arxiv_id")
        batch_op.drop_column("metadata_source")
        batch_op.drop_column("keywords")
        batch_op.drop_column("source_url")
        batch_op.drop_column("arxiv_id")
        batch_op.drop_column("doi")
        batch_op.drop_column("published_at")
        batch_op.drop_column("publication")
        batch_op.drop_column("abstract")
        batch_op.drop_column("authors")

"""add parse progress fields to jobs and papers

Revision ID: 003_parse_progress
Revises: 002_create_jobs
Create Date: 2026-08-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_parse_progress"
down_revision: Union[str, None] = "002_create_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stage", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("progress", sa.Integer(), nullable=True))

    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parse_stage", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("parse_progress", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_column("parse_progress")
        batch_op.drop_column("parse_stage")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("progress")
        batch_op.drop_column("stage")

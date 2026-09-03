"""add paper institutions

Revision ID: 006_paper_institutions
Revises: 005_paper_metadata
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_paper_institutions"
down_revision: Union[str, None] = "005_paper_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("institutions", sa.JSON(), server_default="[]", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_column("institutions")

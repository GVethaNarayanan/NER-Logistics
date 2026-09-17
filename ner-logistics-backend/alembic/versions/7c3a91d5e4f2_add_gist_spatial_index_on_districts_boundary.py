"""add_gist_spatial_index_on_districts_boundary

Revision ID: 7c3a91d5e4f2
Revises: 565b03e472b4
Create Date: 2026-09-15 11:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3a91d5e4f2'
down_revision: Union[str, Sequence[str], None] = '565b03e472b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GiST spatial index on districts.boundary for efficient spatial queries."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_districts_boundary_gist "
        "ON districts USING gist (boundary)"
    )


def downgrade() -> None:
    """Remove the GiST spatial index on districts.boundary."""
    op.execute("DROP INDEX IF EXISTS idx_districts_boundary_gist")

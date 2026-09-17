"""add_osm_columns_and_road_spatial_index

Revision ID: ca51f22c9233
Revises: 7c3a91d5e4f2
Create Date: 2026-09-15 11:39:05.208398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca51f22c9233'
down_revision: Union[str, Sequence[str], None] = '7c3a91d5e4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE roads ADD COLUMN osm_id BIGINT")
    op.execute("ALTER TABLE roads ADD COLUMN osm_tags JSON")
    op.execute("ALTER TABLE roads ADD COLUMN source VARCHAR DEFAULT 'osm'")
    op.execute("ALTER TABLE roads ADD COLUMN is_legacy BOOLEAN DEFAULT false")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_roads_osm_id ON roads (osm_id) WHERE osm_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_roads_geometry_gist ON roads USING gist (geometry)")
    op.execute("UPDATE roads SET is_legacy = true WHERE osm_id IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_roads_geometry_gist")
    op.execute("DROP INDEX IF EXISTS ix_roads_osm_id")
    op.execute("ALTER TABLE roads DROP COLUMN IF EXISTS is_legacy")
    op.execute("ALTER TABLE roads DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE roads DROP COLUMN IF EXISTS osm_tags")
    op.execute("ALTER TABLE roads DROP COLUMN IF EXISTS osm_id")

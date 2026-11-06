"""walking distance from the Esri Rwanda routing service: the walking network is no longer uploaded

The imports of the walking_network kind (an OpenStreetMap .osm.pbf, kept as a routing file beside the upload, no rows
in the data tables) are removed with their data source. The audit log keeps its entries about them (text labels).
Their files in UPLOAD_DIR (<sha256>.pbf, import-<id>.network.npz) are no longer read and can be deleted.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-06 12:00:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM import_runs WHERE kind = 'walking_network'")
    op.execute("DELETE FROM data_sources WHERE code = 'WALKING_NETWORK'")


def downgrade() -> None:
    op.execute("INSERT INTO data_sources (code, name) VALUES ('WALKING_NETWORK', 'Walking network (OpenStreetMap)') "
               "ON CONFLICT (code) DO NOTHING")

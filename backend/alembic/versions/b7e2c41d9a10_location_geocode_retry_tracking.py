"""location geocode retry tracking

Revision ID: b7e2c41d9a10
Revises: 3529ae572fa9
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2c41d9a10'
down_revision: Union[str, None] = '3529ae572fa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('locations', sa.Column('geocode_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('locations', sa.Column('last_geocode_attempt_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('locations', 'last_geocode_attempt_at')
    op.drop_column('locations', 'geocode_attempts')

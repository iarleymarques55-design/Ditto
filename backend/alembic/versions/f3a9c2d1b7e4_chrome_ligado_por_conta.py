"""chrome ligado por conta

Revision ID: f3a9c2d1b7e4
Revises: d7f2a1c84e60
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a9c2d1b7e4'
down_revision: Union[str, Sequence[str], None] = 'd7f2a1c84e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # O painel avisa quando um pedido espera na fila sem nenhum Chrome ligado nesta conta
    op.add_column('users', sa.Column('runner_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'runner_seen_at')

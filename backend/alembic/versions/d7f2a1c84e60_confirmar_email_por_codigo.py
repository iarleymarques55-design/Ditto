"""confirmar e-mail por código

Revision ID: d7f2a1c84e60
Revises: b5e1c7a93d40
Create Date: 2026-11-24 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7f2a1c84e60'
down_revision: Union[str, Sequence[str], None] = 'b5e1c7a93d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    # Quem entra pelo Google já teve o e-mail confirmado por ele. As contas de senha que já
    # existem ficam sem confirmação e recebem o código no próximo login
    op.execute("UPDATE users SET email_verified_at = created_at WHERE google_sub IS NOT NULL")

    op.create_table(
        'email_verifications',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sends_in_window', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_email_verifications_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_email_verifications')),
        sa.UniqueConstraint('user_id', name=op.f('uq_email_verifications_user_id')),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('email_verifications')
    op.drop_column('users', 'email_verified_at')
